---
name: Pinned manual placement before global replanning
description: Agreed direction for a manual placement preview followed by global optimization.
---

Offer a way to position two parts longitudinally on the same layer in a single trip and keep that placement fixed while replanning the remaining loads globally. Include free space on the pinned destination, not only new trips for the remainder, and consider the resulting utilization and trip count elsewhere. Preview changes to other trips before applying. Keep the imported Nr.PL values unchanged rather than using decimal renumbering to imply placement.

**Why:** Changing sort numbers only changes order; a global recomputation from scratch could undo the manual arrangement, so any gained capacity would not reliably carry through. The user reiterated that the manually set elements must stay exactly as placed while the rest is checked again for more loading capacity or fewer trips.

**How to apply:** When implementing a manual placement feature or global optimization around a selected trip, preserve exact pin coordinates and make the rest of the plan eligible for replanning. Search with the pin already present as occupied geometry; do not discard an entire refill attempt just because an empty-deck proposal intersects it. Show additional loads on the destination and total trips before/after. Distinguish geometric acceptance from transport-safety confirmation; never silently force an unsafe pair.

Accepted pins must remain authoritative across input changes and other editing paths until explicitly released. Support cumulative single positions and pairs on the same or different platforms; adding a pin must not release earlier pins. Releasing one pin keeps its accepted positions but removes only its protection; it does not undo the accepted global plan. Reject an invalid automatic remainder rather than silently freezing additional loads.

**Why:** A protected planner path alone is insufficient if a separate manual edit, selective recalculation, or mode change can move the pair. Freezing other loads as a fallback would also contradict the agreed global remainder planning. The user requested multiple adjustments without sacrificing earlier confirmed positions.

**How to apply:** Guard unrelated plan-changing controls while any accepted pin is active, allow additional single positions or pairs and explicit individual/all release actions, and keep preview state separate from accepted state. Invalidate previews when their source inputs change.

Single-element adjustments are horizontal X/Y moves independent of longitudinal pairing. They may affect X only, Y only or both; keep height and destination unchanged.

**Why:** The user requested an additional way to shift elements in X and/or Y without forming a pair. Limiting this flow to horizontal displacement makes it distinct from changing layer or platform.

**How to apply:** Offer signed millimetre offsets with before/after coordinates, then explicit preview and acceptance. Retain linked supports as translated physical rows. Single positions and pairs share cumulative protection, geometry/capacity checks and the existing manual-assessment scope. Reset offsets when the source position changes to avoid applying a released displacement twice.

Count retained distinct trips when calculating remaining trip capacity; trip identifiers do not consume capacity.

**Why:** Retaining a trip named F05 consumes one available trip, not five, because the other trips are discarded and globally replanned.

**How to apply:** Separate the number-of-trips budget from collision-free trip numbering.

Reuse existing unreserved trip numbers and platform names when replanning, and report actual before/after counts separately from names.

**Why:** Offsetting every regenerated trip after the selected trip number made an unchanged trip count look like extra trips, and repeated adjustments could continually increase labels. The user specifically questioned changed names without additional platforms.

**How to apply:** Reserve all pinned destinations and their trip numbers. Reuse other source numbers first; preserve the exact source platform name when its trip and platform type match. Show retained, removed and new platform names in the preview instead of inferring capacity from a label.

For manually adjusted longitudinal pairs, allow manual assessment of center of gravity, support chains and unloading access on the selected destination only. Keep these findings visible as non-blocking advisories with explicit manual-responsibility acknowledgment. Geometry, capacity and identity failures still block; other automatically planned trips remain strictly checked.

**Why:** On 2026-10-01 the user explicitly requested that manual positioning not be blocked by center-of-gravity and similar stability checks. Pair-only checks can reject a position before other loads are planned, and inherited elevated positions may depend on support not retained with the pair.

**How to apply:** Scope this exception to the manual-pair flow, including preview and final apply. Manual assessment is fixed in this UI, not an optional checkbox whose retained value can silently restore strict stability gates. Automation remains strict. Invalidate obsolete previews, including failed previews, when their request changes. Do not describe an override-accepted plan as transport-safe.

Do not silently interpret small millimetre entries as metres; explain the reference and offer explicit corrections instead.

**Why:** Metre-style entries such as 6.54 and 1.98 in millimetre fields caused an almost fully overlapping pair. Users also understood X = 0 as the physical rear deck edge, while the planner includes the configured rear-overhang area in its origin. Guessing units would make exact manual placement unreliable.

**How to apply:** Show millimetres alongside metre equivalents, the physical deck boundaries, and gap/overlap before planning. Suggestions may update input fields only after an explicit click; they are geometric starting points, not load-security approval or permission to move an accepted pin.