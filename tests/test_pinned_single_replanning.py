import unittest

import pandas as pd

import bvx_auswertung_streamlit as app
from test_pinned_multi_replanning import multi_fixture
from test_pinned_manual_replanning import source_plan


class SinglePinTests(unittest.TestCase):
    def preview(self, loads, decks, parts, options, stock, standards, settings, label, x, y):
        row = loads.loc[loads['Bauteile_Liste'].eq(label)].iloc[0]
        uid = str(row['Einheit_ID'])
        return app._preview_pinned_manual_replan(
            loads, decks, parts, options, stock, standards,
            {**settings, 'manual_placement_mode': 'single'}, [uid], str(row['Pritsche']),
            {uid: {'X_mm': x, 'Y_mm': y, 'Z_mm': float(row['Z_mm'])}},
        )

    def test_single_x_y_combined_and_negative_shifts_preserve_height_and_identity(self):
        for label, x, y in [('A', 20.0, 0.0), ('A', 0.0, 3.0),
                            ('A', 20.0, 3.0), ('C', 5.0, 0.0)]:
            with self.subTest(label=label, x=x, y=y):
                loads, decks, parts, options, stock, standards, settings = multi_fixture()
                before = loads.copy(deep=True)
                preview = self.preview(
                    loads, decks, parts, options, stock, standards, settings, label, x, y
                )
                self.assertTrue(preview['ok'], preview['issues'].to_dict('records'))
                accepted = app._apply_pinned_manual_replan(
                    preview, loads, decks, parts, options, stock,
                    {**settings, 'manual_placement_mode': 'single'},
                )
                self.assertTrue(accepted['applied'], accepted['issues'].to_dict('records'))
                self.assertEqual(accepted['pin_requests'][0]['mode'], 'single')
                row = accepted['pinned_placements_df'].iloc[0]
                self.assertEqual((row['X_mm'], row['Y_mm'], row['Z_mm']), (x, y, 2.0))
                self.assertEqual(row['Pritsche'], str(before.loc[before['Bauteile_Liste'].eq(label), 'Pritsche'].iloc[0]))
                self.assertEqual(set(app._pinned_manual_identity_labels(accepted['placements_df'])), set('ABCDEFGH'))
                pd.testing.assert_frame_equal(loads, before)

    def test_single_moves_can_be_followed_by_pair_and_single_on_other_deck(self):
        loads, decks, parts, options, stock, standards, settings = multi_fixture()
        first = self.preview(loads, decks, parts, options, stock, standards, settings, 'A', 20.0, 3.0)
        self.assertTrue(first['ok'], first['issues'].to_dict('records'))
        loads, decks = first['placements_df'], first['platforms_df']
        settings = {**settings, 'retained_pairs': first['pin_requests']}
        ids = [str(loads.loc[loads['Bauteile_Liste'].eq(label), 'Einheit_ID'].iloc[0])
               for label in ('B', 'C')]
        pair = app._preview_pinned_manual_replan(
            loads, decks, parts, options, stock, standards, settings, ids, 'F01 Deck',
            {uid: {'X_mm': float(index * 5), 'Y_mm': 0.0, 'Z_mm': 2.0}
             for index, uid in enumerate(ids)},
        )
        self.assertTrue(pair['ok'], pair['issues'].to_dict('records'))
        loads, decks = pair['placements_df'], pair['platforms_df']
        settings = {**settings, 'retained_pairs': pair['pin_requests']}
        third = self.preview(loads, decks, parts, options, stock, standards, settings, 'E', 20.0, 3.0)
        self.assertTrue(third['ok'], third['issues'].to_dict('records'))
        final = app._apply_pinned_manual_replan(
            third, loads, decks, parts, options, stock,
            {**settings, 'manual_placement_mode': 'single'},
        )
        self.assertTrue(final['applied'], final['issues'].to_dict('records'))
        rows = final['pinned_placements_df'].set_index('Bauteile_Liste')
        self.assertEqual((rows.loc['A', 'X_mm'], rows.loc['A', 'Y_mm']), (20.0, 3.0))
        self.assertEqual(len(final['pin_requests']), 3)
        self.assertEqual(len(rows), 4)
        self.assertEqual(set(final['platforms_df']['Pritsche']), {'F01 Deck', 'F02 Deck'})

    def test_out_of_bounds_height_and_platform_changes_are_rejected(self):
        loads, decks, *_ = multi_fixture()
        for coords, target in [
            ({'X_mm': -1.0, 'Y_mm': 0.0, 'Z_mm': 2.0}, 'F01 Deck'),
            ({'X_mm': 0.0, 'Y_mm': 9.0, 'Z_mm': 2.0}, 'F01 Deck'),
            ({'X_mm': 0.0, 'Y_mm': 0.0, 'Z_mm': 3.0}, 'F01 Deck'),
            ({'X_mm': 0.0, 'Y_mm': 0.0, 'Z_mm': 2.0}, 'F02 Deck'),
        ]:
            result = app._manual_validate_pinned_longitudinal_pair(
                loads, decks, ['A'], {'A': coords}, target,
                include_destination_loads=False, manual_pair_override=True, placement_mode='single',
            )
            self.assertFalse(result['ok'])

    def test_single_shift_cannot_overlap_a_previously_fixed_single(self):
        loads, decks, parts, options, stock, standards, settings = multi_fixture()
        first = self.preview(
            loads, decks, parts, options, stock, standards, settings, 'A', 20.0, 3.0
        )
        self.assertTrue(first['ok'], first['issues'].to_dict('records'))
        before = first['placements_df'].copy(deep=True)
        result = self.preview(
            first['placements_df'], first['platforms_df'], parts, options, stock, standards,
            {**settings, 'retained_pairs': first['pin_requests']}, 'B', 20.0, 3.0,
        )
        self.assertFalse(result['ok'])
        pd.testing.assert_frame_equal(first['placements_df'], before)

    def test_linked_support_moves_in_both_horizontal_axes_without_height_change(self):
        loads, decks = source_plan(with_support=True)
        result = app._manual_validate_pinned_longitudinal_pair(
            loads, decks, ['A'], {'A': {'X_mm': 20.0, 'Y_mm': 3.0, 'Z_mm': 2.0}},
            'F01 Deck', include_destination_loads=False,
            manual_pair_override=True, placement_mode='single',
        )
        self.assertTrue(result['ok'], result['issues'].to_dict('records'))
        helper = result['support_rows_df'].iloc[0]
        self.assertEqual((helper['X_mm'], helper['Y_mm'], helper['Z_mm']), (20.0, 3.0, 0.0))

    def test_bundle_is_one_logical_unit_not_a_required_pair(self):
        loads, decks, parts, options, stock, standards, settings = multi_fixture()
        bundle = loads.iloc[0].copy()
        bundle['Typ'] = 'Bund'
        bundle['Einheit_ID'] = 'BUNDLE_AB'
        bundle['Bauteile_Liste'] = 'A|B'
        bundle['Bauteile'] = 'A / B'
        bundle['Höhe_mm'] = 4.0
        bundle['Gewicht_kg'] = 20.0
        loads = pd.concat([loads.iloc[2:], pd.DataFrame([bundle])], ignore_index=True)
        preview = self.preview(
            loads, decks, parts, options, stock, standards, settings, 'A|B', 20.0, 3.0
        )
        self.assertTrue(preview['ok'], preview['issues'].to_dict('records'))
        accepted = app._apply_pinned_manual_replan(
            preview, loads, decks, parts, options, stock,
            {**settings, 'manual_placement_mode': 'single'},
        )
        self.assertTrue(accepted['applied'], accepted['issues'].to_dict('records'))
        self.assertEqual(accepted['pinned_placements_df']['Typ'].tolist(), ['Bund'])
        self.assertEqual(set(app._pinned_manual_identity_labels(accepted['placements_df'])), set('ABCDEFGH'))


if __name__ == '__main__':
    unittest.main()