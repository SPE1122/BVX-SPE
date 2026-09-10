import fitz
from pathlib import Path
src=Path('attached_assets/Verlad_pritschenplan_a3-4_1789065230287.pdf')
out=Path('.agents/outputs/verlad_review')
doc=fitz.open(src)
print('pages',doc.page_count)
for i,page in enumerate(doc):
    text=page.get_text()
    print('\n--- PAGE',i+1,'---')
    for line in text.splitlines():
        if line.startswith(('Pritschenplan -','Länge Ladung:','Breite Ladung:','Höhe Ladung:','Überhang')):
            print(line)
    page.get_pixmap(matrix=fitz.Matrix(2,2), alpha=False).save(out/f'page-{i+1}.png')
