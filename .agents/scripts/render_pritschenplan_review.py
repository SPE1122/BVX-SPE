from pathlib import Path

import fitz
from PIL import Image, ImageDraw


PDF = Path("attached_assets/28-08-2026-Schulhaus_1994_pritschenplan_a3-5_Kopie_2_1788679033432.pdf")
OUT = Path(".agents/outputs/pritschenplan_review")
OUT.mkdir(parents=True, exist_ok=True)

doc = fitz.open(PDF)
selected = []

for page_no, page in enumerate(doc):
    text = page.get_text()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), f"Seite {page_no + 1}")
    if "Pritschenplan -" in text or "Ladeplan BSD -" in text:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        path = OUT / f"page_{page_no + 1:02d}.png"
        pix.save(path)
        selected.append((page_no + 1, first_line, path))

thumbs = []
for page_no, title, path in selected:
    image = Image.open(path).convert("RGB")
    image.thumbnail((900, 620))
    canvas = Image.new("RGB", (920, 680), "white")
    canvas.paste(image, ((920 - image.width) // 2, 45))
    draw = ImageDraw.Draw(canvas)
    draw.text((15, 12), f"PDF-Seite {page_no}: {title}", fill="black")
    thumbs.append(canvas)

if thumbs:
    contact = Image.new("RGB", (920, 680 * len(thumbs)), "#dddddd")
    for i, thumb in enumerate(thumbs):
        contact.paste(thumb, (0, i * 680))
    contact.save(OUT / "contact_sheet.png")

print(f"pages={doc.page_count}")
for page_no, title, path in selected:
    print(f"{page_no}: {title} -> {path}")