"""Read-only probe: lane-width rejection versus the actual support check."""
from pathlib import Path
import sys

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import bvx_auswertung_streamlit as app
from verlade_varianten_flex import _assign_to_stacks


def main():
    book = openpyxl.load_workbook(
        ROOT / "attached_assets/02.0_fuer_Nesting_1793528729994.xlsx",
        read_only=True, data_only=True,
    )
    values = iter(book.active.values)
    headers = next(values)
    source = [dict(zip(headers, row)) for row in values]

    def part(pak):
        row = next(row for row in source if row["Pak"] == pak)
        return pd.Series({
            "Einheit_ID": str(pak), "Typ": "Bauteil", "Anzahl_Bauteile": 1,
            "Bauteile": str(pak), "Länge_mm": row["Länge"] * 1000,
            "Breite_mm": row["Breite"] * 1000, "Höhe_mm": row["Höhe"],
            "Gewicht_kg": row["Gewicht"],
        })

    lower, upper = part(109), part(102)
    deck = pd.Series({
        "Pritsche": "Probe", "Länge_mm": 7600, "Breite_mm": 2450,
        "Max_Höhe_mm": 3000, "Max_Gewicht_kg": 20000,
        "Überhang_vorne_mm": 0, "Überhang_hinten_mm": 0,
        "Kantholz_erste_Lage_mm": 80, "Einlage_allgemein_mm": 0,
        "Einlage_zwischen_Lagen_mm": 40,
        "Breite_Bund_auf_schmal_verhindern": True,
        "Mindest_Stützbreite_%": 35,
        "Auflager_bei_Verladeplanung_beruecksichtigen": True,
    })
    state = app.init_platform_state(deck, 80, 40, 0)
    state["placements"] = [{
        **lower.to_dict(), "Pritsche": "Probe",
        "X_mm": 100, "Y_mm": 1225, "Z_mm": 80,
    }]
    state["total_weight"] = lower["Gewicht_kg"]
    metrics = app._support_metrics_for_candidate(
        state, 100, 1225, 220, upper["Länge_mm"], upper["Breite_mm"]
    )
    accepted = app.can_place_stable(
        state, upper, 100, 1225, 220,
        upper["Länge_mm"], upper["Breite_mm"], upper["Höhe_mm"], upper["Gewicht_kg"],
    )
    narrow_only = _assign_to_stacks(
        [lower, upper], (lower["Breite_mm"],), 7600, 3000, 80,
        0, 40, 0, "hoehe", True, True,
    )
    print(f"Source: {len(source)} elements, total {sum(r['Gewicht'] for r in source):.3f} kg")
    print(f"Lower Pak109: {lower['Länge_mm']:g} x {lower['Breite_mm']:g} mm")
    print(f"Upper Pak102: {upper['Länge_mm']:g} x {upper['Breite_mm']:g} mm")
    print(f"Direct support: {metrics['area_ratio']:.2%}; minimum: 35%")
    print(f"Local placement/support check accepts: {accepted}")
    print(f"Assignment to 538-mm lane rejected: {narrow_only is None}")
    assert accepted and narrow_only is None
    print("This is a local feasibility probe, NOT a complete replanning or structural certification.")


if __name__ == "__main__":
    main()
