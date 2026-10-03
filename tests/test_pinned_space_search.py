import unittest

import pandas as pd

import bvx_auswertung_streamlit as app
from pinned_space_search import largest_fitting_prefix
from test_pinned_manual_replanning import platform, source_plan


class PinnedSpaceSearchTests(unittest.TestCase):
    def fixture(self):
        source, used = source_plan()
        parts = pd.DataFrame([
            {'Index': i, 'Bauteilnummer': label, 'Nr.PL': number,
             'Länge_mm': 5.0, 'Breite_mm': 2.0, 'Höhe_mm': 2.0,
             'Gewicht_kg': 10.0, 'Volumen_m3': 0.00002}
            for i, (label, number) in enumerate((('A', 101), ('B', 102), ('C', 103)), 1)
        ])
        options = pd.DataFrame([{'Fuhrenoption': 'Standard', 'Freigegeben': True, 'Priorität': 1}])
        stock = pd.DataFrame([platform()])
        stock['Freigabe'] = True
        stock['Pritschen_Reihenfolge'] = 1
        stock['Drehen_90_erlaubt'] = False
        stock['Runge_aktiv'] = False
        standards = {'Standard_Kantholz_erste_Lage': 2.0,
                     'Standard_Einlage_zwischen_Lagen': 0.0,
                     'Standard_Einlage_allgemein': 0.0, 'Längenversatz_je_Lage': 0.0}
        settings = {'allow_beside': True, 'allow_stack': True, 'allow_rotation': False,
                    'use_bundles': False, 'manual_pair_override': True}
        coords = {'A': {'X_mm': 0.0, 'Y_mm': 0.0, 'Z_mm': 2.0},
                  'B': {'X_mm': 5.0, 'Y_mm': 0.0, 'Z_mm': 2.0}}
        return source, used, parts, options, stock, standards, settings, coords

    def preview(self, fixture):
        source, used, parts, options, stock, standards, settings, coords = fixture
        return app._preview_pinned_manual_replan(
            source, used, parts, options, stock, standards, settings,
            ['A', 'B'], 'F01 Deck', coords,
        )

    def test_free_destination_space_is_used_and_trip_is_saved(self):
        fixture = self.fixture()
        result = self.preview(fixture)
        self.assertTrue(result['ok'], result['issues'].to_dict('records'))
        self.assertEqual(result['platforms_df']['Fuhre_Nr'].nunique(), 1)
        self.assertEqual(set(result['placements_df']['Bauteile_Liste']), {'A', 'B', 'C'})
        self.assertTrue(app._pinned_manual_physical_conflicts(result['placements_df']).empty)
        pinned = result['pinned_placements_df'].set_index('Einheit_ID')
        for uid, coordinates in fixture[-1].items():
            for axis, value in coordinates.items():
                self.assertEqual(pinned.loc[uid, axis], value)
        source, used, parts, options, stock, _, settings, _ = fixture
        applied = app._apply_pinned_manual_replan(
            result, source, used, parts, options, stock, settings,
        )
        self.assertTrue(applied['applied'])

    def test_space_below_elevated_pin_is_searched(self):
        fixture = self.fixture()
        for frame in (fixture[1], fixture[4]):
            frame['Länge_mm'] = 10.0
            frame['Breite_mm'] = 2.0
        fixture[0].loc[fixture[0]['Einheit_ID'].eq('C'), 'X_mm'] = 2.5
        fixture[0].loc[fixture[0]['Einheit_ID'].eq('C'), 'Z_mm'] = 4.0
        for coordinates in fixture[-1].values():
            coordinates['Z_mm'] = 10.0
        result = self.preview(fixture)
        self.assertTrue(result['ok'], result['issues'].to_dict('records'))
        loads = result['placements_df']
        remainder = loads.loc[loads['Bauteile_Liste'].eq('C')].iloc[0]
        self.assertEqual(remainder['Pritsche'], 'F01 Deck')
        self.assertEqual(remainder['Z_mm'], 2.0)
        self.assertTrue(result['pinned_placements_df']['Z_mm'].eq(10.0).all())

    def test_bundle_members_stay_together_and_keep_imported_numbers(self):
        fixture = list(self.fixture())
        extra_source = fixture[0].iloc[2].to_dict()
        extra_source.update({'Einheit_ID': 'D', 'Bauteile': 'D', 'Bauteile_Liste': 'D',
                             'Nr.PL': 104, 'X_mm': 15.0})
        fixture[0] = pd.concat([fixture[0], pd.DataFrame([extra_source])], ignore_index=True)
        extra_part = fixture[2].iloc[2].to_dict()
        extra_part.update({'Index': 4, 'Bauteilnummer': 'D', 'Nr.PL': 104})
        fixture[2] = pd.concat([fixture[2], pd.DataFrame([extra_part])], ignore_index=True)
        fixture[6]['use_bundles'] = True
        fixture[6]['max_bundle_weight'] = 1000.0
        result = self.preview(fixture)
        self.assertTrue(result['ok'], result['issues'].to_dict('records'))
        bundle = result['placements_df'].loc[result['placements_df']['Typ'].eq('Bund')]
        self.assertEqual(len(bundle), 1)
        self.assertEqual(set(bundle.iloc[0]['Bauteile_Liste'].split('|')), {'C', 'D'})
        self.assertEqual(set(str(bundle.iloc[0]['Nr.PL']).split('|')), {'103', '104'})
        self.assertEqual(app._pinned_manual_identity_signature(fixture[0]),
                         app._pinned_manual_identity_signature(result['placements_df']))

    def test_full_deck_does_not_reject_valid_global_remainder(self):
        fixture = self.fixture()
        source, used, _, _, stock, _, _, _ = fixture
        for frame in (used, stock):
            frame['Länge_mm'] = 10.0
            frame['Breite_mm'] = 2.0
            frame['Max_Höhe_mm'] = 4.0
        source.loc[source['Einheit_ID'].eq('C'), 'X_mm'] = 2.5
        source.loc[source['Einheit_ID'].eq('C'), 'Pritsche'] = 'F02 Deck'
        source.loc[source['Einheit_ID'].eq('C'), 'Fuhre_Nr'] = 2
        result = self.preview(fixture)
        self.assertTrue(result['ok'], result['issues'].to_dict('records'))
        self.assertEqual(result['platforms_df']['Fuhre_Nr'].nunique(), 2)
        self.assertEqual(len(result['placements_df'].loc[
            result['placements_df']['Pritsche'].eq('F01 Deck')
        ]), 2)

    def test_pin_weight_is_counted_before_filling(self):
        fixture = self.fixture()
        fixture[1]['Max_Gewicht_kg'] = 35.0  # 20 loads + 10 deck leaves only 5.
        result = self.preview(fixture)
        self.assertTrue(result['ok'], result['issues'].to_dict('records'))
        loads = result['placements_df']
        remainder = loads.loc[loads['Bauteile_Liste'].eq('C')].iloc[0]
        self.assertNotEqual(remainder['Pritsche'], 'F01 Deck')
        self.assertEqual(result['platforms_df']['Fuhre_Nr'].nunique(), 2)

    def test_automatic_fill_respects_existing_trip_group(self):
        fixture = self.fixture()
        fixture[2]['GROUP'] = ['ONE', 'ONE', 'TWO']
        fixture[6]['fuhre_split_attr'] = 'GROUP'
        result = self.preview(fixture)
        self.assertTrue(result['ok'], result['issues'].to_dict('records'))
        remainder = result['placements_df'].loc[
            result['placements_df']['Bauteile_Liste'].eq('C')
        ].iloc[0]
        self.assertNotEqual(remainder['Pritsche'], 'F01 Deck')
        self.assertEqual(result['deviation'], '')

    def test_single_part_order_does_not_skip_an_unfitting_prefix(self):
        fixture = self.fixture()
        _, used, parts, _, _, standards, settings, coords = fixture
        units = app.build_loading_units(parts.iloc[2:], False, 1000.0, 0.0, 0.0,
                                        True, False, False, False)
        second = units.iloc[0].to_dict()
        second.update({'Einheit_ID': 'LATER', 'Bauteile': 'D', 'Bauteile_Liste': 'D'})
        units.loc[:, 'Länge_mm'] = 60.0  # First load cannot fit the 50 mm deck.
        units = pd.concat([units, pd.DataFrame([second])], ignore_index=True)
        pair = app._manual_validate_pinned_longitudinal_pair(
            fixture[0], used, ['A', 'B'], coords, include_destination_loads=False,
            manual_pair_override=True,
        )['pinned_placements_df']
        packed, timed_out = largest_fitting_prefix(
            units, pair, used, app._pinned_manual_plan_around_pair,
            {'base_wood_height': 2.0, 'layer_spacer_height': 0.0, 'gap_length': 0.0,
             'allow_beside': True, 'allow_stack': True, 'allow_rotation': False},
        )
        self.assertTrue(packed.empty)
        self.assertFalse(timed_out)

    def test_exhausted_budget_returns_no_unchecked_fill(self):
        fixture = self.fixture()
        units = app.build_loading_units(fixture[2].iloc[2:], False, 1000.0, 0.0, 0.0,
                                        True, False, False, False)
        pair = fixture[0].loc[fixture[0]['Einheit_ID'].isin(['A', 'B'])]
        packed, timed_out = largest_fitting_prefix(
            units, pair, fixture[1], app._pinned_manual_plan_around_pair, {},
            time_budget=0.0,
        )
        self.assertTrue(packed.empty)
        self.assertTrue(timed_out)


if __name__ == '__main__':
    unittest.main()