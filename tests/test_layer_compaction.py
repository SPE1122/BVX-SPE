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
            'Typ': 'Bauteil',
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
    """Real F02: 47/48 with supports below 43--46 on two upper levels."""
    rows = []
    dimensions = [(3025.0, 1200.0)] * 5 + [(3003.0, 952.0)]
    for offset, (length, width) in enumerate(dimensions):
        number = 43 + offset
        rows.append({
            'Pritsche': 'F02 Anhänger',
            'Einheit_ID': f'BE{number}',
            'Typ': 'Bund',
            'X_mm': (offset % 3) * 3025.0,
            'Y_mm': 0.0,
            'Z_mm': 400.0 if number < 45 else (240.0 if number < 47 else 80.0),
            'Länge_mm': length,
            'Breite_mm': width,
            'Höhe_mm': 160.0,
            'Gewicht_kg': 100.0,
            'Ebene': 'Ausgangslage',
            'Logische_Reihenfolge_im_Block': offset + 1,
        })
    for number in (47, 48):
        parent = next(row for row in rows if row['Einheit_ID'] == f'BE{number}')
        rows.append({
            **parent,
            'Einheit_ID': f'AUFLAGER-BE{number}',
            'Typ': 'Unterbau',
            'Auflager_fuer': f'BE{number}',
            'Auflager_Offset_X_mm': 0.0,
            'Auflager_Offset_Y_mm': 0.0,
            'Z_mm': 0.0,
            'Höhe_mm': 80.0,
            'Gewicht_kg': 0.0,
        })
    return pd.DataFrame(rows)


def atomic_group_with_supported_upper_load() -> pd.DataFrame:
    """Realer Datenpfad: lange obere Last erzeugt nach dem Repack eine neue, aber gültige Tragkante."""
    rows = atomic_six_part_group().to_dict('records')
    rows.extend([
        {
            **rows[0],
            'Einheit_ID': 'BE31',
            'Typ': 'Bund',
            'X_mm': 10800.0,
            'Y_mm': 0.0,
            'Z_mm': 600.0,
            'Länge_mm': 1000.0,
            'Breite_mm': 1000.0,
            'Höhe_mm': 280.0,
            'Logische_Reihenfolge_im_Block': 0,
        },
        {
            **rows[0],
            'Einheit_ID': 'AUFLAGER-BE31',
            'Typ': 'Unterbau',
            'Auflager_fuer': 'BE31',
            'Auflager_Offset_X_mm': 0.0,
            'Auflager_Offset_Y_mm': 0.0,
            'X_mm': 10800.0,
            'Y_mm': 0.0,
            'Z_mm': 520.0,
            'Länge_mm': 1000.0,
            'Breite_mm': 1000.0,
            'Höhe_mm': 80.0,
            'Gewicht_kg': 0.0,
            'Logische_Reihenfolge_im_Block': 0,
        },
    ])
    return pd.DataFrame(rows)


def atomic_group_with_generated_support_on_upper_member() -> pd.DataFrame:
    rows = atomic_six_part_group().to_dict('records')
    parent = next(row for row in rows if row['Einheit_ID'] == 'BE43')
    rows.append({
        **parent,
        'Einheit_ID': 'UBP_BE43_1',
        'Typ': 'Unterbau',
        'Auflager_fuer': 'BE43',
        'Auflager_Offset_X_mm': 0.0,
        'Auflager_Offset_Y_mm': 0.0,
        'X_mm': parent['X_mm'],
        'Y_mm': parent['Y_mm'],
        'Z_mm': 0.0,
        'Höhe_mm': parent['Z_mm'],
        'Gewicht_kg': 0.0,
        'Ebene': 'Auflager bei Verladeplanung',
    })
    return pd.DataFrame(rows)


def one_upper_member_after_first_compaction_stage() -> pd.DataFrame:
    rows = atomic_six_part_group()
    rows = rows[
        rows['Einheit_ID'].isin([f'BE{i}' for i in range(43, 48)])
    ].copy().reset_index(drop=True)
    rows.loc[rows['Typ'].eq('Bund'), 'Z_mm'] = 80.0
    rows.loc[rows['Einheit_ID'].eq('BE43'), 'Z_mm'] = 240.0
    return rows


def real_f02_intermediate_stack() -> pd.DataFrame:
    rows = []
    specs = [
        ('32', 752.0, 25.0, 2480.0, 11748.0, 1200.0, 280.0, 1),
        ('33', 752.0, 25.0, 2200.0, 11748.0, 1200.0, 280.0, 2),
        ('34', 752.0, 25.0, 1920.0, 11748.0, 1200.0, 280.0, 3),
        ('35', 752.0, 25.0, 1640.0, 11748.0, 1200.0, 280.0, 4),
        ('36', 752.0, 25.0, 1360.0, 11748.0, 1200.0, 280.0, 5),
        ('37', 752.0, 25.0, 1080.0, 11748.0, 1200.0, 280.0, 6),
        ('38', 752.0, 25.0, 800.0, 11748.0, 1200.0, 280.0, 7),
        ('39', 752.0, 1225.0, 680.0, 11748.0, 413.8, 280.0, 8),
        ('40', 3632.5, 25.0, 520.0, 7335.0, 1200.0, 280.0, 9),
        ('41', 3632.5, 1225.0, 400.0, 7335.0, 1200.0, 280.0, 10),
        ('42', 3910.1, 632.8, 240.0, 7335.0, 592.2, 280.0, 11),
        ('43', 5206.1, 1225.0, 240.0, 3025.0, 1200.0, 160.0, 12),
        ('44', 7300.0, 1225.0, 80.0, 3025.0, 1200.0, 160.0, 13),
        ('45', 7289.0, 25.0, 80.0, 3025.0, 1200.0, 160.0, 14),
        ('46', 4275.0, 1225.0, 80.0, 3025.0, 1200.0, 160.0, 15),
        ('47', 4286.0, 25.0, 80.0, 3003.0, 1200.0, 160.0, 16),
    ]
    for part, x, y, z, length, width, height, rank in specs:
        rows.append({
            'Bauteile': part,
            'Einheit_ID': f'E{int(part) - 12:04d}',
            'Typ': 'Bauteil',
            'Pritsche': 'F02 Anhänger',
            'X_mm': x,
            'Y_mm': y,
            'Z_mm': z,
            'Länge_mm': length,
            'Breite_mm': width,
            'Höhe_mm': height,
            'Gewicht_kg': length * width * height * 4.5e-7,
            'Logische_Reihenfolge_im_Block': rank,
            'Ebene': 'realer F02 Zwischenstand',
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
    def test_compact_mode_uses_safe_multilayer_support_floor_only_when_enabled(self):
        self.assertEqual(0.30, app._effective_multilayer_support_ratio(0.30, False))
        self.assertEqual(0.35, app._effective_multilayer_support_ratio(0.30, True))
        self.assertEqual(0.40, app._effective_multilayer_support_ratio(0.40, True))

    def test_upper_single_stack_is_centered_above_paired_lower_layer(self):
        platform = pd.DataFrame([{
            'Pritsche': 'F02',
            'Länge_mm': 10000.0,
            'Breite_mm': 2400.0,
            'Max_Höhe_mm': 4000.0,
            'Überhang_vorne_mm': 0.0,
            'Überhang_hinten_mm': 0.0,
            'Kantholz_erste_Lage_mm': 0.0,
            'Mindest_Stützbreite_%': 30.0,
        }])
        rows = pd.DataFrame([
            {'Pritsche': 'F02', 'Einheit_ID': '38', 'Typ': 'Einzelteil', 'X_mm': 0.0, 'Y_mm': 1200.0, 'Z_mm': 280.0, 'Länge_mm': 9000.0, 'Breite_mm': 1200.0, 'Höhe_mm': 280.0, 'Gewicht_kg': 1000.0},
            {'Pritsche': 'F02', 'Einheit_ID': '40', 'Typ': 'Einzelteil', 'X_mm': 5000.0, 'Y_mm': 0.0, 'Z_mm': 280.0, 'Länge_mm': 4000.0, 'Breite_mm': 1200.0, 'Höhe_mm': 280.0, 'Gewicht_kg': 500.0},
            {'Pritsche': 'F02', 'Einheit_ID': '37', 'Typ': 'Einzelteil', 'X_mm': 0.0, 'Y_mm': 1200.0, 'Z_mm': 560.0, 'Länge_mm': 9000.0, 'Breite_mm': 1200.0, 'Höhe_mm': 280.0, 'Gewicht_kg': 1000.0},
            {'Pritsche': 'F02', 'Einheit_ID': '36', 'Typ': 'Einzelteil', 'X_mm': 0.0, 'Y_mm': 1200.0, 'Z_mm': 840.0, 'Länge_mm': 9000.0, 'Breite_mm': 1200.0, 'Höhe_mm': 280.0, 'Gewicht_kg': 1000.0},
        ])

        after = app.center_upper_single_stacks_laterally(rows, platform)

        self.assertEqual(600.0, float(after.loc[after['Einheit_ID'].eq('37'), 'Y_mm'].iloc[0]))
        self.assertEqual(600.0, float(after.loc[after['Einheit_ID'].eq('36'), 'Y_mm'].iloc[0]))
        self.assertEqual(1200.0, float(after.loc[after['Einheit_ID'].eq('38'), 'Y_mm'].iloc[0]))
        self.assertTrue(app.find_geometry_conflicts(after, platform).empty)

    def test_early_narrow_filler_is_promoted_beside_top_member(self):
        platform = pd.DataFrame([{
            'Pritsche': 'F02',
            'Länge_mm': 10000.0,
            'Breite_mm': 2400.0,
            'Max_Höhe_mm': 2480.0,
            'Überhang_vorne_mm': 0.0,
            'Überhang_hinten_mm': 0.0,
            'Kantholz_erste_Lage_mm': 0.0,
            'Mindest_Stützbreite_%': 30.0,
        }])
        rows = [
            {'Bauteile': '38', 'Y_mm': 0.0, 'Z_mm': 0.0, 'Breite_mm': 1200.0},
            {'Bauteile': '40', 'Y_mm': 1200.0, 'Z_mm': 0.0, 'Breite_mm': 1200.0},
            {'Bauteile': '37', 'Y_mm': 0.0, 'Z_mm': 280.0, 'Breite_mm': 1200.0},
            {'Bauteile': '31', 'Y_mm': 1200.0, 'Z_mm': 280.0, 'Breite_mm': 400.0},
            {'Bauteile': '36', 'Y_mm': 600.0, 'Z_mm': 560.0, 'Breite_mm': 1200.0},
            {'Bauteile': '35', 'Y_mm': 600.0, 'Z_mm': 840.0, 'Breite_mm': 1200.0},
            {'Bauteile': '34', 'Y_mm': 600.0, 'Z_mm': 1120.0, 'Breite_mm': 1200.0},
            {'Bauteile': '33', 'Y_mm': 600.0, 'Z_mm': 1400.0, 'Breite_mm': 1200.0},
            {'Bauteile': '32', 'Y_mm': 600.0, 'Z_mm': 1680.0, 'Breite_mm': 1200.0},
        ]
        placements = pd.DataFrame([
            {
                'Pritsche': 'F02',
                'Einheit_ID': str(row['Bauteile']),
                'Typ': 'Einzelteil',
                'X_mm': 0.0,
                'Länge_mm': 9000.0,
                'Höhe_mm': 280.0,
                'Gewicht_kg': 1000.0,
                **row,
            }
            for row in rows
        ])

        after = app.promote_early_narrow_fillers_to_top(placements, platform)
        part31 = after[after['Bauteile'].eq('31')].iloc[0]
        part32 = after[after['Bauteile'].eq('32')].iloc[0]

        self.assertEqual(float(part32['Z_mm']), float(part31['Z_mm']))
        edge_gap = min(
            abs(float(part31['Y_mm']) + float(part31['Breite_mm']) - float(part32['Y_mm'])),
            abs(float(part32['Y_mm']) + float(part32['Breite_mm']) - float(part31['Y_mm'])),
        )
        self.assertLessEqual(edge_gap, 0.1)
        self.assertTrue(app.find_geometry_conflicts(after, platform).empty)
        _underbau, warnings = app.calculate_underbau_rows_for_platform(after, platform.iloc[0], min_support_ratio=0.35)
        self.assertTrue(warnings.empty)

    def test_upper_31_to_37_group_is_repacked_into_four_compact_rows(self):
        platform = pd.DataFrame([{
            'Pritsche': 'F02',
            'Länge_mm': 10000.0,
            'Breite_mm': 2400.0,
            'Max_Höhe_mm': 2480.0,
            'Überhang_vorne_mm': 0.0,
            'Überhang_hinten_mm': 0.0,
            'Kantholz_erste_Lage_mm': 0.0,
            'Mindest_Stützbreite_%': 30.0,
        }])
        specs = [
            ('38', 0.0, 0.0, 1200.0), ('40', 1200.0, 0.0, 1200.0),
            ('37', 0.0, 280.0, 1200.0), ('31', 1200.0, 280.0, 400.0),
            ('36', 600.0, 560.0, 1200.0), ('35', 600.0, 840.0, 1200.0),
            ('34', 600.0, 1120.0, 1200.0), ('33', 600.0, 1400.0, 1200.0),
            ('32', 600.0, 1680.0, 1200.0),
        ]
        placements = pd.DataFrame([
            {
                'Pritsche': 'F02', 'Einheit_ID': number, 'Bauteile': number,
                'Typ': 'Einzelteil', 'X_mm': 0.0, 'Y_mm': y, 'Z_mm': z,
                'Länge_mm': 9000.0, 'Breite_mm': width, 'Höhe_mm': 280.0,
                'Gewicht_kg': width, 'Logische_Reihenfolge_im_Block': int(number) - 30,
            }
            for number, y, z, width in specs
        ])

        promoted = app.promote_early_narrow_fillers_to_top(placements, platform)
        after = app.repack_upper_ranked_rows_compactly(promoted, platform)
        by_part = after.set_index('Bauteile')

        self.assertEqual(float(by_part.loc['31', 'Z_mm']), float(by_part.loc['32', 'Z_mm']))
        self.assertEqual(float(by_part.loc['33', 'Z_mm']), float(by_part.loc['34', 'Z_mm']))
        self.assertEqual(float(by_part.loc['35', 'Z_mm']), float(by_part.loc['36', 'Z_mm']))
        self.assertLess(float(by_part.loc['37', 'Z_mm']), float(by_part.loc['36', 'Z_mm']))
        self.assertLess(
            float((after['Z_mm'] + after['Höhe_mm']).max()),
            float((placements['Z_mm'] + placements['Höhe_mm']).max()),
        )
        self.assertTrue(app.find_geometry_conflicts(after, platform).empty)
        _underbau, warnings = app.calculate_underbau_rows_for_platform(
            after, platform.iloc[0], min_support_ratio=0.35
        )
        self.assertTrue(warnings.empty)

    def test_assignment_control_ignores_numbers_absent_from_input(self):
        placements = pd.DataFrame([
            {
                'Pritsche': 'F01 Auflieger',
                'Bauteile': str(number),
                'Bauteile_Liste': str(number),
                'Gewicht_kg': 100.0,
            }
            for number in list(range(1, 13)) + list(range(21, 27))
        ])
        platforms = pd.DataFrame([{'Pritsche': 'F01 Auflieger'}])

        control = app.build_control_assignment_table(placements, platforms)

        self.assertEqual('', control.iloc[0]['Fehlende_Nummern_innerhalb_Bereich'])

    def test_assignment_control_reports_existing_number_on_other_platform(self):
        placements = pd.DataFrame([
            {'Pritsche': 'F01 Auflieger', 'Bauteile': '1', 'Bauteile_Liste': '1', 'Gewicht_kg': 100.0},
            {'Pritsche': 'F02 Auflieger', 'Bauteile': '2', 'Bauteile_Liste': '2', 'Gewicht_kg': 100.0},
            {'Pritsche': 'F01 Auflieger', 'Bauteile': '3', 'Bauteile_Liste': '3', 'Gewicht_kg': 100.0},
        ])
        platforms = pd.DataFrame([
            {'Pritsche': 'F01 Auflieger'},
            {'Pritsche': 'F02 Auflieger'},
        ])

        control = app.build_control_assignment_table(placements, platforms)

        self.assertEqual('2', control.iloc[0]['Fehlende_Nummern_innerhalb_Bereich'])

    def test_atomic_shelf_repack_fits_five_3025_and_one_3003_as_3x2(self):
        platform = f02_platform()
        platform.loc[0, ['Länge_mm', 'Überhang_vorne_mm', 'Überhang_hinten_mm']] = [
            7500.0, 1500.0, 2961.0,
        ]
        before = atomic_six_part_group()
        before_cog = app._load_center_of_gravity_values_for_platform(before, platform.iloc[0])

        after, _summary = app.apply_main_loading_postprocess(
            before, None, platform, gap_mm=0.0, center_geometric=True,
            enable_multilayer_compaction=True, bundles_only_compaction=True,
        )
        after_cog = app._load_center_of_gravity_values_for_platform(after, platform.iloc[0])
        loads = after[after['Typ'].eq('Bund')]

        self.assertTrue((loads['Z_mm'] == 80.0).all())
        self.assertEqual(0, len(app.find_geometry_conflicts(loads, platform)))
        self.assertTrue(loads['Ebene'].astype(str).str.contains('atomar verdichtet').all())
        self.assertListEqual(
            before.loc[before['Typ'].eq('Bund'), 'Logische_Reihenfolge_im_Block'].tolist(),
            loads['Logische_Reihenfolge_im_Block'].tolist(),
        )
        for number in (47, 48):
            parent = after.loc[after['Einheit_ID'].eq(f'BE{number}')].iloc[0]
            support = after.loc[after['Einheit_ID'].eq(f'AUFLAGER-BE{number}')].iloc[0]
            self.assertEqual(float(parent['X_mm']), float(support['X_mm']))
            self.assertEqual(float(parent['Y_mm']), float(support['Y_mm']))
            self.assertGreaterEqual(float(parent['Z_mm']), float(support['Z_mm']) + float(support['Höhe_mm']))
        self.assertLessEqual(
            abs(after_cog['Schwerpunkt_Abstand_X_mm']),
            abs(before_cog['Schwerpunkt_Abstand_X_mm']) + 1.0,
        )
        self.assertLessEqual(
            abs(after_cog['Schwerpunkt_Abstand_Y_mm']),
            abs(before_cog['Schwerpunkt_Abstand_Y_mm']) + 1.0,
        )

    def test_atomic_repack_allows_order_correct_new_support_below_existing_upper_load(self):
        platform = f02_platform()
        platform.loc[0, ['Länge_mm', 'Überhang_vorne_mm', 'Überhang_hinten_mm']] = [
            7500.0, 1500.0, 2961.0,
        ]
        before = atomic_group_with_supported_upper_load()

        after = app.compact_placements_conservatively(before, platform)
        compacted = after[after['Einheit_ID'].isin([f'BE{i}' for i in range(43, 49)])]
        upper = after.loc[after['Einheit_ID'].eq('BE31')].iloc[0]

        self.assertTrue((compacted['Z_mm'] == 80.0).all())
        self.assertEqual(0, len(app.find_geometry_conflicts(
            after[after['Typ'].eq('Bauteil')], platform
        )))
        self.assertTrue(any(
            app._axis_overlap_mm(
                upper['X_mm'],
                upper['X_mm'] + upper['Länge_mm'],
                lower['X_mm'],
                lower['X_mm'] + lower['Länge_mm'],
            ) > 0
            and app._axis_overlap_mm(
                upper['Y_mm'],
                upper['Y_mm'] + upper['Breite_mm'],
                lower['Y_mm'],
                lower['Y_mm'] + lower['Breite_mm'],
            ) > 0
            for _, lower in compacted.iterrows()
        ))

    def test_lowering_removes_obsolete_generated_support_but_keeps_new_position_safe(self):
        platform = f02_platform()
        platform.loc[0, ['Länge_mm', 'Überhang_vorne_mm', 'Überhang_hinten_mm']] = [
            7500.0, 1500.0, 2961.0,
        ]
        before = atomic_group_with_generated_support_on_upper_member()

        after = app.compact_placements_conservatively(before, platform)
        compacted = after[after['Einheit_ID'].isin([f'BE{i}' for i in range(43, 49)])]

        self.assertTrue((compacted['Z_mm'] == 80.0).all())
        self.assertFalse(after['Einheit_ID'].astype(str).eq('UBP_BE43_1').any())
        self.assertEqual(0, len(app.find_geometry_conflicts(compacted, platform)))

    def test_last_single_upper_member_is_included_in_cascade(self):
        platform = f02_platform()
        platform.loc[0, ['Länge_mm', 'Überhang_vorne_mm', 'Überhang_hinten_mm']] = [
            7500.0, 1500.0, 2961.0,
        ]
        before = one_upper_member_after_first_compaction_stage()

        after = app.compact_placements_conservatively(before, platform)

        self.assertTrue((after.loc[after['Typ'].eq('Bund'), 'Z_mm'] == 80.0).all())
        self.assertEqual(0, len(app.find_geometry_conflicts(
            after[after['Typ'].eq('Bund')], platform
        )))

    def test_real_f02_stack_lowers_43_with_42_still_present(self):
        before = real_f02_intermediate_stack()
        platform = f02_platform()
        platform.loc[0, [
            'Länge_mm',
            'Breite_mm',
            'Überhang_vorne_mm',
            'Überhang_hinten_mm',
        ]] = [7600.0, 2450.0, 1400.0, 3500.0]

        after = app.compact_placements_conservatively(before, platform)

        compact_group = after[after['Bauteile'].astype(str).isin(
            ['43', '44', '45', '46', '47']
        )]
        self.assertTrue((compact_group['Z_mm'] == 80.0).all())
        self.assertEqual(0, len(app.find_geometry_conflicts(
            after[after['Typ'].eq('Bund')], platform
        )))

    def test_cross_layer_cascade_pairs_narrow_units_and_moves_upper_load_forward(self):
        before = real_f02_intermediate_stack()
        platform = f02_platform()
        platform.loc[0, [
            'Länge_mm', 'Breite_mm', 'Überhang_vorne_mm', 'Überhang_hinten_mm',
        ]] = [7600.0, 2450.0, 1400.0, 3500.0]
        old_40_x = float(before.loc[before['Bauteile'].eq('40'), 'X_mm'].iloc[0])

        after = app.compact_placements_conservatively(before, platform)

        row_39 = after.loc[after['Bauteile'].eq('39')].iloc[0]
        row_38 = after.loc[after['Bauteile'].eq('38')].iloc[0]
        row_40 = after.loc[after['Bauteile'].eq('40')].iloc[0]
        row_41 = after.loc[after['Bauteile'].eq('41')].iloc[0]
        row_37 = after.loc[after['Bauteile'].eq('37')].iloc[0]
        row_42 = after.loc[after['Bauteile'].eq('42')].iloc[0]
        self.assertEqual(float(row_39['Z_mm']), float(row_42['Z_mm']))
        self.assertTrue(
            abs(float(row_39['Y_mm'] + row_39['Breite_mm']) - float(row_42['Y_mm'])) <= 0.1
            or abs(float(row_42['Y_mm'] + row_42['Breite_mm']) - float(row_39['Y_mm'])) <= 0.1
        )
        narrow_y0 = min(float(row_39['Y_mm']), float(row_42['Y_mm']))
        narrow_y1 = max(
            float(row_39['Y_mm'] + row_39['Breite_mm']),
            float(row_42['Y_mm'] + row_42['Breite_mm']),
        )
        self.assertFalse(narrow_y0 + 0.1 < float(row_41['Y_mm']) < narrow_y1 - 0.1)
        self.assertEqual(float(row_39['Z_mm'] + row_39['Höhe_mm']), float(row_38['Z_mm']))
        self.assertEqual(float(row_38['Z_mm']), float(row_40['Z_mm']))
        self.assertTrue(
            float(row_38['Y_mm']) + float(row_38['Breite_mm']) <= float(row_40['Y_mm'])
            or float(row_40['Y_mm']) + float(row_40['Breite_mm']) <= float(row_38['Y_mm'])
        )
        self.assertGreater(float(row_40['X_mm']), old_40_x)
        self.assertLess(
            float(row_37['Z_mm']),
            float(before.loc[before['Bauteile'].eq('37'), 'Z_mm'].iloc[0]),
        )
        self.assertEqual(0, len(app.find_geometry_conflicts(after, platform)))

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
        self.assertTrue(
            float(row_39['Y_mm']) + float(row_39['Breite_mm']) <= float(row_42['Y_mm'])
            or float(row_42['Y_mm']) + float(row_42['Breite_mm']) <= float(row_39['Y_mm'])
        )
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

    def test_f01_terminal_profile_group_is_compacted_as_complete_six_unit_block(self):
        platform = f02_platform()
        platform.loc[0, 'Pritsche'] = 'F01 Auflieger'
        platform.loc[0, ['Länge_mm', 'Überhang_vorne_mm', 'Überhang_hinten_mm']] = [
            7500.0, 1500.0, 2961.0,
        ]
        rows = []
        for number in range(21, 27):
            offset = number - 21
            rows.append({
                'Pritsche': 'F01 Auflieger',
                'Einheit_ID': f'B{number}',
                'Bauteile': str(number),
                'Typ': 'Bund',
                'Profil': 'P-120',
                'X_mm': (offset % 3) * 3025.0,
                'Y_mm': 0.0,
                'Z_mm': 400.0 if number < 23 else (240.0 if number < 25 else 80.0),
                'Länge_mm': 3025.0 if number < 26 else 3003.0,
                'Breite_mm': 1200.0 if number < 26 else 952.0,
                'Höhe_mm': 160.0,
                'Gewicht_kg': 100.0,
                'Logische_Reihenfolge_im_Block': offset + 1,
                'Ebene': 'Profilblock 21-26',
            })
        before = pd.DataFrame(rows)

        after = app.compact_placements_conservatively(before, platform, bundles_only=True)

        terminal = after[after['Bauteile'].astype(str).isin([str(n) for n in range(21, 27)])]
        self.assertEqual(6, len(terminal))
        self.assertTrue((terminal['Z_mm'] == 80.0).all())
        terminal_x0 = float(terminal['X_mm'].min())
        terminal_x1 = float((terminal['X_mm'] + terminal['Länge_mm']).max())
        own_rear = terminal_x0 - float(platform.iloc[0]['Überhang_hinten_mm'])
        own_front = (
            float(platform.iloc[0]['Länge_mm'])
            + float(platform.iloc[0]['Überhang_hinten_mm'])
            + float(platform.iloc[0]['Überhang_vorne_mm'])
            - terminal_x1
            - float(platform.iloc[0]['Überhang_vorne_mm'])
        )
        self.assertLessEqual(abs(own_rear - own_front), 1.0)
        self.assertEqual(0, len(app.find_geometry_conflicts(after, platform)))

    def test_complete_31_to_48_profile_stack_cascades_from_terminal_six_base(self):
        platform = f02_platform()
        platform.loc[0, ['Länge_mm', 'Breite_mm', 'Max_Höhe_mm']] = [6000.0, 1200.0, 600.0]
        rows = []
        for number in range(31, 49):
            offset = (number - 31) % 6
            # 31--36 and 37--42 are two dependent shelves above the
            # terminal 43--48 profile group.  The original stack exceeds the
            # limit by one layer; the complete cascade must save that layer.
            z = 720.0 if number <= 36 else (560.0 if number <= 42 else (400.0 if number <= 44 else (240.0 if number <= 46 else 80.0)))
            rows.append({
                'Pritsche': 'F02 Anhänger', 'Einheit_ID': f'B{number}',
                'Bauteile': str(number), 'Typ': 'Bund',
                'Profil': 'TERMINAL-PROFIL' if number >= 43 else 'OBERE-LAST',
                'X_mm': (offset % 3) * 1000.0, 'Y_mm': (offset // 3) * 600.0,
                'Z_mm': z, 'Länge_mm': 1000.0, 'Breite_mm': 600.0,
                'Höhe_mm': 160.0, 'Gewicht_kg': 100.0,
                'Logische_Reihenfolge_im_Block': number - 30,
                'Ebene': 'vollständiger Profilblock 31-48',
            })
        before = pd.DataFrame(rows)

        after = app.compact_placements_conservatively(before, platform, bundles_only=True)

        terminal = after[after['Bauteile'].astype(str).isin([str(n) for n in range(43, 49)])]
        self.assertTrue((terminal['Z_mm'] == 80.0).all())
        self.assertLessEqual(float((after['Z_mm'] + after['Höhe_mm']).max()), 600.0)
        self.assertEqual(0, len(app.find_geometry_conflicts(after, platform)))

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