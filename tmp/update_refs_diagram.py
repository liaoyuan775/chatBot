# -*- coding: utf-8 -*-
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING

path = r"D:/AgentLearning/chatBot/tmp/refs_and_diagram.docx"
doc = Document(path)


def set_run_font(run, name='宋体', size=12, bold=False):
    run.font.name = name
    run._element.rPr.rFonts.set(qn('w:eastAsia'), name)
    run.font.size = Pt(size)
    run.bold = bold


def format_body(para):
    pf = para.paragraph_format
    pf.first_line_indent = Cm(0.74)
    pf.left_indent = None
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(18)
    para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for run in para.runs:
        set_run_font(run, '宋体', 12, False)


def format_caption(para):
    pf = para.paragraph_format
    pf.first_line_indent = None
    pf.left_indent = None
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(18)
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in para.runs:
        set_run_font(run, '宋体', 10.5, False)


def format_ref_heading(para):
    pf = para.paragraph_format
    pf.first_line_indent = None
    pf.left_indent = None
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(18)
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in para.runs:
        set_run_font(run, '黑体', 18, True)


def format_ref_item(para):
    pf = para.paragraph_format
    pf.left_indent = Cm(0.74)
    pf.first_line_indent = Cm(-0.74)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(18)
    para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for run in para.runs:
        set_run_font(run, '宋体', 12, False)


def find_para(prefix):
    for p in doc.paragraphs:
        if p.text.strip().startswith(prefix):
            return p
    raise ValueError(prefix)


def insert_paragraph_before(paragraph, text, caption=False):
    new_p = OxmlElement('w:p')
    paragraph._p.addprevious(new_p)
    para = Paragraph(new_p, paragraph._parent)
    para.add_run(text)
    format_caption(para) if caption else format_body(para)
    return para


def insert_paragraph_after(paragraph, text, caption=False):
    new_p = OxmlElement('w:p')
    paragraph._p.addnext(new_p)
    para = Paragraph(new_p, paragraph._parent)
    para.add_run(text)
    format_caption(para) if caption else format_body(para)
    return para

# 1) Insert function module diagram and adjust figure numbering in chapter 4
p_41 = find_para('4.1 总体架构设计思路')
lead = insert_paragraph_after(p_41, '为了更具体地说明各主要功能在系统中的组织关系，本文进一步给出系统功能模块划分，如图4-2所示。该图强调的是面向使用场景的功能构成，而不是底层实现层次。')
img_p = insert_paragraph_after(lead, '')
img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
img_p.add_run().add_picture(r'D:/AgentLearning/chatBot/output/doc/thesis_diagrams/system_function_modules.png', width=Cm(15.0))
cap_p = insert_paragraph_after(img_p, '图4-2 系统功能模块图', caption=True)
explain = insert_paragraph_after(cap_p, '从图4-2可以看出，聊天中心、语音输入、实时通话、知识库管理以及人格与音色管理等前端功能，最终都通过统一会话运行时与后端服务进行协同。这种组织方式使系统既能保持功能边界清晰，又能避免不同页面各自维护一套独立的交互逻辑。')

# Renumber old figure 4-2 to 4-3 and update reference sentence
old_ref = find_para('如图4-2所示，系统并没有把语音交互理解为单一路径')
old_ref.text = old_ref.text.replace('如图4-2所示', '如图4-3所示')
format_body(old_ref)
old_cap = find_para('图4-2 语音交互流程图')
old_cap.text = '图4-3 语音交互流程图'
format_caption(old_cap)

# 2) Rewrite references in stricter GB/T-like style
ref_heading = find_para('参考文献')
format_ref_heading(ref_heading)
refs = [
    '[1] Radford A, Kim J W, Xu T, et al. Robust speech recognition via large-scale weak supervision[EB/OL]. (2022-12-06)[2026-04-21]. https://arxiv.org/abs/2212.04356.',
    '[2] 张俊林. 大语言模型：回顾、现状与未来[J]. 计算机研究与发展, 2024, 61(5): 1025-1045.',
    '[3] 冯珺, 孙飞, 郭宇航, 等. 大语言模型推理研究综述[J]. 软件学报, 2024, 35(11): 5013-5045.',
    '[4] Gao Z, Li Z, Wang J, et al. FunASR: A fundamental end-to-end speech recognition toolkit[C]//Proc. Interspeech 2023. 2023: 1593-1597.',
    '[5] Zhong W, Guo Y, Gao N, et al. MemoryBank: Enhancing large language models with long-term memory[C]//Proceedings of the AAAI Conference on Artificial Intelligence. 2024, 38(17): 19724-19731.',
    '[6] Gao Y, Xiong Y, Gao X, et al. Retrieval-augmented generation for large language models: A survey[EB/OL]. (2023-12-18)[2026-04-21]. https://arxiv.org/abs/2312.10997.',
    '[7] Zhao W X, Zhou K, Li J, et al. A survey of large language models[EB/OL]. (2023-03-31)[2026-04-21]. https://arxiv.org/abs/2303.18223.',
    '[8] Kim J, Kong J, Son J. Conditional variational autoencoder with adversarial learning for end-to-end text-to-speech[C]//Proceedings of the 38th International Conference on Machine Learning. 2021, 139: 5530-5540.',
    '[9] Lewis P, Perez E, Piktus A, et al. Retrieval-augmented generation for knowledge-intensive NLP tasks[C]//Advances in Neural Information Processing Systems. 2020, 33: 9459-9474.',
    '[10] Borgeaud S, Mensch A, Hoffmann J, et al. Improving language models by retrieving from trillions of tokens[J]. Nature, 2022, 601: 67-72.'
]
# Gather current reference item paragraphs
ref_paras = []
collect = False
for p in doc.paragraphs:
    t = p.text.strip()
    if t == '参考文献':
        collect = True
        continue
    if collect and t == '致谢':
        break
    if collect and t:
        ref_paras.append(p)

for i, text in enumerate(refs):
    if i < len(ref_paras):
        ref_paras[i].text = text
        format_ref_item(ref_paras[i])
# blank any extras before 致谢
for p in ref_paras[len(refs):]:
    p.text = ''

# save
for p in doc.paragraphs:
    if p.text.strip() == '图4-2 系统功能模块图' or p.text.strip() == '图4-3 语音交互流程图':
        format_caption(p)

doc.save(path)
print('saved')
