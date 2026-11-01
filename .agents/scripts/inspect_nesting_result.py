"""Read-only inspection of the supplied Nesting calculation PDF."""
from pathlib import Path

import pymupdf


path = Path("attached_assets/02.0_fuer_Nesting_pritschenplan_a3-27_1793526115412.pdf")
out = Path("/tmp/nesting-result-inspection")
out.mkdir(exist_ok=True)
doc = pymupdf.open(path)
print(f"Pages: {len(doc)}")
for index, page in enumerate(doc):
    text = page.get_text()
    (out / f"page-{index + 1}.txt").write_text(text)
    print(f"\n--- PAGE {index + 1} ---\n{text}")
    page.get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25)).save(out / f"page-{index + 1}.png")
    if "Pritschenplan -" in text:
        page.get_pixmap(
            matrix=pymupdf.Matrix(2, 2), clip=pymupdf.Rect(795, 180, 1190, 720)
        ).save(out / f"page-{index + 1}-ends-top.png")
