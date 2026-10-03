import unittest
from contextlib import nullcontext
from unittest.mock import patch

import pandas as pd

import pinned_manual_ui


class FakeColumn:
    def __init__(self, ui):
        self.ui = ui

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def selectbox(self, label, options, index=0, key=None, **_kwargs):
        self.ui.selectboxes.append((label, key))
        return self.ui.widget_values.get(key, options[index])

    def number_input(self, _label, value=0.0, key=None, **_kwargs):
        return self.ui.widget_values.get(key, value)


class FakeStreamlit:
    def __init__(self, *, buttons=None, widgets=None, session_state=None, checkboxes=None):
        self.session_state = {} if session_state is None else session_state
        self.buttons = buttons or {}
        self.widget_values = widgets or {}
        self.checkboxes = checkboxes or {}
        self.selectboxes = []
        self.button_calls = []
        self.checkbox_calls = []
        self.dataframes = []
        self.errors = []
        self.successes = []
        self.warnings = []

    def expander(self, *_args, **_kwargs):
        return nullcontext()

    def spinner(self, *args, **_kwargs):
        self.spinner_text = args[0] if args else ''
        return nullcontext()

    def columns(self, count):
        return [FakeColumn(self) for _ in range(count)]

    def selectbox(self, label, options, index=0, key=None, **_kwargs):
        self.selectboxes.append((label, key))
        return self.widget_values.get(key, options[index])

    def button(self, _label, key=None, disabled=False, **_kwargs):
        self.button_calls.append((key, disabled))
        return bool(self.buttons.get(key, False)) and not disabled

    def checkbox(self, label, value=False, key=None, **_kwargs):
        self.checkbox_calls.append((label, value, key))
        return self.checkboxes.get(key, value)

    def dataframe(self, frame=None, **_kwargs):
        self.dataframes.append(frame)

    def caption(self, *_args, **_kwargs):
        pass

    def success(self, message, **_kwargs):
        self.successes.append(message)

    def error(self, message, **_kwargs):
        self.errors.append(message)

    def warning(self, message, **_kwargs):
        self.warnings.append(message)

    def info(self, *_args, **_kwargs):
        pass

    def markdown(self, *_args, **_kwargs):
        pass

    def plotly_chart(self, *_args, **_kwargs):
        pass

    def rerun(self):
        pass


def input_frames():
    placements = pd.DataFrame([
        {"Einheit_ID": unit_id, "Typ": "Bauteil", "Bauteile": unit_id,
         "Bauteile_Liste": unit_id, "Pritsche": "F01", "X_mm": x,
         "Y_mm": 0.0, "Z_mm": 0.0}
        for unit_id, x in (("A", 0.0), ("B", 10.0))
    ])
    platforms = pd.DataFrame([{"Pritsche": "F01"}])
    return placements, platforms, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}, {}


def valid_preview(coordinates=None, advisory_issues=None):
    return {
        "ok": True,
        "applied": False,
        "source_signature": "source-v1",
        "advisory_issues": advisory_issues if advisory_issues is not None else pd.DataFrame(),
        "unit_ids": ["A", "B"],
        "target_platform": "F01",
        "coordinates": coordinates or {
            "A": {"X_mm": 0.0, "Y_mm": 0.0, "Z_mm": 0.0},
            "B": {"X_mm": 10.0, "Y_mm": 0.0, "Z_mm": 0.0},
        },
        "pinned_placements_df": pd.DataFrame([{"Einheit_ID": "A"}, {"Einheit_ID": "B"}]),
        "placements_df": pd.DataFrame([
            {"Einheit_ID": unit_id, "Typ": "Bauteil", "Bauteile_Liste": unit_id,
             "Pritsche": "F01", "X_mm": x, "Y_mm": 0.0, "Z_mm": 0.0}
            for unit_id, x in (("A", 0.0), ("B", 10.0))
        ]),
        "platforms_df": pd.DataFrame([{"Pritsche": "F01"}]),
        "summary_df": pd.DataFrame(),
    }


class PinnedManualUiTests(unittest.TestCase):
    def setUp(self):
        self.placements, self.platforms, self.parts, self.options, self.stock, self.standards, self.settings = input_frames()
        self.placements_before = self.placements.copy(deep=True)
        self.platforms_before = self.platforms.copy(deep=True)
        self.validation_calls = []
        self.preview_calls = []
        self.apply_calls = []

    def validate_pair(
        self, placements, platforms, unit_ids, coordinates, target,
        include_destination_loads=True, manual_pair_override=False,
    ):
        self.validation_calls.append((
            placements, platforms, unit_ids, coordinates, target,
            include_destination_loads, manual_pair_override,
        ))
        return {"ok": True, "issues": pd.DataFrame(), "advisory_issues": pd.DataFrame()}

    def preview_plan(self, *args):
        self.preview_calls.append(args)
        return valid_preview(args[-1])

    def apply_plan(self, preview, *args):
        self.apply_calls.append((preview, args))
        return {"applied": True}

    def render(self, fake_ui):
        with patch.object(pinned_manual_ui, "st", fake_ui):
            pinned_manual_ui.render_pinned_manual_replanning(
                self.placements, self.platforms, self.parts, self.options,
                self.stock, self.standards, self.settings,
                validate_pair=self.validate_pair,
                preview_plan=self.preview_plan,
                apply_plan=self.apply_plan,
                draw_view=lambda *_args: object(),
                is_real_load=lambda value: value == "Bauteil",
            )

    def test_preview_does_not_mutate_or_commit_plan(self):
        state = {}
        fake_ui = FakeStreamlit(
            buttons={"pinned_manual_preview_button": True},
            session_state=state,
        )
        self.render(fake_ui)

        self.assertEqual(len(self.validation_calls), 1)
        self.assertEqual(len(self.preview_calls), 1)
        self.assertEqual(len(self.apply_calls), 1)  # validity check only, no commit
        pd.testing.assert_frame_equal(self.placements, self.placements_before)
        pd.testing.assert_frame_equal(self.platforms, self.platforms_before)
        self.assertIn("pinned_manual_preview", state)
        self.assertNotIn("manual_placements_df", state)
        self.assertNotIn("pinned_manual_active", state)
        self.assertFalse(fake_ui.checkbox_calls[0][1])  # explicit confirmation starts unchecked
        self.assertNotIn("pinned_manual_override", [key for _, _, key in fake_ui.checkbox_calls])
        self.assertEqual(self.validation_calls[0][5:], (False, True))
        preview_settings = self.preview_calls[0][6]
        self.assertEqual(preview_settings, {"manual_pair_override": True})
        self.assertIsNot(preview_settings, self.settings)
        self.assertEqual(self.apply_calls[0][1][-1], {"manual_pair_override": True})
        self.assertEqual(self.settings, {})
        apply_button = next(
            disabled for key, disabled in fake_ui.button_calls if key == "pinned_manual_apply"
        )
        self.assertTrue(apply_button)

    def test_checkbox_and_apply_button_are_both_required_to_commit(self):
        state = {"pinned_manual_preview": valid_preview()}
        confirm_key = "pinned_manual_confirm_source-v1"
        fake_ui = FakeStreamlit(
            buttons={"pinned_manual_apply": True},
            session_state=state,
        )
        self.render(fake_ui)
        self.assertNotIn("pinned_manual_active", state)
        self.assertTrue(next(
            disabled for key, disabled in fake_ui.button_calls if key == "pinned_manual_apply"
        ))

        accepted = {
            "applied": True,
            "placements_df": self.placements.copy(deep=True),
            "platforms_df": self.platforms.copy(deep=True),
        }
        final_apply_settings = []
        self.apply_plan = lambda _preview, *_args: (
            final_apply_settings.append(_args[-1]) or accepted
        )
        confirmed_ui = FakeStreamlit(
            buttons={"pinned_manual_apply": True},
            checkboxes={confirm_key: True},
            session_state=state,
        )
        self.render(confirmed_ui)

        self.assertIn("pinned_manual_active", state)
        self.assertTrue(state["pinned_manual_active"]["manual_pair_override"])
        self.assertTrue(state["manual_plan_ready_v84"])
        self.assertTrue(state["pinned_manual_active"]["applied"])
        self.assertNotIn("pinned_manual_preview", state)
        self.assertIn("manual_placements_df", state)
        self.assertIn("manuelle Verantwortung", confirmed_ui.checkbox_calls[-1][0])
        self.assertEqual(final_apply_settings, [
            {"manual_pair_override": True},
            {"manual_pair_override": True},
        ])

    def test_discard_removes_preview_without_committing(self):
        state = {"pinned_manual_preview": valid_preview()}
        fake_ui = FakeStreamlit(
            buttons={"pinned_manual_discard": True},
            session_state=state,
        )
        self.render(fake_ui)
        self.assertNotIn("pinned_manual_preview", state)
        self.assertNotIn("pinned_manual_active", state)
        self.assertNotIn("manual_placements_df", state)

    def test_invalid_pair_preview_never_reaches_apply_callback(self):
        self.validate_pair = lambda *_args, **_kwargs: {
            "ok": False, "issues": pd.DataFrame([{"Typ": "Geometrie"}]),
            "advisory_issues": pd.DataFrame([{"Typ": "Hinweis"}]),
        }
        fake_ui = FakeStreamlit(
            buttons={"pinned_manual_preview_button": True},
            session_state={},
        )
        self.render(fake_ui)
        self.assertEqual(len(self.preview_calls), 0)
        self.assertEqual(len(self.apply_calls), 0)
        self.assertFalse(fake_ui.session_state["pinned_manual_preview"]["ok"])
        self.assertEqual(len(fake_ui.dataframes), 2)
        self.assertNotIn("pinned_manual_active", fake_ui.session_state)

    def test_stale_source_preview_cannot_be_applied(self):
        state = {"pinned_manual_preview": valid_preview()}
        self.apply_plan = lambda *_args: {"applied": False, "stale_source": True}
        fake_ui = FakeStreamlit(
            buttons={"pinned_manual_apply": True},
            checkboxes={"pinned_manual_confirm_source-v1": True},
            session_state=state,
        )
        self.render(fake_ui)
        self.assertNotIn("pinned_manual_active", state)
        self.assertNotIn("manual_placements_df", state)
        self.assertTrue(next(
            disabled for key, disabled in fake_ui.button_calls if key == "pinned_manual_apply"
        ))

    def test_edited_coordinate_invalidates_preview_and_blocks_apply(self):
        state = {"pinned_manual_preview": valid_preview()}
        fake_ui = FakeStreamlit(
            buttons={"pinned_manual_apply": True},
            widgets={"pinned_manual_first_A_X": 1.0},
            checkboxes={"pinned_manual_confirm_source-v1": True},
            session_state=state,
        )
        self.render(fake_ui)
        self.assertEqual(len(self.apply_calls), 1)  # preflight only
        self.assertNotIn("pinned_manual_active", state)
        self.assertNotIn("manual_placements_df", state)
        self.assertTrue(next(
            disabled for key, disabled in fake_ui.button_calls if key == "pinned_manual_apply"
        ))

    def test_release_clears_lock_and_next_render_shows_controls(self):
        state = {
            "pinned_manual_active": {"target_platform": "F01", "unit_ids": ["A", "B"]},
            "pinned_manual_preview": valid_preview(),
        }
        release_ui = FakeStreamlit(
            buttons={"pinned_manual_release": True},
            session_state=state,
        )
        self.render(release_ui)
        self.assertNotIn("pinned_manual_active", state)
        self.assertNotIn("pinned_manual_preview", state)

        unlocked_ui = FakeStreamlit(session_state=state)
        self.render(unlocked_ui)
        self.assertIn(("Zielpritsche für das Längspaar", "pinned_manual_target"),
                      unlocked_ui.selectboxes)

    def test_advisory_issues_are_shown_for_preview_and_accepted_pin(self):
        advisory = pd.DataFrame([{"Typ": "Schwerpunkt", "Hinweis": "Manuell beurteilen"}])
        state = {}
        self.preview_plan = lambda *args: valid_preview(args[-1], advisory)
        preview_ui = FakeStreamlit(
            buttons={"pinned_manual_preview_button": True},
            session_state=state,
        )
        self.render(preview_ui)
        self.assertTrue(any(frame is not None and frame.equals(advisory)
                            for frame in preview_ui.dataframes))
        self.assertTrue(any("nicht sicherheitstechnisch bestätigt" in message
                            for message in preview_ui.warnings))

        accepted_pin = {
            "target_platform": "F01",
            "unit_ids": ["A", "B"],
            "manual_pair_override": True,
            "advisory_issues": advisory,
        }
        accepted_ui = FakeStreamlit(session_state={"pinned_manual_active": accepted_pin})
        self.render(accepted_ui)
        self.assertTrue(any(frame is not None and frame.equals(advisory)
                            for frame in accepted_ui.dataframes))
        self.assertTrue(any("nicht sicherheitstechnisch bestätigt" in message
                            for message in accepted_ui.warnings))

    def test_retained_false_widget_value_cannot_restore_strict_stability_gates(self):
        state = {"pinned_manual_override": False}
        fake_ui = FakeStreamlit(
            buttons={"pinned_manual_preview_button": True},
            checkboxes={"pinned_manual_override": False},
            session_state=state,
        )
        self.render(fake_ui)
        self.assertEqual(self.validation_calls[0][5:], (False, True))
        self.assertEqual(self.preview_calls[0][6], {"manual_pair_override": True})
        self.assertEqual(self.apply_calls[0][1][-1], {"manual_pair_override": True})
        self.assertNotIn("pinned_manual_override", [key for _, _, key in fake_ui.checkbox_calls])

    def test_legacy_failed_center_of_gravity_preview_is_discarded_without_mutating_plan(self):
        issues = pd.DataFrame([{"Typ": "Schwerpunkt längs", "Pritsche": "F01"}])
        state = {"pinned_manual_preview": {"ok": False, "issues": issues}}
        fake_ui = FakeStreamlit(session_state=state)
        self.render(fake_ui)
        self.assertNotIn("pinned_manual_preview", state)
        self.assertEqual(fake_ui.errors, [])
        self.assertEqual(fake_ui.dataframes, [])
        self.assertNotIn("pinned_manual_active", state)
        self.assertNotIn("manual_placements_df", state)
        pd.testing.assert_frame_equal(self.placements, self.placements_before)
        pd.testing.assert_frame_equal(self.platforms, self.platforms_before)

    def test_changed_coordinates_discard_an_obsolete_failed_preview(self):
        self.validate_pair = lambda *_args, **_kwargs: {
            "ok": False, "issues": pd.DataFrame([{"Typ": "Geometrie"}]),
        }
        state = {}
        self.render(FakeStreamlit(
            buttons={"pinned_manual_preview_button": True}, session_state=state,
        ))
        self.assertFalse(state["pinned_manual_preview"]["ok"])
        changed_ui = FakeStreamlit(
            widgets={"pinned_manual_first_A_X": 1.0}, session_state=state,
        )
        self.render(changed_ui)
        self.assertNotIn("pinned_manual_preview", state)
        self.assertEqual(changed_ui.errors, [])
        self.assertNotIn("pinned_manual_active", state)

    def test_previous_successful_strict_preview_cannot_be_applied_as_manual(self):
        preview = valid_preview()
        preview["settings"] = {"manual_pair_override": False}
        state = {"pinned_manual_preview": preview}
        fake_ui = FakeStreamlit(
            buttons={"pinned_manual_apply": True},
            checkboxes={"pinned_manual_confirm_source-v1": True},
            session_state=state,
        )
        self.render(fake_ui)
        self.assertNotIn("pinned_manual_preview", state)
        self.assertEqual(self.apply_calls, [])
        self.assertNotIn("pinned_manual_active", state)


if __name__ == "__main__":
    unittest.main()