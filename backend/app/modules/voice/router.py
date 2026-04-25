from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
import wave
from datetime import datetime
from pathlib import Path
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.provider_gateway import ProviderError, asr_transcribe, siliconflow_upload_reference_voice, tts_synthesize
from app.models import ChainConfigEntity, SessionEntity, VoiceProfileEntity
from app.modules.chat.engine import ensure_default_call_config
from app.schemas.common import VoicePreviewRequest, VoiceRename, VoiceUpsert

router = APIRouter(prefix="/api/voices", tags=["voices"])
settings = get_settings()
VOICE_SAMPLE_DIR = Path(__file__).resolve().parents[3] / "storage" / "voice_samples"


def _safe_filename(name: str) -> str:
    safe = "".join(ch for ch in name if ch.isalnum() or ch in {"-", "_", "."})
    return safe or f"sample-{uuid.uuid4()}.wav"


def _safe_custom_name(name: str) -> str:
    # SiliconFlow customName supports only letters/digits/_/-, max length 64.
    raw = str(name or "")
    replaced = re.sub(r"\s+", "-", raw)
    safe = re.sub(r"[^A-Za-z0-9_-]", "", replaced).strip("-_")
    if safe:
        return safe[:64]
    return f"voice-{uuid.uuid4().hex[:16]}"


def _sanitize_new_voice_config(config_json: dict | None) -> dict:
    config = dict(config_json or {})
    for key in [
        "sample_source",
        "sample_source_type",
        "sample_updated_at",
        "clone_uri",
        "clone_error",
        "clone_reference_text",
        "clone_provider",
        "clone_model",
    ]:
        config.pop(key, None)
    return config


def _validate_clone_sample(target: Path, suffix: str) -> str | None:
    if suffix != ".wav":
        return None
    try:
        with wave.open(str(target), "rb") as wav:
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frame_count = wav.getnframes()
        duration = frame_count / sample_rate if sample_rate else 0
    except wave.Error as exc:
        return f"WAV 文件解析失败：{exc}"
    if sample_width != 2:
        return f"WAV 样本必须是 16-bit PCM，当前采样宽度为 {sample_width * 8} bit。"
    if sample_rate not in {16000, 22050, 24000, 32000, 44100, 48000}:
        return f"WAV 采样率不受支持：{sample_rate}Hz。请转换为 16k/22.05k/24k/32k/44.1k/48k 后重试。"
    if duration <= 0:
        return "WAV 样本为空，请重新导出后重试。"
    if duration > 30:
        return f"WAV 样本时长 {duration:.1f}s，超过 30s 上限。"
    return None


def _convert_wav_to_clone_safe_pcm(target: Path) -> str | None:
    converted_target = target.with_name(f"{target.stem}_clone_safe.wav")
    script = (
        "from pathlib import Path\n"
        "import numpy as np\n"
        "from scipy.io import wavfile\n"
        f"src = Path(r'{str(target)}')\n"
        f"dst = Path(r'{str(converted_target)}')\n"
        "sample_rate, data = wavfile.read(str(src))\n"
        "mono = data.mean(axis=1) if getattr(data, 'ndim', 1) > 1 else data\n"
        "mono = np.clip(mono, -32768, 32767).astype(np.int16)\n"
        "wavfile.write(str(dst), sample_rate, mono)\n"
    )
    try:
        subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
    except Exception as exc:  # noqa: BLE001
        return f"WAV 样本自动转换失败：{exc}"
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    converted_target.replace(target)
    return _validate_clone_sample(target, ".wav")


async def _next_voice_copy_name(db: AsyncSession, base_name: str) -> str:
    candidate = f"{base_name}-clone"
    exists = await db.scalar(select(VoiceProfileEntity).where(VoiceProfileEntity.name == candidate))
    if not exists:
        return candidate
    idx = 2
    while True:
        candidate = f"{base_name}-clone-{idx}"
        exists = await db.scalar(select(VoiceProfileEntity).where(VoiceProfileEntity.name == candidate))
        if not exists:
            return candidate
        idx += 1


@router.get("")
async def list_voices(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(VoiceProfileEntity).order_by(VoiceProfileEntity.created_at.desc()))).all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "voice_type": r.voice_type,
            "is_default": r.is_default,
            "is_enabled": r.is_enabled,
            "config_json": r.config_json,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("")
async def create_voice(payload: VoiceUpsert, db: AsyncSession = Depends(get_db)):
    if payload.is_default:
        await db.execute(update(VoiceProfileEntity).values(is_default=False))
    row = VoiceProfileEntity(
        name=payload.name,
        voice_type=payload.voice_type,
        is_default=payload.is_default,
        is_enabled=payload.is_enabled,
        config_json=_sanitize_new_voice_config(payload.config_json),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="音色名称已存在，请更换后重试。") from exc
    await db.refresh(row)
    return {"id": str(row.id), "message": "音色创建成功。"}


@router.post("/{voice_id}/clone")
async def clone_voice(voice_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(VoiceProfileEntity, voice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Voice not found.")
    clone = VoiceProfileEntity(
        name=await _next_voice_copy_name(db, row.name),
        voice_type="custom",
        is_default=False,
        is_enabled=True,
        vector_ref=f"clone://{voice_id}",
        config_json=row.config_json,
    )
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    return {"id": str(clone.id), "message": "音色克隆成功。"}


@router.post("/{voice_id}/sample")
async def upload_voice_sample(
    voice_id: uuid.UUID,
    file: UploadFile = File(...),
    source_type: str = Form(default="upload"),
    reference_text: str = Form(default=""),
    clone: bool = Form(default=True),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(VoiceProfileEntity, voice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Voice not found.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".webm", ".aac"}:
        raise HTTPException(status_code=400, detail="仅支持 wav/mp3/m4a/webm/aac 样本文件。")
    VOICE_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    voice_dir = VOICE_SAMPLE_DIR / str(voice_id)
    voice_dir.mkdir(parents=True, exist_ok=True)
    target = voice_dir / f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{_safe_filename(file.filename or 'sample.wav')}"
    with target.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    clone_sample_error = _validate_clone_sample(target, suffix)

    config = dict(row.config_json or {})
    config["sample_source"] = str(target)
    config["sample_source_type"] = source_type
    config["sample_updated_at"] = datetime.utcnow().isoformat()
    config.setdefault("voice_name", settings.siliconflow_tts_voice)

    row.config_json = config
    row.voice_type = "custom"
    clone_uri: str | None = None
    used_reference_text: str | None = None
    if clone:
        config.pop("clone_uri", None)
        config.pop("clone_error", None)
        config.pop("clone_reference_text", None)
        row.config_json = config
        audio_bytes = target.read_bytes()
        if clone_sample_error:
            config["clone_error"] = clone_sample_error
            row.config_json = config
        else:
            used_reference_text = (reference_text or "").strip()
            if not used_reference_text:
                try:
                    used_reference_text = (
                        await asr_transcribe(db, "siliconflow", settings.siliconflow_asr_model, audio_bytes, target.name)
                    ).strip()
                except Exception:  # noqa: BLE001
                    used_reference_text = ""
            if used_reference_text:
                try:
                    clone_uri = await siliconflow_upload_reference_voice(
                        db=db,
                        model=settings.siliconflow_tts_model,
                        custom_name=_safe_custom_name(row.name),
                        reference_text=used_reference_text,
                        audio_bytes=audio_bytes,
                        filename=target.name,
                    )
                    config["clone_uri"] = clone_uri
                    config["clone_provider"] = "siliconflow"
                    config["clone_model"] = settings.siliconflow_tts_model
                    config["tts_provider"] = "siliconflow"
                    config["tts_model"] = settings.siliconflow_tts_model
                    config["voice_name"] = clone_uri
                    config["clone_reference_text"] = used_reference_text
                    config.pop("clone_error", None)
                    row.config_json = config
                except Exception as exc:  # noqa: BLE001
                    config["clone_error"] = str(exc)
                    row.config_json = config
            else:
                config["clone_error"] = "未获取到参考文本，请手动填写参考文本后重试。"
                row.config_json = config
    await db.commit()
    clone_error = str((row.config_json or {}).get("clone_error") or "")
    if clone_uri:
        message = "音色样本上传成功，音色克隆完成。"
    elif clone:
        message = f"音色样本上传成功，但音色克隆失败：{clone_error or '未知错误'}"
    else:
        message = "音色样本上传成功。"
    return {
        "message": message,
        "sample_source": str(target),
        "clone_uri": clone_uri,
        "clone_reference_text": used_reference_text,
        "clone_error": clone_error,
    }


@router.patch("/{voice_id}/rename")
async def rename_voice(voice_id: uuid.UUID, payload: VoiceRename, db: AsyncSession = Depends(get_db)):
    row = await db.get(VoiceProfileEntity, voice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Voice not found.")
    row.name = payload.name
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="音色名称已存在，请更换后重试。") from exc
    return {"message": "音色重命名成功。"}


@router.post("/{voice_id}/preview")
async def preview_voice(voice_id: uuid.UUID, payload: VoicePreviewRequest, db: AsyncSession = Depends(get_db)):
    row = await db.get(VoiceProfileEntity, voice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Voice not found.")

    cfg = await ensure_default_call_config(db)
    tts_provider = cfg.fallback_tts_provider
    tts_model = cfg.fallback_tts_model
    fallback_voice = cfg.fallback_tts_voice or settings.siliconflow_tts_voice

    config = row.config_json or {}
    requested_voice = str(config.get("voice_name") or row.name or fallback_voice)
    if str(config.get("tts_provider") or "").strip():
        tts_provider = str(config.get("tts_provider"))
    if str(config.get("tts_model") or "").strip():
        tts_model = str(config.get("tts_model"))
    if requested_voice.startswith("speech:") or requested_voice.startswith("custom:"):
        tts_provider = "siliconflow"
        tts_model = settings.siliconflow_tts_model
        fallback_voice = settings.siliconflow_tts_voice
    requested_text = (payload.text or "").strip()
    safe_text = requested_text.encode("utf-8", errors="ignore").decode("utf-8").strip()
    candidates = [
        (requested_voice, requested_text or "Hello, this is a voice preview."),
        (requested_voice, safe_text or "Hello, this is a voice preview."),
        (fallback_voice, safe_text or "Hello, this is a voice preview."),
        (fallback_voice, "Hello, this is a voice preview."),
    ]

    last_error = "Voice preview failed."
    seen: set[tuple[str, str]] = set()
    for voice_name, text_input in candidates:
        pair = (voice_name, text_input)
        if pair in seen:
            continue
        seen.add(pair)
        try:
            audio_base64, audio_mime = await tts_synthesize(
                db,
                tts_provider,
                tts_model,
                voice_name,
                text_input,
                response_format="wav",
                stream=False,
            )
            return {"audio_base64": audio_base64, "format": "wav", "audio_mime": audio_mime, "voice_used": voice_name, "text_used": text_input}
        except ProviderError as exc:
            last_error = str(exc)
            continue

    raise HTTPException(status_code=400, detail=last_error)


@router.put("/{voice_id}")
async def update_voice(voice_id: uuid.UUID, payload: VoiceUpsert, db: AsyncSession = Depends(get_db)):
    row = await db.get(VoiceProfileEntity, voice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Voice not found.")
    if payload.is_default:
        await db.execute(update(VoiceProfileEntity).values(is_default=False))
    row.name = payload.name
    row.voice_type = payload.voice_type
    row.is_default = payload.is_default
    row.is_enabled = payload.is_enabled
    row.config_json = payload.config_json
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="音色名称已存在，请更换后重试。") from exc
    return {"message": "音色更新成功。"}


@router.delete("/{voice_id}")
async def delete_voice(voice_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(VoiceProfileEntity, voice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Voice not found.")
    default_voice = await db.scalar(
        select(VoiceProfileEntity).where(VoiceProfileEntity.is_default.is_(True), VoiceProfileEntity.id != voice_id)
    )
    replacement = default_voice.id if default_voice else None
    await db.execute(update(ChainConfigEntity).where(ChainConfigEntity.voice_id == voice_id).values(voice_id=replacement))
    await db.execute(update(SessionEntity).where(SessionEntity.voice_id == voice_id).values(voice_id=replacement))
    await db.delete(row)
    await db.commit()
    return {"message": "音色删除成功。"}
