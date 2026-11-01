import unittest

import pandas as pd

import bvx_auswertung_streamlit as app
from loading_shelf_search import _respects_order, try_side_by_side_shelves
from test_flexible_loading_integration import make_platform
from transverse_loading_supports import _merge_padding_cells


class SharedShelfTests(unittest.TestCase):
    def fixture(self, widths=(662, 414), heights=(140, 120), bundle=False):
        deck = make_platform().iloc[0].copy()
        deck["Auflager_bei_Verladeplanung_beruecksichtigen"] = True
        deck["Mindest_Stützbreite_%"] = 35

        def state(supports=True):
            result = app.init_platform_state(deck, 80, 40, 100)
            result.update(allow_transverse_supports=True, min_support_width_ratio=.35,
                          prevent_wide_on_narrow=True, consider_generated_supports=supports)
            return result

        def unit(uid, width, height, mass):
            return pd.Series({
                "Einheit_ID": uid, "Typ": "Bauteil", "Bauteile": uid,
                "Bauteile_Liste": uid, "Anzahl_Bauteile": 1,
                "Länge_mm": 3556., "Breite_mm": float(width), "Höhe_mm": float(height),
                "Gewicht_kg": float(mass),
            })

        units = [unit("base", 1200, 140, 100)]
        units += [unit(f"N{i}", w, h, 100 if i == 0 else 10)
                  for i, (w, h) in enumerate(zip(widths, heights))]
        units += [unit("top", 1200, 140, 100), unit("right", 1200, 140, 500)]
        if bundle:
            units[1]["Typ"] = "Bund"
            units[1]["Bauteile_Liste"] = "B1|B2"
            units[1]["Anzahl_Bauteile"] = 2
        poses = [("base", 25, 80), ("right", 1225, 80)]
        z = 220.
        for i, (w, h) in enumerate(zip(widths, heights)):
            poses.append((f"N{i}", 1225-w, z))
            z += h
        poses.append(("top", 25, z))
        original_state = state()
        by_id = {u.Einheit_ID: u for u in units}
        for uid, y, z in sorted(poses, key=lambda pose: pose[2]):
            u = by_id[uid]
            app.commit_place(original_state, u, 2000, y, z, u.Länge_mm, u.Breite_mm,
                             u.Höhe_mm, 0, "original")
        return deck, units, pd.DataFrame(original_state["placements"]), state

    def search(self, deck, units, rows, factory, validator=None, placement=None):
        def valid(candidate):
            decks = pd.DataFrame([deck])
            return (app.find_geometry_conflicts(candidate, decks).empty
                    and app._pinned_manual_support_chain_issues(candidate, decks).empty
                    and app._pinned_manual_physical_conflicts(candidate).empty)
        return try_side_by_side_shelves(
            rows, deck, units, make_state=factory,
            can_place_stable=placement or app.can_place_stable,
            commit_place=app.commit_place, validate=validator or valid,
        )

    def test_different_thickness_uses_physical_twenty_mm_packing(self):
        deck, units, old, factory = self.fixture()
        untouched = old.copy(deep=True)
        new = self.search(deck, units, old, factory)
        self.assertIsNot(new, old)
        real = new[new.Typ.ne("Unterbau")].set_index("Einheit_ID")
        self.assertEqual(real.loc["N0", "Z_mm"], 220)
        self.assertEqual(real.loc["N1", "Z_mm"], 240)
        self.assertEqual(real.loc["top", "Z_mm"], 360)
        self.assertEqual(real.loc["N1", "Y_mm"] + real.loc["N1", "Breite_mm"],
                         real.loc["N0", "Y_mm"])
        packing = new[new.get("Auflager_fuer", pd.Series(dtype=str)).eq("N1")]
        self.assertEqual(len(packing), 1)
        self.assertEqual(packing.iloc[0].Höhe_mm, 20)
        self.assertEqual(packing.iloc[0].Z_mm, 220)
        # Packing is distributed over the available bearing footprint, not at one end.
        self.assertLessEqual(packing.iloc[0].X_mm, 3778)
        self.assertGreaterEqual(packing.iloc[0].X_mm + packing.iloc[0].Länge_mm, 3778)
        self.assertEqual(set(real.index), {u.Einheit_ID for u in units})
        pd.testing.assert_frame_equal(old, untouched)

    def test_three_members_can_share_a_shelf_without_pair_objects(self):
        deck, units, old, factory = self.fixture((400, 300, 200), (140, 140, 140))
        new = self.search(deck, units, old, factory)
        self.assertIsNot(new, old)
        members = new[new.Einheit_ID.isin(["N0", "N1", "N2"])]
        self.assertEqual(len(members), 3)
        self.assertEqual(members.Z_mm.nunique(), 1)
        self.assertEqual(members.Breite_mm.sum(), 900)

    def test_bundles_remain_whole(self):
        deck, units, old, factory = self.fixture(bundle=True)
        new = self.search(deck, units, old, factory)
        self.assertIsNot(new, old)
        bundle = new[new.Einheit_ID.eq("N0")].iloc[0]
        self.assertEqual(bundle.Typ, "Bund")
        self.assertEqual(bundle.Bauteile_Liste, "B1|B2")
        self.assertEqual(bundle.Anzahl_Bauteile, 2)

    def test_unequal_heights_without_automatic_supports_keep_original(self):
        deck, units, old, factory = self.fixture()
        new = self.search(deck, units, old, lambda: factory(False))
        self.assertIs(new, old)

    def test_parts_exceeding_available_half_width_are_not_merged(self):
        deck, units, old, factory = self.fixture((900, 414))
        self.assertIs(self.search(deck, units, old, factory), old)

    def test_nonconsecutive_input_units_are_not_merged(self):
        deck, units, old, factory = self.fixture()
        units.insert(2, units.pop())
        self.assertIs(self.search(deck, units, old, factory), old)

    def test_rejected_geometry_keeps_exact_original(self):
        deck, units, old, factory = self.fixture()
        self.assertIs(self.search(deck, units, old, factory, validator=lambda rows: False), old)

    def test_rejected_placement_keeps_exact_original(self):
        deck, units, old, factory = self.fixture()
        self.assertIs(self.search(deck, units, old, factory, placement=lambda *args: False), old)

    def test_new_vertical_obstructions_must_respect_input_order(self):
        rows = pd.DataFrame([
            {"Einheit_ID": "later", "X_mm": 0, "Y_mm": 0, "Z_mm": 0,
             "Länge_mm": 1000, "Breite_mm": 600, "Höhe_mm": 140},
            {"Einheit_ID": "earlier", "X_mm": 0, "Y_mm": 0, "Z_mm": 140,
             "Länge_mm": 1000, "Breite_mm": 600, "Höhe_mm": 140},
        ])
        self.assertFalse(_respects_order(rows, {"earlier": 0, "later": 1}))

    def test_adjacent_padding_cells_merge_but_free_gaps_do_not(self):
        merged = _merge_padding_cells([
            (20, 0, 100, 0, 50, 200), (20, 100, 200, 0, 50, 200),
            (20, 250, 300, 0, 50, 200),
        ])
        self.assertEqual(len(merged), 2)
        self.assertIn((20, 0, 200, 0, 50, 200), merged)


if __name__ == "__main__":
    unittest.main()
