import io
import json
from contextlib import nullcontext
import unittest
import zipfile

import pandas as pd

import bvx_auswertung_streamlit as app
from loading_diagnostics import (
    build_diagnostic_zip, make_snapshot, render_diagnostic_download,
    support_diagnostic_table, trace_event, traced_loading_run,
)
from test_flexible_loading_integration import make_parts, make_platform, plan


class DiagnosticTests(unittest.TestCase):
    def test_snapshot_keeps_original_inputs_and_settings(self):
        parts = make_parts()
        settings = {"minimum": 35, "order": ["Pak", "absteigend"], "number": float("nan")}
        snap = make_snapshot(settings, parts, pd.DataFrame(), make_platform(), {})
        parts.loc[0, "Breite_mm"] = 99
        settings["order"].append("changed")
        self.assertEqual(snap["parts"].iloc[0]["Breite_mm"], 1200)
        self.assertEqual(snap["settings"]["order"], ["Pak", "absteigend"])
        self.assertIsNone(snap["settings"]["number"])

    def test_trace_is_bounded_and_reset_on_failure(self):
        @traced_loading_run
        def run():
            for i in range(800):
                trace_event("reject", index=i)
            trace_event("result", accepted=True)
            return (pd.DataFrame({"x": [1]}),)
        result = run()[0].attrs["loading_diagnostics"]
        self.assertEqual(result["counts"]["reject"], 800)
        self.assertTrue(result["samples_truncated"])
        self.assertEqual(len(result["samples"]), 31)
        self.assertEqual(result["samples"][-1]["stage"], "result")
        self.assertGreaterEqual(result["elapsed_seconds"], 0)

        @traced_loading_run
        def fail():
            raise ValueError("test")
        with self.assertRaises(ValueError):
            fail()
        trace_event("outside")
        self.assertNotIn("outside", run()[0].attrs["loading_diagnostics"]["counts"])

    def test_real_plan_unchanged_by_observation(self):
        parts = make_parts()
        original = parts.copy(deep=True)
        # Bypass only the observation decorator, not the compaction wrapper.
        kwargs = dict(flexible_lane_compare=True, flexible_width_compare=True)
        observed = plan(parts, **kwargs)
        self.assertIn("loading_diagnostics", observed[0].attrs)
        trace = observed[0].attrs["loading_diagnostics"]
        self.assertIn("Flexible_Suche", trace["counts"])
        unobserved = app.create_variant_a_loading_plan.__wrapped__.__wrapped__(
            parts,
            pd.DataFrame([{"Freigegeben": True, "Priorität": 1, "Fuhrenoption": "Auflieger"}]),
            make_platform(),
            {"Standard_Kantholz_erste_Lage": 80.0, "Standard_Einlage_zwischen_Lagen": 40.0,
             "Standard_Einlage_allgemein": 0.0, "Längenversatz_je_Lage": 100.0},
            allow_beside=True, allow_stack=True, allow_rotation=False, use_bundles=False,
            min_support_width_ratio=0.35, **kwargs,
        )
        for before, after in zip(unobserved, observed):
            pd.testing.assert_frame_equal(before, after)
        pd.testing.assert_frame_equal(original, parts)

    def test_zip_contains_real_positions_settings_and_explicit_check_errors(self):
        positions, summary, decks, trips, units = plan(make_parts())
        before = positions.copy(deep=True)
        snap = make_snapshot({"minimum": 35}, make_parts(), pd.DataFrame(), make_platform(), {})

        def failed():
            raise ValueError("cannot inspect")

        payload = build_diagnostic_zip(
            snapshot=snap, current_settings={"minimum": 50},
            tables={"positionen_aktuell": positions, "summary": summary, "units": units},
            checks={
                "geometrie": lambda: app.find_geometry_conflicts(positions, decks),
                "auflage": lambda: support_diagnostic_table(
                    positions, decks, app.init_platform_state, app._support_metrics_for_candidate),
                "failed": failed,
            },
            metadata={"settings_changed_since_calculation": True},
        )
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIsNone(archive.testzip())
            manifest = json.loads(archive.read("diagnose.json"))
            self.assertEqual(manifest["calculation"]["settings"]["minimum"], 35)
            self.assertEqual(manifest["current_settings"]["minimum"], 50)
            self.assertTrue(manifest["settings_changed_since_calculation"])
            self.assertEqual(manifest["checks"][-1]["status"], "fehlgeschlagen")
            self.assertIn("ValueError", manifest["checks"][-1]["error"])
            exported = pd.read_csv(io.BytesIO(archive.read("tabellen/positionen_aktuell.csv")))
            self.assertEqual(exported["X_mm"].tolist(), positions["X_mm"].tolist())
            self.assertIn("eingabe/parts.csv", archive.namelist())
            support = pd.read_csv(io.BytesIO(archive.read("pruefungen/auflage.csv")))
            self.assertEqual(len(support), len(make_parts()))
            self.assertIn("Auflage_berechnet_%", support)
            self.assertNotIn("SESSION_SECRET", archive.read("diagnose.json").decode())
        pd.testing.assert_frame_equal(before, positions)

    def test_older_plan_missing_snapshot_explicit(self):
        data = build_diagnostic_zip(
            snapshot=None, current_settings={}, tables={}, checks={}, metadata={}
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read("diagnose.json"))
            self.assertFalse(manifest["calculation_snapshot_available"])
            self.assertEqual(manifest["calculation"], {})

    def test_ui_generation_only_on_click_and_download(self):
        class UI:
            clicked = False
            download = None
            def subheader(self, *args): pass
            def caption(self, *args): pass
            def warning(self, *args): pass
            def spinner(self, *args): return nullcontext()
            def button(self, *args, **kwargs): return self.clicked
            def download_button(self, *args, **kwargs): self.download = kwargs
            def error(self, message): raise AssertionError(message)
        ui = UI()
        kwargs = dict(snapshot=None, current_settings={}, tables={}, checks={}, metadata={})
        render_diagnostic_download(ui, **kwargs)
        self.assertIsNone(ui.download)
        ui.clicked = True
        render_diagnostic_download(ui, **kwargs)
        self.assertEqual(ui.download["mime"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(ui.download["data"])) as archive:
            self.assertIn("diagnose.json", archive.namelist())

    def test_actual_loading_screen_exposes_diagnostic_download(self):
        from streamlit.testing.v1 import AppTest
        script = '''
import io
import sys
import streamlit as st
sys.path.insert(0, "tests")
from test_flexible_loading_integration import make_parts, plan
import bvx_auswertung_streamlit as app
positions, summary, decks, trips, units = plan(make_parts())
st.session_state["loading_plan_started_v84"] = True
if "automatic_loading_plan_v84" not in st.session_state:
    st.session_state["automatic_loading_plan_v84"] = {
        "signature": "test-older-plan", "placements": positions, "summary": summary,
        "platforms": decks, "fuhren_log": trips, "units": units,
    }
source = io.BytesIO(open("attached_assets/02.0_fuer_Nesting_1793528729994.xlsx", "rb").read())
source.name = "02.0_fuer_Nesting.xlsx"
app.render_loading_module(None, parts_excel_file=source)
'''
        screen = AppTest.from_string(script).run(timeout=30)
        self.assertEqual(len(screen.exception), 0, list(screen.exception))
        screen.button(key="build_loading_diagnostic_zip").click().run(timeout=30)
        self.assertEqual(len(screen.exception), 0, list(screen.exception))
        self.assertFalse(any("Diagnosepaket konnte nicht" in e.value for e in screen.error))
        downloads = screen.get("download_button")
        self.assertTrue(any(
            "Diagnosepaket herunterladen" in button.proto.label for button in downloads
        ))


if __name__ == "__main__":
    unittest.main()
