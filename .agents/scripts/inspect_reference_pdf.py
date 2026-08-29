import fitz
from pathlib import Path

pdf_path = Path("attached_assets/12213_Saumacker_-_Brettstapel_pritschenplan_a3-29_1788035834726.pdf")
out_dir = Path(".agents/outputs/reference_pdf")
out_dir.mkdir(parents=True, exist_ok=True)

doc = fitz.open(pdf_path)
print("pages:", doc.page_count)
print("metadata:", doc.metadata)
for index, page in enumerate(doc):
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    output = out_dir / f"page_{index + 1:02d}.png"
    pix.save(output)
    text = page.get_text("text").replace("\n", " | ")
    print(f"page {index + 1}: {text[:500]}")