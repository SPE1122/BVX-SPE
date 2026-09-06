import fitz
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
pdf=Path('attached_assets/28-08-2026-Schulhaus_1994_pritschenplan_a3-7_Kopie_1788692802494.pdf')
out=Path('.agents/outputs/pdf_result')
doc=fitz.open(pdf)
thumbs=[]
for i,page in enumerate(doc):
    pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
    path=out/f'page-{i+1}.png'; pix.save(path)
    im=Image.open(path).convert('RGB'); im.thumbnail((700,500))
    canvas=Image.new('RGB',(720,540),'white'); canvas.paste(im,((720-im.width)//2,25))
    ImageDraw.Draw(canvas).text((12,8),f'Seite {i+1}',fill='black')
    thumbs.append(canvas)
sheet=Image.new('RGB',(1440,1620),(220,220,220))
for i,im in enumerate(thumbs): sheet.paste(im,((i%2)*720,(i//2)*540))
sheet.save(out/'contact-sheet.jpg',quality=90)
print('pages',len(doc))
for i,p in enumerate(doc):
    txt=' '.join(p.get_text().split())
    print(i+1,txt[:300])
