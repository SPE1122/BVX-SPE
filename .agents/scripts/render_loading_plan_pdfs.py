from pathlib import Path
import fitz

OUT = Path(".agents/outputs/loading_plan_review")
OUT.mkdir(parents=True, exist_ok=True)

for pdf in [
    Path("attached_assets/12213_Saumacker_-_Brettstapel_pritschenplan_a3-21_1788103297194.pdf"),
    Path("attached_assets/12213_Saumacker_-_Brettstapel_pritschenplan_a3-22_1788103812489.pdf"),
]:
    doc = fitz.open(pdf)
    prefix = pdf.stem
    for index, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        pix.save(OUT / f"{prefix}_page_{index + 1:02d}.png")
        text = page.get_text("text")
        (OUT / f"{prefix}_page_{index + 1:02d}.txt").write_text(text, encoding="utf-8")
    print(pdf.name, "pages=", len(doc))