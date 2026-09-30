---
name: Pinned manual placement before global replanning
description: Agreed direction for a manual placement preview followed by global optimization.
---

Offer a way to position two parts longitudinally on the same layer in a single trip, validate the complete placement, and keep that validated placement fixed while replanning the remaining loads globally. Preview changes to other trips before applying. Keep the imported Nr.PL values unchanged rather than using decimal renumbering to imply placement.

**Why:** Changing sort numbers only changes order; a global recomputation from scratch could undo the manual arrangement, so any gained capacity would not reliably carry through.

**How to apply:** When implementing a manual placement feature or global optimization around a selected trip, pin only a validated placement and make the rest of the plan eligible for replanning; never silently force an unsafe pair.