"""Render the uploaded reference and a display-only fixture from its BVX."""
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import bvx_auswertung_streamlit as app


def main():
    output = Path("/tmp/bundle-pdf-verification")
    output.mkdir(exist_ok=True)
    source = ROOT / "attached_assets/1054300_MFH,_Hinterried,_Churwalden_Brettstapel_1792317773976.bvx"
    reference = ROOT / "attached_assets/1054300_MFH,_Hinterried,_Churwalden_Brettstapel_pritschenplan__1792317765068.pdf"
    parts = [
        node.attrib for node in ET.parse(source).iter()
        if "DimensionX" in node.attrib and "DimensionY" in node.attrib and "DimensionZ" in node.attrib
    ]
    assert len(parts) == 27, len(parts)
    sizes = [(float(p["DimensionX"]), float(p["DimensionZ"]), float(p["DimensionY"])) for p in parts]
    ranges = [(0, 3), (3, 6), (6, 9), (9, 13), (13, 17), (17, 20), (20, 23), (23, 27)]
    rows = {}
    # Reproduce the two stack memberships only for visual verification. This is
    # not a planner rerun or a replacement for the user's stored loading plan.
    for y, stack in ((0, [7, 6, 4, 2]), (1200, [8, 5, 3, 1])):
        z = 80
        for number in stack:
            start, end = ranges[number - 1]
            members = sizes[start:end]
            length, width = max(p[0] for p in members), max(p[1] for p in members)
            height = sum(p[2] for p in members)
            labels = "|".join(f"DE{i+1:02d}" for i in range(start, end))
            rows[number] = {
                "Pritsche": "F01 Deck", "Einheit_ID": f"B{number}", "Typ": "Bund",
                "Anzahl_Bauteile": len(members), "Bauteile": labels,
                "Bauteile_Liste": labels, "Ansicht_Liste": labels, "Ansicht_Label": f"B{number}",
                "Einzellängen_mm": "|".join(str(p[0]) for p in members),
                "Einzelbreiten_mm": "|".join(str(p[1]) for p in members),
                "Einzelhöhen_mm": "|".join(str(p[2]) for p in members),
                "Einlage_allgemein_mm": 0, "Bundeinlage_mm": 80,
                "X_mm": (7600 - length) / 2, "Y_mm": y, "Z_mm": z,
                "Länge_mm": length, "Breite_mm": width, "Höhe_mm": height,
                "Gewicht_kg": sum(l * w * h / 1e9 * 450 for l, w, h in members),
                "Drehung": 0,
            }
            z += height + 80
    placements = pd.DataFrame([rows[n] for n in sorted(rows)])
    platforms = pd.DataFrame([{
        "Pritsche": "F01 Deck", "Fuhre_Nr": 1, "Fuhrenoption": "Standard",
        "Pritschenname": "Deck", "Länge_mm": 7600, "Breite_mm": 2450,
        "Max_Höhe_mm": 3000, "Max_Gewicht_kg": 15000,
        "Eigengewicht_Pritsche_kg": 1000, "Überhang_vorne_mm": 0,
        "Überhang_hinten_mm": 0, "Kantholz_erste_Lage_mm": 80,
        "Einlage_zwischen_Lagen_mm": 80, "Einlage_allgemein_mm": 0,
    }])
    snapshot = placements.copy(deep=True)
    pdf = app.create_loading_pdf(
        placements, platforms, pd.DataFrame(columns=["Pritsche"]), pd.DataFrame(),
        project_name="Darstellungsprüfung - BVX-Abmessungen",
    )
    pd.testing.assert_frame_equal(snapshot, placements)
    (output / "display-check.pdf").write_bytes(pdf)
    for name, doc in (("reference", pymupdf.open(reference)), ("updated", pymupdf.open(stream=pdf, filetype="pdf"))):
        doc[0].get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(output / f"{name}-page1.png")
        doc[0].get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), clip=pymupdf.Rect(795, 180, 1028, 715)).save(output / f"{name}-ends.png")
        if name == "updated":
            assert "Einlage 80 mm" in doc[1].get_text()
            print(doc[1].get_text()[-350:])
    print(f"Rendered reference and updated fixture to {output}; plan unchanged.")


if __name__ == "__main__":
    main()
