from pathlib import Path
import fitz

source = Path("attached_assets/Vorlage_neu_pritschenplan_a3-20_1791052779482.pdf")
output = Path(".agents/outputs/manual_pair_pdf")
output.mkdir(parents=True, exist_ok=True)
doc = fitz.open(source)
print("Pages:", len(doc))
for index, page in enumerate(doc):
    text = page.get_text()
    print(f"Page {index + 1}: {text.splitlines()[0]}")
    if text.startswith("Pritschenplan - F01"):
        print(text[:800])
        path = output / f"page-{index + 1}.png"
        page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4)).save(str(path))
        print("IMAGE:", path)