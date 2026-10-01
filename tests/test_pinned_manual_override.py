import unittest

import pandas as pd

import bvx_auswertung_streamlit as app


def platform(
    name="F01 Deck",
    trip=1,
    length=50.0,
    width=10.0,
    max_height=20.0,
    max_weight=1000.0,
):
    return {
        "Fuhre_Nr": trip,
        "Fuhrenoption": "Standard",
        "Pritschenname": "Deck",
        "Pritsche": name,
        "Länge_mm": length,
        "Breite_mm": width,
        "Max_Höhe_mm": max_height,
        "Max_Gewicht_kg": max_weight,
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


def floating_pair_plan(include_remainder=True, max_weight=1000.0):
    deck = platform(
        length=5000.0, width=2000.0, max_height=500.0, max_weight=max_weight
    )
    deck.update({
        "Freigabe": True,
        "Pritschen_Reihenfolge": 1,
        "Drehen_90_erlaubt": False,
        "Runge_aktiv": False,
    })
    labels = [("A", 101, 0.0), ("B", 102, 500.0)]
    if include_remainder:
        labels.append(("C", 103, 1000.0))
    rows = [
        {
            **deck,
            "Einheit_ID": label,
            "Typ": "Bauteil",
            "Bauteile": label,
            "Bauteile_Liste": label,
            "Nr.PL": number,
            "X_mm": x,
            "Y_mm": 0.0,
            "Z_mm": 0.0,
            "Länge_mm": 500.0,
            "Breite_mm": 1000.0,
            "Höhe_mm": 100.0,
            "Gewicht_kg": 10.0,
        }
        for label, number, x in labels
    ]
    placements = pd.DataFrame(rows)
    platforms = pd.DataFrame([deck])
    parts = pd.DataFrame([
        {
            "Bauteilnummer": label,
            "Nr.PL": number,
            "Länge_mm": 500.0,
            "Breite_mm": 1000.0,
            "Höhe_mm": 100.0,
            "Gewicht_kg": 10.0,
            "Volumen_m3": 0.05,
        }
        for label, number, _x in labels
    ])
    options = pd.DataFrame([{
        "Fuhrenoption": "Standard", "Freigegeben": True, "Priorität": 1,
    }])
    stock = pd.DataFrame([deck])
    standards = {
        "Standard_Kantholz_erste_Lage": 0.0,
        "Standard_Einlage_zwischen_Lagen": 0.0,
        "Standard_Einlage_allgemein": 0.0,
        "Längenversatz_je_Lage": 0.0,
    }
    settings = {
        "allow_beside": True,
        "allow_stack": True,
        "allow_rotation": False,
        "use_bundles": False,
        "max_fuhren": 5,
        "min_support_width_ratio": 0.6,
        "manual_pair_override": True,
    }
    coordinates = {
        "A": {"X_mm": 3500.0, "Y_mm": 0.0, "Z_mm": 320.0},
        "B": {"X_mm": 4000.0, "Y_mm": 0.0, "Z_mm": 320.0},
    }
    return placements, platforms, parts, options, stock, standards, settings, coordinates


def preview_floating_pair(include_remainder=True):
    (
        placements, platforms, parts, options, stock, standards, settings, coordinates,
    ) = floating_pair_plan(include_remainder)
    preview = app._preview_pinned_manual_replan(
        placements, platforms, parts, options, stock, standards, settings,
        ["A", "B"], "F01 Deck", coordinates,
    )
    return preview, (placements, platforms, parts, options, stock, settings)


class PinnedManualOverrideTests(unittest.TestCase):
    def test_same_height_floating_asymmetric_pair_is_advisory_only_when_enabled(self):
        placements, platforms, *_ = floating_pair_plan(include_remainder=False)
        coordinates = {
            "A": {"X_mm": 3500.0, "Y_mm": 0.0, "Z_mm": 320.0},
            "B": {"X_mm": 4000.0, "Y_mm": 0.0, "Z_mm": 320.0},
        }
        strict_default = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"], coordinates, "F01 Deck",
            include_destination_loads=False,
        )
        strict_explicit = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"], coordinates, "F01 Deck",
            include_destination_loads=False, manual_pair_override=False,
        )
        self.assertFalse(strict_default["ok"])
        self.assertFalse(strict_explicit["ok"])
        self.assertTrue(strict_default["advisory_issues"].empty)

        relaxed = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"], coordinates, "F01 Deck",
            include_destination_loads=False, manual_pair_override=True,
        )
        self.assertTrue(relaxed["ok"], relaxed["issues"].to_dict("records"))
        self.assertTrue(relaxed["issues"].empty)
        advisory = relaxed["advisory_issues"]
        self.assertTrue({"Schwerpunkt längs", "Schwerpunkt quer", "Auflagekette"}.issubset(
            set(advisory["Typ"])
        ))
        self.assertTrue(advisory["Pritsche"].eq("F01 Deck").all())
        self.assertEqual(
            relaxed["pinned_placements_df"].set_index("Einheit_ID")["Z_mm"].to_dict(),
            {"A": 320.0, "B": 320.0},
        )

    def test_real_preview_and_apply_preserve_pair_when_no_remainder(self):
        preview, source = preview_floating_pair(include_remainder=False)
        placements, platforms, parts, options, stock, settings = source
        source_before = [frame.copy(deep=True) for frame in source[:-1]]
        self.assertTrue(preview["ok"], preview["issues"].to_dict("records"))
        self.assertTrue(preview["identity_conserved"])
        self.assertTrue(preview["advisory_issues"]["Typ"].str.startswith(
            ("Schwerpunkt", "Auflagekette")
        ).any())
        final = preview["placements_df"]
        self.assertEqual(set(final["Einheit_ID"].astype(str)), {"A", "B"})
        pinned = final.set_index(final["Einheit_ID"].astype(str)).loc[["A", "B"]]
        self.assertEqual(pinned["X_mm"].tolist(), [3500.0, 4000.0])
        self.assertEqual(pinned["Y_mm"].tolist(), [0.0, 0.0])
        self.assertEqual(pinned["Z_mm"].tolist(), [320.0, 320.0])

        applied = app._apply_pinned_manual_replan(
            preview, placements, platforms, parts, options, stock, settings
        )
        self.assertTrue(applied["applied"], applied["issues"].to_dict("records"))
        self.assertEqual(
            set(applied["placements_df"]["Einheit_ID"].astype(str)), {"A", "B"}
        )
        self.assertTrue(applied["advisory_issues"]["Typ"].str.startswith(
            ("Schwerpunkt", "Auflagekette")
        ).any())
        for original, before in zip(source[:-1], source_before):
            pd.testing.assert_frame_equal(original, before)

    def test_real_preview_replans_remainder_and_apply_keeps_identity_and_exact_pin(self):
        preview, source = preview_floating_pair(include_remainder=True)
        placements, platforms, parts, options, stock, settings = source
        source_before = [frame.copy(deep=True) for frame in source[:-1]]
        parts_before = parts.copy(deep=True)
        self.assertTrue(preview["ok"], preview["issues"].to_dict("records"))
        self.assertTrue(preview["identity_conserved"])
        self.assertEqual(
            sorted(app._pinned_manual_identity_labels(preview["placements_df"])),
            ["A", "B", "C"],
        )
        pinned = preview["placements_df"].set_index(
            preview["placements_df"]["Einheit_ID"].astype(str)
        ).loc[["A", "B"]]
        self.assertEqual(pinned["X_mm"].tolist(), [3500.0, 4000.0])
        self.assertEqual(pinned["Y_mm"].tolist(), [0.0, 0.0])
        self.assertEqual(pinned["Z_mm"].tolist(), [320.0, 320.0])
        self.assertTrue(preview["advisory_issues"]["Typ"].isin({
            "Schwerpunkt längs", "Schwerpunkt quer", "Auflagekette", "Entladereihenfolge",
        }).any())

        applied = app._apply_pinned_manual_replan(
            preview, placements, platforms, parts, options, stock, settings
        )
        self.assertTrue(applied["applied"], applied["issues"].to_dict("records"))
        self.assertEqual(
            sorted(app._pinned_manual_identity_labels(applied["placements_df"])),
            ["A", "B", "C"],
        )
        applied_pinned = applied["placements_df"].set_index(
            applied["placements_df"]["Einheit_ID"].astype(str)
        ).loc[["A", "B"]]
        self.assertEqual(applied_pinned["X_mm"].tolist(), [3500.0, 4000.0])
        self.assertEqual(applied_pinned["Z_mm"].tolist(), [320.0, 320.0])
        labels_to_nr = {
            label: row["Nr.PL"]
            for _, row in applied["placements_df"].iterrows()
            for label in app._split_bsd_text_list(row.get("Bauteile_Liste", ""))
        }
        self.assertEqual(labels_to_nr, {"A": 101, "B": 102, "C": 103})
        pd.testing.assert_frame_equal(parts, parts_before)
        for original, before in zip(source[:-1], source_before):
            pd.testing.assert_frame_equal(original, before)

    def test_override_does_not_relax_advisories_on_another_platform(self):
        issue_types = [
            "Schwerpunkt längs",
            "Schwerpunkt quer",
            "Auflagekette",
            "Entladereihenfolge",
        ]
        rows = pd.DataFrame([
            {"Typ": issue_type, "Pritsche": trip, "Warnung": issue_type}
            for trip in ("F01 Deck", "F02 Deck")
            for issue_type in issue_types
        ])
        hard, advisory = app._pinned_manual_classify_issues(
            rows, "F01 Deck", manual_pair_override=True
        )
        self.assertEqual(set(advisory["Pritsche"]), {"F01 Deck"})
        self.assertEqual(set(advisory["Typ"]), set(issue_types))
        self.assertEqual(set(hard["Pritsche"]), {"F02 Deck"})
        self.assertEqual(set(hard["Typ"]), set(issue_types))

    def test_weight_overlap_and_out_of_bounds_remain_hard_with_override(self):
        placements, platforms, *_ = floating_pair_plan(
            include_remainder=False, max_weight=15.0
        )
        normal_coordinates = {
            "A": {"X_mm": 3500.0, "Y_mm": 0.0, "Z_mm": 320.0},
            "B": {"X_mm": 4000.0, "Y_mm": 0.0, "Z_mm": 320.0},
        }
        overweight = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"], normal_coordinates, "F01 Deck",
            include_destination_loads=False, manual_pair_override=True,
        )
        self.assertFalse(overweight["ok"])
        self.assertIn("Gewicht", set(overweight["issues"]["Typ"]))

        platforms.loc[:, "Max_Gewicht_kg"] = 1000.0
        overlap_coordinates = {
            "A": {"X_mm": 3500.0, "Y_mm": 0.0, "Z_mm": 320.0},
            "B": {"X_mm": 3900.0, "Y_mm": 0.0, "Z_mm": 320.0},
        }
        overlap = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"], overlap_coordinates, "F01 Deck",
            include_destination_loads=False, manual_pair_override=True,
        )
        self.assertFalse(overlap["ok"])
        self.assertTrue(overlap["issues"]["Typ"].isin({
            "Längspaar", "Physische Geometrieüberschneidung",
        }).any())

        outside_coordinates = {
            "A": {"X_mm": 3500.0, "Y_mm": 1100.0, "Z_mm": 320.0},
            "B": {"X_mm": 4000.0, "Y_mm": 1100.0, "Z_mm": 320.0},
        }
        out_of_bounds = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"], outside_coordinates, "F01 Deck",
            include_destination_loads=False, manual_pair_override=True,
        )
        self.assertFalse(out_of_bounds["ok"])
        self.assertIn("Geometrie", set(out_of_bounds["issues"]["Typ"]))

    def test_settings_change_and_preview_policy_tampering_invalidate_apply(self):
        preview, source = preview_floating_pair(include_remainder=False)
        placements, platforms, parts, options, stock, settings = source
        changed_settings = dict(settings, manual_pair_override=False)
        toggled = app._apply_pinned_manual_replan(
            preview, placements, platforms, parts, options, stock, changed_settings
        )
        self.assertFalse(toggled["applied"])
        self.assertTrue(toggled["stale_source"])

        tampered = dict(preview)
        tampered["settings"] = dict(preview["settings"], manual_pair_override=False)
        # Exercise the optional-arguments apply path: policy integrity must still
        # be covered by the preview artifact signature.
        rejected = app._apply_pinned_manual_replan(tampered, placements, platforms)
        self.assertFalse(rejected["applied"])
        self.assertFalse(rejected["stale_source"])
        self.assertTrue(rejected["issues"]["Typ"].eq("Vorschau verändert").any())

    def test_failed_preview_and_apply_do_not_mutate_source_frames(self):
        placements, platforms, parts, options, stock, standards, settings, coordinates = (
            floating_pair_plan(include_remainder=False)
        )
        placements_before = placements.copy(deep=True)
        platforms_before = platforms.copy(deep=True)
        parts_before = parts.copy(deep=True)
        failed = app._manual_validate_pinned_longitudinal_pair(
            placements, platforms, ["A", "B"],
            {
                "A": {"X_mm": 3500.0, "Y_mm": 0.0, "Z_mm": 320.0},
                "B": {"X_mm": 3900.0, "Y_mm": 0.0, "Z_mm": 320.0},
            },
            "F01 Deck", manual_pair_override=True,
        )
        self.assertFalse(failed["ok"])
        pd.testing.assert_frame_equal(placements, placements_before)
        pd.testing.assert_frame_equal(platforms, platforms_before)

        settings["manual_pair_override"] = False
        failed_preview = app._preview_pinned_manual_replan(
            placements, platforms, parts, options, stock, standards, settings,
            ["A", "B"], "F01 Deck", coordinates,
        )
        self.assertFalse(failed_preview["ok"])
        failed_apply = app._apply_pinned_manual_replan(
            failed_preview, placements, platforms, parts, options, stock, settings
        )
        self.assertFalse(failed_apply["applied"])
        pd.testing.assert_frame_equal(placements, placements_before)
        pd.testing.assert_frame_equal(platforms, platforms_before)
        pd.testing.assert_frame_equal(parts, parts_before)


if __name__ == "__main__":
    unittest.main()