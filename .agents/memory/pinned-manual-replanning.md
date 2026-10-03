---
name: Pinned manual placement before global replanning
description: Agreed direction for a manual placement preview followed by global optimization.
---

Offer a way to position two parts longitudinally on the same layer in a single trip and keep that placement fixed while replanning the remaining loads globally. Preview changes to other trips before applying. Keep the imported Nr.PL values unchanged rather than using decimal renumbering to imply placement.

**Why:** Changing sort numbers only changes order; a global recomputation from scratch could undo the manual arrangement, so any gained capacity would not reliably carry through.

**How to apply:** When implementing a manual placement feature or global optimization around a selected trip, preserve exact pin coordinates and make the rest of the plan eligible for replanning. Distinguish geometric acceptance from transport-safety confirmation; never silently force an unsafe pair.

An accepted pin must remain authoritative across input changes and other editing paths until explicitly released. Releasing a pin keeps the accepted positions; it does not undo the accepted global plan. Reject an invalid automatic remainder rather than silently freezing additional loads.

**Why:** A protected planner path alone is insufficient if a separate manual edit, selective recalculation, or mode change can move the pair. Freezing other loads as a fallback would also contradict the agreed global remainder planning.

**How to apply:** Guard all plan-changing controls while the accepted pin is active, provide an explicit release action, and keep preview state separate from accepted state. Invalidate previews when their source inputs change.

Count retained distinct trips when calculating remaining trip capacity; trip identifiers do not consume capacity.

**Why:** Retaining a trip named F05 consumes one available trip, not five, because the other trips are discarded and globally replanned.

**How to apply:** Separate the number-of-trips budget from collision-free trip numbering.

For manually adjusted longitudinal pairs, allow manual assessment of center of gravity, support chains and unloading access on the selected destination only. Keep these findings visible as non-blocking advisories with explicit manual-responsibility acknowledgment. Geometry, capacity and identity failures still block; other automatically planned trips remain strictly checked.

**Why:** On 2026-10-01 the user explicitly requested that manual positioning not be blocked by center-of-gravity and similar stability checks. Pair-only checks can reject a position before other loads are planned, and inherited elevated positions may depend on support not retained with the pair.

**How to apply:** Scope this exception to the manual-pair flow, including preview and final apply. Manual assessment is fixed in this UI, not an optional checkbox whose retained value can silently restore strict stability gates. Automation remains strict. Invalidate obsolete previews, including failed previews, when their request changes. Do not describe an override-accepted plan as transport-safe.