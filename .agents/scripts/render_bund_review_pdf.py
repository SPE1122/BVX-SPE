from pathlib import Path
import fitz


PDF_PATH = Path("attached_assets/12213_Saumacker_-_Brettstapel_pritschenplan_a3-30_1788201598012.pdf")
OUTPUT_DIR = Path(".agents/outputs/bund_review_a3_30")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(PDF_PATH)
    print(f"pages={len(doc)}")
    for page_number, page in enumerate(doc, start=1):
        text = page.get_text("text")
        (OUTPUT_DIR / f"page_{page_number:02d}.txt").write_text(text, encoding="utf-8")
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        pix.save(OUTPUT_DIR / f"page_{page_number:02d}.png")
        if page_number in {1, 5, 7, 13}:
            crop = page.get_pixmap(
                matrix=fitz.Matrix(4, 4),
                clip=fitz.Rect(0, 130, page.rect.width, 620),
                alpha=False,
            )
            crop.save(OUTPUT_DIR / f"page_{page_number:02d}_views_zoom.png")
        print(f"page={page_number} chars={len(text)} images={len(page.get_images(full=True))}")


if __name__ == "__main__":
    main()