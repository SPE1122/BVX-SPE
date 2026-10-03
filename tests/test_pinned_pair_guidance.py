import unittest

from pinned_pair_guidance import pair_geometry, x_suggestion


class PairGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.platform = {'Länge_mm': 7600.0, 'Überhang_hinten_mm': 3500.0,
                         'Überhang_vorne_mm': 1400.0}
        self.rows = {'FRONT': {'Länge_mm': 4560.0}, 'REAR': {'Länge_mm': 4560.0}}

    def test_front_flush_values_from_user_case(self):
        self.assertEqual(
            x_suggestion(self.platform, self.rows, 'REAR', 0, 'front_flush'),
            {'REAR': 1980.0, 'FRONT': 6540.0},
        )

    def test_centered_and_gap_values(self):
        self.assertEqual(x_suggestion(self.platform, self.rows, 'REAR', 0, 'centered'),
                         {'REAR': 2740.0, 'FRONT': 7300.0})
        self.assertEqual(x_suggestion(self.platform, self.rows, 'REAR', 440, 'front_flush'),
                         {'REAR': 1540.0, 'FRONT': 6540.0})
        self.assertEqual(x_suggestion(self.platform, self.rows, 'REAR', 440, 'centered'),
                         {'REAR': 2520.0, 'FRONT': 7520.0})

    def test_decimal_metre_input_is_not_silently_converted(self):
        info = pair_geometry(self.platform, self.rows,
                             {'FRONT': {'X_mm': 6.54}, 'REAR': {'X_mm': 1.98}})
        self.assertAlmostEqual(info['overlap'], 4555.44)
        self.assertEqual(info['rear_id'], 'REAR')
        self.assertEqual(info['deck_start'], 3500)
        self.assertEqual(info['effective_end'], 12500)

    def test_actual_overhang_with_front_flush_pair(self):
        values = x_suggestion(self.platform, self.rows, 'REAR', 0, 'front_flush')
        info = pair_geometry(self.platform, self.rows,
                             {uid: {'X_mm': x} for uid, x in values.items()})
        self.assertEqual(info['rear_overhang'], 1520)
        self.assertEqual(info['front_overhang'], 0)
        self.assertEqual(info['gap'], 0)

    def test_unequal_lengths_and_chosen_direction(self):
        rows = {'A': {'Länge_mm': 2000}, 'B': {'Länge_mm': 3000}}
        values = x_suggestion(self.platform, rows, 'B', 100, 'front_flush')
        self.assertEqual(values, {'B': 6000.0, 'A': 9100.0})

    def test_does_not_offer_out_of_bounds_positions(self):
        platform = {**self.platform, 'Überhang_hinten_mm': 100,
                    'Überhang_vorne_mm': 100}
        for mode in ('front_flush', 'centered'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                x_suggestion(platform, self.rows, 'REAR', 0, mode)

    def test_invalid_dimensions_gap_and_duplicate_selection(self):
        for gap in (-1, float('nan')):
            with self.assertRaises(ValueError):
                x_suggestion(self.platform, self.rows, 'REAR', gap, 'centered')
        with self.assertRaises(ValueError):
            x_suggestion(self.platform, {'A': {'Länge_mm': 0}}, 'A', 0, 'front_flush')

    def test_no_overhang_configuration(self):
        rows = {'A': {'Länge_mm': 2000}, 'B': {'Länge_mm': 1000}}
        values = x_suggestion({'Länge_mm': 7600}, rows, 'A', 0, 'front_flush')
        self.assertEqual(values, {'A': 4600.0, 'B': 6600.0})


if __name__ == '__main__':
    unittest.main()