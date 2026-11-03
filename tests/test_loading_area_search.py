import unittest
import pandas as pd

import bvx_auswertung_streamlit as app
from loading_area_search import try_area_layout, pack_area_units, _metrics
from loading_shelf_search import _respects_order
from test_flexible_loading_integration import make_platform


class AreaSearchTests(unittest.TestCase):
    def fixture(self):
        deck = make_platform().iloc[0].copy()
        deck["Überhang_hinten_mm"] = deck["Überhang_vorne_mm"] = 0.
        deck["Länge_mm"] = 7600.
        deck["Mindest_Stützbreite_%"] = 35.
        deck["Einlage_allgemein_mm"] = 0.
        def state():
            return app.init_platform_state(deck, 80., 40., 0.)
        s = state()
        for i in range(4):
            unit = pd.Series(dict(
                Einheit_ID=f"E{i}", Typ="Bauteil", Bauteile=f"E{i}",
                Anzahl_Bauteile=1, Länge_mm=3500., Breite_mm=2300.,
                Höhe_mm=140., Gewicht_kg=100.,
                Logische_Reihenfolge_im_Block=4-i,
            ))
            app.commit_place(s, unit, 2050., 75., 80.+i*140, 3500., 2300., 140., 0, "Original")
        return deck, pd.DataFrame(s["placements"]), state

    def search(self, rows, deck, state, **kwargs):
        def valid(c):
            ds = pd.DataFrame([deck])
            return (app.find_geometry_conflicts(c, ds).empty
                    and app._pinned_manual_support_chain_issues(c, ds).empty
                    and app._pinned_manual_physical_conflicts(c).empty)
        return try_area_layout(rows, deck, make_state=state, can_place=app.can_place_stable,
                               commit=app.commit_place, validate=kwargs.pop("validate", valid), **kwargs)

    def test_floor_used_before_tower_and_order_kept(self):
        deck, old, state = self.fixture()
        new = self.search(old, deck, state)
        self.assertLess(_metrics(new, deck)["height"], _metrics(old, deck)["height"])
        self.assertEqual(sorted(new.Einheit_ID), sorted(old.Einheit_ID))
        self.assertTrue(_respects_order(new, {f"E{i}": i for i in range(4)}))
        self.assertEqual(new.Gewicht_kg.sum(), old.Gewicht_kg.sum())

    def test_rejected_validation_returns_original(self):
        deck, old, state = self.fixture()
        self.assertIs(self.search(old, deck, state, validate=lambda _: False), old)

    def test_timeout_returns_original(self):
        deck, old, state = self.fixture()
        self.assertIs(self.search(old, deck, state, seconds=0), old)

    def test_missing_or_duplicate_order_is_not_guessed(self):
        deck, old, state = self.fixture()
        old["Logische_Reihenfolge_im_Block"] = 1
        self.assertIs(self.search(old, deck, state), old)

    def test_manual_position_not_moved(self):
        deck, old, state = self.fixture()
        old["Manuelle_Zone"] = "VL"
        self.assertIs(self.search(old, deck, state), old)

    def test_zero_manual_order_does_not_disable_search(self):
        deck, old, state = self.fixture()
        old["Manuelle_Reihenfolge"] = 0.
        self.assertIsNot(self.search(old, deck, state), old)

    def test_bundle_contents_remain_atomic(self):
        deck, old, state = self.fixture()
        old["Typ"] = "Bund"
        old["Bauteile_Liste"] = "one|two"
        old["Anzahl_Bauteile"] = 2
        new = self.search(old, deck, state)
        self.assertEqual(new.Bauteile_Liste.tolist(), ["one|two"]*4)

    def test_no_stacking_when_disabled(self):
        deck, old, factory = self.fixture()
        def state():
            s = factory()
            s["area_allow_stack"] = False
            return s
        self.assertIs(self.search(old, deck, state), old)

    def test_complete_prefix_fits_without_a_preexisting_tall_plan(self):
        deck, old, _ = self.fixture()
        deck["Max_Höhe_mm"] = 400.
        def state():
            return app.init_platform_state(deck, 80., 40., 0.)
        result = pack_area_units(
            old, deck, make_state=state, can_place=app.can_place_stable,
            commit=app.commit_place,
            validate=lambda p: app.find_geometry_conflicts(p, pd.DataFrame([deck])).empty
            and app._pinned_manual_support_chain_issues(p, pd.DataFrame([deck])).empty,
        )
        self.assertEqual(len(result), 4)
        self.assertLessEqual((result.Z_mm+result.Höhe_mm).max(), 400.)

    def test_failed_prefix_never_returns_seed_coordinates(self):
        deck, old, state = self.fixture()
        result = pack_area_units(old, deck, make_state=state,
                                 can_place=lambda *a: False,
                                 commit=app.commit_place, validate=lambda p: True)
        self.assertTrue(result.empty)

    def test_prefix_requires_valid_physical_order(self):
        deck, old, state = self.fixture()
        old["Logische_Reihenfolge_im_Block"] = 1
        self.assertTrue(pack_area_units(
            old, deck, make_state=state, can_place=app.can_place_stable,
            commit=app.commit_place, validate=lambda p: True).empty)


if __name__ == "__main__":
    unittest.main()
