"""Exercise the real Streamlit widgets and backend together."""

import unittest

from streamlit.testing.v1 import AppTest


SCRIPT = """
import pandas as pd
import streamlit as st
import bvx_auswertung_streamlit as app
from pinned_manual_ui import render_pinned_manual_replanning
parts = pd.DataFrame([
    {'Bauteilnummer': label, 'Nr.PL': number, 'Länge_mm': 5.0,
     'Breite_mm': 2.0, 'Höhe_mm': 2.0, 'Gewicht_kg': 10.0, 'Volumen_m3': 0.00002}
    for label, number in [('0.29', 29), ('0.31', 31), ('0.32', 32)]
])
stock = pd.DataFrame([{
    'Fuhrenoption': 'Standard', 'Pritschenname': 'Deck', 'Pritsche': 'Deck',
    'Pritschen_Reihenfolge': 1, 'Freigabe': True, 'Länge_mm': 50.0,
    'Breite_mm': 10.0, 'Max_Höhe_mm': 20.0, 'Max_Gewicht_kg': 1000.0,
    'Eigengewicht_Pritsche_kg': 10.0, 'Überhang_vorne_mm': 0.0,
    'Überhang_hinten_mm': 0.0, 'Drehen_90_erlaubt': False, 'Runge_aktiv': False,
    'Mindest_Stützbreite_%': 60.0,
}])
options = pd.DataFrame([{'Fuhrenoption': 'Standard', 'Freigegeben': True, 'Priorität': 1}])
standards = {'Standard_Kantholz_erste_Lage': 2.0, 'Standard_Einlage_zwischen_Lagen': 0.0,
             'Standard_Einlage_allgemein': 0.0, 'Längenversatz_je_Lage': 0.0}
settings = {'allow_beside': True, 'allow_stack': True, 'allow_rotation': False,
            'use_bundles': False, 'max_fuhren': 5, 'min_support_width_ratio': 0.6}
if 'source' not in st.session_state:
    placements, _, platforms, _, _ = app.create_variant_a_loading_plan(
        parts, options, stock, standards, **settings)
    st.session_state['source'] = placements
    st.session_state['source_platforms'] = platforms
render_pinned_manual_replanning(
    st.session_state['source'], st.session_state['source_platforms'], parts,
    options, stock, standards, settings,
    validate_pair=app._manual_validate_pinned_longitudinal_pair,
    preview_plan=app._preview_pinned_manual_replan,
    apply_plan=app._apply_pinned_manual_replan,
    draw_view=app.draw_loading_view, is_real_load=app._is_real_load_type_value,
)
"""


class PinnedManualStreamlitTests(unittest.TestCase):
    def test_real_widgets_validate_preview_confirm_and_release(self):
        at = AppTest.from_string(SCRIPT, default_timeout=60).run()
        self.assertFalse(at.exception)
        source = at.session_state['source']
        ids = {str(row['Bauteile_Liste']): str(row['Einheit_ID'])
               for _, row in source.iterrows() if row['Typ'] == 'Bauteil'}
        at.selectbox(key='pinned_manual_first').set_value(ids['0.29'])
        at.selectbox(key='pinned_manual_second').set_value(ids['0.31']).run()
        for which, label, x in [('first', '0.29', 0.0), ('second', '0.31', 5.0)]:
            for axis, value in [('X', x), ('Y', 0.0), ('Z', 2.0)]:
                at.number_input(key=f'pinned_manual_{which}_{ids[label]}_{axis}').set_value(value)
        at.button(key='pinned_manual_preview_button').click().run()
        self.assertFalse(at.exception)
        preview = at.session_state['pinned_manual_preview']
        self.assertTrue(preview['ok'], preview['issues'].to_dict('records'))
        self.assertNotIn('pinned_manual_active', at.session_state)
        self.assertTrue(at.button(key='pinned_manual_apply').disabled)
        at.checkbox(key=f"pinned_manual_confirm_{preview['source_signature']}").check().run()
        at.button(key='pinned_manual_apply').click().run()
        self.assertFalse(at.exception)
        self.assertIn('pinned_manual_active', at.session_state)
        accepted = at.session_state['manual_placements_df']
        self.assertEqual(
            sorted(accepted[accepted['Typ'].eq('Bauteil')]['Nr.PL'].tolist()),
            [29, 31, 32],
        )
        at.button(key='pinned_manual_release').click().run()
        self.assertFalse(at.exception)
        self.assertNotIn('pinned_manual_active', at.session_state)
        self.assertIn('manual_placements_df', at.session_state)


if __name__ == '__main__':
    unittest.main()