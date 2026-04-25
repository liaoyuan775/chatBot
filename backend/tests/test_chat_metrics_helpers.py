from app.modules.chat.service import (
    PreparedAssistantTurn,
    build_retrieval_metrics_payload,
    build_turn_metrics_payload,
    should_retrieve_knowledge,
)


def test_build_retrieval_metrics_payload_includes_all_fields():
    prepared = PreparedAssistantTurn(
        runtime=None,
        context_hint="No context",
        knowledge_text="Source: handbook\nexample",
        rag_trace={},
        rag_reason=None,
        image_prompt=None,
        context_latency_ms=42,
        retrieval_decision="retrieve",
        retrieval_gate_reason="fact_question_pattern",
        retrieval_reason="retrieval_hit",
        retrieval_latency_ms=128,
        retrieval_hit_count=1,
        retrieval_timed_out=False,
    )

    payload = build_retrieval_metrics_payload(prepared, turn_id="turn-1")

    assert payload == {
        "turn_id": "turn-1",
        "latency_ms": 128,
        "hit_count": 1,
        "decision": "retrieve",
        "reason": "retrieval_hit",
        "timed_out": False,
    }


def test_build_turn_metrics_payload_keeps_stage_breakdown():
    payload = build_turn_metrics_payload(
        turn_id="turn-2",
        context_latency_ms=15,
        first_text_latency_ms=200,
        first_audio_latency_ms=360,
        retrieval_latency_ms=120,
        llm_latency_ms=410,
        tts_latency_ms=180,
        total_latency_ms=730,
    )

    assert payload["turn_id"] == "turn-2"
    assert payload["context_latency_ms"] == 15
    assert payload["retrieval_latency_ms"] == 120
    assert payload["llm_latency_ms"] == 410
    assert payload["tts_latency_ms"] == 180
    assert payload["total_latency_ms"] == 730


def test_short_follow_up_still_skips_retrieval():
    decision = should_retrieve_knowledge("继续")
    assert decision.decision == "skip"
    assert decision.reason == "short_follow_up"


def test_long_structured_query_prefers_retrieval():
    decision = should_retrieve_knowledge("请说明 API 网关的熔断、降级、超时预算分别有什么作用？")
    assert decision.decision == "retrieve"
