from __future__ import annotations

from app.modules.chain_config.router import validate_chain_mapping


def test_validate_chain_mapping_includes_disabled_model_name() -> None:
    mapping = {
        "asr_model": "FunAudioLLM/SenseVoiceSmall",
        "llm_model": "doubao-seed-1-6-flash-250615",
        "embedding_model": "BAAI/bge-m3",
        "rerank_model": "BAAI/bge-reranker-v2-m3",
        "tts_model": "cosyvoice-v3-flash",
        "image_model": "z-image-turbo",
    }
    enabled = {
        "FunAudioLLM/SenseVoiceSmall",
        "BAAI/bge-m3",
        "BAAI/bge-reranker-v2-m3",
        "cosyvoice-v3-flash",
        "z-image-turbo",
    }
    is_valid, errors = validate_chain_mapping(mapping, enabled)
    assert is_valid is False
    assert errors
    assert "llm_model=doubao-seed-1-6-flash-250615" in errors[0]


def test_validate_chain_mapping_allows_minimal_omni_chain() -> None:
    mapping = {"llm_model": "qwen3.5-omni-plus-realtime"}
    enabled = {"qwen3.5-omni-plus-realtime"}

    is_valid, errors = validate_chain_mapping(mapping, enabled)

    assert is_valid is True
    assert errors == []


def test_validate_chain_mapping_only_requires_llm_model() -> None:
    mapping = {
        "llm_model": "qwen3.5-omni-plus-realtime",
        "embedding_model": "",
        "rerank_model": "",
        "asr_model": "",
        "tts_model": "",
        "image_model": "",
    }
    enabled = {"qwen3.5-omni-plus-realtime"}

    is_valid, errors = validate_chain_mapping(mapping, enabled)

    assert is_valid is True
    assert errors == []


def test_validate_chain_mapping_still_requires_llm_model() -> None:
    mapping = {"asr_model": "FunAudioLLM/SenseVoiceSmall"}
    enabled = {"FunAudioLLM/SenseVoiceSmall"}

    is_valid, errors = validate_chain_mapping(mapping, enabled)

    assert is_valid is False
    assert errors == ["Missing model configuration: llm_model"]
