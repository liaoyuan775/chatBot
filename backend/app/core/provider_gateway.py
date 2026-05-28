from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import mimetypes
from typing import Any, AsyncIterator

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import ProviderConfigEntity

settings = get_settings()


class ProviderError(RuntimeError):
    pass


@dataclass
class ProviderContext:
    provider_name: str
    base_url: str
    api_key: str
    timeout_seconds: int


def _mime_from_audio_filename(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    if guessed and guessed.startswith("audio/"):
        return guessed
    suffix = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    return {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "m4a": "audio/mp4",
        "aac": "audio/aac",
        "webm": "audio/webm",
        "ogg": "audio/ogg",
        "opus": "audio/opus",
        "flac": "audio/flac",
    }.get(suffix, "application/octet-stream")


def _mime_from_response_format(response_format: str) -> str:
    fmt = (response_format or "").lower()
    return {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "opus": "audio/opus",
        "pcm": "audio/pcm",
    }.get(fmt, "application/octet-stream")


def _mime_from_image_format(image_format: str | None) -> str:
    fmt = (image_format or "").strip().lower()
    return {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "webp": "image/webp",
    }.get(fmt, "image/png")


def _clean_base(base: str) -> str:
    return base.rstrip("/")


def _candidate_endpoints(base_url: str, path: str, provider_name: str) -> list[str]:
    base = _clean_base(base_url)
    if provider_name == "dashscope":
        return [f"{base}/compatible-mode/v1{path}", f"{base}{path}"]
    if provider_name == "siliconflow":
        return [f"{base}/v1{path}", f"{base}{path}"]
    if provider_name == "volcengine":
        return [f"{base}{path}", f"{base}/v1{path}"]
    return [f"{base}/v1{path}", f"{base}{path}"]


def _format_http_error(status_code: int, body_text: str) -> str:
    return f"{status_code}: {(body_text or '')[:300]}"


async def decrypt_api_key(db: AsyncSession, provider_id) -> str | None:
    if not settings.app_encryption_key:
        return None
    row = await db.execute(
        text(
            """
            SELECT CASE
                   WHEN api_key_enc IS NULL THEN NULL
                   ELSE pgp_sym_decrypt(decode(api_key_enc, 'base64'), :secret)::text
                   END AS api_key
            FROM provider_configs
            WHERE id = :provider_id
            """
        ),
        {"provider_id": str(provider_id), "secret": settings.app_encryption_key},
    )
    value = row.scalar_one_or_none()
    return str(value) if value else None


async def encrypt_api_key(db: AsyncSession, provider_id, raw_key: str) -> None:
    await db.execute(
        text(
            """
            UPDATE provider_configs
            SET api_key_enc = encode(pgp_sym_encrypt(:raw_key, :secret), 'base64'),
                updated_at = now()
            WHERE id = :provider_id
            """
        ),
        {"provider_id": str(provider_id), "raw_key": raw_key, "secret": settings.app_encryption_key},
    )


async def get_provider_context(db: AsyncSession, provider_name: str) -> ProviderContext:
    result = await db.execute(
        text(
            """
            SELECT id, provider_name, base_url, timeout_seconds
            FROM provider_configs
            WHERE provider_name = :provider_name
            """
        ),
        {"provider_name": provider_name},
    )
    row = result.mappings().first()
    if row is None:
        raise ProviderError(f"Provider `{provider_name}` is not configured.")

    provider_id = row["id"]
    api_key = await decrypt_api_key(db, provider_id)
    if not api_key:
        raise ProviderError(f"Provider `{provider_name}` API key is missing.")
    base_url = row["base_url"] or ""
    if not base_url:
        raise ProviderError(f"Provider `{provider_name}` base_url is missing.")
    return ProviderContext(
        provider_name=provider_name,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=int(row["timeout_seconds"] or 10),
    )


async def _request_with_fallback(
    ctx: ProviderContext, method: str, path: str, json_payload: dict[str, Any] | None = None, files: Any = None
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {ctx.api_key}"}
    if files is None:
        headers["Content-Type"] = "application/json"

    last_error: str | None = None
    urls = _candidate_endpoints(ctx.base_url, path, ctx.provider_name)
    async with httpx.AsyncClient(timeout=ctx.timeout_seconds, trust_env=False) as client:
        for idx, url in enumerate(urls):
            try:
                response = await client.request(method, url, headers=headers, json=json_payload, files=files)
                if response.status_code >= 400:
                    error_text = _format_http_error(response.status_code, response.text)
                    last_error = error_text
                    # Only fallback when endpoint path is likely mismatched.
                    if response.status_code == 404 and idx < len(urls) - 1:
                        continue
                    raise ProviderError(error_text)
                if not response.text:
                    return {}
                return response.json()
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue
    raise ProviderError(last_error or f"Provider request failed: {ctx.provider_name} {path}")


async def list_models_remote(db: AsyncSession, provider_name: str) -> list[dict[str, Any]]:
    ctx = await get_provider_context(db, provider_name)
    payload = await _request_with_fallback(ctx, "GET", "/models")
    data = payload.get("data") if isinstance(payload, dict) else []
    if isinstance(data, list):
        return data
    return []


async def chat_completion(
    db: AsyncSession, provider_name: str, model: str, messages: list[dict[str, Any]], temperature: float = 0.4
) -> str:
    ctx = await get_provider_context(db, provider_name)
    payload = await _request_with_fallback(
        ctx,
        "POST",
        "/chat/completions",
        json_payload={"model": model, "messages": messages, "temperature": temperature},
    )
    choices = payload.get("choices") or []
    if not choices:
        raise ProviderError("No choices returned from chat completion.")
    return choices[0].get("message", {}).get("content", "")


async def stream_chat_completion(
    db: AsyncSession,
    provider_name: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.4,
) -> AsyncIterator[str]:
    ctx = await get_provider_context(db, provider_name)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {ctx.api_key}", "Content-Type": "application/json"}
    last_error: str | None = None
    urls = _candidate_endpoints(ctx.base_url, "/chat/completions", ctx.provider_name)
    async with httpx.AsyncClient(timeout=ctx.timeout_seconds, trust_env=False) as client:
        for idx, url in enumerate(urls):
            try:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code >= 400:
                        error_text = _format_http_error(response.status_code, await response.aread())
                        last_error = error_text
                        if response.status_code == 404 and idx < len(urls) - 1:
                            continue
                        raise ProviderError(error_text)
                    content_type = (response.headers.get("content-type") or "").lower()
                    if "application/json" in content_type:
                        body = await response.aread()
                        data = json.loads(body.decode("utf-8", errors="ignore") or "{}")
                        choices = data.get("choices") or []
                        if not choices:
                            raise ProviderError("No choices returned from chat completion.")
                        full_text = str(choices[0].get("message", {}).get("content", "") or "")
                        if full_text:
                            yield full_text
                        return

                    async for raw_line in response.aiter_lines():
                        line = (raw_line or "").strip()
                        if not line:
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if not line or line == "[DONE]":
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        text = delta.get("content")
                        if isinstance(text, str) and text:
                            yield text
                    return
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue
    raise ProviderError(last_error or "Chat stream failed.")


async def embedding(
    db: AsyncSession, provider_name: str, model: str, text_input: str | list[str]
) -> list[list[float]]:
    ctx = await get_provider_context(db, provider_name)
    inputs = [text_input] if isinstance(text_input, str) else list(text_input)
    if not inputs:
        raise ProviderError("Embedding input is empty.")

    max_batch_size = 64
    result: list[list[float]] = []
    for start in range(0, len(inputs), max_batch_size):
        batch = inputs[start : start + max_batch_size]
        payload = await _request_with_fallback(
            ctx,
            "POST",
            "/embeddings",
            json_payload={"model": model, "input": batch if len(batch) > 1 else batch[0]},
        )
        data = payload.get("data") or []
        for item in data:
            vec = item.get("embedding") or []
            if vec:
                result.append([float(x) for x in vec])
    if not result:
        raise ProviderError("No embeddings returned.")
    return result


async def rerank(
    db: AsyncSession, provider_name: str, model: str, query: str, documents: list[str], top_n: int = 5
) -> list[dict[str, Any]]:
    if not documents:
        return []
    ctx = await get_provider_context(db, provider_name)
    safe_top_n = max(1, min(top_n, len(documents)))
    payload = await _request_with_fallback(
        ctx,
        "POST",
        "/rerank",
        json_payload={"model": model, "query": query, "documents": documents, "top_n": safe_top_n, "return_documents": False},
    )
    results = payload.get("results") or payload.get("data") or []
    if not isinstance(results, list):
        return []
    return results


async def asr_transcribe(
    db: AsyncSession, provider_name: str, model: str, audio_bytes: bytes, filename: str = "audio.wav"
) -> str:
    ctx = await get_provider_context(db, provider_name)
    files = {
        "file": (filename, audio_bytes, _mime_from_audio_filename(filename)),
        "model": (None, model),
    }
    payload = await _request_with_fallback(ctx, "POST", "/audio/transcriptions", files=files)
    return str(payload.get("text") or payload.get("result") or "")


async def omni_transcribe(
    db: AsyncSession, provider_name: str, model: str, audio_bytes: bytes, filename: str = "audio.wav"
) -> str:
    return await asr_transcribe(db, provider_name, model, audio_bytes, filename)


async def omni_synthesize(
    db: AsyncSession,
    provider_name: str,
    model: str,
    voice: str,
    text_input: str,
    *,
    response_format: str = "mp3",
) -> tuple[str, str]:
    return await tts_synthesize(
        db,
        provider_name,
        model,
        voice,
        text_input,
        response_format=response_format,
        stream=False,
    )


async def tts_synthesize(
    db: AsyncSession,
    provider_name: str,
    model: str,
    voice: str,
    text_input: str,
    *,
    response_format: str = "mp3",
    stream: bool = False,
    sample_rate: int | None = None,
) -> tuple[str, str]:
    if provider_name == "dashscope":
        ctx = await get_provider_context(db, provider_name)
        base = _clean_base(ctx.base_url)
        url = f"{base}/api/v1/services/audio/tts/SpeechSynthesizer"
        headers = {"Authorization": f"Bearer {ctx.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "input": {
                "text": text_input,
                "voice": voice,
                "format": "wav",
                "sample_rate": 24000,
            },
        }
        async with httpx.AsyncClient(timeout=ctx.timeout_seconds, trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                raise ProviderError(f"{response.status_code}: {response.text[:300]}")
            data = response.json()
            audio_data = (
                data.get("output", {})
                .get("audio", {})
                .get("data")
            )
            if audio_data:
                return str(audio_data), "audio/wav"
            audio_url = (
                data.get("output", {})
                .get("audio", {})
                .get("url")
            )
            if audio_url:
                audio_response = await client.get(str(audio_url))
                if audio_response.status_code >= 400:
                    raise ProviderError(f"Failed to download dashscope audio: {audio_response.status_code}")
                return base64.b64encode(audio_response.content).decode("utf-8"), "audio/wav"
            raise ProviderError("DashScope TTS response does not include audio data.")

    ctx = await get_provider_context(db, provider_name)
    headers = {"Authorization": f"Bearer {ctx.api_key}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": model,
        "voice": voice,
        "input": text_input,
        "response_format": response_format,
        "stream": bool(stream),
    }
    if sample_rate is not None:
        payload["sample_rate"] = int(sample_rate)
    last_error: str | None = None
    urls = _candidate_endpoints(ctx.base_url, "/audio/speech", ctx.provider_name)
    async with httpx.AsyncClient(timeout=ctx.timeout_seconds, trust_env=False) as client:
        for idx, url in enumerate(urls):
            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code >= 400:
                    error_text = _format_http_error(response.status_code, response.text)
                    last_error = error_text
                    if response.status_code == 404 and idx < len(urls) - 1:
                        continue
                    raise ProviderError(error_text)

                content_type = (response.headers.get("content-type") or "").lower()
                # Some providers return raw audio bytes (e.g. text/plain / audio/*)
                # instead of JSON wrappers.
                if "application/json" in content_type:
                    data = response.json()
                    if "audio" in data and isinstance(data["audio"], str):
                        return data["audio"], _mime_from_response_format(response_format)
                    if "audio_base64" in data and isinstance(data["audio_base64"], str):
                        return data["audio_base64"], _mime_from_response_format(response_format)
                    if "data" in data and isinstance(data["data"], str):
                        return data["data"], _mime_from_response_format(response_format)
                    last_error = "TTS JSON response does not include audio payload."
                    continue

                if response.content:
                    mime = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
                    if not mime or mime == "application/octet-stream":
                        mime = _mime_from_response_format(response_format)
                    return base64.b64encode(response.content).decode("utf-8"), mime
                last_error = "TTS response body is empty."
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue
    raise ProviderError(last_error or "TTS response does not include audio payload.")


async def image_generate(
    db: AsyncSession,
    provider_name: str,
    model: str,
    prompt: str,
    *,
    size: str = "1024x1024",
) -> tuple[str, dict[str, Any]]:
    clean_prompt = (prompt or "").strip()
    if not clean_prompt:
        raise ProviderError("Image prompt is empty.")

    ctx = await get_provider_context(db, provider_name)
    headers = {"Authorization": f"Bearer {ctx.api_key}", "Content-Type": "application/json"}
    image_format = "png"
    if provider_name == "dashscope":
        base = _clean_base(ctx.base_url)
        size_value = size.replace("x", "*")
        payloads = [
            (
                f"{base}/api/v1/services/aigc/multimodal-generation/generation",
                {
                    "model": model,
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": [{"text": clean_prompt}],
                            }
                        ]
                    },
                    "parameters": {"size": size_value, "prompt_extend": False},
                },
            ),
        ]
    else:
        payloads = [
            (
                url,
                {
                    "model": model,
                    "prompt": clean_prompt,
                    "size": size,
                    "n": 1,
                    "response_format": "b64_json",
                },
            )
            for url in _candidate_endpoints(ctx.base_url, "/images/generations", ctx.provider_name)
        ]

    last_error = "Image generation failed."
    async with httpx.AsyncClient(timeout=max(ctx.timeout_seconds, 30), trust_env=False) as client:
        for url, payload in payloads:
            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code >= 400:
                    last_error = _format_http_error(response.status_code, response.text)
                    continue
                data = response.json()
                output = data.get("output") if isinstance(data, dict) else None
                if isinstance(output, dict):
                    choices = output.get("choices") or []
                    if isinstance(choices, list):
                        for choice in choices:
                            if not isinstance(choice, dict):
                                continue
                            message = choice.get("message") or {}
                            contents = message.get("content") or []
                            if isinstance(contents, list):
                                for item in contents:
                                    if not isinstance(item, dict):
                                        continue
                                    if isinstance(item.get("image"), str) and item["image"].strip():
                                        return item["image"], {"provider": provider_name, "model": model, "endpoint": url}
                    results = output.get("results") or output.get("images") or []
                    if isinstance(results, list):
                        for item in results:
                            if not isinstance(item, dict):
                                continue
                            if isinstance(item.get("url"), str) and item["url"].strip():
                                return item["url"], {"provider": provider_name, "model": model, "endpoint": url}
                            b64_value = item.get("b64_image") or item.get("base64_data")
                            if isinstance(b64_value, str) and b64_value.strip():
                                mime = _mime_from_image_format(item.get("format") or image_format)
                                return (
                                    f"data:{mime};base64,{b64_value}",
                                    {"provider": provider_name, "model": model, "endpoint": url},
                                )
                items = data.get("data") if isinstance(data, dict) else None
                if isinstance(items, list):
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        if isinstance(item.get("url"), str) and item["url"].strip():
                            return item["url"], {"provider": provider_name, "model": model, "endpoint": url}
                        b64_value = item.get("b64_json") or item.get("image_base64")
                        if isinstance(b64_value, str) and b64_value.strip():
                            mime = _mime_from_image_format(item.get("format") or image_format)
                            return (
                                f"data:{mime};base64,{b64_value}",
                                {"provider": provider_name, "model": model, "endpoint": url},
                            )
                last_error = "Image payload does not include url or base64 image."
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue
    raise ProviderError(last_error)


async def siliconflow_upload_reference_voice(
    db: AsyncSession,
    model: str,
    custom_name: str,
    reference_text: str,
    audio_bytes: bytes,
    filename: str,
) -> str:
    """
    Upload reference audio for SiliconFlow CosyVoice voice cloning.
    Returns a `uri` (e.g. `speech:xxx`) which can be used as the `voice` param in `/v1/audio/speech`.
    """
    ctx = await get_provider_context(db, "siliconflow")
    headers = {"Authorization": f"Bearer {ctx.api_key}"}
    files = {"file": (filename, audio_bytes, _mime_from_audio_filename(filename))}
    data = {"model": model, "customName": custom_name, "text": reference_text}
    last_error: str | None = None
    urls = _candidate_endpoints(ctx.base_url, "/uploads/audio/voice", "siliconflow")
    async with httpx.AsyncClient(timeout=ctx.timeout_seconds, trust_env=False) as client:
        for idx, url in enumerate(urls):
            try:
                response = await client.post(url, headers=headers, data=data, files=files)
                if response.status_code >= 400:
                    error_text = _format_http_error(response.status_code, response.text)
                    last_error = error_text
                    if response.status_code == 404 and idx < len(urls) - 1:
                        continue
                    raise ProviderError(error_text)
                payload = response.json()
                uri = payload.get("uri") or payload.get("data", {}).get("uri")
                if not uri:
                    last_error = "Upload reference voice did not return `uri`."
                    continue
                return str(uri)
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue
    raise ProviderError(last_error or "Upload reference voice failed.")
