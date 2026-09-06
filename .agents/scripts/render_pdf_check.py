import fitz
from pathlib import Path
src = Path('attached_assets/28-08-2026-Schulhaus_1994_pritschenplan_a3-8_1788718923993.pdf')
out = Path('.agents/outputs/pdf_check_1788718923993')
doc = fitz.open(src)
for i, page in enumerate(doc):
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    pix.save(out / f'page-{i+1}.png')
    text = page.get_text()
    print(f'--- PAGE {i+1} ---')
    print(text[:1200])
