from pathlib import Path
from zipfile import ZipFile
import shutil

from PIL import Image, ImageDraw, ImageFont


BASE = Path(r"D:\AgentLearning\chatBot\output\doc")
ASSETS = BASE / "thesis_assets"
DOCX = max(BASE.glob("*.docx"), key=lambda p: p.stat().st_size)
TMP_DIR = Path(r"D:\AgentLearning\chatBot\tmp")


def load_font(size: int, bold: bool = False):
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


FONT_BIG = load_font(30, bold=True)
FONT_MED = load_font(22, bold=True)
FONT_SMALL = load_font(18, bold=False)
FONT_TINY = load_font(15, bold=False)


def center_text(draw, xy_center, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    x = xy_center[0] - (bbox[2] - bbox[0]) / 2
    y = xy_center[1] - (bbox[3] - bbox[1]) / 2
    draw.text((x, y), text, font=font, fill=fill)


def multiline_center_text(draw, box, text, font, fill, spacing=4):
    lines = text.split("\n")
    heights = []
    widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        widths.append(bbox[2] - bbox[0])
        heights.append(bbox[3] - bbox[1])
    total_height = sum(heights) + spacing * (len(lines) - 1)
    y = box[1] + (box[3] - box[1] - total_height) / 2
    for i, line in enumerate(lines):
        w = widths[i]
        h = heights[i]
        x = box[0] + (box[2] - box[0] - w) / 2
        draw.text((x, y), line, font=font, fill=fill)
        y += h + spacing


def annotate_realtime_interrupt():
    path = ASSETS / "fig5-10-realtime-interrupt-scene.png"
    backup = ASSETS / "fig5-10-realtime-interrupt-scene.original.png"
    if not backup.exists():
        shutil.copy2(path, backup)

    img = Image.open(backup).convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    title_color = "#1565D8"
    accent_orange = "#FF7A00"
    sub_color = "#4E5E7A"

    centers_x = [155, 456, 762, 1075, 1380, 1684]
    top_titles = [
        "1  User Speaks",
        "2  AI Listening",
        "3  AI Responding",
        "4  User Interrupts",
        "5  System Reprocesses",
        "6  New Turn Response",
    ]
    for cx, text in zip(centers_x, top_titles):
        color = accent_orange if text.startswith("4") else title_color
        center_text(draw, (cx, 34), text, FONT_MED, color)

    bottom_titles = [
        ("User Turn", title_color),
        ("Listening", "#13B7C8"),
        ("AI Turn", title_color),
        ("Interrupt", accent_orange),
        ("Reprocess", "#13B7C8"),
        ("New Turn", title_color),
    ]
    for idx, (title, color) in enumerate(bottom_titles):
        cx = centers_x[idx]
        center_text(draw, (cx, 732), title, FONT_SMALL, color)

    inner_labels = [
        ((155, 328), "User Input (Speech)", title_color),
        ((455, 329), "AI Waiting for Input", "#13B7C8"),
        ((760, 329), "AI Reply in Progress", title_color),
        ((1073, 329), "Current Reply Interrupted", accent_orange),
        ((1380, 329), "Recognize and Replan", "#13B7C8"),
        ((1684, 329), "New Reply Returned", title_color),
    ]
    for (cx, cy), text, color in inner_labels:
        center_text(draw, (cx, cy), text, FONT_SMALL, color)

    img.convert("RGB").save(path, quality=95)


def annotate_rag_workflow():
    path = ASSETS / "fig4-4-rag-workflow.png"
    backup = ASSETS / "fig4-4-rag-workflow.original.png"
    if not backup.exists():
        shutil.copy2(path, backup)

    img = Image.open(backup).convert("RGBA")
    draw = ImageDraw.Draw(img)

    blue = "#1C69D8"
    teal = "#12AAB5"
    orange = "#F59A23"
    purple = "#7A63D1"
    dark = "#4A566E"

    labels = [
        ("User Question", blue),
        ("Retrieval\nDecision Gate", orange),
        ("Document Chunk\nRetrieval", blue),
        ("Vector Search\n(Embedding)", teal),
        ("Keyword Matching\n(BM25)", teal),
        ("Reranking\n(Top-K)", blue),
        ("Context\nAssembly", blue),
        ("LLM Response\nGeneration", purple),
        ("Final Answer\nOutput", blue),
    ]
    centers = [113, 292, 494, 688, 885, 1083, 1290, 1497, 1698]
    for (text, color), cx in zip(labels, centers):
        multiline_center_text(draw, (cx - 82, 704, cx + 82, 765), text, FONT_SMALL, color, spacing=2)

    img.convert("RGB").save(path, quality=95)


def replace_docx_media():
    replacements = {
        "word/media/image6.png": ASSETS / "fig4-4-rag-workflow.png",
        "word/media/image15.png": ASSETS / "fig5-10-realtime-interrupt-scene.png",
    }
    temp_docx = TMP_DIR / "thesis_images_replaced.docx"
    with ZipFile(DOCX, "r") as zin, ZipFile(temp_docx, "w") as zout:
        for item in zin.infolist():
            if item.filename in replacements:
                zout.writestr(item, replacements[item.filename].read_bytes())
            else:
                zout.writestr(item, zin.read(item.filename))
    shutil.move(str(temp_docx), str(DOCX))


annotate_realtime_interrupt()
annotate_rag_workflow()
replace_docx_media()
print(DOCX)
