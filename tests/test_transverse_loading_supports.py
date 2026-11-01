import io
import unittest
import zipfile
from pathlib import Path

import pandas as pd
import pymupdf

import bvx_auswertung_streamlit as app
import verlade_varianten_flex as flex
from test_flexible_loading_integration import make_platform


class TransverseSupportTests(unittest.TestCase):
    def state(self):
        deck = make_platform().iloc[0].copy()
        deck["Pritsche"] = "T"
        deck["Auflager_bei_Verladeplanung_beruecksichtigen"] = True
        state = app.init_platform_state(deck, 80, 40, 0)
        state["allow_transverse_supports"] = True
        state["placements"] = [
            {"Pritsche": "T", "Einheit_ID": "base", "Typ": "Bauteil",
             "Bauteile": "base", "X_mm": 100., "Y_mm": 1225., "Z_mm": 80.,
             "Länge_mm": 3556., "Breite_mm": 1200., "Höhe_mm": 140., "Gewicht_kg": 100.},
            {"Pritsche": "T", "Einheit_ID": "narrow", "Typ": "Bauteil",
             "Bauteile": "narrow", "X_mm": 100., "Y_mm": 1225., "Z_mm": 220.,
             "Länge_mm": 3556., "Breite_mm": 331., "Höhe_mm": 140., "Gewicht_kg": 100.},
        ]
        unit = pd.Series({
            "Einheit_ID": "wide", "Typ": "Bund", "Bauteile": "A|B",
            "Anzahl_Bauteile": 2, "Bauteile_Liste": "A|B",
            "Länge_mm": 3556., "Breite_mm": 1200., "Höhe_mm": 140., "Gewicht_kg": 100.,
        })
        return deck, state, unit

    def test_wide_on_narrow_gets_grounded_side_timber(self):
        deck, state, unit = self.state()
        original = pd.DataFrame(state["placements"]).copy(deep=True)
        metrics = app._support_metrics_for_candidate(state, 100, 1225, 360, 3556, 1200)
        self.assertLess(metrics["area_ratio"], .35)
        self.assertTrue(app.can_place_stable(state, unit, 100, 1225, 360, 3556, 1200, 140, 100))
        pd.testing.assert_frame_equal(original, pd.DataFrame(state["placements"]))
        supports = app._planned_support_rows_for_candidate(state, unit, 100, 1225, 360, 3556, 1200)
        self.assertTrue(supports)
        for support in supports:
            self.assertEqual(support["Z_mm"], 220)
            self.assertGreaterEqual(support["Y_mm"], 1556)
            self.assertEqual(support["Auflager_fuer"], "wide")
            self.assertTrue(support["Einheit_ID"].startswith("UBY_"))
        app.commit_place(state, unit, 100, 1225, 360, 3556, 1200, 140, 0, "test")
        placed = pd.DataFrame(state["placements"])
        decks = pd.DataFrame([deck])
        self.assertTrue(app._pinned_manual_support_chain_issues(placed, decks).empty)
        self.assertTrue(app._pinned_manual_physical_conflicts(placed).empty)
        self.assertTrue(app.find_geometry_conflicts(placed, decks).empty)
        self.assertEqual(placed.iloc[-1]["Bauteile_Liste"], "A|B")
        self.assertEqual(placed.iloc[-1]["Typ"], "Bund")

    def test_legacy_and_disabled_supports_remain_unchanged(self):
        _, state, unit = self.state()
        state["allow_transverse_supports"] = False
        self.assertFalse(app.can_place_stable(state, unit, 100, 1225, 360, 3556, 1200, 140, 100))
        state["allow_transverse_supports"] = True
        state["consider_generated_supports"] = False
        self.assertFalse(app.can_place_stable(state, unit, 100, 1225, 360, 3556, 1200, 140, 100))

    def test_transverse_timber_cannot_create_longitudinal_support_in_air(self):
        _, state, unit = self.state()
        state["placements"] = []
        result = app._planned_support_rows_for_candidate(
            state, unit, 7500, 1225, 360, 3556, 1200
        )
        self.assertIsNone(result)

    def test_side_support_cannot_penetrate_existing_load(self):
        _, state, unit = self.state()
        # All side space is blocked above the prospective upper part's underside.
        state["placements"].append({
            "Typ": "Bauteil", "Einheit_ID": "obstacle", "X_mm": 100,
            "Y_mm": 1556, "Z_mm": 220, "Länge_mm": 3556,
            "Breite_mm": 869, "Höhe_mm": 300, "Gewicht_kg": 100,
        })
        self.assertIsNone(app._planned_support_rows_for_candidate(
            state, unit, 100, 1225, 360, 3556, 1200))

    def test_required_support_note_is_in_pdf(self):
        deck, state, unit = self.state()
        app.commit_place(state, unit, 100, 1225, 360, 3556, 1200, 140, 0, "test")
        placed = pd.DataFrame(state["placements"])
        pdf = app.create_loading_pdf(
            placed, pd.DataFrame([deck]),
            pd.DataFrame(columns=["Pritsche"]), pd.DataFrame(),
        )
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        self.assertIn("Seitlicher Ausgleich erforderlich", doc[0].get_text())

    def test_real_blocks_keep_all_parts_and_improve_both_sides(self):
        path = Path("attached_assets/BVX_Verladediagnose_1793530474636.zip")
        if not path.is_file():
            self.skipTest("User reference fixture unavailable")
        import sys
        sys.path.insert(0, ".agents/scripts")
        from verify_nesting_flexible_widths import calculate
        with zipfile.ZipFile(path) as archive:
            read = lambda name: pd.read_csv(io.BytesIO(archive.read(name)))
            old = read("tabellen/positionen_automatik.csv")
            units = read("tabellen/verladeeinheiten.csv")
            decks = read("tabellen/pritschen_verwendet.csv")
        for _, deck in decks.iterrows():
            with self.subTest(deck=deck.Pritsche):
                previous = old[old.Pritsche.eq(deck.Pritsche)]
                block = units[units.Einheit_ID.isin(previous.Einheit_ID)].sort_values(
                    "Einheit_ID", ascending=False, kind="stable"
                )
                result, _, _ = calculate(block, deck)
                real = result[result.Typ.ne("Unterbau")]
                self.assertEqual(sorted(real.Einheit_ID), sorted(previous.Einheit_ID))
                self.assertLess(flex.seitenbalance_kennzahl(result, deck), 50)
                self.assertLess(app._loading_layout_quality(result, deck)["sp_mm"], 1)
                self.assertLess((real.Z_mm + real.Höhe_mm).max(),
                                (previous.Z_mm + previous.Höhe_mm).max())
                # Each physical stack keeps the incoming element order.
                for y_side in (0, 1):
                    group = real[
                        ((real.Y_mm + real.Breite_mm / 2) >= float(deck.Breite_mm) / 2) == bool(y_side)
                    ]
                    for _, lower in group.iterrows():
                        for _, upper in group.iterrows():
                            x_overlap = min(lower.X_mm + lower.Länge_mm, upper.X_mm + upper.Länge_mm) - max(lower.X_mm, upper.X_mm)
                            if x_overlap > 1 and lower.Z_mm < upper.Z_mm:
                                self.assertGreater(lower.Einheit_ID, upper.Einheit_ID)


if __name__ == "__main__":
    unittest.main()
