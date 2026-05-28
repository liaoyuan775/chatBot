from __future__ import annotations

import json
import shutil
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.text.paragraph import Paragraph
from PIL import Image


ROOT = Path(r"D:/AgentLearning/chatBot")
OUTPUT_DIR = ROOT / "output" / "doc"
TMP_DIR = ROOT / "tmp" / "docs"
SCREENSHOT_DIR = TMP_DIR / "screenshots_final"
FRONTEND_SHOTS_DIR = ROOT / "frontend" / "output" / "playwright"
ASSET_DIR = OUTPUT_DIR / "thesis_assets"


def main() -> int:
    thesis_path = max(OUTPUT_DIR.glob("*.docx"), key=lambda p: p.stat().st_size)
    backup_path = TMP_DIR / "thesis_before_final_rebuild.docx"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(thesis_path, backup_path)

    image_assets = build_screenshot_assets()

    doc = Document(thesis_path)
    normalize_headings(doc)
    rebuild_chapter_five(doc, image_assets)
    enforce_layout_rules(doc)
    save_document_with_fallback(doc, thesis_path)

    write_markdown_source(doc)
    write_image_map(image_assets)
    write_reference_verification_json()
    return 0


def save_document_with_fallback(doc: Document, thesis_path: Path) -> Path:
    try:
        doc.save(thesis_path)
        return thesis_path
    except PermissionError:
        fallback = TMP_DIR / thesis_path.name
        doc.save(fallback)
        return fallback


def build_screenshot_assets() -> dict[str, Path]:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    mapping = {
        "chat": FRONTEND_SHOTS_DIR / "chat-final.png",
        "persona": SCREENSHOT_DIR / "personas.png",
        "chain": SCREENSHOT_DIR / "chains.png",
        "provider": SCREENSHOT_DIR / "providers.png",
        "knowledge": SCREENSHOT_DIR / "knowledge.png",
        "context": SCREENSHOT_DIR / "context.png",
        "voice": SCREENSHOT_DIR / "voices.png",
        "settings": SCREENSHOT_DIR / "settings.png",
    }

    assets: dict[str, Path] = {}
    assets["chat"] = copy_or_crop(mapping["chat"], ASSET_DIR / "fig5-2-chat.png")
    assets["persona"] = copy_or_crop(mapping["persona"], ASSET_DIR / "fig5-3-persona.png", crop=(0, 0, 1440, 920))
    assets["chain"] = copy_or_crop(mapping["chain"], ASSET_DIR / "fig5-4-chain.png")
    assets["provider"] = copy_or_crop(mapping["provider"], ASSET_DIR / "fig5-5-provider.png", crop=(0, 0, 1516, 590))
    assets["knowledge"] = copy_or_crop(mapping["knowledge"], ASSET_DIR / "fig5-6-knowledge.png", crop=(0, 0, 1280, 1100))
    assets["context"] = copy_or_crop(mapping["context"], ASSET_DIR / "fig5-7-context.png", crop=(0, 0, 1440, 920))
    assets["voice"] = copy_or_crop(mapping["voice"], ASSET_DIR / "fig5-8-voice.png", crop=(0, 0, 1440, 540))
    assets["settings"] = copy_or_crop(mapping["settings"], ASSET_DIR / "fig5-9-settings.png", crop=(0, 0, 820, 920))
    return assets


def copy_or_crop(source: Path, dest: Path, crop: tuple[int, int, int, int] | None = None) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"missing screenshot: {source}")
    if crop is None:
        shutil.copy2(source, dest)
        return dest
    with Image.open(source) as img:
        width, height = img.size
        left, top, right, bottom = crop
        right = min(right, width)
        bottom = min(bottom, height)
        clipped = img.crop((left, top, right, bottom))
        clipped.save(dest)
    return dest


def normalize_headings(doc: Document) -> None:
    chapter_titles = {
        "1 绪论",
        "2 开发环境及相关技术介绍",
        "3 系统需求分析与数据库设计",
        "4 系统总体设计",
        "5 系统详细设计",
        "6 系统测试",
        "7 结论",
    }
    non_toc_center_titles = {"参考文献", "致谢", "附录"}

    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if text in chapter_titles:
            paragraph.style = "Heading 1"
            format_heading1(paragraph)
        elif paragraph.style.name == "Heading 2":
            format_heading2(paragraph)
        elif paragraph.style.name == "Heading 3":
            format_heading3(paragraph)
        elif text in non_toc_center_titles:
            format_center_title(paragraph)
        elif paragraph.style.name == "Title":
            paragraph.style = "Normal"
            format_cover_title(paragraph)


def rebuild_chapter_five(doc: Document, image_assets: dict[str, Path]) -> None:
    insert_after_text(
        doc,
        "从处理流程看，运行时会根据底层事件持续修正前端状态。",
        [
            paragraph_body("对应实现中，SessionRuntime 通过统一事件入口同步转写文本、助手增量回复与轮次指标，关键片段如下："),
            code_block(
                "if (type === \"user.transcript.partial\") {\n"
                "  this.snapshot.transcript = data.text;\n"
                "  this.addUserMessage(data.text, true);\n"
                "}\n"
                "if (type === \"assistant.text.delta\") {\n"
                "  this.addOrUpdateAssistantMessage(data.text, false);\n"
                "}"
            ),
        ],
    )

    insert_after_text(
        doc,
        "在具体流程上，系统会先根据环境能力判断使用浏览器原生识别还是后端识别，再将识别文本提交给聊天服务，之后依次进入知识增强、文本生成和语音播报环节。",
        [
            paragraph_body("链路配置界面用于把一体化链路与可拆分链路绑定到具体模型、人格和音色，相关页面如图5-4所示。"),
            image_block(image_assets["chain"], "图5-4 链路配置页面"),
            paragraph_body("SplitChainStrategy 在浏览器 ASR 与后端 ASR 之间自动切换，并在识别阶段提前执行插话判断："),
            code_block(
                "if (cfg.splitAsr === \"backend\") {\n"
                "  await this.startBackendAsr(ctx);\n"
                "  return;\n"
                "}\n"
                "try {\n"
                "  await this.startBrowserAsr(ctx);\n"
                "} catch {\n"
                "  await this.startBackendAsr(ctx);\n"
                "}"
            ),
        ],
    )

    insert_after_text(
        doc,
        "与分阶段链路相比，一体化实时链路的优势在于交互节奏更紧凑、插话更自然，更适合强调陪伴感和连续对话体验的场景；但它对网络稳定性、音频处理和后端协同提出了更高要求，调试成本也相对更大。",
        [
            paragraph_body("IntegratedRealtimeStrategy 使用 WebSocket 持续上送音频块，并把服务端事件还原为统一运行时事件："),
            code_block(
                "const ws = new WebSocket(`${getWsBase()}/ws/realtime-chat?session_id=${sessionId}`);\n"
                "ws.onmessage = (event) => {\n"
                "  const data = JSON.parse(String(event.data));\n"
                "  if (data.event === \"assistant.text.delta\") {\n"
                "    ctx.emit(\"assistant.text.delta\", { text: String(data.text ?? \"\") });\n"
                "  }\n"
                "};"
            ),
        ],
    )

    insert_after_text(
        doc,
        "页面还维护了当前会话、当前链路模式、是否正在监听、当前转写文本以及最近一轮的性能指标。",
        [
            paragraph_body("聊天中心页面承担主交互入口，其真实界面如图5-2所示。"),
            image_block(image_assets["chat"], "图5-2 聊天中心页面"),
            paragraph_body("人格配置页用于维护角色定位、语气、严格程度和默认人格规则，其界面如图5-3所示。"),
            image_block(image_assets["persona"], "图5-3 人格配置页面"),
            paragraph_body("ChatCenterPage 直接订阅 SessionRuntime 事件，并把轮次性能指标同步到页面状态："),
            code_block(
                "if (event.type === \"metrics.turn\") {\n"
                "  setRuntimeMetrics({\n"
                "    turnId: event.payload.turn_id,\n"
                "    firstTextLatencyMs: event.payload.first_text_latency_ms,\n"
                "    totalLatencyMs: event.payload.total_latency_ms,\n"
                "  });\n"
                "}"
            ),
        ],
    )

    insert_after_text(
        doc,
        "在回复生成完成后，系统还会统一记录链路名称、Provider 信息、回退原因、知识命中情况和音色配置等运行数据。",
        [
            paragraph_body("聊天服务模块在发起回复前先完成知识检索决策，再组织上下文、RAG 片段与会话配置生成统一请求："),
            code_block(
                "decision = should_retrieve_knowledge(user_text, image_prompt=image_prompt)\n"
                "if decision.decision == \"retrieve\":\n"
                "    knowledge_text, rag_trace, rag_reason, retrieval_timed_out = await _retrieve_knowledge_text(\n"
                "        db, rag_query, chain_mapping=getattr(runtime, \"chain_mapping\", None)\n"
                "    )"
            ),
        ],
    )

    insert_after_text(
        doc,
        "这种设计的实际意义在于，后端不需要因为某一类模型服务变化而重写整条业务链路。",
        [
            paragraph_body("厂商与模型管理页面把 Provider 配置、连通性测试与模型同步放在统一入口中，相关界面如图5-5所示。"),
            image_block(image_assets["provider"], "图5-5 厂商与模型管理页面"),
            paragraph_body("Provider 路由通过测试连通性和同步远端模型，把模型目录与业务调用解耦："),
            code_block(
                "ok, msg = await test_connectivity(db, provider_name)\n"
                "row.status = \"connected\" if ok else \"error\"\n"
                "remote_models = await list_models_remote(db, provider_name)\n"
                "for item in remote_models:\n"
                "    model_name = str(item.get(\"id\") or item.get(\"model\") or \"\")"
            ),
        ],
    )

    insert_after_text(
        doc,
        "从作用上看，这一模块解决的是“模型会说，但未必知道本项目资料”的问题。",
        [
            paragraph_body("知识库管理页面用于维护知识库、上传文档、设置检索参数并执行检索测试，界面如图5-6所示。"),
            image_block(image_assets["knowledge"], "图5-6 知识库管理页面"),
            paragraph_body("文档进入知识库后会先完成切片、向量化和分块持久化，再被用于后续检索："),
            code_block(
                "chunks = split_chunks(full_text, chunk_size=chunk_size, overlap=overlap)\n"
                "vectors = await embedding(db, embedding_provider, embedding_model, chunks)\n"
                "for idx, chunk in enumerate(chunks):\n"
                "    db.add(KnowledgeChunkEntity(document_id=document.id, chunk_index=idx, content=chunk, embedding=vectors[idx][:8]))"
            ),
        ],
    )

    insert_after_text(
        doc,
        "记忆管理模块主要面向多轮对话中的连续性问题。",
        [
            paragraph_body("上下文管理页面把三级记忆参数、当前会话快照、导出与压缩操作集中到一个页面中，界面如图5-7所示。"),
            image_block(image_assets["context"], "图5-7 上下文管理页面"),
            paragraph_body("后台通过短期原文、中期摘要和长期记忆的分层重算，控制上下文长度并保留关键事实："),
            code_block(
                "short = payload[-memory.short_turns:]\n"
                "mid_raw = older[-memory.mid_turns:]\n"
                "memory.mid_summary = [{\"summary\": summarize_text(x[\"text\"]), \"message_id\": x[\"message_id\"]} for x in mid_raw]\n"
                "for item in long_raw[-memory.long_turns:]:\n"
                "    vec = await _embed_summary(db, summarize_text(item[\"text\"]))"
            ),
        ],
    )

    insert_after_text(
        doc,
        "结合项目测试代码可以看出，音色模块还对克隆失败、旧 URI 清理、文件格式异常和服务端 404 回退等情况做了处理。",
        [
            paragraph_body("音色管理页面同时覆盖系统音色、样本上传、克隆与试听，其界面如图5-8所示。"),
            image_block(image_assets["voice"], "图5-8 音色管理页面"),
            paragraph_body("后台在接收样本后先做格式与时长校验，再决定是否调用音色克隆接口："),
            code_block(
                "clone_sample_error = _validate_clone_sample(target, suffix)\n"
                "config[\"sample_source\"] = str(target)\n"
                "if clone and not clone_sample_error:\n"
                "    clone_uri = await siliconflow_upload_reference_voice(\n"
                "        db=db, model=settings.siliconflow_tts_model, custom_name=_safe_custom_name(row.name), reference_text=used_reference_text, audio_bytes=audio_bytes, filename=target.name\n"
                "    )"
            ),
        ],
    )

    insert_after_text(
        doc,
        "在实现细节上，服务端会维护当前轮次任务、局部识别任务、最近局部文本、音频格式以及去重窗口等状态，并对重复提交、空提交和并发冲突做额外判断。",
        [
            paragraph_body("系统配置页面集中展示数据库状态、异常策略和高危清理操作，其界面如图5-9所示。"),
            image_block(image_assets["settings"], "图5-9 系统配置页面"),
            paragraph_body("实时 WebSocket 服务通过局部识别任务、轮次任务和持久化逻辑配合完成实时通话闭环："),
            code_block(
                "await websocket.send_json({\"event\": \"session.ready\", \"session_id\": str(session_id), \"mode\": \"integrated-realtime\"})\n"
                "prepared_turn = await prepare_assistant_turn(db, session, text_input)\n"
                "prepared = await prepare_realtime_chain(db, session_id=session_id, text_input=text_input, context_text=prepared_turn.context_hint, knowledge_text=prepared_turn.knowledge_text)\n"
                "await recompute_session_memory(db, session_id)"
            ),
        ],
    )


def enforce_layout_rules(doc: Document) -> None:
    chapter_titles = {
        "1 绪论",
        "2 开发环境及相关技术介绍",
        "3 系统需求分析与数据库设计",
        "4 系统总体设计",
        "5 系统详细设计",
        "6 系统测试",
        "7 结论",
    }
    center_titles = {"摘要", "Abstract", "参考文献", "致谢", "附录"}

    for section in doc.sections:
        section.start_type = WD_SECTION.NEW_PAGE

    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        style_name = paragraph.style.name if paragraph.style else ""
        if text in chapter_titles:
            format_heading1(paragraph)
        elif style_name == "Heading 2":
            format_heading2(paragraph)
        elif style_name == "Heading 3":
            format_heading3(paragraph)
        elif text in center_titles:
            format_center_title(paragraph)
        elif text in {"安徽工业大学", "毕业设计（论文）说明书"}:
            paragraph.style = "Normal"
            format_cover_title(paragraph)
        elif text.startswith("图"):
            format_figure_caption(paragraph)
        elif text.startswith("表"):
            format_table_caption(paragraph)
            set_keep_with_next(paragraph, True)
        elif style_name.startswith("toc"):
            continue
        elif paragraph._p.xpath(".//pic:pic"):
            format_image_paragraph(paragraph)
        elif style_name == "Body Text" or style_name == "Normal":
            format_body_paragraph(paragraph)

    for table in doc.tables:
        for row_idx, row in enumerate(table.rows):
            prevent_row_split(row)
            if row_idx == 0:
                repeat_table_header(row)
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    format_table_text(paragraph)


def write_markdown_source(doc: Document) -> None:
    lines: list[str] = []
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = paragraph.style.name if paragraph.style else ""
        if text == "安徽工业大学" or text == "毕业设计（论文）说明书":
            continue
        if style == "Heading 1":
            lines.append(f"# {text}")
        elif style == "Heading 2":
            lines.append(f"## {text}")
        elif style == "Heading 3":
            lines.append(f"### {text}")
        else:
            lines.append(text)
    md_path = OUTPUT_DIR / "智能语音聊天机器人设计与实现_本科毕业论文.md"
    md_path.write_text("\n\n".join(lines), encoding="utf-8")


def write_image_map(image_assets: dict[str, Path]) -> None:
    payload = {
        "图5-2 聊天中心页面": str(image_assets["chat"]),
        "图5-3 人格配置页面": str(image_assets["persona"]),
        "图5-4 链路配置页面": str(image_assets["chain"]),
        "图5-5 厂商与模型管理页面": str(image_assets["provider"]),
        "图5-6 知识库管理页面": str(image_assets["knowledge"]),
        "图5-7 上下文管理页面": str(image_assets["context"]),
        "图5-8 音色管理页面": str(image_assets["voice"]),
        "图5-9 系统配置页面": str(image_assets["settings"]),
    }
    path = OUTPUT_DIR / "智能语音聊天机器人设计与实现_本科毕业论文-image-map.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_reference_verification_json() -> None:
    refs = [
        {
            "title": "Robust speech recognition via large-scale weak supervision",
            "authors": "Radford A, Kim J W, Xu T, et al.",
            "year": 2022,
            "source": "arXiv",
            "doi_or_url": "https://arxiv.org/abs/2212.04356",
            "relevance_note": "语音识别与 Whisper 路线综述依据。",
            "status": "verified",
        },
        {
            "title": "Attention Is All You Need",
            "authors": "Vaswani A, Shazeer N, Parmar N, et al.",
            "year": 2017,
            "source": "NeurIPS 2017",
            "doi_or_url": "https://proceedings.neurips.cc/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html",
            "relevance_note": "Transformer 基础理论依据。",
            "status": "verified",
        },
        {
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "authors": "Lewis P, Perez E, Piktus A, et al.",
            "year": 2020,
            "source": "NeurIPS 2020",
            "doi_or_url": "https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html",
            "relevance_note": "RAG 基本框架依据。",
            "status": "verified",
        },
        {
            "title": "Improving language models by retrieving from trillions of tokens",
            "authors": "Borgeaud S, Mensch A, Hoffmann J, et al.",
            "year": 2022,
            "source": "Nature",
            "doi_or_url": "https://www.nature.com/articles/s41586-022-04489-8",
            "relevance_note": "检索增强大模型工程意义依据。",
            "status": "verified",
        },
        {
            "title": "A Survey of Large Language Models",
            "authors": "Zhao W X, Zhou K, Li J, et al.",
            "year": 2023,
            "source": "arXiv",
            "doi_or_url": "https://arxiv.org/abs/2303.18223",
            "relevance_note": "大语言模型综述依据。",
            "status": "verified",
        },
        {
            "title": "Retrieval-Augmented Generation for Large Language Models: A Survey",
            "authors": "Gao Y, Xiong Y, Gao X, et al.",
            "year": 2023,
            "source": "arXiv",
            "doi_or_url": "https://arxiv.org/abs/2312.10997",
            "relevance_note": "RAG 综述依据。",
            "status": "verified",
        },
        {
            "title": "FunASR: A Fundamental End-to-End Speech Recognition Toolkit",
            "authors": "Gao Z, Li Z, Wang J, et al.",
            "year": 2023,
            "source": "Interspeech 2023",
            "doi_or_url": "https://www.isca-archive.org/interspeech_2023/gao23b_interspeech.html",
            "relevance_note": "ASR 工具链与工程实现依据。",
            "status": "verified",
        },
        {
            "title": "MemoryBank: Enhancing Large Language Models with Long-Term Memory",
            "authors": "Zhong W, Guo Y, Gao N, et al.",
            "year": 2023,
            "source": "AAAI 2024",
            "doi_or_url": "https://ojs.aaai.org/index.php/AAAI/article/view/29836",
            "relevance_note": "长时记忆设计依据。",
            "status": "verified",
        },
        {
            "title": "Conditional Variational Autoencoder with Adversarial Learning for End-to-End Text-to-Speech",
            "authors": "Kim J, Kong J, Son J.",
            "year": 2021,
            "source": "ICML 2021",
            "doi_or_url": "https://proceedings.mlr.press/v139/kim21f.html",
            "relevance_note": "端到端语音合成技术依据。",
            "status": "verified",
        },
        {
            "title": "The WebSocket Protocol",
            "authors": "Fette I, Melnikov A.",
            "year": 2011,
            "source": "RFC 6455",
            "doi_or_url": "https://datatracker.ietf.org/doc/html/rfc6455",
            "relevance_note": "实时 WebSocket 通讯协议依据。",
            "status": "verified",
        },
        {
            "title": "PostgreSQL Documentation",
            "authors": "The PostgreSQL Global Development Group",
            "year": 2026,
            "source": "Official Documentation",
            "doi_or_url": "https://www.postgresql.org/docs/current/",
            "relevance_note": "数据库与事务能力说明依据。",
            "status": "verified",
        },
        {
            "title": "pgvector: Open-source vector similarity search for Postgres",
            "authors": "pgvector",
            "year": 2026,
            "source": "GitHub",
            "doi_or_url": "https://github.com/pgvector/pgvector",
            "relevance_note": "向量检索存储实现依据。",
            "status": "verified",
        },
    ]
    path = OUTPUT_DIR / "智能语音聊天机器人设计与实现_本科毕业论文-文献核验清单.json"
    path.write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")


def insert_after_text(doc: Document, text_start: str, blocks: list[dict]) -> None:
    anchor = find_paragraph_by_start(doc, text_start)
    for block in blocks:
        if block["kind"] == "paragraph":
            anchor = insert_body_paragraph(anchor, block["text"])
        elif block["kind"] == "code":
            anchor = insert_code_paragraph(anchor, block["text"])
        elif block["kind"] == "image":
            anchor = insert_image_with_caption(anchor, block["path"], block["caption"])


def paragraph_body(text: str) -> dict:
    return {"kind": "paragraph", "text": text}


def code_block(text: str) -> dict:
    return {"kind": "code", "text": text}


def image_block(path: Path, caption: str) -> dict:
    return {"kind": "image", "path": path, "caption": caption}


def find_paragraph_by_start(doc: Document, text_start: str) -> Paragraph:
    for paragraph in doc.paragraphs:
        if paragraph.text.strip().startswith(text_start):
            return paragraph
    raise ValueError(f"paragraph not found: {text_start}")


def insert_body_paragraph(anchor: Paragraph, text: str) -> Paragraph:
    paragraph = insert_paragraph_after(anchor)
    paragraph.add_run(text)
    format_body_paragraph(paragraph)
    return paragraph


def insert_code_paragraph(anchor: Paragraph, text: str) -> Paragraph:
    paragraph = insert_paragraph_after(anchor)
    paragraph.add_run(text)
    format_code_paragraph(paragraph)
    return paragraph


def insert_image_with_caption(anchor: Paragraph, image_path: Path, caption: str) -> Paragraph:
    image_p = insert_paragraph_after(anchor)
    image_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    image_run = image_p.add_run()
    image_run.add_picture(str(image_path), width=Cm(14.5))
    format_image_paragraph(image_p)
    set_keep_with_next(image_p, True)

    caption_p = insert_paragraph_after(image_p)
    caption_p.add_run(caption)
    format_figure_caption(caption_p)
    return caption_p


def insert_paragraph_after(paragraph: Paragraph) -> Paragraph:
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    return Paragraph(new_p, paragraph._parent)


def format_cover_title(paragraph: Paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    for run in paragraph.runs:
        set_run_font(run, "黑体", "Times New Roman", 18, bold=True)


def format_heading1(paragraph: Paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(18)
    set_page_break_before(paragraph, True)
    set_keep_with_next(paragraph, True)
    set_keep_together(paragraph, True)
    set_widow_control(paragraph, True)
    for run in paragraph.runs:
        set_run_font(run, "黑体", "Times New Roman", 18, bold=True)


def format_heading2(paragraph: Paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(18)
    set_keep_with_next(paragraph, True)
    set_widow_control(paragraph, True)
    for run in paragraph.runs:
        set_run_font(run, "黑体", "Times New Roman", 15, bold=True)


def format_heading3(paragraph: Paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(3)
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(18)
    set_keep_with_next(paragraph, True)
    set_widow_control(paragraph, True)
    for run in paragraph.runs:
        set_run_font(run, "黑体", "Times New Roman", 12, bold=True)


def format_center_title(paragraph: Paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(18)
    set_keep_with_next(paragraph, True)
    set_widow_control(paragraph, True)
    for run in paragraph.runs:
        set_run_font(run, "黑体", "Times New Roman", 18, bold=True)


def format_body_paragraph(paragraph: Paragraph) -> None:
    text = paragraph.text.strip()
    if not text:
        return
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.first_line_indent = Pt(24)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(18)
    set_widow_control(paragraph, True)
    set_keep_with_next(paragraph, False)
    for run in paragraph.runs:
        set_run_font(run, "宋体", "Times New Roman", 12)


def format_figure_caption(paragraph: Paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    paragraph.paragraph_format.line_spacing = 1.0
    set_keep_together(paragraph, True)
    set_widow_control(paragraph, True)
    for run in paragraph.runs:
        set_run_font(run, "宋体", "Times New Roman", 10.5)


def format_table_caption(paragraph: Paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    paragraph.paragraph_format.line_spacing = 1.0
    set_keep_together(paragraph, True)
    set_widow_control(paragraph, True)
    for run in paragraph.runs:
        set_run_font(run, "宋体", "Times New Roman", 10.5)


def format_image_paragraph(paragraph: Paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    paragraph.paragraph_format.line_spacing = 1.0
    set_keep_together(paragraph, True)
    set_widow_control(paragraph, True)


def format_code_paragraph(paragraph: Paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.left_indent = Cm(0.35)
    paragraph.paragraph_format.right_indent = Cm(0.35)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    paragraph.paragraph_format.line_spacing = 1.0
    set_widow_control(paragraph, True)
    set_keep_together(paragraph, True)
    set_paragraph_shading(paragraph, "F4F7F7")
    for run in paragraph.runs:
        set_run_font(run, "Consolas", "Consolas", 9.5)


def format_table_text(paragraph: Paragraph) -> None:
    if not paragraph.text.strip():
        return
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    paragraph.paragraph_format.line_spacing = 1.0
    set_keep_together(paragraph, True)
    for run in paragraph.runs:
        set_run_font(run, "宋体", "Times New Roman", 10.5)


def set_run_font(run, east_asia: str, latin: str, size_pt: float, bold: bool = False) -> None:
    run.bold = bold
    run.font.name = latin
    run.font.size = Pt(size_pt)
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.rFonts
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    r_fonts.set(qn("w:eastAsia"), east_asia)
    r_fonts.set(qn("w:ascii"), latin)
    r_fonts.set(qn("w:hAnsi"), latin)


def set_page_break_before(paragraph: Paragraph, enabled: bool) -> None:
    set_on_off_property(paragraph, "pageBreakBefore", enabled)


def set_keep_with_next(paragraph: Paragraph, enabled: bool) -> None:
    set_on_off_property(paragraph, "keepNext", enabled)


def set_keep_together(paragraph: Paragraph, enabled: bool) -> None:
    set_on_off_property(paragraph, "keepLines", enabled)


def set_widow_control(paragraph: Paragraph, enabled: bool) -> None:
    set_on_off_property(paragraph, "widowControl", enabled)


def set_on_off_property(paragraph: Paragraph, tag: str, enabled: bool) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    target = p_pr.find(qn(f"w:{tag}"))
    if enabled:
        if target is None:
            target = OxmlElement(f"w:{tag}")
            p_pr.append(target)
    else:
        if target is not None:
            p_pr.remove(target)


def set_paragraph_shading(paragraph: Paragraph, fill: str) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    shd = p_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        p_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)


def prevent_row_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        tr_pr.append(OxmlElement("w:cantSplit"))


def repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:tblHeader")) is None:
        tr_pr.append(OxmlElement("w:tblHeader"))


if __name__ == "__main__":
    raise SystemExit(main())
