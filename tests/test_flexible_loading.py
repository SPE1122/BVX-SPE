"""Regression checks for the optional flexible packing module."""
import unittest

import pandas as pd

from verlade_varianten_flex import _width_profiles, _assign_to_stacks, calculate_flexible_loading


def unit(uid, width=600.0, length=1800.0, height=140.0):
    return pd.Series({
        'Einheit_ID': uid, 'Typ': 'Bauteil', 'Anzahl_Bauteile': 1,
        'Länge_mm': length, 'Breite_mm': width, 'Höhe_mm': height,
        'Gewicht_kg': 100.0,
    })


class FlexibleVariantTests(unittest.TestCase):
    def test_mixed_1800_200_has_candidate(self):
        profiles = _width_profiles([unit('A', 1800), unit('B', 200)], 2450, False, True)
        self.assertTrue(any(
            len(p) >= 2 and max(p) >= 1800 and min(p) >= 200
            for p in profiles
        ))

    def test_600_mm_can_share_a_half_lane(self):
        profiles = _width_profiles([unit(str(i)) for i in range(4)], 2450, True, True)
        self.assertTrue(any(len(p) >= 4 for p in profiles))

    def test_two_lanes_are_separate_when_width_mode_off(self):
        profiles = _width_profiles([unit('A', 1200), unit('B', 1200)], 2450, True, False)
        self.assertEqual(profiles, [(1225.0, 1225.0)])
        self.assertEqual(_width_profiles([unit('A', 1800)], 2450, True, False), [])

    def test_no_stacking_when_disabled(self):
        records = [unit('A'), unit('B'), unit('C'), unit('D'), unit('E')]
        stacks = _assign_to_stacks(records, (1225.0, 1225.0),
                                  7600.0, 2800.0, 80.0, 100.0,
                                  40.0, 0.0, 'hoehe', False)
        self.assertIsNone(stacks)

    def test_bauteil_not_mistaken_for_helper(self):
        records = pd.DataFrame([unit('A'), unit('B')])
        platform = pd.Series({
            'Pritsche': 'T', 'Länge_mm': 7600.0, 'Breite_mm': 2450.0,
            'Max_Höhe_mm': 2800.0, 'Max_Gewicht_kg': 20000.0,
            'Eigengewicht_Pritsche_kg': 0.0,
            'Überhang_hinten_mm': 0.0, 'Überhang_vorne_mm': 0.0,
            'Kantholz_erste_Lage_mm': 80.0,
            'Einlage_zwischen_Lagen_mm': 40.0, 'Einlage_allgemein_mm': 0.0,
        })
        def init(row, base, layer, gap):
            return {'placements': [], 'Pritsche': 'T'}
        def can_place(*args):
            return True
        def commit(state, part, x, y, z, length, width, height, rotation, mode):
            state['placements'].append({
                'Pritsche': 'T', 'Einheit_ID': part['Einheit_ID'],
                'Typ': part['Typ'], 'X_mm': x, 'Y_mm': y, 'Z_mm': z,
                'Länge_mm': length, 'Breite_mm': width,
                'Höhe_mm': height, 'Gewicht_kg': part['Gewicht_kg'],
            })
        def no_errors(*args):
            return pd.DataFrame()
        rows, summary, reason = calculate_flexible_loading(
            records, platform,
            two_lane=True, flexible_width=False,
            init_platform_state=init, can_place_stable=can_place,
            commit_place=commit, find_geometry_conflicts=no_errors,
            support_chain_issues=no_errors, physical_conflicts=no_errors,
            recompute_summary=lambda df, deck: pd.DataFrame([{'count': len(df)}]),
            load_quality=lambda df, deck: {'score': 1.0},
            base_default=80, layer_default=40, general_default=0,
            gap_default=100, prevent_wide_on_narrow=True,
            min_support_ratio=.35, max_unsupported_length_mm=0,
            max_unsupported_side_mm=0, max_unsupported_length_percent=0,
            max_unsupported_side_percent=0, prefer_support_quality=True,
        )
        self.assertEqual(set(rows['Einheit_ID']), {'A', 'B'})
        self.assertEqual(reason, 'Gültige flexible Anordnung')

    def test_original_module_not_called_when_beside_off(self):
        rows, _, reason = calculate_flexible_loading(
            pd.DataFrame([unit('A')]), pd.Series(),
            two_lane=True, flexible_width=True,
            init_platform_state=lambda *args: None,
            can_place_stable=lambda *args: False,
            commit_place=lambda *args: None,
            find_geometry_conflicts=lambda *args: pd.DataFrame(),
            support_chain_issues=lambda *args: pd.DataFrame(),
            physical_conflicts=lambda *args: pd.DataFrame(),
            recompute_summary=lambda *args: pd.DataFrame(),
            load_quality=lambda *args: {'score': 0.0},
            base_default=80, layer_default=40, general_default=0,
            gap_default=100, prevent_wide_on_narrow=True,
            min_support_ratio=.35, max_unsupported_length_mm=0,
            max_unsupported_side_mm=0, max_unsupported_length_percent=0,
            max_unsupported_side_percent=0, prefer_support_quality=True,
            allow_beside=False,
        )
        self.assertTrue(rows.empty)
        self.assertIn('deaktiviert', reason)


if __name__ == '__main__':
    unittest.main()
