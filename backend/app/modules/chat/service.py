from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.provider_gateway import ProviderError, image_generate
from app.models import MessageEntity, SessionEntity
from app.modules.chat.engine import resolve_session_runtime, run_text_chain
from app.modules.chat.langchain_pipeline import (
    get_retrieval_runtime_config,
    is_knowledge_globally_enabled,
    run_history_context_lcel,
    run_rag_chain_lcel,
    summarize_title_lcel,
)
from app.modules.context_memory.service import recompute_session_memory

settings = get_settings()
DEFAULT_SESSION_TITLE = "新建会话"


@dataclass
class AssistantReply:
    text: str
    chain_name: str
    pipeline: str = ""
    fallback_reason: str | None = None
    voice_used: str | None = None
    content_type: str = "text"
    image_url: str | None = None
    provider_trace: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreparedAssistantTurn:
    runtime: Any
    context_hint: str
    knowledge_text: str
    rag_trace: dict[str, Any]
    rag_reason: str | None
    image_prompt: str | None
    grounded_answer: str | None = None
    context_latency_ms: int = 0
    retrieval_decision: str = "skip"
    retrieval_gate_reason: str = "not_evaluated"
    retrieval_reason: str = "not_evaluated"
    retrieval_latency_ms: int | None = None
    retrieval_hit_count: int = 0
    retrieval_timed_out: bool = False


@dataclass
class RetrievalDecision:
    decision: str
    reason: str


def build_retrieval_metrics_payload(prepared: PreparedAssistantTurn, *, turn_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "latency_ms": prepared.retrieval_latency_ms,
        "hit_count": prepared.retrieval_hit_count,
        "decision": prepared.retrieval_decision,
        "reason": prepared.retrieval_reason,
        "timed_out": prepared.retrieval_timed_out,
    }
    if turn_id:
        payload["turn_id"] = turn_id
    return payload


def build_turn_metrics_payload(
    *,
    turn_id: str,
    context_latency_ms: int | None = None,
    first_text_latency_ms: int | None = None,
    first_audio_latency_ms: int | None = None,
    interrupt_latency_ms: int | None = None,
    retrieval_latency_ms: int | None = None,
    llm_latency_ms: int | None = None,
    tts_latency_ms: int | None = None,
    total_latency_ms: int | None = None,
) -> dict[str, Any]:
    return {
        "turn_id": turn_id,
        "context_latency_ms": context_latency_ms,
        "first_text_latency_ms": first_text_latency_ms,
        "first_audio_latency_ms": first_audio_latency_ms,
        "interrupt_latency_ms": interrupt_latency_ms,
        "retrieval_latency_ms": retrieval_latency_ms,
        "llm_latency_ms": llm_latency_ms,
        "tts_latency_ms": tts_latency_ms,
        "total_latency_ms": total_latency_ms,
    }


def _resolve_retrieval_outcome(
    *,
    decision: str,
    gate_reason: str,
    knowledge_text: str,
    rag_reason: str | None,
    timed_out: bool,
) -> tuple[str, int]:
    if decision != "retrieve":
        return gate_reason, 0
    hit_count = max(0, str(knowledge_text).count("Source:")) or (1 if str(knowledge_text).strip() else 0)
    if timed_out:
        return "retrieval_timeout", 0
    if rag_reason:
        return "retrieval_provider_error", 0
    if hit_count <= 0:
        return "retrieval_no_hit", 0
    return "retrieval_hit", hit_count


def _looks_like_smalltalk(text: str) -> bool:
    normalized = re.sub(r"\s+", "", (text or "").strip().lower())
    if not normalized:
        return True
    if any(
        phrase in normalized
        for phrase in [
            "介绍一下你自己",
            "介绍下你自己",
            "简单介绍一下你自己",
            "你能做什么",
            "你是谁",
            "你叫什么",
        ]
    ):
        return True
    smalltalk_patterns = [
        r"^(你好|您好|嗨|哈喽|在吗|早上好|中午好|晚上好)$",
        r"^(谢谢|谢了|感谢|辛苦了|ok|好的|收到|明白了|嗯嗯|哦哦|哈哈|拜拜|再见)[!！。]*$",
        r"^(你是谁|你叫什么|你能做什么|介绍一下你自己)[?？!！。]*$",
        r"^(是吗|对吗|真的吗|然后呢|还有吗|为啥|为什么呢|咋办|怎么办)[?？!！。]*$",
    ]
    return any(re.fullmatch(pattern, normalized) for pattern in smalltalk_patterns)


def _looks_like_short_follow_up(text: str) -> bool:
    cleaned = re.sub(r"\s+", "", (text or "").strip())
    if not cleaned:
        return True
    return cleaned in {"继续", "展开", "细说", "具体点", "再说说", "再详细点", "然后", "接着", "举例", "总结下", "好的", "嗯嗯", "哦哦", "明白了", "懂了", "行", "可以"}


def _contains_knowledge_request(text: str) -> bool:
    keywords = [
        "知识库",
        "文档",
        "资料",
        "根据",
        "基于",
        "参考",
        "引用",
        "出处",
        "上传",
        "手册",
        "规范",
        "原文",
        "检索",
        "查找",
        "查询",
        "搜索",
        "搜一下",
        "找一下",
        "查一下",
        "帮我查",
        "帮我找",
        "匹配",
        "定位",
        "命中",
        "从知识库里",
        "在知识库里",
    ]
    return any(keyword in text for keyword in keywords)


def _contains_fact_pattern(text: str) -> bool:
    triggers = [
        "什么是",
        "是什么",
        "有哪些",
        "区别",
        "功能",
        "作用",
        "原理",
        "步骤",
        "怎么",
        "如何",
        "为什么",
        "支持",
        "配置",
        "参数",
        "报错",
        "异常",
        "总结",
        "概括",
        "说明",
        "介绍",
        "计划",
        "安排",
        "时间",
        "课程",
        "内容",
        "要求",
        "格式",
        "方法",
        "流程",
        "规则",
        "条件",
        "标准",
        "定义",
        "含义",
        "关系",
        "影响",
        "原因",
        "方案",
        "策略",
        "建议",
        "检索",
        "查找",
        "查询",
        "搜索",
        "匹配",
        "定位",
        "是谁",
        "叫什么",
        "主人",
        "姓名",
        "名字",
        "电话",
        "手机号",
        "号码",
        "编号",
        "学号",
        "工号",
        "对应谁",
        "谁的",
        "归属",
    ]
    return any(trigger in text for trigger in triggers)


def _has_dense_terms(text: str) -> bool:
    raw_terms = re.findall(r"[A-Z]{2,}[A-Z0-9_-]*|[a-z]{3,}[a-z0-9_-]*|\d+(?:\.\d+)?|[\u4e00-\u9fff]{2,}", text)
    unique_terms = {term.lower() for term in raw_terms if str(term).strip()}
    return len(unique_terms) >= 4


def _image_prompt_requires_knowledge(user_text: str | None) -> bool:
    text = (user_text or "").strip()
    knowledge_cues = ["根据知识库", "根据文档", "根据资料", "根据上传", "参考文档", "基于知识库", "基于资料"]
    return any(cue in text for cue in knowledge_cues)


def _extract_grounded_answer(user_text: str | None, knowledge_text: str | None) -> str | None:
    question = (user_text or "").strip()
    knowledge = str(knowledge_text or "").strip()
    if not question or not knowledge:
        return None

    phone_numbers = re.findall(r"1\d{10}", question)
    lookup_cues = ["查", "检索", "查询", "搜索", "找", "对应谁", "是谁", "主人", "姓名", "名字", "号码", "手机号", "电话", "归属"]
    if phone_numbers and any(cue in question for cue in lookup_cues):
        for phone in phone_numbers:
            blocks = [block.strip() for block in knowledge.split("Source:") if block.strip()]
            for block in blocks:
                if phone not in block:
                    continue
                lines = [line.strip() for line in block.splitlines() if line.strip()]
                source_line = lines[0] if lines else ""
                match = re.search(rf"-([\u4e00-\u9fff]{{2,8}})-{re.escape(phone)}(?:-|\.|$)", source_line)
                if match:
                    return f"根据知识库，号码{phone}对应的人是{match.group(1)}。"
                for line in lines[1:]:
                    name_match = re.search(r"(?:姓名|联系人|作者|负责人)[:：]\s*([\u4e00-\u9fff]{2,8})", line)
                    if name_match:
                        return f"根据知识库，号码{phone}对应的人是{name_match.group(1)}。"
    return None


def should_retrieve_knowledge(user_text: str | None, *, image_prompt: str | None = None) -> RetrievalDecision:
    text = (user_text or "").strip()
    if not text:
        return RetrievalDecision(decision="skip", reason="empty_input")
    if image_prompt and not _image_prompt_requires_knowledge(text):
        return RetrievalDecision(decision="skip", reason="image_request_without_knowledge_dependency")
    if _looks_like_smalltalk(text):
        return RetrievalDecision(decision="skip", reason="smalltalk")
    if _looks_like_short_follow_up(text):
        return RetrievalDecision(decision="skip", reason="short_follow_up")
    if _contains_knowledge_request(text):
        return RetrievalDecision(decision="retrieve", reason="explicit_knowledge_request")
    if _contains_fact_pattern(text):
        return RetrievalDecision(decision="retrieve", reason="fact_question_pattern")
    if _has_dense_terms(text):
        return RetrievalDecision(decision="retrieve", reason="dense_terms")
    if len(text) >= 24 and any(token in text for token in ["？", "?", "：", ":", "，", ","]):
        return RetrievalDecision(decision="retrieve", reason="long_structured_query")
    return RetrievalDecision(decision="skip", reason="default_skip")


async def _retrieve_knowledge_text(
    db: AsyncSession,
    question: str,
    *,
    chain_mapping: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], str | None, bool]:
    retrieval_config = await get_retrieval_runtime_config(db, chain_mapping=chain_mapping)
    rag = await run_rag_chain_lcel(
        db=db,
        question=question,
        top_k=int(retrieval_config.get("top_k", 3)),
        similarity_threshold=float(retrieval_config.get("similarity_threshold", 0.0)),
        chain_mapping=chain_mapping,
        rag_timeout_ms=int(retrieval_config.get("rag_timeout_ms", 1500)),
    )
    return rag.text, rag.provider_trace, rag.fallback_reason, rag.timed_out


def _extract_image_prompt(user_text: str | None) -> str | None:
    text = (user_text or "").strip()
    if not text:
        return None
    explicit = re.match(r"^(?:/image|/img|/draw)\s*[:：]?\s*(.+)$", text, flags=re.IGNORECASE)
    if explicit and explicit.group(1).strip():
        return explicit.group(1).strip()
    keywords = [
        "生成图片", "生成一张图", "生成一张", "生成个", "生成一幅", "生成图像", "生图",
        "画一张", "画一张图", "画个", "画幅", "画图", "帮我画",
        "绘制", "出一张图", "出一张", "帮我生成一张", "帮我生成",
        "帮我做一张", "帮我做图", "作图", "做一张图", "来一张", "来张", "整个图",
    ]
    if any(keyword in text for keyword in keywords):
        return text[:600]
    return None


async def build_assistant_reply(db: AsyncSession, session: SessionEntity, user_text: str | None) -> AssistantReply:
    prepared = await prepare_assistant_turn(db, session, user_text)
    runtime = prepared.runtime
    context_hint = prepared.context_hint
    knowledge_text = prepared.knowledge_text
    rag_trace = prepared.rag_trace
    rag_reason = prepared.rag_reason
    image_prompt = prepared.image_prompt
    return await build_assistant_reply_from_prepared(
        db,
        session,
        user_text,
        prepared=prepared,
    )


async def prepare_assistant_turn(db: AsyncSession, session: SessionEntity, user_text: str | None) -> PreparedAssistantTurn:
    runtime = await resolve_session_runtime(db, session.id)
    history = (
        await db.scalars(
            select(MessageEntity)
            .where(MessageEntity.session_id == session.id, MessageEntity.role.in_(["user", "assistant"]))
            .order_by(MessageEntity.created_at.desc())
            .limit(8)
        )
    ).all()
    history_lines: list[str] = []
    for item in reversed(history):
        text = (item.text_content or "").strip()
        if not text:
            continue
        role_label = "用户" if item.role == "user" else "助手"
        history_lines.append(f"{role_label}: {text}")

    context_started = perf_counter()
    if history_lines:
        try:
            context_hint = await asyncio.wait_for(
                run_history_context_lcel(
                    db=db,
                    provider_name=runtime.text_llm_provider,
                    model_name=runtime.text_llm_model,
                    history_texts=history_lines,
                ),
                timeout=5.0,
            )
        except Exception:
            context_hint = "\n".join(f"- {line}" for line in history_lines[-6:])
    else:
        context_hint = "No context"
    context_latency_ms = int((perf_counter() - context_started) * 1000)

    image_prompt = _extract_image_prompt(user_text)
    knowledge_text = ""
    rag_trace: dict[str, Any] = {}
    rag_reason: str | None = None
    retrieval_decision = "skip"
    retrieval_gate_reason = "session_knowledge_disabled"
    retrieval_reason = "session_knowledge_disabled"
    retrieval_latency_ms: int | None = 0
    retrieval_hit_count = 0
    retrieval_timed_out = False
    grounded_answer: str | None = None
    if session.knowledge_enabled and await is_knowledge_globally_enabled(db):
        rag_query = (user_text or "").strip()
        if len(rag_query) > 1000:
            rag_query = rag_query[:1000]
        decision = should_retrieve_knowledge(user_text, image_prompt=image_prompt)
        retrieval_decision = decision.decision
        retrieval_gate_reason = decision.reason
        if decision.decision == "retrieve":
            rag_started = perf_counter()
            knowledge_text, rag_trace, rag_reason, retrieval_timed_out = await _retrieve_knowledge_text(
                db,
                rag_query,
                chain_mapping=getattr(runtime, "chain_mapping", None),
            )
            retrieval_latency_ms = int((perf_counter() - rag_started) * 1000)
            retrieval_reason, retrieval_hit_count = _resolve_retrieval_outcome(
                decision=decision.decision,
                gate_reason=decision.reason,
                knowledge_text=knowledge_text,
                rag_reason=rag_reason,
                timed_out=retrieval_timed_out,
            )
            if retrieval_reason == "retrieval_hit":
                grounded_answer = _extract_grounded_answer(user_text, knowledge_text)
        else:
            retrieval_reason = decision.reason
            rag_trace = {"decision": decision.decision, "reason": decision.reason, "timed_out": False, "hit_count": 0}
    elif not session.knowledge_enabled:
        rag_trace = {"decision": "skip", "reason": retrieval_reason, "timed_out": False, "hit_count": 0}
    else:
        retrieval_reason = "knowledge_global_disabled"
        retrieval_gate_reason = retrieval_reason
        rag_trace = {"decision": "skip", "reason": retrieval_reason, "timed_out": False, "hit_count": 0}

    return PreparedAssistantTurn(
        runtime=runtime,
        context_hint=context_hint,
        context_latency_ms=context_latency_ms,
        knowledge_text=knowledge_text,
        rag_trace=rag_trace,
        rag_reason=rag_reason,
        image_prompt=image_prompt,
        grounded_answer=grounded_answer,
        retrieval_decision=retrieval_decision,
        retrieval_gate_reason=retrieval_gate_reason,
        retrieval_reason=retrieval_reason,
        retrieval_latency_ms=retrieval_latency_ms,
        retrieval_hit_count=retrieval_hit_count,
        retrieval_timed_out=retrieval_timed_out,
    )


async def build_assistant_reply_from_prepared(
    db: AsyncSession,
    session: SessionEntity,
    user_text: str | None,
    *,
    prepared: PreparedAssistantTurn,
) -> AssistantReply:
    runtime = prepared.runtime
    context_hint = prepared.context_hint
    knowledge_text = prepared.knowledge_text
    rag_trace = prepared.rag_trace
    rag_reason = prepared.rag_reason
    image_prompt = prepared.image_prompt
    grounded_answer = prepared.grounded_answer

    if image_prompt:
        prompt = image_prompt
        if knowledge_text.strip():
            prompt = (
                f"{image_prompt}\n\n"
                "以下是可选参考资料，仅在与画图需求直接相关时使用：\n"
                f"{knowledge_text[:1200]}"
            )
        try:
            image_url, image_trace = await image_generate(
                db,
                runtime.image_provider,
                runtime.image_model,
                prompt,
            )
            provider_trace = {
                "image": {
                    **image_trace,
                    "prompt": image_prompt,
                    "knowledge_applied": bool(knowledge_text.strip()),
                    "retrieval_decision": prepared.retrieval_decision,
                    "retrieval_gate_reason": prepared.retrieval_gate_reason,
                    "retrieval_reason": prepared.retrieval_reason,
                    "retrieval_timed_out": prepared.retrieval_timed_out,
                }
            }
            provider_trace["llm_fallback"] = False
            if rag_trace:
                provider_trace["rag"] = rag_trace
            if rag_reason:
                provider_trace["rag_error"] = rag_reason
            return AssistantReply(
                text="已根据你的描述生成图片，请查看下方结果。",
                chain_name="image_chain",
                pipeline="rag_chain->image_chain" if knowledge_text.strip() else "image_chain",
                voice_used=runtime.tts_voice,
                content_type="generated_image",
                image_url=image_url,
                provider_trace=provider_trace,
            )
        except ProviderError as exc:
            return AssistantReply(
                text=f"抱歉，当前图片模型暂时不可用：{exc}",
                chain_name="image_chain",
                pipeline="image_chain",
                fallback_reason=str(exc),
                voice_used=runtime.tts_voice,
                provider_trace={"image_error": str(exc), "rag": rag_trace} if rag_trace else {"image_error": str(exc)},
            )

    if grounded_answer:
        provider_trace = {
            "llm_fallback": False,
            "retrieval_gate": {
                "decision": prepared.retrieval_decision,
                "gate_reason": prepared.retrieval_gate_reason,
                "reason": prepared.retrieval_reason,
                "timed_out": prepared.retrieval_timed_out,
                "hit_count": prepared.retrieval_hit_count,
            },
            "stage_metrics": {
                "context_latency_ms": prepared.context_latency_ms,
                "retrieval_latency_ms": prepared.retrieval_latency_ms,
                "llm_latency_ms": 0,
            },
            "grounded_answer": True,
        }
        if rag_trace:
            provider_trace["rag"] = rag_trace
        if rag_reason:
            provider_trace["rag_error"] = rag_reason
        return AssistantReply(
            text=grounded_answer,
            chain_name="knowledge_grounded_answer",
            pipeline="rag_chain->knowledge_grounded_answer",
            voice_used=runtime.tts_voice,
            provider_trace=provider_trace,
        )

    try:
        chain_result = await run_text_chain(
            db=db,
            session_id=session.id,
            user_text=(user_text or "").strip(),
            context_text=context_hint,
            knowledge_text=knowledge_text,
            llm_provider=runtime.text_llm_provider,
            llm_model=runtime.text_llm_model,
            system_prompt=runtime.persona_system_prompt,
            chain_name_hint=runtime.chain_name,
        )
    except Exception as exc:  # noqa: BLE001
        return AssistantReply(
            text="抱歉，当前模型服务暂不可用，请稍后重试。",
            chain_name="text_chain",
            pipeline="rag_chain->text_chain",
            fallback_reason=str(exc),
            voice_used=runtime.tts_voice,
            provider_trace={"llm_error": str(exc), "rag": rag_trace} if rag_trace else {"llm_error": str(exc)},
        )

    provider_trace = dict(chain_result.provider_trace or {})
    provider_trace["llm_fallback"] = bool(chain_result.used_fallback)
    provider_trace["retrieval_gate"] = {
        "decision": prepared.retrieval_decision,
        "gate_reason": prepared.retrieval_gate_reason,
        "reason": prepared.retrieval_reason,
        "timed_out": prepared.retrieval_timed_out,
        "hit_count": prepared.retrieval_hit_count,
    }
    provider_trace["stage_metrics"] = {
        "context_latency_ms": prepared.context_latency_ms,
        "retrieval_latency_ms": prepared.retrieval_latency_ms,
        "llm_latency_ms": chain_result.latency_ms,
    }
    if rag_trace:
        provider_trace["rag"] = rag_trace
    if rag_reason:
        provider_trace["rag_error"] = rag_reason

    fallback_reason = chain_result.fallback_reason or chain_result.fail_reason
    return AssistantReply(
        text=chain_result.text,
        chain_name=chain_result.chain_name,
        pipeline=chain_result.pipeline,
        fallback_reason=fallback_reason,
        voice_used=chain_result.voice_used or runtime.tts_voice,
        provider_trace=provider_trace,
    )


def _sanitize_session_title(raw: str) -> str:
    text = re.sub(r"[\r\n\t]+", " ", raw).strip()
    text = re.sub(r"[\"'“”‘’【】\[\]（）()]", "", text)
    text = re.sub(r"\s+", " ", text)
    if not text:
        return DEFAULT_SESSION_TITLE
    return text[:24]


async def summarize_session_title(db: AsyncSession, session: SessionEntity, user_text: str) -> None:
    content = (user_text or "").strip()
    if not content:
        return
    if (session.title or "").strip() not in {"", DEFAULT_SESSION_TITLE, "New Session"}:
        return

    candidate = DEFAULT_SESSION_TITLE
    try:
        runtime = await resolve_session_runtime(db, session.id)
        candidate = await summarize_title_lcel(
            db=db,
            provider_name=runtime.text_llm_provider,
            model_name=runtime.text_llm_model,
            user_text=content,
        )
    except Exception:  # noqa: BLE001
        candidate = DEFAULT_SESSION_TITLE
    session.title = _sanitize_session_title(candidate)


async def sync_memory_after_chat(db: AsyncSession, session_id) -> dict:
    snapshot = await recompute_session_memory(db, session_id)
    return {"short_term": snapshot.short_term, "mid_summary": snapshot.mid_summary, "long_count": snapshot.long_count}
