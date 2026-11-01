"""Read-only inspection of the user's latest plan and element 108."""
import io
import json
from pathlib import Path
import zipfile

import pandas as pd
import pymupdf


def main():
    out = Path("/tmp/element-108-review")
    out.mkdir(exist_ok=True)
    pdf = pymupdf.open("attached_assets/02.0_fuer_Nesting_pritschenplan_a3-29_1793532538808.pdf")
    for i in (0, 2):
        pdf[i].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(out / f"page-{i+1}.png")
    with zipfile.ZipFile("attached_assets/BVX_Verladediagnose-2_1793532541747.zip") as archive:
        read = lambda name: pd.read_csv(io.BytesIO(archive.read(name)))
        pos = read("tabellen/positionen_aktuell.csv")
        auto = read("tabellen/positionen_automatik.csv")
        target = pos[pos.Bauteile.astype(str).eq("108")].iloc[0]
        cols = ["Einheit_ID", "Typ", "Bauteile", "X_mm", "Y_mm", "Z_mm",
                "Länge_mm", "Breite_mm", "Höhe_mm", "Gewicht_kg"]
        print("TARGET", target[cols].to_dict())
        print("AUTO", auto[auto.Einheit_ID.eq(target.Einheit_ID)][cols].to_dict("records"))
        group = pos[pos.Pritsche.eq(target.Pritsche)]
        below = group[
            (group.Z_mm + group.Höhe_mm).le(target.Z_mm + .1)
            & (group.X_mm + group.Länge_mm).gt(target.X_mm)
            & group.X_mm.lt(target.X_mm + target.Länge_mm)
            & (group.Y_mm + group.Breite_mm).gt(target.Y_mm)
            & group.Y_mm.lt(target.Y_mm + target.Breite_mm)
        ]
        print("BELOW", below[cols].sort_values("Z_mm").to_dict("records"))
        print("STACK", group[
            (group.Y_mm + group.Breite_mm / 2).lt(1225)
            & group.X_mm.lt(3800)
        ][cols].sort_values("Z_mm").to_dict("records"))
        support = read("pruefungen/auflage_je_einheit.csv")
        print("SUPPORT", support[support.Einheit_ID.eq(target.Einheit_ID)].to_dict("records"))
        manifest = json.loads(archive.read("diagnose.json"))
        print("CHECKS", manifest.get("checks"), "SETTINGS_CHANGED",
              manifest.get("settings_changed_since_calculation"))
        print("SUMMARY", read("tabellen/zusammenfassung.csv").to_dict("records"))


if __name__ == "__main__":
    main()
