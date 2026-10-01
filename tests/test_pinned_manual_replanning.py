import unittest
from unittest.mock import patch

import pandas as pd

import bvx_auswertung_streamlit as app


def platform(name="F01 Deck", trip=1):
    return {
        "Fuhre_Nr": trip,
        "Fuhrenoption": "Standard",
        "Pritschenname": "Deck",
        "Pritsche": name,
        "Länge_mm": 50.0,
        "Breite_mm": 10.0,
        "Max_Höhe_mm": 20.0,
        "Max_Gewicht_kg": 1000.0,
        "Eigengewicht_Pritsche_kg": 10.0,
        "Überhang_vorne_mm": 0.0,
        "Überhang_hinten_mm": 0.0,
        "Kantholz_erste_Lage_mm": 2.0,
        "Mindest_Stützbreite_%": 60.0,
    }


def source_plan(with_support=False):
    loads = [
        {
            "Fuhre_Nr": 1, "Fuhrenoption": "Standard", "Pritschenname": "Deck",
            "Pritsche": "F01 Deck", "Einheit_ID": unit_id, "Typ": "Bauteil",
            "Bauteile": unit_id, "Bauteile_Liste": unit_id, "Nr.PL": nr,
            "X_mm": x, "Y_mm": 0.0, "Z_mm": 2.0,
            "Länge_mm": 5.0, "Breite_mm": 2.0, "Höhe_mm": 2.0,
            "Gewicht_kg": 10.0,
        }
        for unit_id, nr, x in (("A", 101, 0.0), ("B", 102, 5.0), ("C", 103, 10.0))
    ]
    if with_support:
        loads.append({
            "Fuhre_Nr": 1, "Fuhrenoption": "Standard", "Pritschenname": "Deck",
            "Pritsche": "F01 Deck", "Einheit_ID": "UB_A", "Typ": "Unterbau",
            "Bauteile": "Unterbau", "Bauteile_Liste": "Unterbau", "Auflager_fuer": "A",
            "X_mm": 0.0, "Y_mm": 0.0, "Z_mm": 0.0,
            "Länge_mm": 5.0, "Breite_mm": 2.0, "Höhe_mm": 2.0,
            "Gewicht_kg": 0.0,
        })
    return pd.DataFrame(loads), pd.DataFrame([platform()])


class PinnedManualReplanningTests(unittest.TestCase):
    def test_pair_validation_keeps_exact_coordinates_and_supports_separate(self):
        placements, platforms = source_plan(with_support=True)
        before = placements.copy(deep=True)
        result = app._manual_validate_pinned_longitudinal_pair(
            placements,
            platforms,
            ["A", "B"],
            {"A": {"X_mm": 0, "Y_mm": 0, "Z_mm": 2},
             "B": {"X_mm": 5, "Y_mm": 0, "Z_mm": 2}},
            "F01 Deck",
        )
        self.assertTrue(result["ok"], result["issues"].to_dict("records"))
        self.assertEqual(result["pinned_placements_df"]["X_mm"].tolist(), [0.0, 5.0])
        self.assertEqual(len(result["support_rows_df"]), 1)
        self.assertTrue(result["support_rows_df"]["Typ"].eq("Unterbau").all())
        pd.testing.assert_frame_equal(placements, before)

    def test_penetrating_support_is_rejected_in_pair_preview_and_apply(self):
        placements, platforms = source_plan(with_support=True)
        placements.loc[placements["Einheit_ID"].eq("UB_A"), "Höhe_mm"] = 4.0
        result = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"],
            {"A": {"X_mm": 0, "Y_mm": 0, "Z_mm": 2},
             "B": {"X_mm": 5, "Y_mm": 0, "Z_mm": 2}},
            "F01 Deck", include_destination_loads=False,
        )
        self.assertFalse(result["ok"])
        self.assertTrue(result["issues"]["Typ"].eq("Physische Geometrieüberschneidung").any())

        valid_placements, used_platforms = source_plan(with_support=True)
        valid_placements = valid_placements[
            valid_placements["Einheit_ID"].isin(["A", "B", "UB_A"])
        ].copy()
        parts = pd.DataFrame([
            {"Bauteilnummer": label, "Nr.PL": number, "Länge_mm": 5.0,
             "Breite_mm": 2.0, "Höhe_mm": 2.0, "Gewicht_kg": 10.0,
             "Volumen_m3": 0.00002}
            for label, number in (("A", 101), ("B", 102))
        ])
        options = pd.DataFrame([{"Fuhrenoption": "Standard", "Freigegeben": True, "Priorität": 1}])
        stock = pd.DataFrame([platform()])
        settings = {"allow_beside": True, "allow_stack": True, "allow_rotation": False}
        preview = app._preview_pinned_manual_replan(
            valid_placements, used_platforms, parts, options, stock,
            {"Standard_Kantholz_erste_Lage": 2.0}, settings, ["A", "B"], "F01 Deck",
            {"A": {"X_mm": 0, "Y_mm": 0, "Z_mm": 2},
             "B": {"X_mm": 5, "Y_mm": 0, "Z_mm": 2}},
        )
        self.assertTrue(preview["ok"], preview["issues"].to_dict("records"))
        preview["placements_df"].loc[
            preview["placements_df"]["Einheit_ID"].eq("UB_A"), "Höhe_mm"
        ] = 4.0
        # Recompute the artifact stamp to exercise safety revalidation, not only tamper detection.
        preview["_preview_artifact_signature"] = app._pinned_manual_preview_artifact_signature(preview)
        applied = app._apply_pinned_manual_replan(
            preview, valid_placements, used_platforms, parts, options, stock, settings
        )
        self.assertFalse(applied["applied"])
        self.assertTrue(
            applied["issues"]["Typ"].eq("Physische Geometrieüberschneidung").any()
        )

    def test_overlapping_pair_and_unsafe_height_are_rejected(self):
        placements, platforms = source_plan()
        overlap = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"],
            {"A": {"X_mm": 2, "Y_mm": 0, "Z_mm": 2},
             "B": {"X_mm": 4, "Y_mm": 0, "Z_mm": 2}},
            "F01 Deck",
        )
        self.assertFalse(overlap["ok"])
        high = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"],
            {"A": {"X_mm": 0, "Y_mm": 0, "Z_mm": 19},
             "B": {"X_mm": 5, "Y_mm": 0, "Z_mm": 19}},
            "F01 Deck",
        )
        self.assertFalse(high["ok"])

    def test_same_lane_finite_coordinates_and_complete_destination_are_required(self):
        placements, platforms = source_plan()
        disjoint_y = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"],
            {"A": {"X_mm": 0, "Y_mm": 0, "Z_mm": 2},
             "B": {"X_mm": 5, "Y_mm": 5, "Z_mm": 2}},
            "F01 Deck", include_destination_loads=False,
        )
        self.assertFalse(disjoint_y["ok"])
        different_z = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"],
            {"A": {"X_mm": 0, "Y_mm": 0, "Z_mm": 2},
             "B": {"X_mm": 5, "Y_mm": 0, "Z_mm": 3.5}},
            "F01 Deck", include_destination_loads=False,
        )
        self.assertFalse(different_z["ok"])
        nonfinite = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"],
            {"A": {"X_mm": float("nan"), "Y_mm": 0, "Z_mm": 2},
             "B": {"X_mm": 5, "Y_mm": 0, "Z_mm": 2}},
            "F01 Deck", include_destination_loads=False,
        )
        self.assertFalse(nonfinite["ok"])
        out_of_bounds = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"],
            {"A": {"X_mm": 0, "Y_mm": 0, "Z_mm": 2},
             "B": {"X_mm": 5, "Y_mm": 9, "Z_mm": 2}},
            "F01 Deck", include_destination_loads=False,
        )
        self.assertFalse(out_of_bounds["ok"])
        colliding_destination = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"],
            {"A": {"X_mm": 10, "Y_mm": 0, "Z_mm": 2},
             "B": {"X_mm": 15, "Y_mm": 0, "Z_mm": 2}},
            "F01 Deck",
        )
        self.assertFalse(colliding_destination["ok"])

    def test_floating_and_lost_support_chains_are_rejected(self):
        placements, platforms = source_plan()
        floating = placements[placements["Einheit_ID"].eq("A")].copy()
        floating.loc[:, "Z_mm"] = 10.0
        issues = app._pinned_manual_support_chain_issues(floating, platforms)
        self.assertFalse(issues.empty)
        supported, supported_platforms = source_plan(with_support=True)
        # Move A above the deck: removing its physical support row breaks the chain.
        supported.loc[supported["Einheit_ID"].eq("A"), "Z_mm"] = 10.0
        supported = supported[~supported["Einheit_ID"].eq("UB_A")]
        issues = app._pinned_manual_support_chain_issues(supported, supported_platforms)
        self.assertFalse(issues.empty)

    def test_unrelated_support_at_same_height_does_not_poison_chain(self):
        rows = pd.DataFrame([
            {"Pritsche": "F01 Deck", "Einheit_ID": "A", "Typ": "Bauteil",
             "X_mm": 0, "Y_mm": 0, "Z_mm": 5, "Länge_mm": 5, "Breite_mm": 2, "Höhe_mm": 2},
            {"Pritsche": "F01 Deck", "Einheit_ID": "UB_A", "Typ": "Unterbau",
             "X_mm": 0, "Y_mm": 0, "Z_mm": 2, "Länge_mm": 5, "Breite_mm": 2, "Höhe_mm": 3},
            {"Pritsche": "F01 Deck", "Einheit_ID": "UB_OTHER", "Typ": "Unterbau",
             "X_mm": 20, "Y_mm": 0, "Z_mm": 2, "Länge_mm": 5, "Breite_mm": 2, "Höhe_mm": 3},
        ])
        _, platforms = source_plan()
        self.assertTrue(app._pinned_manual_support_chain_issues(rows, platforms).empty)

    def test_center_of_gravity_is_a_pair_validation_gate(self):
        placements, platforms = source_plan()
        platforms.loc[:, "Länge_mm"] = 5000.0
        platforms.loc[:, "Breite_mm"] = 2000.0
        placements.loc[:, "Länge_mm"] = 500.0
        placements.loc[:, "Breite_mm"] = 1000.0
        placements.loc[:, "Gewicht_kg"] = 10.0
        result = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"],
            {"A": {"X_mm": 3500, "Y_mm": 0, "Z_mm": 2},
             "B": {"X_mm": 4000, "Y_mm": 0, "Z_mm": 2}},
            "F01 Deck", include_destination_loads=False,
        )
        self.assertFalse(result["ok"])
        self.assertTrue(
            result["issues"]["Typ"].astype(str).str.contains("Schwerpunkt").any()
        )

    def test_new_pair_unloading_dependency_is_detected(self):
        source = pd.DataFrame([
            {"Pritsche": "F01 Deck", "Einheit_ID": "A", "Typ": "Bauteil",
             "X_mm": 0, "Y_mm": 0, "Z_mm": 0, "Länge_mm": 5, "Breite_mm": 2, "Höhe_mm": 2},
            {"Pritsche": "F01 Deck", "Einheit_ID": "B", "Typ": "Bauteil",
             "X_mm": 5, "Y_mm": 0, "Z_mm": 0, "Länge_mm": 5, "Breite_mm": 2, "Höhe_mm": 2},
            {"Pritsche": "F01 Deck", "Einheit_ID": "C", "Typ": "Bauteil",
             "X_mm": 0, "Y_mm": 0, "Z_mm": 0, "Länge_mm": 5, "Breite_mm": 2, "Höhe_mm": 2},
        ])
        changed = source.copy()
        changed.loc[changed["Einheit_ID"].eq("A"), "Z_mm"] = 5
        issues = app._pinned_manual_unloading_issues(changed, source, ["A", "B"])
        self.assertFalse(issues.empty)

    def test_preview_replans_all_unpinned_parts_and_apply_detects_stale_source(self):
        placements, used_platforms = source_plan()
        parts = pd.DataFrame([
            {"Bauteilnummer": label, "Nr.PL": number, "Länge_mm": 5.0,
             "Breite_mm": 2.0, "Höhe_mm": 2.0, "Gewicht_kg": 10.0,
             "Volumen_m3": 0.00002}
            for label, number in (("A", 101), ("B", 102), ("C", 103))
        ])
        options = pd.DataFrame([{"Fuhrenoption": "Standard", "Freigegeben": True, "Priorität": 1}])
        stock = pd.DataFrame([platform()])
        standards = {"Standard_Kantholz_erste_Lage": 0.0}
        settings = {"allow_beside": True, "allow_stack": True, "allow_rotation": False}
        planned_platform = pd.DataFrame([platform()])
        planned_load = pd.DataFrame([{
            **platform(), "Einheit_ID": "R001", "Typ": "Bauteil",
            "Bauteile": "C", "Bauteile_Liste": "C", "X_mm": 0.0,
            "Y_mm": 0.0, "Z_mm": 2.0, "Länge_mm": 5.0,
            "Breite_mm": 2.0, "Höhe_mm": 2.0, "Gewicht_kg": 10.0,
        }])

        def plan_remaining(remaining, *_args, **_kwargs):
            self.assertEqual(remaining["Bauteilnummer"].tolist(), ["C"])
            return planned_load.copy(), pd.DataFrame(), planned_platform.copy(), pd.DataFrame(), pd.DataFrame()

        with patch.object(app, "create_loading_plan", return_value=(pd.DataFrame(), pd.DataFrame())), \
             patch.object(app, "create_variant_a_loading_plan", side_effect=plan_remaining):
            preview = app._preview_pinned_manual_replan(
                placements, used_platforms, parts, options, stock, standards,
                settings, ["A", "B"], "F01 Deck",
                {"A": {"X_mm": 0, "Y_mm": 0, "Z_mm": 2},
                 "B": {"X_mm": 5, "Y_mm": 0, "Z_mm": 2}},
            )
        self.assertTrue(preview["ok"], preview["issues"].to_dict("records"))
        self.assertTrue(preview["identity_conserved"])
        self.assertEqual(set(preview["placements_df"]["Bauteile_Liste"]), {"A", "B", "C"})
        self.assertEqual(
            preview["placements_df"].loc[
                preview["placements_df"]["Einheit_ID"].astype(str).eq("A"), "X_mm"
            ].iloc[0],
            0.0,
        )
        applied = app._apply_pinned_manual_replan(
            preview, placements, used_platforms, parts, options, stock, settings
        )
        self.assertTrue(applied["applied"])
        changed = placements.copy()
        changed.loc[0, "Nr.PL"] = 999
        stale = app._apply_pinned_manual_replan(
            preview, changed, used_platforms, parts, options, stock, settings
        )
        self.assertFalse(stale["applied"])
        self.assertTrue(stale["stale_source"])

    def test_real_planner_replans_unpinned_remainder_and_preserves_nr_pl(self):
        parts = pd.DataFrame([
            {"Bauteilnummer": label, "Nr.PL": number, "Länge_mm": 5.0,
             "Breite_mm": 2.0, "Höhe_mm": 2.0, "Gewicht_kg": 10.0,
             "Volumen_m3": 0.00002}
            for label, number in (("A", 101), ("B", 102), ("C", 103))
        ])
        options = pd.DataFrame([{"Fuhrenoption": "Standard", "Freigegeben": True, "Priorität": 1}])
        stock = pd.DataFrame([{**platform("Deck", 0), "Pritsche": "Deck",
                               "Freigabe": True, "Pritschen_Reihenfolge": 1,
                               "Drehen_90_erlaubt": False, "Runge_aktiv": False}])
        standards = {
            "Standard_Kantholz_erste_Lage": 2.0,
            "Standard_Einlage_zwischen_Lagen": 0.0,
            "Standard_Einlage_allgemein": 0.0,
            "Längenversatz_je_Lage": 0.0,
        }
        placements, _, used, _, _ = app.create_variant_a_loading_plan(
            parts, options, stock, standards,
            allow_beside=True, allow_stack=True, allow_rotation=False,
            use_bundles=False, max_fuhren=5, min_support_width_ratio=0.6,
        )
        ids_by_label = {
            str(row["Bauteile_Liste"]): str(row["Einheit_ID"])
            for _, row in placements[placements["Typ"].apply(app._is_real_load_type_value)].iterrows()
        }
        self.assertIn("A", ids_by_label)
        self.assertIn("B", ids_by_label)
        selected_platform = str(used.iloc[0]["Pritsche"])
        result = app._preview_pinned_manual_replan(
            placements, used, parts, options, stock, standards,
            {"allow_beside": True, "allow_stack": True, "allow_rotation": False,
             "use_bundles": False, "max_fuhren": 5, "min_support_width_ratio": 0.6},
            [ids_by_label["A"], ids_by_label["B"]], selected_platform,
            {ids_by_label["A"]: {"X_mm": 0, "Y_mm": 0, "Z_mm": 2},
             ids_by_label["B"]: {"X_mm": 5, "Y_mm": 0, "Z_mm": 2}},
        )
        self.assertTrue(result["ok"], result["issues"].to_dict("records"))
        self.assertTrue(result["identity_conserved"])
        self.assertTrue(set([ids_by_label["A"], ids_by_label["B"]]).issubset(
            set(result["units_df"]["Einheit_ID"].astype(str))
        ))
        self.assertTrue(
            pd.to_numeric(result["fuhren_log_df"]["Fuhre_Nr"], errors="coerce")
            .eq(pd.to_numeric(used.iloc[0]["Fuhre_Nr"], errors="coerce")).any()
        )
        final_real = result["placements_df"][
            result["placements_df"]["Typ"].apply(app._is_real_load_type_value)
        ]
        self.assertEqual(
            sorted(app._pinned_manual_identity_labels(final_real)), ["A", "B", "C"]
        )
        nr_by_label = {
            label: row["Nr.PL"]
            for _, row in final_real.iterrows()
            for label in app._split_bsd_text_list(row.get("Bauteile_Liste", ""))
        }
        self.assertEqual(nr_by_label, {"A": 101, "B": 102, "C": 103})
        self.assertEqual(parts["Nr.PL"].tolist(), [101, 102, 103])
        self.assertEqual(final_real["Einheit_ID"].astype(str).nunique(), len(final_real))

    def test_pair_only_preview_keeps_pair_when_global_remainder_is_empty(self):
        placements, used_platforms = source_plan()
        placements = placements[placements["Einheit_ID"].isin(["A", "B"])].copy()
        parts = pd.DataFrame([
            {"Bauteilnummer": label, "Nr.PL": number, "Länge_mm": 5.0,
             "Breite_mm": 2.0, "Höhe_mm": 2.0, "Gewicht_kg": 10.0,
             "Volumen_m3": 0.00002}
            for label, number in (("A", 101), ("B", 102))
        ])
        options = pd.DataFrame([{"Fuhrenoption": "Standard", "Freigegeben": True, "Priorität": 1}])
        stock = pd.DataFrame([platform()])
        result = app._preview_pinned_manual_replan(
            placements, used_platforms, parts, options, stock,
            {"Standard_Kantholz_erste_Lage": 2.0},
            {"allow_beside": True, "allow_stack": True, "allow_rotation": False, "use_bundles": False},
            ["A", "B"], "F01 Deck",
            {"A": {"X_mm": 0, "Y_mm": 0, "Z_mm": 2},
             "B": {"X_mm": 5, "Y_mm": 0, "Z_mm": 2}},
        )
        self.assertTrue(result["ok"], result["issues"].to_dict("records"))
        self.assertEqual(set(result["placements_df"]["Einheit_ID"].astype(str)), {"A", "B"})
        self.assertEqual(set(result["units_df"]["Einheit_ID"].astype(str)), {"A", "B"})
        self.assertTrue(result["fuhren_log_df"]["Fuhre_Nr"].eq(1).any())

    def test_nonfirst_retained_trip_uses_distinct_trip_count_for_max_fuhren(self):
        placements, used_platforms = source_plan()
        placements["Fuhre_Nr"] = 5
        placements["Pritsche"] = "F05 Deck"
        used_platforms["Fuhre_Nr"] = 5
        used_platforms["Pritsche"] = "F05 Deck"
        parts = pd.DataFrame([
            {"Bauteilnummer": label, "Nr.PL": number, "Länge_mm": 5.0,
             "Breite_mm": 2.0, "Höhe_mm": 2.0, "Gewicht_kg": 10.0,
             "Volumen_m3": 0.00002}
            for label, number in (("A", 101), ("B", 102), ("C", 103))
        ])
        options = pd.DataFrame([{"Fuhrenoption": "Standard", "Freigegeben": True, "Priorität": 1}])
        stock = pd.DataFrame([platform()])
        new_platform = pd.DataFrame([platform()])
        new_load = pd.DataFrame([{
            **platform(), "Einheit_ID": "E0001", "Typ": "Bauteil",
            "Bauteile": "C", "Bauteile_Liste": "C", "X_mm": 0.0,
            "Y_mm": 0.0, "Z_mm": 2.0, "Länge_mm": 5.0,
            "Breite_mm": 2.0, "Höhe_mm": 2.0, "Gewicht_kg": 10.0,
        }])
        received_max_fuhren = []

        def capture_limit(remaining, *_args, **kwargs):
            received_max_fuhren.append(kwargs.get("max_fuhren"))
            self.assertEqual(remaining["Bauteilnummer"].tolist(), ["C"])
            return new_load.copy(), pd.DataFrame(), new_platform.copy(), pd.DataFrame(), pd.DataFrame()

        with patch.object(app, "create_loading_plan", return_value=(pd.DataFrame(), pd.DataFrame())), \
             patch.object(app, "create_variant_a_loading_plan", side_effect=capture_limit):
            result = app._preview_pinned_manual_replan(
                placements, used_platforms, parts, options, stock,
                {"Standard_Kantholz_erste_Lage": 2.0},
                {"allow_beside": True, "allow_stack": True, "allow_rotation": False,
                 "use_bundles": False, "max_fuhren": 5},
                ["A", "B"], "F05 Deck",
                {"A": {"X_mm": 0, "Y_mm": 0, "Z_mm": 2},
                 "B": {"X_mm": 5, "Y_mm": 0, "Z_mm": 2}},
            )
        self.assertTrue(result["ok"], result["issues"].to_dict("records"))
        self.assertEqual(received_max_fuhren, [4])
        trip_numbers = set(pd.to_numeric(result["platforms_df"]["Fuhre_Nr"], errors="coerce"))
        self.assertEqual(trip_numbers, {5, 6})
        self.assertLessEqual(len(trip_numbers), 5)
        final_ids = result["placements_df"]["Einheit_ID"].astype(str)
        self.assertEqual(final_ids.nunique(), len(final_ids))

    def test_bundle_nr_pl_values_are_preserved_as_original_members(self):
        units = pd.DataFrame([{
            "Einheit_ID": "BND", "Typ": "Bund", "Bauteile_Liste": "A|B",
            "Bauteile": "A / B", "Nr.PL": 999,
        }])
        source_parts = pd.DataFrame([
            {"Bauteilnummer": "A", "Nr.PL": 41},
            {"Bauteilnummer": "B", "Nr.PL": 57},
        ])
        before = source_parts.copy(deep=True)
        result = app._pinned_manual_preserve_nr_pl(units, source_parts)
        self.assertEqual(result.iloc[0]["Nr.PL"], "41|57")
        pd.testing.assert_frame_equal(source_parts, before)
        pinned = pd.DataFrame([{
            "Einheit_ID": "A", "Typ": "Bauteil", "Bauteile_Liste": "A", "Nr.PL": 904,
        }])
        unchanged = app._pinned_manual_preserve_nr_pl(pinned, source_parts, ["A"])
        self.assertEqual(unchanged.iloc[0]["Nr.PL"], 904)

    def test_replanned_ids_are_namespaced_and_support_parent_links_updated(self):
        placements = pd.DataFrame([
            {"Einheit_ID": "E0001", "Typ": "Bauteil", "Pritsche": "F02 Deck",
             "Auflager_fuer": "", "Bauteile_Liste": "C"},
            {"Einheit_ID": "UBP_E0001_1", "Typ": "Unterbau", "Pritsche": "F02 Deck",
             "Auflager_fuer": "E0001", "Bauteile_Liste": "Unterbau"},
        ])
        units = pd.DataFrame([{"Einheit_ID": "E0001", "Typ": "Bauteil"}])
        pinned = pd.DataFrame([{"Einheit_ID": "E0001", "Typ": "Bauteil"}])
        mapped_placements, mapped_units = app._pinned_manual_namespace_replanned_ids(
            placements, units, pinned, "R02"
        )
        self.assertEqual(mapped_placements.loc[0, "Einheit_ID"], "R02_E0001")
        self.assertEqual(mapped_placements.loc[1, "Einheit_ID"], "UBP_R02_E0001_1")
        self.assertEqual(mapped_placements.loc[1, "Auflager_fuer"], "R02_E0001")
        self.assertEqual(mapped_units.loc[0, "Einheit_ID"], "R02_E0001")

    def test_preview_rejects_missing_identity_and_floating_replanned_load(self):
        placements, used_platforms = source_plan()
        parts = pd.DataFrame([
            {"Bauteilnummer": label, "Nr.PL": number, "Länge_mm": 5.0,
             "Breite_mm": 2.0, "Höhe_mm": 2.0, "Gewicht_kg": 10.0,
             "Volumen_m3": 0.00002}
            for label, number in (("A", 101), ("B", 102), ("C", 103))
        ])
        options = pd.DataFrame([{"Fuhrenoption": "Standard", "Freigegeben": True, "Priorität": 1}])
        stock = pd.DataFrame([platform()])
        standards = {"Standard_Kantholz_erste_Lage": 2.0}
        settings = {"allow_beside": True, "allow_stack": True, "allow_rotation": False, "use_bundles": False}
        coords = {"A": {"X_mm": 0, "Y_mm": 0, "Z_mm": 2},
                  "B": {"X_mm": 5, "Y_mm": 0, "Z_mm": 2}}

        def no_remaining_load(*_args, **_kwargs):
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        with patch.object(app, "create_loading_plan", return_value=(pd.DataFrame(), pd.DataFrame())), \
             patch.object(app, "create_variant_a_loading_plan", side_effect=no_remaining_load):
            missing = app._preview_pinned_manual_replan(
                placements, used_platforms, parts, options, stock, standards,
                settings, ["A", "B"], "F01 Deck", coords,
            )
        self.assertFalse(missing["ok"])
        self.assertFalse(missing["identity_conserved"])

        floating_load = pd.DataFrame([{
            **platform(), "Einheit_ID": "C-new", "Typ": "Bauteil",
            "Bauteile": "C", "Bauteile_Liste": "C", "X_mm": 0.0,
            "Y_mm": 0.0, "Z_mm": 10.0, "Länge_mm": 5.0,
            "Breite_mm": 2.0, "Höhe_mm": 2.0, "Gewicht_kg": 10.0,
        }])
        floating_platform = pd.DataFrame([platform()])

        def floating_remaining(*_args, **_kwargs):
            return floating_load.copy(), pd.DataFrame(), floating_platform.copy(), pd.DataFrame(), pd.DataFrame()

        with patch.object(app, "create_loading_plan", return_value=(pd.DataFrame(), pd.DataFrame())), \
             patch.object(app, "create_variant_a_loading_plan", side_effect=floating_remaining):
            floating = app._preview_pinned_manual_replan(
                placements, used_platforms, parts, options, stock, standards,
                settings, ["A", "B"], "F01 Deck", coords,
            )
        self.assertFalse(floating["ok"])
        self.assertTrue(
            floating["issues"].get("Typ", pd.Series(dtype=str)).astype(str).eq("Auflagekette").any()
        )


if __name__ == "__main__":
    unittest.main()