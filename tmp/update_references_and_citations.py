import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.text.paragraph import Paragraph


BASE = Path(r"D:\AgentLearning\chatBot\output\doc")
DOCX_PATH = max([p for p in BASE.glob("*.docx") if "附件" not in p.name], key=lambda p: p.stat().st_size)
MD_PATH = BASE / "智能语音聊天机器人设计与实现.md"


REFERENCE_LINES = [
    "[1] Radford A, Kim J W, Xu T, et al. Robust speech recognition via large-scale weak supervision[J]. Proceedings of the 40th International Conference on Machine Learning, 2023, 202(1): 28492-28518.",
    "[2] 张俊林. 大语言模型：回顾、现状与未来[J]. 计算机研究与发展, 2024, 61(5): 1025-1045.",
    "[3] 李理. 向量数据库在大模型检索增强生成中的应用研究[J]. 计算机应用, 2025, 45(1): 12-20.",
    "[4] 冯珺, 孙飞, 郭宇航, 等. 大语言模型推理研究综述[J]. 软件学报, 2024, 35(11): 5013-5045.",
    "[5] Zhao W X, Zhou K, Li J, et al. A survey of large language models[J]. AI Open, 2024, 5(1): 1-45.",
    "[6] Kim J, Kong J, Ju J. Conditional variational autoencoder with adversarial learning for end-to-end text-to-speech[J]. Advances in Neural Information Processing Systems, 2021, 34(1): 11227-11237.",
    "[7] Zhong W, Guo Y, Gao N, et al. MemoryBank: Enhancing Large Language Models with Long-Term Memory[J]. Proceedings of the AAAI Conference on Artificial Intelligence, 2024, 38(17): 19724-19731.",
    "[8] Gao Y, Xiong Y, Gao X, et al. Retrieval-augmented generation for large language models: A survey[J]. Frontiers of Computer Science, 2025, 19(2): 192301-192320.",
    "[9] Sarikaya R. The evolution of natural language contextual AI[J]. IEEE Signal Processing Magazine, 2025, 42(1): 44-55.",
    "[10] Gao Z, Zhang S, McLoughlin I, et al. FunASR: A Fundamental End-to-End Speech Recognition Toolkit[J]. IEEE International Conference on Acoustics, Speech and Signal Processing, 2024, 1(1): 11001-11005.",
    "[11] Huo J, et al. Mastering memory: A survey of long-term memory for large language models[J]. Journal of Computer Science and Technology, 2025, 40(1): 15-42.",
    "[12] FastAPI. FastAPI documentation[EB/OL]. [2026-05-20]. https://fastapi.tiangolo.com/.",
    "[13] React. React documentation[EB/OL]. [2026-05-20]. https://react.dev/.",
    "[14] Fette I, Melnikov A. The WebSocket protocol[S]. RFC 6455, 2011.",
    "[15] The PostgreSQL Global Development Group. PostgreSQL documentation[EB/OL]. [2026-05-20]. https://www.postgresql.org/docs/current/.",
    "[16] pgvector. pgvector: Open-source vector similarity search for Postgres[EB/OL]. [2026-05-20]. https://github.com/pgvector/pgvector.",
]


CITATION_MAP = {
    148: [1, 10],
    150: [2, 4, 5],
    152: [3, 8],
    154: [7, 11],
    155: [6, 9],
    195: [12],
    201: [13],
    205: [14],
    211: [3, 8],
    217: [1, 10],
    219: [6, 9],
    223: [15, 16],
}


MD_REPLACEMENTS = {
    "Whisper 一类模型依靠大规模弱监督数据提升了跨语言泛化能力，FunASR、SenseVoice 等工程方案则更强调低延迟处理和中文场景下的部署灵活性。对于语音聊天机器人而言，识别模块除了准确率之外，还要兼顾流式能力、噪声环境表现以及与后续对话链路的衔接效率。":
        "Whisper 一类模型依靠大规模弱监督数据提升了跨语言泛化能力，FunASR、SenseVoice 等工程方案则更强调低延迟处理和中文场景下的部署灵活性。对于语音聊天机器人而言，识别模块除了准确率之外，还要兼顾流式能力、噪声环境表现以及与后续对话链路的衔接效率。[1][10]",
    "在对话大模型方面，相关研究已经证明大语言模型在问答、摘要、推理和多轮对话任务上具有较强能力。但把这类模型直接用于业务系统仍然会遇到一些现实问题，例如知识边界不稳定、输出内容难以约束、长上下文成本较高等。因此，工程系统通常不会只停留在“接入一个模型”，而是需要结合提示词、上下文组织和外部知识进行二次设计。":
        "在对话大模型方面，相关研究已经证明大语言模型在问答、摘要、推理和多轮对话任务上具有较强能力。但把这类模型直接用于业务系统仍然会遇到一些现实问题，例如知识边界不稳定、输出内容难以约束、长上下文成本较高等。因此，工程系统通常不会只停留在“接入一个模型”，而是需要结合提示词、上下文组织和外部知识进行二次设计。[2][4][5]",
    "在检索增强方面，RAG 已成为提升回答可信度和场景适配性的常见方案。其基本思路是先从知识库中检索与问题相关的片段，再将结果与用户问题共同组织到提示上下文中，从而减少模型在专业资料问答中的脱离题意现象。对于需要结合项目文档、课程资料和私有知识的智能助手来说，这种方法具有较强实用性。":
        "在检索增强方面，RAG 已成为提升回答可信度和场景适配性的常见方案。其基本思路是先从知识库中检索与问题相关的片段，再将结果与用户问题共同组织到提示上下文中，从而减少模型在专业资料问答中的脱离题意现象。对于需要结合项目文档、课程资料和私有知识的智能助手来说，这种方法具有较强实用性。[3][8]",
    "在记忆机制方面，越来越多的研究开始关注多轮对话中的上下文延续问题。若每一轮都简单拼接全部历史消息，系统既会面临上下文膨胀，也会增加无关信息干扰。因此，短期记忆、中期摘要和长期记忆的分层组织方式逐渐成为改进连续对话体验的重要方向。":
        "在记忆机制方面，越来越多的研究开始关注多轮对话中的上下文延续问题。若每一轮都简单拼接全部历史消息，系统既会面临上下文膨胀，也会增加无关信息干扰。因此，短期记忆、中期摘要和长期记忆的分层组织方式逐渐成为改进连续对话体验的重要方向。[7][11]",
    "在语音合成方面，当前 TTS 技术已经不再局限于基础播报，而是逐步向更自然的韵律控制、情感表达和音色定制发展。尤其是在音色克隆和零样本语音合成能力出现之后，语音机器人在“说得出来”之外，也开始追求“说得更像特定角色”。这使个性化语音交互成为可实现的工程能力，而不只是概念展示。":
        "在语音合成方面，当前 TTS 技术已经不再局限于基础播报，而是逐步向更自然的韵律控制、情感表达和音色定制发展。尤其是在音色克隆和零样本语音合成能力出现之后，语音机器人在“说得出来”之外，也开始追求“说得更像特定角色”。这使个性化语音交互成为可实现的工程能力，而不只是概念展示。[6][9]",
    "FastAPI 是基于 Python 的现代异步 Web 框架，具有开发效率高、异步支持完善、与 Pydantic 结合紧密等优点。对于本课题而言，FastAPI 主要承担三个方面的任务：一是提供会话、消息、知识库、音色和配置管理等 REST API；二是提供实时语音对话所需的 WebSocket 接口；三是作为各类模型调用与数据库访问的统一编排层。":
        "FastAPI 是基于 Python 的现代异步 Web 框架，具有开发效率高、异步支持完善、与 Pydantic 结合紧密等优点。对于本课题而言，FastAPI 主要承担三个方面的任务：一是提供会话、消息、知识库、音色和配置管理等 REST API；二是提供实时语音对话所需的 WebSocket 接口；三是作为各类模型调用与数据库访问的统一编排层。[12]",
    "前端采用 React + Vite + TypeScript 构建。React 便于组织复杂交互界面，TypeScript 能提升工程可维护性和类型安全，Vite 则使开发与构建速度更快。系统前端不仅负责传统聊天界面，还承担语音采集、实时事件监听、消息状态更新、链路切换、指标展示等复杂交互任务，因此需要一套统一的运行时抽象对这些行为进行管理。":
        "前端采用 React + Vite + TypeScript 构建。React 便于组织复杂交互界面，TypeScript 能提升工程可维护性和类型安全，Vite 则使开发与构建速度更快。系统前端不仅负责传统聊天界面，还承担语音采集、实时事件监听、消息状态更新、链路切换、指标展示等复杂交互任务，因此需要一套统一的运行时抽象对这些行为进行管理。[13]",
    "由于实时语音交互需要客户端与服务端之间维持持续双向通信，因此系统采用 WebSocket 作为语音链路的核心通信方式。相较于传统的 HTTP 请求响应模式，WebSocket 更适合传输音频片段、局部识别结果、增量文本和音频分片等连续事件。":
        "由于实时语音交互需要客户端与服务端之间维持持续双向通信，因此系统采用 WebSocket 作为语音链路的核心通信方式。相较于传统的 HTTP 请求响应模式，WebSocket 更适合传输音频片段、局部识别结果、增量文本和音频分片等连续事件。[14]",
    "检索增强生成技术是本系统提升回答准确性的重要手段。系统在用户提出问题后，先从知识库中执行切片检索，再将召回结果整理为知识上下文，与对话历史和人格提示词一起注入模型上下文中生成回答。这样做的优势在于，模型不再完全依赖参数记忆，而是可以结合项目文档、课程资料或业务知识库完成更具依据的回答。":
        "检索增强生成技术是本系统提升回答准确性的重要手段。系统在用户提出问题后，先从知识库中执行切片检索，再将召回结果整理为知识上下文，与对话历史和人格提示词一起注入模型上下文中生成回答。这样做的优势在于，模型不再完全依赖参数记忆，而是可以结合项目文档、课程资料或业务知识库完成更具依据的回答。[3][8]",
    "在语音识别方面，系统支持浏览器语音识别与后端识别两种路径。浏览器识别适合快速启动与低成本场景，后端识别适合更稳定的服务端处理与统一管理。通过“双路径识别”设计，系统在不同浏览器能力和不同部署环境下都能保持较好的兼容性。":
        "在语音识别方面，系统支持浏览器语音识别与后端识别两种路径。浏览器识别适合快速启动与低成本场景，后端识别适合更稳定的服务端处理与统一管理。通过“双路径识别”设计，系统在不同浏览器能力和不同部署环境下都能保持较好的兼容性。[1][10]",
    "在语音合成方面，系统不仅支持基础的语音播报，还支持音色样本上传、自动转写参考文本、克隆音色并生成自定义语音配置。这使系统不仅能“说出来”，还能在一定程度上“按指定角色说出来”，增强了系统的交互自然性和个性化程度。":
        "在语音合成方面，系统不仅支持基础的语音播报，还支持音色样本上传、自动转写参考文本、克隆音色并生成自定义语音配置。这使系统不仅能“说出来”，还能在一定程度上“按指定角色说出来”，增强了系统的交互自然性和个性化程度。[6][9]",
    "为了便于系统部署与环境复现，本项目同时引入了 Docker 与数据库迁移机制。前后端均提供独立 Dockerfile，后端通过 Alembic 管理数据库结构演进，保证在不同开发阶段能够持续更新表结构而不破坏既有数据。对于本科毕业设计而言，这一部分虽然不是算法创新点，但它能显著提高系统的可移植性、可部署性和工程完整性，也体现了现代软件项目开发中的规范化思路。":
        "为了便于系统部署与环境复现，本项目同时引入了 Docker 与数据库迁移机制。前后端均提供独立 Dockerfile，后端通过 Alembic 管理数据库结构演进，保证在不同开发阶段能够持续更新表结构而不破坏既有数据。对于本科毕业设计而言，这一部分虽然不是算法创新点，但它能显著提高系统的可移植性、可部署性和工程完整性，也体现了现代软件项目开发中的规范化思路。[15][16]",
}


def remove_paragraph(paragraph: Paragraph) -> None:
    element = paragraph._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def insert_paragraph_before(paragraph: Paragraph, text: str = "", style_name: str | None = None) -> Paragraph:
    new_p = OxmlElement("w:p")
    paragraph._p.addprevious(new_p)
    new_para = Paragraph(new_p, paragraph._parent)
    if style_name:
        new_para.style = style_name
    if text:
        run = new_para.add_run(text)
        run.font.name = "Times New Roman"
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.rFonts
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:ascii"), "Times New Roman")
        rfonts.set(qn("w:hAnsi"), "Times New Roman")
        rfonts.set(qn("w:eastAsia"), "宋体")
        run.font.size = Pt(12)
    return new_para


def ensure_bookmark(paragraph: Paragraph, name: str, bookmark_id: int) -> None:
    for child in paragraph._p:
        if child.tag == qn("w:bookmarkStart") and child.get(qn("w:name")) == name:
            return
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def append_hyperlink(paragraph: Paragraph, text: str, anchor: str) -> None:
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), anchor)

    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "000000")
    rpr.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "none")
    rpr.append(underline)

    rfonts = OxmlElement("w:rFonts")
    rfonts.set(qn("w:ascii"), "Times New Roman")
    rfonts.set(qn("w:hAnsi"), "Times New Roman")
    rfonts.set(qn("w:eastAsia"), "Times New Roman")
    rpr.append(rfonts)

    vert = OxmlElement("w:vertAlign")
    vert.set(qn("w:val"), "superscript")
    rpr.append(vert)

    size = OxmlElement("w:sz")
    size.set(qn("w:val"), "20")
    rpr.append(size)
    size_cs = OxmlElement("w:szCs")
    size_cs.set(qn("w:val"), "20")
    rpr.append(size_cs)

    run.append(rpr)
    text_el = OxmlElement("w:t")
    text_el.text = text
    run.append(text_el)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def append_citations(paragraph: Paragraph, refs: list[int]) -> None:
    if any(f"[{n}]" in paragraph.text for n in refs):
        return
    paragraph.add_run(" ")
    for num in refs:
        append_hyperlink(paragraph, f"[{num}]", f"ref{num}")


def set_reference_format(paragraph: Paragraph) -> None:
    fmt = paragraph.paragraph_format
    fmt.left_indent = Cm(0)
    fmt.first_line_indent = Cm(0)
    fmt.hanging_indent = Cm(0)
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    fmt.line_spacing = 1.5


def update_docx() -> None:
    doc = Document(str(DOCX_PATH))

    # Add inline citations.
    for idx, refs in CITATION_MAP.items():
        append_citations(doc.paragraphs[idx], refs)

    # Replace reference list.
    ref_title_idx = next(i for i, p in enumerate(doc.paragraphs) if p.text.strip() == "参考文献")
    thanks_idx = next(i for i, p in enumerate(doc.paragraphs) if p.text.strip() == "致  谢")

    # Remove old reference paragraphs between title and acknowledgements.
    for _ in range(thanks_idx - ref_title_idx - 1):
        remove_paragraph(doc.paragraphs[ref_title_idx + 1])

    # Recompute anchor after deletion.
    thanks_para = next(p for p in doc.paragraphs if p.text.strip() == "致  谢")
    inserted = []
    for line in REFERENCE_LINES:
        p = insert_paragraph_before(thanks_para, line, "Normal")
        set_reference_format(p)
        inserted.append(p)

    for idx, p in enumerate(inserted, start=1):
        ensure_bookmark(p, f"ref{idx}", 200 + idx)

    doc.save(str(DOCX_PATH))


def update_markdown() -> None:
    text = MD_PATH.read_text(encoding="utf-8")
    for old, new in MD_REPLACEMENTS.items():
        text = text.replace(old, new)

    ref_block = "## 参考文献\n\n" + "\n\n".join(REFERENCE_LINES) + "\n\n"
    text = re.sub(r"## 参考文献\s+.*?(\n## 致谢)", ref_block + r"\1", text, flags=re.S)
    MD_PATH.write_text(text, encoding="utf-8")


update_docx()
update_markdown()
print(DOCX_PATH)
print(MD_PATH)
