import os
import sys
import time
import asyncio
from pathlib import Path

ROOT = Path(r"D:\AgentLearning\chatBot\backend")
sys.path.insert(0, str(ROOT))

raw = (ROOT / ".env").read_text(encoding="utf-8-sig")
for line in raw.splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    os.environ[key] = value

from app.core.database import SessionLocal
from app.core.provider_gateway import tts_synthesize, ProviderError
from app.core.config import get_settings

settings = get_settings()

CASES = [
    ("dashscope", settings.dashscope_tts_model, settings.dashscope_tts_voice, "你好，这是一次速度测试。"),
    ("siliconflow", settings.siliconflow_tts_model, settings.siliconflow_tts_voice, "你好，这是一次速度测试。"),
]

async def main() -> None:
    async with SessionLocal() as db:
        for provider, model, voice, text in CASES:
            start = time.perf_counter()
            try:
                audio_base64, audio_mime = await tts_synthesize(
                    db,
                    provider,
                    model,
                    voice,
                    text,
                    response_format="wav",
                    stream=False,
                )
                elapsed = (time.perf_counter() - start) * 1000
                print(f"{provider}\t{model}\t{elapsed:.1f}ms\t{audio_mime}\tlen={len(audio_base64)}")
            except ProviderError as exc:
                elapsed = (time.perf_counter() - start) * 1000
                print(f"{provider}\t{model}\tERROR\t{elapsed:.1f}ms\t{exc}")

asyncio.run(main())
