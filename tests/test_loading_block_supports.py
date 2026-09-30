import unittest
from unittest.mock import patch

import pandas as pd

import bvx_auswertung_streamlit as app


def parts():
    # Logical order is top to bottom. Physically the short part is placed first.
    return pd.DataFrame([
        {'Index': 2, 'Bauteilnummer': 'LONG', 'Länge_mm': 9123.0,
         'Breite_mm': 1733.0, 'Höhe_mm': 120.0, 'Gewicht_kg': 850.0,
         'Volumen_m3': 1.89721908},
        {'Index': 1, 'Bauteilnummer': 'SHORT', 'Länge_mm': 4560.0,
         'Breite_mm': 2063.0, 'Höhe_mm': 120.0, 'Gewicht_kg': 500.0,
         'Volumen_m3': 1.1288736},
    ])


def platforms():
    return pd.DataFrame([{
        'Fuhrenoption': 'Auflieger', 'Pritschen_Reihenfolge': 1,
        'Pritschenname': 'Auflieger', 'Pritsche': 'Auflieger',
        'Freigabe': True, 'Länge_mm': 7600.0, 'Breite_mm': 2450.0,
        'Max_Höhe_mm': 2800.0, 'Max_Gewicht_kg': 20000.0,
        'Eigengewicht_Pritsche_kg': 1000.0,
        'Überhang_hinten_mm': 3500.0, 'Überhang_vorne_mm': 1400.0,
        'Drehen_90_erlaubt': False, 'Runge_aktiv': False,
        'Auflager_bei_Verladeplanung_beruecksichtigen': True,
        'Auflager_Strenge': 'Nur notwendige Auflager',
        'Mindest_Stützbreite_%': 30.0,
    }])


def plan(spacer, compaction=False):
    options = pd.DataFrame([{
        'Freigegeben': True, 'Priorität': 1, 'Fuhrenoption': 'Auflieger',
    }])
    standards = {
        'Standard_Kantholz_erste_Lage': 80.0,
        'Standard_Einlage_zwischen_Lagen': 40.0,
        'Standard_Einlage_allgemein': spacer,
        'Längenversatz_je_Lage': 100.0,
    }
    return app.create_variant_a_loading_plan(
        parts(), options, platforms(), standards,
        allow_beside=True, allow_stack=True, allow_rotation=False,
        use_bundles=False, general_spacer_height=spacer,
        min_support_width_ratio=0.30,
        enable_multilayer_compaction=compaction,
    )


class LoadingBlockSupportTests(unittest.TestCase):
    def test_spacers_do_not_split_complete_block_and_supports_are_preserved(self):
        for spacer in (0.0, 0.15, 15.0):
            with self.subTest(spacer=spacer):
                placements, summary, used, log, units = plan(spacer)
                self.assertEqual(len(used), 1)
                self.assertEqual(len(log), 1)
                self.assertFalse(placements['Pritsche'].eq('NICHT VERLADEN').any())
                real = placements[placements['Typ'].apply(app._is_real_load_type_value)]
                self.assertEqual(set(real['Einheit_ID']), set(units['Einheit_ID']))
                self.assertEqual(len(real), 2)
                self.assertLessEqual(summary['Höhe genutzt_mm'].max(), 2800.0)
                if spacer > 0:
                    supports = placements[placements['Typ'].eq('Unterbau')]
                    self.assertFalse(supports.empty)
                    self.assertTrue(supports['Einheit_ID'].str.startswith('UBP_').all())
                    self.assertTrue(supports['Höhe_mm'].gt(0).all())

    def test_missing_real_load_is_not_hidden_by_support_row(self):
        original = app.create_loading_plan

        def missing_load(*args, **kwargs):
            placements, summary = original(*args, **kwargs)
            wanted_id = str(args[0].iloc[0]['Einheit_ID'])
            return placements[~placements['Einheit_ID'].astype(str).eq(wanted_id)], summary

        with patch.object(app, 'create_loading_plan', side_effect=missing_load):
            placements, _, used, _, _ = plan(15.0)
        self.assertTrue(used.empty)
        self.assertTrue(placements['Pritsche'].eq('NICHT VERLADEN').all())

    def test_optional_compaction_keeps_supports_for_complete_block(self):
        original = app.apply_main_loading_postprocess
        received_supports = []

        def checked_postprocess(placements, *args, **kwargs):
            received_supports.append(placements['Typ'].eq('Unterbau').any())
            return original(placements, *args, **kwargs)

        with patch.object(app, 'apply_main_loading_postprocess', side_effect=checked_postprocess):
            placements, _, used, _, units = plan(15.0, compaction=True)
        self.assertEqual(len(used), 1)
        real = placements[placements['Typ'].apply(app._is_real_load_type_value)]
        self.assertEqual(set(real['Einheit_ID']), set(units['Einheit_ID']))
        # Compaction may safely remove obsolete supports, but must receive them
        # before moving or validating any of the real loads.
        self.assertTrue(received_supports[0])
        self.assertTrue(app.find_geometry_conflicts(placements, used).empty)


if __name__ == '__main__':
    unittest.main()