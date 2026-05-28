import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


BASE = Path(r"D:\AgentLearning\chatBot\output\doc")
DOCX_PATH = max([p for p in BASE.glob("*.docx") if "附件" not in p.name], key=lambda p: p.stat().st_size)
MD_PATH = BASE / "智能语音聊天机器人设计与实现.md"


KEEP_REFERENCE_LINES = [
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
]


REMOVE_INLINE_CITATION_PARAGRAPHS = [195, 201, 205, 223]


def remove_paragraph(paragraph):
    parent = paragraph._element.getparent()
    if parent is not None:
        parent.remove(paragraph._element)


def clear_runs_and_hyperlinks(paragraph):
    for child in list(paragraph._p):
        if child.tag != qn("w:pPr"):
            paragraph._p.remove(child)


def set_plain_text(paragraph, text):
    clear_runs_and_hyperlinks(paragraph)
    run = paragraph.add_run(text)
    run.font.name = "Times New Roman"
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.rFonts
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), "Times New Roman")
    rfonts.set(qn("w:hAnsi"), "Times New Roman")
    rfonts.set(qn("w:eastAsia"), "宋体")


def cleanup_docx():
    doc = Document(str(DOCX_PATH))

    for idx in REMOVE_INLINE_CITATION_PARAGRAPHS:
        p = doc.paragraphs[idx]
        cleaned = re.sub(r"\[(12|13|14|15|16)\]", "", p.text)
        cleaned = re.sub(r"\s+$", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        set_plain_text(p, cleaned)

    ref_title_idx = next(i for i, p in enumerate(doc.paragraphs) if p.text.strip() == "参考文献")
    thanks_idx = next(i for i, p in enumerate(doc.paragraphs) if p.text.strip() == "致  谢")
    ref_paras = doc.paragraphs[ref_title_idx + 1 : thanks_idx]

    for p in ref_paras:
        remove_paragraph(p)

    doc = Document(str(DOCX_PATH))
    ref_title_idx = next(i for i, p in enumerate(doc.paragraphs) if p.text.strip() == "参考文献")
    thanks_para = next(p for p in doc.paragraphs if p.text.strip() == "致  谢")

    from docx.text.paragraph import Paragraph
    from docx.shared import Pt

    def insert_before(anchor, text):
        new_p = OxmlElement("w:p")
        anchor._p.addprevious(new_p)
        para = Paragraph(new_p, anchor._parent)
        para.style = "Normal"
        run = para.add_run(text)
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
        return para

    for line in KEEP_REFERENCE_LINES:
        insert_before(thanks_para, line)

    doc.save(str(DOCX_PATH))


def cleanup_markdown():
    text = MD_PATH.read_text(encoding="utf-8")
    text = text.replace("[12]", "")
    text = text.replace("[13]", "")
    text = text.replace("[14]", "")
    text = text.replace("[15][16]", "")
    text = re.sub(r"\n## 参考文献\s+.*?(\n## 致谢)", "\n## 参考文献\n\n" + "\n\n".join(KEEP_REFERENCE_LINES) + "\n\n" + r"\1", text, flags=re.S)
    MD_PATH.write_text(text, encoding="utf-8")


cleanup_docx()
cleanup_markdown()
print(DOCX_PATH)
print(MD_PATH)
