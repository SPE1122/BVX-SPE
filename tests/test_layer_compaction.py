import unittest

import pandas as pd

import bvx_auswertung_streamlit as app


def f02_platform() -> pd.DataFrame:
    return pd.DataFrame([{
        'Pritsche': 'F02 Anhänger',
        'Pritschenname': 'Anhänger',
        'Fuhrenoption': 'LKW mit Anhänger',
        'Fuhre_Nr': 2,
        'Länge_mm': 6000.0,
        'Breite_mm': 2400.0,
        'Max_Höhe_mm': 3000.0,
        'Überhang_vorne_mm': 0.0,
        'Überhang_hinten_mm': 0.0,
        'Max_Gewicht_kg': 20000.0,
        'Eigengewicht_Pritsche_kg': 0.0,
        'Kantholz_erste_Lage_mm': 80.0,
        'Einlage_zwischen_Lagen_mm': 0.0,
        'Einlage_allgemein_mm': 0.0,
        'Drehen_90_erlaubt': False,
        'Runge_aktiv': False,
        'Mindest_Stützbreite_%': 35.0,
    }])


def f02_groups_37_to_48() -> pd.DataFrame:
    rows = []
    for number in range(43, 49):
        offset = number - 43
        rows.append({
            'Pritsche': 'F02 Anhänger',
            'Einheit_ID': f'BE{number}',
            'Typ': 'Bund',
            'X_mm': (offset % 3) * 2000.0,
            'Y_mm': (offset // 3) * 600.0,
            'Z_mm': 80.0,
            'Länge_mm': 1000.0,
            'Breite_mm': 600.0,
            'Höhe_mm': 200.0,
            'Gewicht_kg': 100.0,
            'Ebene': 'untere Gruppe 43-48',
            'Logische_Reihenfolge_im_Block': number - 36,
        })
    for number in range(37, 43):
        offset = number - 37
        rows.append({
            'Pritsche': 'F02 Anhänger',
            'Einheit_ID': f'BE{number}',
            'Typ': 'Bund',
            'X_mm': (offset % 3) * 2000.0,
            'Y_mm': (offset // 3) * 600.0,
            'Z_mm': 280.0,
            'Länge_mm': 1000.0,
            'Breite_mm': 600.0,
            'Höhe_mm': 200.0,
            'Gewicht_kg': 100.0,
            'Ebene': 'obere Gruppe 37-42',
            'Logische_Reihenfolge_im_Block': number - 36,
        })
    return pd.DataFrame(rows)


def atomic_six_part_group() -> pd.DataFrame:
    """Real-F02-shaped topology: target plus two adjacent source levels."""
    rows = []
    dimensions = [(3025.0, 1200.0)] * 5 + [(3003.0, 952.0)]
    for offset, (length, width) in enumerate(dimensions):
        rows.append({
            'Pritsche': 'F02 Anhänger',
            'Einheit_ID': f'BE{43 + offset}',
            'Typ': 'Bund',
            'X_mm': (offset % 3) * 3025.0,
            'Y_mm': 0.0,
            # Two parts are already on the target level.  The regression is
            # only solved when they are shuffled with both upper levels.
            'Z_mm': 80.0 if offset < 2 else (280.0 if offset < 4 else 480.0),
            'Länge_mm': length,
            'Breite_mm': width,
            'Höhe_mm': 200.0,
            'Gewicht_kg': 100.0,
            'Ebene': 'Ausgangslage',
            'Logische_Reihenfolge_im_Block': offset + 1,
        })
    return pd.DataFrame(rows)


def f02_side_by_side_release_group() -> pd.DataFrame:
    rows = []
    for number, y, z in [(39, 0.0, 80.0), (42, 1200.0, 80.0), (38, 600.0, 280.0)]:
        rows.append({
            'Pritsche': 'F02 Anhänger',
            'Einheit_ID': f'BE{number}',
            'Typ': 'Bund',
            'X_mm': 2000.0,
            'Y_mm': y,
            'Z_mm': z,
            'Länge_mm': 1000.0,
            'Breite_mm': 600.0,
            'Höhe_mm': 200.0,
            'Gewicht_kg': 100.0,
            'Ebene': 'F02 Freigabe',
            'Logische_Reihenfolge_im_Block': number,
        })
    support = {
        **rows[0],
        'Einheit_ID': 'AUFLAGER-BE39',
        'Typ': 'Unterbau',
        'Auflager_fuer': 'BE39',
        'Z_mm': 0.0,
        'Höhe_mm': 80.0,
    }
    return pd.DataFrame(rows + [support])


class LayerCompactionTest(unittest.TestCase):
    def test_atomic_shelf_repack_fits_five_3025_and_one_3003_as_3x2(self):
        platform = f02_platform()
        platform.loc[0, 'Länge_mm'] = 9250.0
        before = atomic_six_part_group()
        before_cog = app._load_center_of_gravity_values_for_platform(before, platform.iloc[0])

        after = app.compact_placements_conservatively(before, platform)
        after_cog = app._load_center_of_gravity_values_for_platform(after, platform.iloc[0])

        self.assertTrue((after['Z_mm'] == 80.0).all())
        self.assertEqual(0, len(app.find_geometry_conflicts(after, platform)))
        self.assertTrue(after['Ebene'].astype(str).str.contains('atomar verdichtet').all())
        self.assertListEqual(
            before['Logische_Reihenfolge_im_Block'].tolist(),
            after['Logische_Reihenfolge_im_Block'].tolist(),
        )
        self.assertLessEqual(
            abs(after_cog['Schwerpunkt_Abstand_X_mm']),
            abs(before_cog['Schwerpunkt_Abstand_X_mm']) + 1.0,
        )
        self.assertLessEqual(
            abs(after_cog['Schwerpunkt_Abstand_Y_mm']),
            abs(before_cog['Schwerpunkt_Abstand_Y_mm']) + 1.0,
        )

    def test_f02_side_by_side_release_keeps_attached_support_and_lowers_38(self):
        platform = f02_platform()
        before = f02_side_by_side_release_group()
        before_cog = app._load_center_of_gravity_values_for_platform(before, platform.iloc[0])

        after = app.compact_placements_conservatively(before, platform)
        after_cog = app._load_center_of_gravity_values_for_platform(after, platform.iloc[0])
        row_38 = after.loc[after['Einheit_ID'].eq('BE38')].iloc[0]
        row_39 = after.loc[after['Einheit_ID'].eq('BE39')].iloc[0]
        row_42 = after.loc[after['Einheit_ID'].eq('BE42')].iloc[0]
        support = after.loc[after['Einheit_ID'].eq('AUFLAGER-BE39')].iloc[0]

        self.assertEqual(80.0, float(row_38['Z_mm']))
        self.assertEqual(float(row_39['Z_mm']), float(row_42['Z_mm']))
        self.assertLessEqual(float(row_39['Y_mm']) + float(row_39['Breite_mm']), float(row_42['Y_mm']))
        self.assertFalse(app._boxes_overlap_3d(app._row_box_values(row_39), app._row_box_values(support), tol=1.0))
        self.assertEqual(0, len(app.find_geometry_conflicts(
            after[after['Typ'].eq('Bund')], platform
        )))
        self.assertLessEqual(
            abs(after_cog['Schwerpunkt_Abstand_X_mm']),
            abs(before_cog['Schwerpunkt_Abstand_X_mm']) + 1.0,
        )
        self.assertLessEqual(
            abs(after_cog['Schwerpunkt_Abstand_Y_mm']),
            abs(before_cog['Schwerpunkt_Abstand_Y_mm']) + 1.0,
        )

    def test_atomic_shelf_repack_rejects_insufficient_lateral_width(self):
        platform = f02_platform()
        platform.loc[0, 'Länge_mm'] = 9250.0
        platform.loc[0, 'Breite_mm'] = 2399.0
        before = atomic_six_part_group()

        after = app.compact_placements_conservatively(before, platform)

        # A 3x2 shelf needs two 1200-mm shelf widths.  Greedy single moves
        # may still make a safe local improvement, but the atomic 3x2 state
        # must never be accepted beyond the effective platform width.
        self.assertFalse(after['Ebene'].astype(str).str.contains('atomar verdichtet').any())
        self.assertFalse((after['Z_mm'] == 80.0).all())

    def test_f02_groups_use_free_xy_area_without_losing_order_or_support(self):
        platform = f02_platform()
        before = f02_groups_37_to_48()
        before_cog = app._load_center_of_gravity_values_for_platform(before, platform.iloc[0])

        after = app.compact_adjacent_loading_layers(before, platform)
        after_cog = app._load_center_of_gravity_values_for_platform(after, platform.iloc[0])

        self.assertEqual(set(before['Einheit_ID']), set(after['Einheit_ID']))
        self.assertLess(float(after['Z_mm'].sum()), float(before['Z_mm'].sum()))
        self.assertEqual(0, len(app.find_geometry_conflicts(after, platform)))
        self.assertTrue(after['Ebene'].astype(str).str.contains('Lagen kaskadiert verdichtet').any())
        self.assertLessEqual(
            abs(after_cog['Schwerpunkt_Abstand_X_mm']),
            abs(before_cog['Schwerpunkt_Abstand_X_mm']) + 1.0,
        )
        self.assertLessEqual(
            abs(after_cog['Schwerpunkt_Abstand_Y_mm']),
            abs(before_cog['Schwerpunkt_Abstand_Y_mm']) + 1.0,
        )

    def test_compaction_rejects_variant_when_no_supported_free_area_exists(self):
        platform = f02_platform()
        before = f02_groups_37_to_48()
        before['Breite_mm'] = 1200.0
        upper = before['Einheit_ID'].isin([f'BE{i}' for i in range(37, 43)])
        before.loc[upper, 'Y_mm'] = (
            (before.loc[upper, 'Logische_Reihenfolge_im_Block'] - 1) // 3 * 1200.0
        )

        after = app.compact_adjacent_loading_layers(before, platform)

        pd.testing.assert_frame_equal(
            before[['X_mm', 'Y_mm', 'Z_mm']],
            after[['X_mm', 'Y_mm', 'Z_mm']],
            check_dtype=False,
        )

    def test_unit_with_generated_support_is_not_moved(self):
        platform = f02_platform()
        before = f02_groups_37_to_48()
        supported_id = 'BE37'
        supported_before = before.loc[before['Einheit_ID'].eq(supported_id), ['X_mm', 'Y_mm', 'Z_mm']].copy()
        support = {
            **before.iloc[0].to_dict(),
            'Einheit_ID': 'AUFLAGER-BE37',
            'Typ': 'Unterbau',
            'Auflager_fuer': supported_id,
            'X_mm': 0.0,
            'Y_mm': 0.0,
            'Z_mm': 80.0,
            'Länge_mm': 1000.0,
            'Breite_mm': 600.0,
            'Höhe_mm': 200.0,
            'Gewicht_kg': 0.0,
        }
        before = pd.concat([before, pd.DataFrame([support])], ignore_index=True)

        after = app.compact_adjacent_loading_layers(before, platform)
        supported_after = after.loc[after['Einheit_ID'].eq(supported_id), ['X_mm', 'Y_mm', 'Z_mm']].copy()

        pd.testing.assert_frame_equal(
            supported_before.reset_index(drop=True),
            supported_after.reset_index(drop=True),
            check_dtype=False,
        )

    def test_generated_only_support_does_not_block_other_safe_compaction(self):
        platform = f02_platform()
        before = f02_groups_37_to_48().iloc[[0, 6, 7]].copy().reset_index(drop=True)
        before.loc[before['Einheit_ID'].eq('BE37'), ['X_mm', 'Y_mm', 'Z_mm']] = [0.0, 1800.0, 280.0]
        before.loc[before['Einheit_ID'].eq('BE38'), ['X_mm', 'Y_mm', 'Z_mm']] = [2000.0, 0.0, 280.0]
        support = {
            **before.iloc[0].to_dict(),
            'Einheit_ID': 'AUFLAGER-BE37',
            'Typ': 'Unterbau',
            'Auflager_fuer': 'BE37',
            'X_mm': 0.0,
            'Y_mm': 1800.0,
            'Z_mm': 80.0,
            'Länge_mm': 1000.0,
            'Breite_mm': 600.0,
            'Höhe_mm': 200.0,
            'Gewicht_kg': 0.0,
        }
        before = pd.concat([before, pd.DataFrame([support])], ignore_index=True)
        fixed_before = before.loc[before['Einheit_ID'].eq('BE37'), ['X_mm', 'Y_mm', 'Z_mm']].copy()

        after = app.compact_adjacent_loading_layers(before, platform)

        fixed_after = after.loc[after['Einheit_ID'].eq('BE37'), ['X_mm', 'Y_mm', 'Z_mm']].copy()
        pd.testing.assert_frame_equal(
            fixed_before.reset_index(drop=True),
            fixed_after.reset_index(drop=True),
            check_dtype=False,
        )
        self.assertLess(
            float(after.loc[after['Einheit_ID'].eq('BE38'), 'Z_mm'].iloc[0]),
            float(before.loc[before['Einheit_ID'].eq('BE38'), 'Z_mm'].iloc[0]),
        )

    def test_postprocess_keeps_supported_parent_out_of_its_support_body(self):
        platform = f02_platform()
        before = f02_groups_37_to_48()
        supported_id = 'BE37'
        support = {
            **before.iloc[0].to_dict(),
            'Einheit_ID': 'AUFLAGER-BE37',
            'Typ': 'Unterbau',
            'Auflager_fuer': supported_id,
            'X_mm': 0.0,
            'Y_mm': 0.0,
            'Z_mm': 80.0,
            'Länge_mm': 1000.0,
            'Breite_mm': 600.0,
            'Höhe_mm': 200.0,
            'Gewicht_kg': 0.0,
        }
        before = pd.concat([before, pd.DataFrame([support])], ignore_index=True)

        after, _summary = app.apply_main_loading_postprocess(
            before, None, platform, gap_mm=0.0, center_geometric=True
        )
        parent = after.loc[after['Einheit_ID'].eq(supported_id)].iloc[0]
        support_after = after.loc[after['Einheit_ID'].eq('AUFLAGER-BE37')].iloc[0]

        self.assertFalse(
            app._boxes_overlap_3d(
                app._row_box_values(parent),
                app._row_box_values(support_after),
                tol=1.0,
            )
        )
        self.assertGreaterEqual(
            float(parent['Z_mm']),
            float(support_after['Z_mm']) + float(support_after['Höhe_mm']) - 1.0,
        )


if __name__ == '__main__':
    unittest.main()