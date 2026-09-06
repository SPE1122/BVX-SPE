import fitz
src='attached_assets/28-08-2026-Schulhaus_1994_pritschenplan_a3-8_1788700091547.pdf'
doc=fitz.open(src)
page=doc[2]
page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).save('.agents/outputs/pdf_user_latest/f02-page3.png')
# Crop the side/front views at higher resolution for clear visual inspection.
page.get_pixmap(matrix=fitz.Matrix(3,3),clip=fitz.Rect(0,210,900,840),alpha=False).save('.agents/outputs/pdf_user_latest/f02-views.png')
print(doc.page_count, page.rect)
