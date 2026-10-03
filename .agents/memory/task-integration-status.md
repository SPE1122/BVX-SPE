---
name: Task integration status
description: Distinguish completed isolated work from features integrated into the main application.
---

Verify that a separately completed task's changes are present in the current source and running app before describing the feature as available.

**Why:** An implemented task notification can precede application of its changes to the main version. A status-only completion claim previously directed the user to a UI feature that did not yet exist in the current project.

**How to apply:** Locate the actual feature in main source and identify its real UI labels. If absent, explain that the task must be reviewed and applied to the main version rather than suggesting a browser refresh or assuming the app already contains it.

Verify the actual runtime callable, not just a matching source definition, when changing planning behavior.

**Why:** Historical duplicate definitions can shadow an edited helper later in the same module. An opportunistic branch may then catch the resulting error and fall back, leaving tests green while the intended behavior never runs.

**How to apply:** Check which implementation the rendered flow receives and exercise the new branch directly. Assert its placement or capacity outcome, not merely that a fallback preview returns successfully.