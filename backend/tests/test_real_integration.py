from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest
import websockets

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8010"


def _wait_for_server(timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    with httpx.Client(base_url=BASE_URL, timeout=5, trust_env=False) as client:
        while time.time() < deadline:
            try:
                response = client.get("/healthz")
                if response.status_code == 200:
                    return
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)
    raise RuntimeError("Server did not become healthy in time.")


@pytest.fixture(scope="session", autouse=True)
def backend_server() -> None:
    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_server()
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_healthz_ok() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30, trust_env=False) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_call_config_defaults() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30, trust_env=False) as client:
        init_resp = client.post("/api/call-config/init-defaults")
        assert init_resp.status_code == 200
        response = client.get("/api/call-config")
    assert response.status_code == 200
    body = response.json()
    assert body["main_provider"] == "dashscope"
    assert body["main_model"] == "qwen3.5-omni-plus-realtime"


def test_text_message_and_memory_flow() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=120, trust_env=False) as client:
        session_resp = client.post("/api/sessions", json={"title": "pytest-session"})
        assert session_resp.status_code == 200
        session_id = session_resp.json()["id"]

        msg_resp = client.post(
            "/api/messages",
            json={
                "session_id": session_id,
                "content_type": "text",
                "text_content": "hello from pytest",
            },
        )
        assert msg_resp.status_code == 200
        payload = msg_resp.json()
        assert payload["assistant_reply"]

        context_resp = client.get(f"/api/context/sessions/{session_id}")
        assert context_resp.status_code == 200
        assert "short_term" in context_resp.json()


def test_knowledge_upload_and_retrieval() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=120, trust_env=False) as client:
        retrieval_cfg = client.get("/api/knowledge/retrieval-config")
        assert retrieval_cfg.status_code == 200
        assert "rag_timeout_ms" in retrieval_cfg.json()

        files = {"file": ("pytest_doc.txt", io.BytesIO(b"fallback chain includes sensevoice and cosyvoice"), "text/plain")}
        upload_resp = client.post("/api/knowledge/documents", files=files, data={"chunk_size": "64", "overlap": "8"})
        assert upload_resp.status_code == 200

        retrieval_resp = client.post(
            "/api/knowledge/retrieval-test",
            data={"question": "what is fallback chain", "top_k": "3"},
        )
        assert retrieval_resp.status_code == 200
        assert retrieval_resp.json()["count"] >= 1


@pytest.mark.asyncio
async def test_realtime_empty_commit_does_not_trigger_reply() -> None:
    ws_url = f"ws://127.0.0.1:8010/ws/realtime-chat?session_id={uuid.uuid4()}"
    try:
        async with websockets.connect(ws_url, proxy=None) as websocket:
            ready = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5))
            assert ready["event"] == "session.ready"

            state = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5))
            assert state["event"] == "session.state.changed"
            assert state["state"] == "listening"

            await websocket.send(json.dumps({"event": "input_audio.commit"}))
            no_speech = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5))
            assert no_speech["event"] == "session.state.changed"
            assert no_speech["state"] == "listening"
            assert no_speech["reason"] == "no-speech"

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(websocket.recv(), timeout=0.8)
    except (websockets.exceptions.InvalidMessage, OSError):
        pytest.skip("Local test server websocket handshake is unavailable in this environment.")
