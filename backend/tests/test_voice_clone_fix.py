from __future__ import annotations

import io
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import UploadFile
from scipy.io import wavfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.core.provider_gateway as provider_gateway
from app.core.provider_gateway import ProviderContext, ProviderError
from app.modules.voice import router as voice_router


class DummyResponse:
    def __init__(self, status_code: int, text: str = "", json_data: dict | None = None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data or {}
        self.headers: dict[str, str] = {}
        self.content: bytes = b""

    def json(self) -> dict:
        return self._json_data


class DummyAsyncClient:
    def __init__(self, calls: list[tuple[str, str]], responses: dict[str, list[object]]):
        self._calls = calls
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    def _next(self, method: str, url: str) -> DummyResponse:
        self._calls.append((method, url))
        if url not in self._responses or not self._responses[url]:
            raise AssertionError(f"Unexpected request URL: {url}")
        item = self._responses[url].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def request(self, method: str, url: str, **kwargs):  # noqa: ANN003
        return self._next(method, url)

    async def post(self, url: str, **kwargs):  # noqa: ANN003
        return self._next("POST", url)


def _install_async_client_mock(
    monkeypatch: pytest.MonkeyPatch, responses: dict[str, list[object]]
) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    response_map = {url: list(queue) for url, queue in responses.items()}

    def _factory(*args, **kwargs):  # noqa: ANN002, ANN003
        return DummyAsyncClient(calls, response_map)

    monkeypatch.setattr(provider_gateway.httpx, "AsyncClient", _factory)
    return calls


@pytest.mark.asyncio
async def test_request_with_fallback_does_not_mask_non_404_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = ProviderContext(
        provider_name="siliconflow",
        base_url="https://api.example.com",
        api_key="fake-key",
        timeout_seconds=10,
    )
    first_url = "https://api.example.com/v1/test-path"
    second_url = "https://api.example.com/test-path"
    calls = _install_async_client_mock(
        monkeypatch,
        {
            first_url: [DummyResponse(400, text='{"code":20022,"message":"bad request"}')],
            second_url: [DummyResponse(404, text="Not Found")],
        },
    )

    with pytest.raises(ProviderError, match="400:"):
        await provider_gateway._request_with_fallback(ctx, "POST", "/test-path", json_payload={"x": 1})

    assert calls == [("POST", first_url)]


@pytest.mark.asyncio
async def test_request_with_fallback_still_tries_next_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = ProviderContext(
        provider_name="siliconflow",
        base_url="https://api.example.com",
        api_key="fake-key",
        timeout_seconds=10,
    )
    first_url = "https://api.example.com/v1/test-path"
    second_url = "https://api.example.com/test-path"
    calls = _install_async_client_mock(
        monkeypatch,
        {
            first_url: [DummyResponse(404, text="Not Found")],
            second_url: [DummyResponse(200, text='{"ok":true}', json_data={"ok": True})],
        },
    )

    payload = await provider_gateway._request_with_fallback(ctx, "GET", "/test-path")

    assert payload == {"ok": True}
    assert calls == [("GET", first_url), ("GET", second_url)]


@pytest.mark.asyncio
async def test_siliconflow_upload_reference_voice_uses_404_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_provider_context(db, provider_name: str):  # noqa: ANN001
        assert provider_name == "siliconflow"
        return ProviderContext(
            provider_name="siliconflow",
            base_url="https://api.example.com",
            api_key="fake-key",
            timeout_seconds=10,
        )

    monkeypatch.setattr(provider_gateway, "get_provider_context", _fake_get_provider_context)
    first_url = "https://api.example.com/v1/uploads/audio/voice"
    second_url = "https://api.example.com/uploads/audio/voice"
    calls = _install_async_client_mock(
        monkeypatch,
        {
            first_url: [DummyResponse(404, text="Not Found")],
            second_url: [DummyResponse(200, json_data={"uri": "speech:new-voice"})],
        },
    )

    uri = await provider_gateway.siliconflow_upload_reference_voice(
        db=None,  # type: ignore[arg-type]
        model="FunAudioLLM/CosyVoice2-0.5B",
        custom_name="demo-voice",
        reference_text="hello world",
        audio_bytes=b"RIFF....WAVE",
        filename="sample.wav",
    )

    assert uri == "speech:new-voice"
    assert calls == [("POST", first_url), ("POST", second_url)]


class DummyVoiceRow:
    def __init__(self):
        self.id = uuid.uuid4()
        self.name = "demo-voice"
        self.voice_type = "custom"
        self.config_json = {
            "voice_name": "speech:old-voice",
            "clone_uri": "speech:old-voice",
            "clone_error": "old error",
        }


class DummyDB:
    def __init__(self, row: DummyVoiceRow):
        self._row = row
        self.commit_count = 0

    async def get(self, model, voice_id):  # noqa: ANN001
        if voice_id == self._row.id:
            return self._row
        return None

    async def commit(self):
        self.commit_count += 1


@pytest.mark.asyncio
async def test_upload_voice_sample_persists_clone_error_and_clears_stale_uri(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _always_fail_clone(**kwargs):  # noqa: ANN003
        raise ProviderError("400: reference audio too long")

    monkeypatch.setattr(voice_router, "VOICE_SAMPLE_DIR", tmp_path)
    monkeypatch.setattr(voice_router, "siliconflow_upload_reference_voice", _always_fail_clone)

    row = DummyVoiceRow()
    db = DummyDB(row)
    sample = UploadFile(filename="sample.wav", file=io.BytesIO(b"RIFF....WAVEfmt "))

    resp = await voice_router.upload_voice_sample(
        voice_id=row.id,
        file=sample,
        source_type="upload",
        reference_text="reference text",
        clone=True,
        db=db,  # type: ignore[arg-type]
    )

    assert db.commit_count == 1
    assert "克隆失败" in resp["message"]
    assert resp["clone_error"].startswith("400:")
    assert resp["clone_uri"] is None
    assert row.config_json["clone_error"].startswith("400:")
    assert "clone_uri" not in row.config_json


def test_safe_custom_name_is_ascii_and_limited() -> None:
    name = voice_router._safe_custom_name("default voice (A) #1")
    assert len(name) <= 64
    assert all(ch.isascii() for ch in name)
    assert all(ch.isalnum() or ch in {"_", "-"} for ch in name)


def test_validate_clone_sample_allows_stereo_16bit_wav(tmp_path: Path) -> None:
    src = tmp_path / "stereo.wav"
    wavfile.write(str(src), 44100, [[100, -100], [300, -300], [500, -500]])

    error = voice_router._validate_clone_sample(src, ".wav")

    assert error is None
