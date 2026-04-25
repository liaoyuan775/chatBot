from app.modules.chat.service import _extract_image_prompt, _resolve_retrieval_outcome, should_retrieve_knowledge


def test_smalltalk_skips_retrieval():
    decision = should_retrieve_knowledge("你好")
    assert decision.decision == "skip"
    assert decision.reason == "smalltalk"


def test_fact_question_triggers_retrieval():
    decision = should_retrieve_knowledge("系统支持哪些功能？")
    assert decision.decision == "retrieve"


def test_explicit_knowledge_request_triggers_retrieval():
    decision = should_retrieve_knowledge("请根据知识库里的文档总结重点")
    assert decision.decision == "retrieve"
    assert decision.reason == "explicit_knowledge_request"


def test_plain_image_request_skips_retrieval():
    decision = should_retrieve_knowledge("/draw 画一只赛博朋克风格的猫", image_prompt="画一只赛博朋克风格的猫")
    assert decision.decision == "skip"
    assert decision.reason == "image_request_without_knowledge_dependency"


def test_knowledge_based_image_request_can_retrieve():
    decision = should_retrieve_knowledge(
        "根据知识库里的产品说明画一张结构示意图",
        image_prompt="根据知识库里的产品说明画一张结构示意图",
    )
    assert decision.decision == "retrieve"


def test_keyword_image_request_detected_from_natural_language():
    prompt = _extract_image_prompt("帮我画一张太空里的鲸鱼")
    assert prompt is not None


def test_generate_image_keyword_detected():
    prompt = _extract_image_prompt("请生成图片：一个未来城市夜景")
    assert prompt is not None


def test_non_image_text_not_detected_as_image_prompt():
    prompt = _extract_image_prompt("系统支持哪些功能")
    assert prompt is None


def test_retrieval_outcome_marks_hit():
    reason, hit_count = _resolve_retrieval_outcome(
        decision="retrieve",
        gate_reason="fact_question_pattern",
        knowledge_text="Source: manual\nsomething useful",
        rag_reason=None,
        timed_out=False,
    )
    assert reason == "retrieval_hit"
    assert hit_count == 1


def test_retrieval_outcome_marks_timeout():
    reason, hit_count = _resolve_retrieval_outcome(
        decision="retrieve",
        gate_reason="fact_question_pattern",
        knowledge_text="",
        rag_reason="rag_timeout:200ms",
        timed_out=True,
    )
    assert reason == "retrieval_timeout"
    assert hit_count == 0


def test_retrieval_outcome_marks_provider_error():
    reason, hit_count = _resolve_retrieval_outcome(
        decision="retrieve",
        gate_reason="fact_question_pattern",
        knowledge_text="",
        rag_reason="provider exploded",
        timed_out=False,
    )
    assert reason == "retrieval_provider_error"
    assert hit_count == 0
