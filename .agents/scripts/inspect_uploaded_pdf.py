from pathlib import Path
import fitz
from PIL import Image, ImageDraw


pdf_path = Path("attached_assets/12213_Saumacker_-_Brettstapel_pritschenplan_a3-15_1788010421502.pdf")
output_dir = Path(".agents/outputs/pdf_inspection")
output_dir.mkdir(parents=True, exist_ok=True)

doc = fitz.open(pdf_path)
print(f"pages={doc.page_count}")
print(f"metadata={doc.metadata}")

for page_number, page in enumerate(doc, start=1):
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    image_path = output_dir / f"page-{page_number:02d}.png"
    pix.save(image_path)
    text = page.get_text("text")
    print(
        f"page={page_number} size={page.rect.width:.1f}x{page.rect.height:.1f} "
        f"images={len(page.get_images(full=True))} text_chars={len(text)} "
        f"render={image_path}"
    )
    print(text[:4000].replace("\x00", " "))

rendered_images = [
    Image.open(output_dir / f"page-{page_number:02d}.png").convert("RGB")
    for page_number in range(1, doc.page_count + 1)
]
thumb_width = 360
thumbs = []
for page_number, image in enumerate(rendered_images, start=1):
    thumb_height = round(image.height * thumb_width / image.width)
    thumb = image.resize((thumb_width, thumb_height))
    canvas = Image.new("RGB", (thumb_width, thumb_height + 28), "white")
    canvas.paste(thumb, (0, 28))
    ImageDraw.Draw(canvas).text((8, 7), f"Seite {page_number}", fill="black")
    thumbs.append(canvas)

columns = 2
rows = (len(thumbs) + columns - 1) // columns
contact = Image.new("RGB", (columns * thumb_width, rows * thumbs[0].height), "#dddddd")
for index, thumb in enumerate(thumbs):
    contact.paste(thumb, ((index % columns) * thumb_width, (index // columns) * thumb.height))
contact.save(output_dir / "contact-sheet.png")
print(f"contact_sheet={output_dir / 'contact-sheet.png'}")