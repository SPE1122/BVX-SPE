import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pandas as pd

import bvx_auswertung_streamlit as app
import compaction_runtime as runtime


def fixture():
    platform = pd.DataFrame([{
        'Pritsche': 'F01', 'Länge_mm': 5000., 'Breite_mm': 2000.,
        'Max_Höhe_mm': 1000., 'Kantholz_erste_Lage_mm': 0.,
        'Max_Gewicht_kg': 5000., 'Mindest_Stützbreite_%': 35.,
        'Überhang_vorne_mm': 0., 'Überhang_hinten_mm': 0.,
    }])
    rows = pd.DataFrame([{
        'Pritsche': 'F01', 'Einheit_ID': str(i), 'Bauteile': str(i), 'Typ': 'Bund',
        'X_mm': 2000., 'Y_mm': float(i % 2) * 1000., 'Z_mm': float(i // 2) * 100.,
        'Länge_mm': 500., 'Breite_mm': 500., 'Höhe_mm': 100., 'Gewicht_kg': 100.,
        'Logische_Reihenfolge_im_Block': 4 - i, 'Ebene': '',
    } for i in range(4)])
    return rows, platform


class CompactionRuntimeTests(unittest.TestCase):
    def test_deadlines_are_shared_by_repeated_candidates_and_total_budget(self):
        budget = runtime.CompactionBudget(per_platform_seconds=2., total_seconds=3.)
        with patch.object(runtime.time, 'monotonic', return_value=0.):
            self.assertEqual(budget.deadline('F01'), 2.)
        with patch.object(runtime.time, 'monotonic', return_value=1.):
            self.assertEqual(budget.deadline('F01'), 2.)
            self.assertEqual(budget.deadline('F02'), 3.)
        with patch.object(runtime.time, 'monotonic', return_value=2.5):
            self.assertTrue(budget.expired('F01'))
            self.assertFalse(budget.expired('F02'))
            self.assertEqual(budget.deadline('F03'), 3.)
        with patch.object(runtime.time, 'monotonic', return_value=3.):
            self.assertTrue(budget.expired('F02'))
            self.assertTrue(budget.expired('F03'))

    def test_nested_calls_share_budget_and_new_calculation_gets_fresh_budget(self):
        @runtime.with_compaction_budget
        def child():
            return runtime.compaction_budget()

        @runtime.with_compaction_budget
        def parent():
            return runtime.compaction_budget(), child()

        outer, inner = parent()
        self.assertIs(outer, inner)
        self.assertIsNot(outer, parent()[0])
        with self.assertRaises(RuntimeError):
            runtime.compaction_budget()

    def test_exception_cleans_up_and_parallel_requests_are_isolated(self):
        @runtime.with_compaction_budget
        def failing():
            raise ValueError('test')
        with self.assertRaises(ValueError):
            failing()
        with self.assertRaises(RuntimeError):
            runtime.compaction_budget()
        @runtime.with_compaction_budget
        def get_budget():
            return runtime.compaction_budget()
        with ThreadPoolExecutor(max_workers=2) as pool:
            budgets = list(pool.map(lambda _: get_budget(), range(4)))
        self.assertEqual(len({id(budget) for budget in budgets}), 4)

    def test_exhausted_budget_skips_all_optional_stages_and_preserves_coordinates(self):
        rows, platforms = fixture()
        original = rows.copy(deep=True)
        stages = (
            app.compact_adjacent_loading_layers,
            app.compact_placements_conservatively,
            app.center_upper_single_stacks_laterally,
            app.promote_early_narrow_fillers_to_top,
            app.repack_upper_ranked_rows_compactly,
            app.repack_terminal_cascade_deterministically,
        )
        token = runtime._budget.set(runtime.CompactionBudget(total_seconds=0.))
        try:
            with patch.object(app, 'find_geometry_conflicts', side_effect=AssertionError('search after expiry')):
                for stage in stages:
                    result = stage(rows, platforms)
                    pd.testing.assert_frame_equal(
                        result[['Einheit_ID', 'X_mm', 'Y_mm', 'Z_mm']],
                        original[['Einheit_ID', 'X_mm', 'Y_mm', 'Z_mm']],
                        check_dtype=False,
                    )
        finally:
            runtime._budget.reset(token)
        pd.testing.assert_frame_equal(rows, original)
        with patch.object(runtime, 'CompactionBudget', return_value=runtime.CompactionBudget(total_seconds=0.)):
            completed = app.compact_adjacent_loading_layers(rows, platforms)
        self.assertEqual(completed.attrs.get('Verdichtungsbudget_erreicht'), ['F01'])

    def test_expiry_during_validation_does_not_commit_rejected_candidate(self):
        rows, platforms = fixture()
        clock = [0.]
        calls = []
        def reject(*_args, **_kwargs):
            calls.append(1)
            clock[0] = 100.
            return pd.DataFrame([{'Typ': 'Breiten-/Kollisionsprüfung'}])
        with patch.object(runtime.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(app, 'find_geometry_conflicts', side_effect=reject):
            result = app.compact_adjacent_loading_layers(rows, platforms)
        self.assertEqual(len(calls), 1)
        pd.testing.assert_frame_equal(
            result[['Einheit_ID', 'X_mm', 'Y_mm', 'Z_mm']],
            rows[['Einheit_ID', 'X_mm', 'Y_mm', 'Z_mm']],
            check_dtype=False,
        )

    def test_geometry_check_matches_exact_pairwise_reference(self):
        rows, platforms = fixture()
        rows.loc[1, ['X_mm', 'Y_mm', 'Z_mm']] = [2100., 0., 0.]
        rows.loc[2, ['X_mm', 'Y_mm', 'Z_mm']] = [2100., 0., 100.]  # touching, not overlap
        rows = pd.concat([rows, rows.iloc[[0]].assign(
            Typ='Unterbau', Einheit_ID='support',
        ), rows.iloc[[1]].assign(
            Pritsche='NICHT VERLADEN', Einheit_ID='unloaded',
        )], ignore_index=True)
        expected = []
        real = rows[rows.Typ.eq('Bund') & rows.Pritsche.ne('NICHT VERLADEN')]
        for position, (_, first) in enumerate(real.iterrows()):
            for _, second in real.iloc[position + 1:].iterrows():
                if app._boxes_overlap_3d(app._row_box_values(first), app._row_box_values(second)):
                    expected.append(f"{first.Bauteile} / {second.Bauteile}")
        found = app.find_geometry_conflicts(rows, platforms)
        self.assertEqual(found['Einheit_ID'].tolist(), expected)
        self.assertEqual(expected, ['0 / 1'])


if __name__ == '__main__':
    unittest.main()