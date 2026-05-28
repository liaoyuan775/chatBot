import asyncio
from types import SimpleNamespace

import pytest

from app.modules.realtime_ws.router import _cancel_turn_task, _is_usable_partial_text, _should_use_native_omni


def test_partial_placeholder_is_not_usable():
    assert _is_usable_partial_text("语音未识别，请用户重试") is False
    assert _is_usable_partial_text("  ") is False


def test_normal_partial_text_is_usable():
    assert _is_usable_partial_text("帮我总结一下这个方案") is True


def test_native_omni_requires_dashscope_realtime_model():
    runtime = SimpleNamespace(
        realtime_main_provider="dashscope",
        realtime_main_model="qwen3.5-omni-plus-realtime",
        omni_mode="auto",
    )
    assert _should_use_native_omni(runtime) is True


def test_force_legacy_disables_native_omni():
    runtime = SimpleNamespace(
        realtime_main_provider="dashscope",
        realtime_main_model="qwen3.5-omni-plus-realtime",
        omni_mode="force_legacy",
    )
    assert _should_use_native_omni(runtime) is False


@pytest.mark.asyncio
async def test_cancel_turn_task_cancels_running_task():
    async def sleeper():
        await asyncio.sleep(10)

    task = asyncio.create_task(sleeper())
    cancelled = await _cancel_turn_task(task)

    assert cancelled is True
    assert task.cancelled() is True
