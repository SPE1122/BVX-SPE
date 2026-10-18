import unittest
from unittest.mock import patch

import pandas as pd
import pymupdf

import bvx_auswertung_streamlit as app
from pdf_bundle_display import bundle_spacer_pdf_note, expand_bundle_display_rows


def bundle(**changes):
    row = {
        "Pritsche": "F01 Deck", "Einheit_ID": "B1", "Typ": "Bund",
        "Anzahl_Bauteile": 3, "Bauteile": "DE01|DE02|DE03",
        "Bauteile_Liste": "DE01|DE02|DE03", "Ansicht_Label": "B1",
        "Ansicht_Liste": "DE01|DE02|DE03",
        "Einzellängen_mm": "4302|4824|4500",
        "Einzelbreiten_mm": "1200|703.4|786",
        "Einzelhöhen_mm": "120|120|120",
        "Einlage_allgemein_mm": 0, "Bundeinlage_mm": 80,
        "X_mm": 1300, "Y_mm": 0, "Z_mm": 80,
        "Länge_mm": 4824, "Breite_mm": 1200, "Höhe_mm": 360,
        "Drehung": 0, "Gewicht_kg": 500,
    }
    return dict(row, **changes)


def sample_plan():
    rows = pd.DataFrame([
        bundle(),
        bundle(Einheit_ID="B2", Z_mm=520),
    ])
    platforms = pd.DataFrame([{
        "Pritsche": "F01 Deck", "Fuhre_Nr": 1, "Fuhrenoption": "Standard",
        "Pritschenname": "Deck", "Länge_mm": 7600, "Breite_mm": 2450,
        "Max_Höhe_mm": 3000, "Max_Gewicht_kg": 10000,
        "Eigengewicht_Pritsche_kg": 1000, "Überhang_vorne_mm": 0,
        "Überhang_hinten_mm": 0, "Kantholz_erste_Lage_mm": 80,
        "Einlage_zwischen_Lagen_mm": 80, "Einlage_allgemein_mm": 0,
    }])
    return rows, platforms


class BundleDisplayTests(unittest.TestCase):
    def test_member_sizes_order_and_source_unchanged(self):
        rows = pd.DataFrame([bundle()])
        original = rows.copy(deep=True)
        result = expand_bundle_display_rows(rows)
        self.assertEqual(result.Ansicht_Label.tolist(), ["DE03", "DE02", "DE01"])
        self.assertEqual(result.Z_mm.tolist(), [80, 200, 320])
        self.assertEqual(result.Länge_mm.tolist(), [4500, 4824, 4302])
        self.assertEqual(result.Breite_mm.tolist(), [786, 703.4, 1200])
        self.assertEqual(result.X_mm.tolist(), [1300] * 3)
        self.assertEqual(result.Y_mm.tolist(), [0] * 3)
        pd.testing.assert_frame_equal(original, rows)

    def test_no_inter_bundle_spacers_inside_bundle(self):
        result = expand_bundle_display_rows(pd.DataFrame([bundle()]))
        self.assertEqual(len(result), 3)
        self.assertEqual(result.Z_mm.tolist(), [80, 200, 320])

    def test_existing_internal_spacing_only(self):
        rows = pd.DataFrame([bundle(Einlage_allgemein_mm=20, Höhe_mm=400)])
        result = expand_bundle_display_rows(rows)
        self.assertEqual(result.Z_mm.tolist(), [80, 220, 360])

    def test_upright_bundle_swaps_y_z_only_for_display(self):
        rows = pd.DataFrame([bundle(Drehung=90, Breite_mm=360, Höhe_mm=1200)])
        result = expand_bundle_display_rows(rows)
        self.assertEqual(result.Y_mm.tolist(), [0, 120, 240])
        self.assertEqual(result.Z_mm.tolist(), [80] * 3)
        self.assertEqual(result.Breite_mm.tolist(), [120] * 3)
        self.assertEqual(result.Höhe_mm.tolist(), [786, 703.4, 1200])

    def test_missing_invalid_or_inconsistent_metadata_keeps_envelope(self):
        for changes in (
            {"Einzellängen_mm": ""}, {"Einzelhöhen_mm": "120|nan|120"},
            {"Einzelbreiten_mm": "1200|703.4"}, {"Höhe_mm": 999},
            {"Drehung": 45}, {"Anzahl_Bauteile": float("nan")},
        ):
            with self.subTest(changes=changes):
                rows = pd.DataFrame([bundle(**changes)])
                pd.testing.assert_frame_equal(expand_bundle_display_rows(rows), rows)

    def test_empty_and_nonbundle_rows_unchanged(self):
        rows = pd.DataFrame([bundle(Typ="Bauteil")])
        pd.testing.assert_frame_equal(expand_bundle_display_rows(rows), rows)
        self.assertTrue(expand_bundle_display_rows(rows.iloc[:0]).empty)

    def test_spacers_created_once_from_bundles_not_members(self):
        rows, platforms = sample_plan()
        result = expand_bundle_display_rows(
            app._pdf_add_visible_spacer_rows(rows, platforms.iloc[0], "back")
        )
        self.assertEqual(result.Typ.tolist().count("Bauteil"), 6)
        self.assertEqual(result.Typ.tolist().count("Bundeinlage"), 1)
        self.assertEqual(result.Typ.tolist().count("Kantholz"), 1)
        spacer = result[result.Typ == "Bundeinlage"].iloc[0]
        self.assertEqual((spacer.Z_mm, spacer.Höhe_mm), (440, 80))

    def test_both_top_views_have_no_spacer_layers(self):
        rows, platforms = sample_plan()
        for view in ("top", "top_rotated"):
            pd.testing.assert_frame_equal(
                app._pdf_add_visible_spacer_rows(rows, platforms.iloc[0], view), rows
            )

    def test_footer_uses_actual_configuration(self):
        self.assertIn("80 mm", bundle_spacer_pdf_note(80))
        self.assertIn("60.5 mm", bundle_spacer_pdf_note(60.5))
        self.assertIn("Keine Bundeinlage", bundle_spacer_pdf_note(0))
        self.assertNotIn("40", bundle_spacer_pdf_note(None))

    def test_export_has_real_member_geometry_and_preserves_plan(self):
        rows, platforms = sample_plan()
        original_rows, original_platforms = rows.copy(deep=True), platforms.copy(deep=True)
        bsd_before = app.create_bsd_matrix_for_platform(rows, platforms.iloc[0])
        with patch.object(app, "expand_bundle_display_rows", wraps=expand_bundle_display_rows) as expand:
            pdf = app.create_loading_pdf(
                rows, platforms, pd.DataFrame(columns=["Pritsche"]), pd.DataFrame(), project_name="PDF-Test"
            )
            self.assertTrue(expand.called)
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        self.assertEqual(len(doc), 2)
        self.assertIn("Einlage 80 mm", doc[1].get_text())
        self.assertNotIn("Einlage 40 /", doc[1].get_text())
        self.assertIn("Bundursprung", doc[0].get_text())
        self.assertIn("DE01", doc[0].get_text())
        pd.testing.assert_frame_equal(original_rows, rows)
        pd.testing.assert_frame_equal(original_platforms, platforms)
        pd.testing.assert_frame_equal(
            bsd_before, app.create_bsd_matrix_for_platform(rows, platforms.iloc[0])
        )

    def test_explicit_bundle_overview_remains_unchanged(self):
        rows, platforms = sample_plan()
        with patch.object(app, "expand_bundle_display_rows") as expand:
            app.create_loading_pdf(
                rows, platforms, pd.DataFrame(columns=["Pritsche"]), pd.DataFrame(),
                project_meta={"Bundnummern_nur_in_Verladung": True},
            )
            expand.assert_not_called()


if __name__ == "__main__":
    unittest.main()
