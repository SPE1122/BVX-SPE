import unittest
import pandas as pd
from loading_longitudinal_pairs import build_paired_short_base


class PairedBaseTests(unittest.TestCase):
    def setUp(self):
        parts = []
        for side, y in enumerate((25., 1225.)):
            for level, length, z, rank in (
                (0, 3200., 80., 6-side),
                (1, 3200., 280., 4-side),
                (2, 8000., 480., 2-side),
            ):
                parts.append(dict(
                    Einheit_ID=f'P{side}{level}', Typ='Bauteil',
                    Logische_Reihenfolge_im_Block=rank,
                    X_mm=3000. if level == 2 else 5400.,
                    Y_mm=y, Z_mm=z, Länge_mm=length,
                    Breite_mm=1200., Höhe_mm=200., Ebene='Standard'
                ))
        self.parts = pd.DataFrame(parts)
        self.deck = pd.Series({
            'Länge_mm': 7600., 'Breite_mm': 2450.,
            'Überhang_hinten_mm': 3500., 'Überhang_vorne_mm': 500.,
            'Kantholz_erste_Lage_mm': 80.,
        })

    def test_pair_each_side_and_keep_order(self):
        candidate, reason = build_paired_short_base(self.parts, self.deck, 100.)
        self.assertFalse(candidate.empty, reason)
        self.assertEqual(
            candidate.Logische_Reihenfolge_im_Block.tolist(),
            self.parts.Logische_Reihenfolge_im_Block.tolist()
        )
        for side in range(2):
            pair = candidate.loc[
                candidate.Einheit_ID.isin((f'P{side}0', f'P{side}1'))
            ]
            self.assertEqual(set(pair.Z_mm), {80.})
            self.assertEqual(pair.X_mm.max() - pair.X_mm.min(), 3300.)
            self.assertEqual(
                candidate.loc[
                    candidate.Einheit_ID.eq(f'P{side}2'), 'Z_mm'
                ].iloc[0], 280.
            )

    def test_no_single_side_candidate(self):
        candidate, _ = build_paired_short_base(
            self.parts[self.parts.Y_mm.eq(25.)], self.deck, 100.
        )
        self.assertTrue(candidate.empty)

    def test_no_overlong_candidate(self):
        candidate, _ = build_paired_short_base(self.parts, self.deck, 1700.)
        self.assertTrue(candidate.empty)


if __name__ == '__main__':
    unittest.main()
