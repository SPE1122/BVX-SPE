import unittest

import pandas as pd

import bvx_auswertung_streamlit as app
from pinned_plan_identity import restore_trip_names
from test_pinned_manual_replanning import platform


def multi_fixture():
    parts = pd.DataFrame([
        {'Bauteilnummer': label, 'Nr.PL': index + 1, 'PB': 'one' if index < 4 else 'two',
         'Länge_mm': 5.0, 'Breite_mm': 2.0, 'Höhe_mm': 2.0, 'Gewicht_kg': 10.0,
         'Volumen_m3': 0.00002}
        for index, label in enumerate('ABCDEFGH')
    ])
    decks = pd.DataFrame([platform(), platform('F02 Deck', 2)])
    placements = pd.DataFrame([
        {**platform('F01 Deck' if index < 4 else 'F02 Deck', 1 if index < 4 else 2),
         'Einheit_ID': label, 'Typ': 'Bauteil', 'Bauteile': label, 'Bauteile_Liste': label,
         'Nr.PL': index + 1, 'X_mm': float((index % 4) * 5), 'Y_mm': 0.0,
         'Z_mm': 2.0, 'Länge_mm': 5.0, 'Breite_mm': 2.0, 'Höhe_mm': 2.0,
         'Gewicht_kg': 10.0}
        for index, label in enumerate('ABCDEFGH')
    ])
    options = pd.DataFrame([{'Fuhrenoption': 'Standard', 'Freigegeben': True, 'Priorität': 1}])
    stock = pd.DataFrame([{**platform(), 'Freigabe': True, 'Pritschen_Reihenfolge': 1}])
    standards = {'Standard_Kantholz_erste_Lage': 2.0, 'Standard_Einlage_zwischen_Lagen': 0.0,
                 'Standard_Einlage_allgemein': 0.0, 'Längenversatz_je_Lage': 0.0}
    settings = {'allow_beside': True, 'allow_stack': True, 'allow_rotation': False,
                'use_bundles': False, 'max_fuhren': 2, 'min_support_width_ratio': 0.6,
                'fuhre_split_attr': 'PB', 'manual_pair_override': True}
    return placements, decks, parts, options, stock, standards, settings


class MultiPinTests(unittest.TestCase):
    def setUp(self):
        (self.loads, self.decks, self.parts, self.options, self.stock,
         self.standards, self.settings) = multi_fixture()

    def accept_pair(self, labels, destination, x_values, *, y=0.0):
        ids = [str(self.loads.loc[self.loads['Bauteile_Liste'].eq(label), 'Einheit_ID'].iloc[0])
               for label in labels]
        coordinates = {uid: {'X_mm': float(x), 'Y_mm': y, 'Z_mm': 2.0}
                       for uid, x in zip(ids, x_values)}
        preview = app._preview_pinned_manual_replan(
            self.loads, self.decks, self.parts, self.options, self.stock,
            self.standards, self.settings, ids, destination, coordinates,
        )
        self.assertTrue(preview['ok'], preview['issues'].to_dict('records'))
        accepted = app._apply_pinned_manual_replan(
            preview, self.loads, self.decks, self.parts, self.options, self.stock, self.settings
        )
        self.assertTrue(accepted['applied'], accepted['issues'].to_dict('records'))
        self.loads, self.decks = accepted['placements_df'], accepted['platforms_df']
        self.settings = {**self.settings, 'retained_pairs': accepted['pin_requests']}
        return accepted

    def test_two_pairs_on_one_deck_then_pair_on_other_deck_keep_every_coordinate_and_name(self):
        first = self.accept_pair(['A', 'B'], 'F01 Deck', [0, 5])
        second = self.accept_pair(['C', 'D'], 'F01 Deck', [10, 15])
        third = self.accept_pair(['E', 'F'], 'F02 Deck', [0, 5])
        self.assertEqual(len(third['pin_requests']), 3)
        self.assertEqual(set(self.decks['Pritsche']), {'F01 Deck', 'F02 Deck'})
        self.assertEqual(self.decks['Fuhre_Nr'].nunique(), 2)
        self.assertEqual(set(app._pinned_manual_identity_labels(self.loads)), set('ABCDEFGH'))
        for old in (first, second):
            for _, row in old['pinned_placements_df'].iterrows():
                actual = self.loads.loc[self.loads['Einheit_ID'].eq(row['Einheit_ID'])].iloc[0]
                for column in ('Pritsche', 'X_mm', 'Y_mm', 'Z_mm', 'Länge_mm', 'Breite_mm', 'Höhe_mm'):
                    self.assertEqual(actual[column], row[column], column)
        self.assertEqual(set(third['fuhren_log_df']['Fuhre_Nr']), {1, 2})
        self.assertEqual(set(self.loads.loc[self.loads['Typ'].eq('Bauteil'), 'Nr.PL']), set(range(1, 9)))

    def test_collision_with_earlier_pair_and_repeat_selection_are_rejected(self):
        self.accept_pair(['A', 'B'], 'F01 Deck', [0, 5])
        for labels in (['C', 'D'], ['A', 'B']):
            ids = [str(self.loads.loc[self.loads['Bauteile_Liste'].eq(label), 'Einheit_ID'].iloc[0])
                   for label in labels]
            preview = app._preview_pinned_manual_replan(
                self.loads, self.decks, self.parts, self.options, self.stock,
                self.standards, self.settings, ids, 'F01 Deck',
                {uid: {'X_mm': float(index * 5), 'Y_mm': 0.0, 'Z_mm': 2.0}
                 for index, uid in enumerate(ids)},
            )
            self.assertFalse(preview['ok'])

    def test_final_apply_revalidates_earlier_pin_even_with_recomputed_artifact_stamp(self):
        first = self.accept_pair(['A', 'B'], 'F01 Deck', [0, 5])
        ids = [str(self.loads.loc[self.loads['Bauteile_Liste'].eq(label), 'Einheit_ID'].iloc[0])
               for label in ('E', 'F')]
        preview = app._preview_pinned_manual_replan(
            self.loads, self.decks, self.parts, self.options, self.stock,
            self.standards, self.settings, ids, 'F02 Deck',
            {uid: {'X_mm': float(index * 5), 'Y_mm': 0.0, 'Z_mm': 2.0}
             for index, uid in enumerate(ids)},
        )
        self.assertTrue(preview['ok'], preview['issues'].to_dict('records'))
        first_id = first['unit_ids'][0]
        preview['placements_df'].loc[preview['placements_df']['Einheit_ID'].eq(first_id), 'X_mm'] += 1
        preview['_preview_artifact_signature'] = app._pinned_manual_preview_artifact_signature(preview)
        result = app._apply_pinned_manual_replan(
            preview, self.loads, self.decks, self.parts, self.options, self.stock, self.settings
        )
        self.assertFalse(result['applied'])
        self.assertIn('Fixiertes Paar', set(result['issues']['Typ']))

    def test_original_numbers_are_reused_instead_of_offsetting_after_f05(self):
        source = pd.DataFrame([platform(f'F{number:02d} Deck', number) for number in range(1, 6)])
        retained = source.iloc[[4]]
        used = pd.DataFrame([platform(f'F{number:02d} Deck', number) for number in range(1, 5)])
        loads = used[['Fuhre_Nr', 'Pritsche']].copy()
        log = used[['Fuhre_Nr']].copy()
        log['Pritschen'] = used['Pritsche']
        restore_trip_names((loads, pd.DataFrame(), used, log, pd.DataFrame()), source, retained)
        self.assertEqual(used['Fuhre_Nr'].tolist(), [1, 2, 3, 4])
        self.assertEqual(loads['Pritsche'].tolist(), [f'F{n:02d} Deck' for n in range(1, 5)])
        self.assertEqual(log['Pritschen'].tolist(), loads['Pritsche'].tolist())


if __name__ == '__main__':
    unittest.main()