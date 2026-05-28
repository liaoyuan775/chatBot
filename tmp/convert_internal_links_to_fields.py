from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree


NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": NS_W}


def w_tag(name: str) -> str:
    return f"{{{NS_W}}}{name}"


docx_path = Path(r"D:\AgentLearning\chatBot\output\doc\智能语音聊天机器人设计与实现.docx")
tmp_path = docx_path.with_name(docx_path.stem + ".tmp.docx")

with ZipFile(docx_path, "r") as zin:
    document_xml = zin.read("word/document.xml")

root = etree.fromstring(document_xml)

changed = 0
for hl in root.xpath(".//w:hyperlink[@w:anchor]", namespaces=NSMAP):
    anchor = hl.get(w_tag("anchor"))
    if not anchor or not anchor.startswith("ref"):
        continue

    # Find visible text and formatting from the first run inside hyperlink.
    first_run = hl.find("w:r", namespaces=NSMAP)
    rpr = None
    display_text = ""
    if first_run is not None:
        rpr = first_run.find("w:rPr", namespaces=NSMAP)
        texts = first_run.findall(".//w:t", namespaces=NSMAP)
        display_text = "".join(t.text or "" for t in texts)

    parent = hl.getparent()
    idx = parent.index(hl)

    def make_run(text=None, fld_type=None, instr=None):
        r = etree.Element(w_tag("r"))
        if rpr is not None:
            r.append(deepcopy(rpr))
        if fld_type is not None:
            fld = etree.Element(w_tag("fldChar"))
            fld.set(w_tag("fldCharType"), fld_type)
            r.append(fld)
        elif instr is not None:
            it = etree.Element(w_tag("instrText"))
            it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            it.text = instr
            r.append(it)
        else:
            t = etree.Element(w_tag("t"))
            t.text = text or ""
            r.append(t)
        return r

    new_nodes = [
        make_run(fld_type="begin"),
        make_run(instr=f' HYPERLINK \\\\l "{anchor}" '),
        make_run(fld_type="separate"),
        make_run(text=display_text),
        make_run(fld_type="end"),
    ]

    parent.remove(hl)
    for offset, node in enumerate(new_nodes):
        parent.insert(idx + offset, node)
    changed += 1

new_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")

with ZipFile(docx_path, "r") as zin, ZipFile(tmp_path, "w", compression=ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        if item.filename == "word/document.xml":
            zout.writestr(item, new_xml)
        else:
            zout.writestr(item, zin.read(item.filename))

tmp_path.replace(docx_path)
print(f"changed={changed}")
print(docx_path)
