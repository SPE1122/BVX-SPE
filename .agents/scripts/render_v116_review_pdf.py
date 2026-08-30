from pathlib import Path

import fitz


pdf_path = Path("attached_assets/12213_Saumacker_-_Brettstapel_pritschenplan_a3-16_1788116459242.pdf")
output_dir = Path(".agents/outputs/v116_review_a3_16")
output_dir.mkdir(parents=True, exist_ok=True)

doc = fitz.open(pdf_path)
print(f"pages={doc.page_count}")
for page_number, page in enumerate(doc, start=1):
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    output_path = output_dir / f"page_{page_number:02d}.png"
    pixmap.save(output_path)
    print(output_path)