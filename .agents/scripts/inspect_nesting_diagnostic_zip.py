"""Inspect supplied diagnostics without extracting or modifying their contents."""
from pathlib import Path
import io
import json
import zipfile

import pandas as pd
import pymupdf


def main():
    out = Path("/tmp/nesting-diagnosis-review")
    out.mkdir(exist_ok=True)
    with zipfile.ZipFile("attached_assets/BVX_Verladediagnose_1793530474636.zip") as archive:
        manifest = json.loads(archive.read("diagnose.json"))
        for key in ("calculation_snapshot_available", "settings_changed_since_calculation",
                    "calculation_seconds_total", "variant_decision", "checks"):
            print(key, json.dumps(manifest.get(key), ensure_ascii=False))
        print("CALC_SETTINGS", json.dumps(manifest.get("calculation", {}).get("settings"), ensure_ascii=False))
        for name, run in manifest.get("search_runs", {}).items():
            if run:
                print("RUN", name, "seconds", run.get("elapsed_seconds"), "counts", run.get("counts"))
                samples = run.get("samples", [])
                print("SAMPLE_STAGES", sorted(set(s.get("stage", "") for s in samples)))
                for stage in ("Flexible_Suche", "Flexible_Suche_Ergebnis", "Flexible_Suche_ohne_Ergebnis",
                              "Auflage_oder_Platzierung_abgelehnt"):
                    examples = [s for s in samples if s.get("stage") == stage]
                    print(stage, json.dumps(examples[:2], ensure_ascii=False))

        def table(name):
            return pd.read_csv(io.BytesIO(archive.read(name)))

        for name in ("tabellen/pritschen_verwendet.csv", "tabellen/zusammenfassung.csv",
                     "tabellen/warnungen.csv"):
            print(name, "\n", table(name).to_string(index=False))
        positions = table("tabellen/positionen_aktuell.csv")
        auto = table("tabellen/positionen_automatik.csv")
        support = table("pruefungen/auflage_je_einheit.csv")
        print("POSITION_COLUMNS", positions.columns.tolist())
        print("POSITIONS", len(positions), "AUTO", len(auto))
        for name, group in positions.groupby("Pritsche"):
            real = group[~group.Typ.isin(["Unterbau", "Kantholz", "Einlage", "Bundeinlage", "Lagenholz"])]
            print("\nDECK", name, "real", len(real), "weight", real.Gewicht_kg.sum())
            print("Y range", real.Y_mm.min(), (real.Y_mm + real.Breite_mm).max())
            print(real.groupby(["Y_mm", "Breite_mm"]).agg(
                Anzahl=("Einheit_ID", "count"), Oberkante=("Z_mm", "max"),
                Gewicht=("Gewicht_kg", "sum")
            ).to_string())
            print("HELPERS", group[group.Typ.isin(["Unterbau", "Kantholz", "Einlage", "Bundeinlage", "Lagenholz"])].to_string(index=False))
        print("SUPPORT_MIN", support["Auflage_berechnet_%"].min(),
              "BELOW", support[support.Auflageziel_erreicht == False].to_string(index=False))
        keys = ["Pritsche", "Einheit_ID", "X_mm", "Y_mm", "Z_mm", "Länge_mm", "Breite_mm", "Höhe_mm"]
        print("AUTO_POSITIONS_EQUAL", positions[keys].equals(auto[keys]))
        print("REAL_POSITIONS\n", positions[[c for c in (
            "Pritsche", "Einheit_ID", "Bauteile", "X_mm", "Y_mm", "Z_mm", "Länge_mm", "Breite_mm", "Höhe_mm"
        ) if c in positions]].to_string(index=False))
    doc = pymupdf.open("attached_assets/02.0_fuer_Nesting_pritschenplan_a3-28_1793530404870.pdf")
    old = pymupdf.open("attached_assets/02.0_fuer_Nesting_pritschenplan_a3-27_1793526115412.pdf")
    print("PDF_TEXT_EQUAL", len(doc) == len(old) and all(a.get_text() == b.get_text() for a, b in zip(doc, old)))
    for index in (0, 2):
        doc[index].get_pixmap(
            matrix=pymupdf.Matrix(1.5, 1.5), clip=pymupdf.Rect(795, 180, 1190, 720)
        ).save(out / f"page-{index+1}.png")


if __name__ == "__main__":
    main()
