from pathlib import Path

import fitz


PDFS = {
    "vorher": Path("attached_assets/28-08-2026-Schulhaus_1994_pritschenplan_a3-2_1788633209333.pdf"),
    "nachher": Path("attached_assets/28-08-2026-Schulhaus_1994_pritschenplan_a3-4_1788637880593.pdf"),
}

output_dir = Path(".agents/outputs/current_pritschenplan")
output_dir.mkdir(parents=True, exist_ok=True)

for label, pdf_path in PDFS.items():
    document = fitz.open(pdf_path)
    for page_number, page in enumerate(document, start=1):
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
        pixmap.save(output_dir / f"{label}-page-{page_number:02d}.png")