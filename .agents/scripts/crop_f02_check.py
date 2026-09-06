import pymupdf
from pathlib import Path
src = 'attached_assets/28-08-2026-Schulhaus_1994_pritschenplan_a3-8_1788718923993.pdf'
out = Path('.agents/outputs/pdf_check_1788718923993')
doc = pymupdf.open(src)
page = doc[2]
# Page 3: rear/front cross-sections and side profiles
clips = {
    'f02_rear_section.png': pymupdf.Rect(680, 130, 910, 390),
    'f02_side_profiles.png': pymupdf.Rect(10, 120, 670, 650),
}
for name, clip in clips.items():
    pix = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=clip, alpha=False)
    pix.save(out / name)
    print(out / name)
