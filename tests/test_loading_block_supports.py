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
    def test_declared_general_inserts_do_not_break_support_chain(self):
        for spacer in (0.0, 0.15, 15.0):
            with self.subTest(spacer=spacer):
                placements, _, used, _, _ = plan(spacer)
                issues = app._pinned_manual_support_chain_issues(placements, used, 0.30)
                self.assertTrue(issues.empty, issues.to_dict('records'))

    def _layer_contact_case(self, gap=15.0, lower_type='Bauteil', upper_type='Bauteil'):
        deck = platforms().iloc[0].to_dict()
        deck.update({
            'Pritsche': 'F04 Auflieger',
            'Kantholz_erste_Lage_mm': 80.0,
            'Einlage_allgemein_mm': 15.0,
            'Einlage_zwischen_Lagen_mm': 40.0,
            'Mindest_Stützbreite_%': 35.0,
        })
        loads = pd.DataFrame([
            {'Pritsche': deck['Pritsche'], 'Einheit_ID': unit_id, 'Typ': typ,
             'X_mm': 5000.0, 'Y_mm': 0.0, 'Z_mm': z,
             'Länge_mm': 1000.0, 'Breite_mm': 1000.0, 'Höhe_mm': 120.0}
            for unit_id, typ, z in (
                ('LOWER', lower_type, 80.0), ('UPPER', upper_type, 200.0 + gap),
            )
        ])
        return loads, pd.DataFrame([deck])

    def test_declared_bundle_insert_works_on_either_side_of_bundle(self):
        for lower_type, upper_type in (('Bund', 'Bauteil'), ('Bauteil', 'Bund')):
            with self.subTest(lower_type=lower_type, upper_type=upper_type):
                loads, decks = self._layer_contact_case(40.0, lower_type, upper_type)
                self.assertTrue(app._pinned_manual_support_chain_issues(loads, decks).empty)

    def test_undeclared_or_incorrect_air_gaps_still_fail(self):
        for gap in (7.5, 30.0, 60.0):
            with self.subTest(gap=gap):
                loads, decks = self._layer_contact_case(gap)
                issues = app._pinned_manual_support_chain_issues(loads, decks)
                self.assertEqual(issues['Einheit_ID'].tolist(), ['UPPER'])
        loads, decks = self._layer_contact_case()
        decks['Einlage_allgemein_mm'] = 0.0
        self.assertFalse(app._pinned_manual_support_chain_issues(loads, decks).empty)

    def test_declared_insert_does_not_replace_minimum_contact_area(self):
        loads, decks = self._layer_contact_case()
        loads.loc[loads['Einheit_ID'].eq('LOWER'), 'Länge_mm'] = 200.0
        issues = app._pinned_manual_support_chain_issues(loads, decks)
        self.assertEqual(issues['Einheit_ID'].tolist(), ['UPPER'])

    def test_declared_insert_does_not_ground_a_floating_lower_layer(self):
        loads, decks = self._layer_contact_case()
        loads['Z_mm'] += 60.0
        issues = app._pinned_manual_support_chain_issues(loads, decks)
        self.assertEqual(set(issues['Einheit_ID']), {'LOWER', 'UPPER'})

    def test_declared_insert_does_not_ground_a_floating_helper(self):
        loads, decks = self._layer_contact_case()
        helper = loads.iloc[1].to_dict()
        helper.update({'Einheit_ID': 'FLOATING_HELPER', 'Typ': 'Unterbau', 'Höhe_mm': 15.0})
        loads.loc[loads['Einheit_ID'].eq('UPPER'), 'Z_mm'] = 230.0
        loads = pd.concat([loads, pd.DataFrame([helper])], ignore_index=True)
        issues = app._pinned_manual_support_chain_issues(loads, decks)
        self.assertEqual(issues['Einheit_ID'].tolist(), ['UPPER'])

    def test_manual_pair_preview_and_apply_with_spaced_automatic_remainder(self):
        source_parts = pd.DataFrame([
            {'Index': i, 'Bauteilnummer': label, 'Nr.PL': i,
             'Länge_mm': 9120.0 if label.startswith('OTHER') else 4560.0,
             'Breite_mm': width,
             'Höhe_mm': 140.0 if label.startswith('OTHER') else 120.0,
             'Gewicht_kg': 500.0, 'Volumen_m3': 1.0}
            for i, label, width in (
                (1, '0.29', 2063.0), (2, '0.31', 1774.0),
                (3, 'OTHER_A', 2000.0), (4, 'OTHER_B', 2000.0),
                (5, 'OTHER_C', 2000.0), (6, 'OTHER_D', 2000.0),
            )
        ])
        stock = platforms()
        stock['Mindest_Stützbreite_%'] = 35.0
        stock['Max_Höhe_mm'] = 650.0
        options = pd.DataFrame([{
            'Freigegeben': True, 'Priorität': 1, 'Fuhrenoption': 'Auflieger',
        }])
        standards = {
            'Standard_Kantholz_erste_Lage': 80.0,
            'Standard_Einlage_zwischen_Lagen': 40.0,
            'Standard_Einlage_allgemein': 15.0,
            'Längenversatz_je_Lage': 100.0,
        }
        settings = {
            'allow_beside': True, 'allow_stack': True, 'allow_rotation': False,
            'use_bundles': False, 'general_spacer_height': 15.0,
            'bundle_spacer_height': 40.0, 'min_support_width_ratio': 0.35,
        }
        source, _, used, _, _ = app.create_variant_a_loading_plan(
            source_parts, options, stock, standards, **settings,
        )
        real = source[source['Typ'].apply(app._is_real_load_type_value)]
        ids = [str(real.loc[real['Bauteile_Liste'].eq(label), 'Einheit_ID'].iloc[0])
               for label in ('0.29', '0.31')]
        coordinates = {
            ids[0]: {'X_mm': 0.0, 'Y_mm': 193.5, 'Z_mm': 350.0},
            ids[1]: {'X_mm': 5100.0, 'Y_mm': 193.5, 'Z_mm': 350.0},
        }
        settings['manual_pair_override'] = True
        preview = app._preview_pinned_manual_replan(
            source, used, source_parts, options, stock, standards, settings,
            ids, 'F01 Auflieger', coordinates,
        )
        self.assertTrue(preview['ok'], preview['issues'].to_dict('records'))
        remaining = preview['placements_df'].loc[
            preview['placements_df']['Pritsche'].ne('F01 Auflieger')
        ]
        remaining_count = len(remaining[remaining['Typ'].apply(app._is_real_load_type_value)])
        self.assertGreater(remaining_count, 0)
        self.assertEqual(remaining_count + len(
            preview['placements_df'].loc[
                preview['placements_df']['Pritsche'].eq('F01 Auflieger')
                & preview['placements_df']['Typ'].apply(app._is_real_load_type_value)
                & ~preview['placements_df']['Einheit_ID'].isin(ids)
            ]
        ), 4)
        self.assertGreater(remaining['Z_mm'].max(), 80.0)
        self.assertTrue(app._pinned_manual_support_chain_issues(
            remaining, preview['platforms_df'], 0.35,
        ).empty)
        for unit_id in ids:
            pinned = preview['pinned_placements_df'].set_index('Einheit_ID').loc[unit_id]
            for axis, value in coordinates[unit_id].items():
                self.assertEqual(pinned[axis], value)
        applied = app._apply_pinned_manual_replan(
            preview, source, used, source_parts, options, stock, settings,
        )
        self.assertTrue(applied['applied'], applied.get('issues'))
        self.assertEqual(app._pinned_manual_identity_signature(source),
                         app._pinned_manual_identity_signature(applied['placements_df']))

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