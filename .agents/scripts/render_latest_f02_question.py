import fitz
src='attached_assets/28-08-2026-Schulhaus_1994_pritschenplan_a3-8_1788714377503.pdf'
doc=fitz.open(src)
page=doc[2]
page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).save('.agents/outputs/pdf_user_latest/f02-question-page3.png')
page.get_pixmap(matrix=fitz.Matrix(3,3),clip=fitz.Rect(0,200,910,840),alpha=False).save('.agents/outputs/pdf_user_latest/f02-question-views.png')
print('rendered',doc.page_count)
