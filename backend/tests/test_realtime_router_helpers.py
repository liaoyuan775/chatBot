from types import SimpleNamespace

from app.modules.realtime_ws.router import _is_usable_partial_text, _should_use_native_omni


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
