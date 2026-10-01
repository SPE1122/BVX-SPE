"""Exercise accepted-pin protection through the complete loading-module renderer."""

import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest


SCRIPT = r"""
from types import SimpleNamespace
import pandas as pd
import streamlit as st
import bvx_auswertung_streamlit as app

parts = pd.DataFrame([
    {'Bauteilnummer': label, 'Nr.PL': number, 'Länge_mm': 5.0,
     'Breite_mm': 2.0, 'Höhe_mm': 2.0, 'Gewicht_kg': 10.0,
     'Volumen_m3': 0.00002, 'Pak/Unit': 'A'}
    for label, number in [('A', 101), ('B', 102), ('C', 103)]
])
options = pd.DataFrame([
    {'Fuhrenoption': 'Standard', 'Freigegeben': True, 'Priorität': 1}
])
stock = pd.DataFrame([{
    'Fuhrenoption': 'Standard', 'Pritschenname': 'Deck', 'Pritsche': 'Deck',
    'Pritschen_Reihenfolge': 1, 'Freigabe': True, 'Länge_mm': 50.0,
    'Breite_mm': 10.0, 'Max_Höhe_mm': 20.0, 'Max_Gewicht_kg': 1000.0,
    'Eigengewicht_Pritsche_kg': 10.0, 'Überhang_vorne_mm': 0.0,
    'Überhang_hinten_mm': 0.0, 'Drehen_90_erlaubt': False,
    'Runge_aktiv': False, 'Mindest_Stützbreite_%': 60.0,
    'Kantholz_erste_Lage_mm': 2.0, 'Einlage_zwischen_Lagen_mm': 0.0,
    'Einlage_allgemein_mm': 0.0,
}])
standards = {
    'Holzdichte': 500.0, 'Max_Bundgewicht': 1000.0,
    'Standard_Kantholz_erste_Lage': 2.0,
    'Standard_Einlage_zwischen_Lagen': 0.0,
    'Standard_Einlage_allgemein': 0.0, 'Längenversatz_je_Lage': 0.0,
}

# Use the module's ordinary renderer and calculation paths while keeping uploaded
# workbook parsing deterministic and independent of external files.
app.read_parts_excel_to_dataframe = lambda *_args, **_kwargs: (parts.copy(deep=True), [])
app.read_transport_config_excel = lambda *_args, **_kwargs: (
    options.copy(deep=True), stock.copy(deep=True), standards.copy(), []
)
parts_upload = SimpleNamespace(name='fixture-parts.xlsx')

if not st.session_state.get('_test_pin_fixture_initialized'):
    starting, _, used_platforms, fuhren_log, units = app.create_variant_a_loading_plan(
        parts, options, stock, standards,
        allow_beside=True, allow_stack=True, allow_rotation=False,
        use_bundles=False, max_fuhren=5, min_support_width_ratio=0.6,
    )
    accepted = starting.copy(deep=True)
    # Give the accepted snapshot a distinguishable but otherwise valid coordinate.
    real_indices = accepted.index[
        accepted.get('Typ', pd.Series(index=accepted.index, dtype=str)).apply(
            app._is_real_load_type_value
        )
    ]
    if len(real_indices):
        accepted.loc[real_indices[0], 'X_mm'] = float(accepted.loc[real_indices[0], 'X_mm']) + 1.0
    accepted_platforms = used_platforms.copy(deep=True)
    st.session_state['_test_accepted_placements'] = accepted.copy(deep=True)
    st.session_state['_test_accepted_platforms'] = accepted_platforms.copy(deep=True)
    st.session_state['manual_placements_df'] = starting.copy(deep=True)
    st.session_state['manual_platforms_df'] = used_platforms.copy(deep=True)
    st.session_state['manual_plan_ready_v84'] = True
    real_ids = accepted.loc[
        accepted.get('Typ', pd.Series(index=accepted.index, dtype=str)).apply(
            app._is_real_load_type_value
        ), 'Einheit_ID'
    ].astype(str).tolist()
    st.session_state['pinned_manual_active'] = {
        'applied': True,
        'unit_ids': real_ids[:2],
        'target_platform': str(accepted_platforms.iloc[0]['Pritsche']),
        'placements_df': accepted.copy(deep=True),
        'platforms_df': accepted_platforms.copy(deep=True),
        'units_df': units.copy(deep=True),
        'fuhren_log_df': fuhren_log.copy(deep=True),
        'pinned_placements_df': accepted[
            accepted.get('Einheit_ID', pd.Series(index=accepted.index, dtype=str))
            .astype(str).isin(real_ids[:2])
        ].copy(deep=True),
    }
    st.session_state['loading_plan_started_v84'] = True
    st.session_state['_test_pin_fixture_initialized'] = True

app.render_loading_module(None, parts_excel_file=parts_upload)
"""


def run_module():
    at = AppTest.from_string(SCRIPT, default_timeout=90).run()
    if at.exception:
        raise AssertionError(at.exception[0].message)
    return at


def widget_keys(elements):
    return {element.key for element in elements if getattr(element, "key", None)}


class PinnedLoadingModuleTests(unittest.TestCase):
    def test_accepted_pin_blocks_module_actions_and_overrides_source_plan(self):
        at = run_module()

        expected = at.session_state["_test_accepted_placements"]
        pd.testing.assert_frame_equal(at.session_state["manual_placements_df"], expected)
        self.assertTrue(at.button(key="start_loading_plan_v84").disabled)
        self.assertTrue(at.button(key="reset_loading_plan_v84").disabled)

        # V116 and ordinary manual-zone controls are not offered at all while pinned.
        buttons = widget_keys(at.button)
        self.assertNotIn("v113_recalc_preview_button", buttons)
        for key in (
            "manual_start_next_platform_v84",
            "manual_zone_reset_v84",
            "manual_zone_unload_v84",
            "manual_zone_direct_VL_v84",
            "manual_zone_direct_VR_v84",
            "manual_zone_direct_HL_v84",
            "manual_zone_direct_HR_v84",
        ):
            self.assertNotIn(key, buttons)

    def test_mode_and_input_changes_keep_pin_and_release_retains_accepted_plan(self):
        at = run_module()
        expected = at.session_state["_test_accepted_placements"]

        # Changing both placement mode and an input that participates in planning
        # must not replace the accepted snapshot.
        at.radio(key="verladeart_v84").set_value("Manuell").run()
        self.assertFalse(at.exception)
        pd.testing.assert_frame_equal(at.session_state["manual_placements_df"], expected)
        self.assertIn("pinned_manual_active", at.session_state)
        pinned_buttons = widget_keys(at.button)
        self.assertNotIn("v113_recalc_preview_button", pinned_buttons)
        for key in (
            "manual_start_next_platform_v84",
            "manual_zone_reset_v84",
            "manual_zone_unload_v84",
            "manual_zone_direct_VL_v84",
            "manual_zone_direct_VR_v84",
            "manual_zone_direct_HL_v84",
            "manual_zone_direct_HR_v84",
        ):
            self.assertNotIn(key, pinned_buttons)

        at.radio(key="product_mode_v93").set_value("Stangen").run()
        self.assertFalse(at.exception)
        pd.testing.assert_frame_equal(at.session_state["manual_placements_df"], expected)
        self.assertIn("pinned_manual_active", at.session_state)

        wood_input = next(
            widget for widget in at.number_input
            if widget.label == "Standard Kantholz erste Lage mm"
        )
        wood_input.set_value(10.0).run()
        self.assertFalse(at.exception)
        pd.testing.assert_frame_equal(at.session_state["manual_placements_df"], expected)

        at.button(key="pinned_manual_release").click().run()
        self.assertFalse(at.exception)
        self.assertNotIn("pinned_manual_active", at.session_state)
        pd.testing.assert_frame_equal(at.session_state["manual_placements_df"], expected)
        retained_platforms = at.session_state["manual_platforms_df"]
        accepted_platforms = at.session_state["_test_accepted_platforms"]
        pd.testing.assert_frame_equal(
            retained_platforms[accepted_platforms.columns],
            accepted_platforms,
        )
        # With the lock removed and manual mode selected, ordinary controls return.
        self.assertIn("manual_zone_direct_VL_v84", widget_keys(at.button))


if __name__ == "__main__":
    unittest.main()