---
name: Area-oriented loading
description: User-approved extension beyond fixed towers, with the existing plan as fallback.
---

The user explicitly approved additional area-oriented placement after observing
two uneven towers: use available floor and lower bearing surfaces, not fixed
stack centres, while retaining unloading order and actual support.

**Why:** The longest upper member can reserve a whole tower envelope while short
lower members leave usable floor empty. The previously approved transverse shelf
search alone cannot solve this longitudinal problem.

**How to apply:** Compare complete valid candidates against the accepted plan,
without adding trips or changing platform membership. Keep manual positions
untouched. Do not run legacy per-stack centering after the free-area search:
that would recreate the constraint being removed. This approval extends the
earlier narrow shelf-only scope; it does not authorize relaxed safety checks.

The user requested a separate, opt-in “Nach Fläche verladen” control for this
work, independent of compact trip selection.

**Why:** They want to compare and disable this new placement behaviour separately.

**How to apply:** Keep it off by default and carry it through main planning,
selective recalculation and diagnostic snapshots. Evaluate longitudinal balance
on complete loads rather than chasing the centre after every element.
An almost perfectly centred old tower must not veto a substantially lower load
inside a small centre band (2% of deck length); this is a search preference,
not a transport safety certification. Configured hard support limits still apply.
