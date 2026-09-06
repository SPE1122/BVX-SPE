---
name: Controlled multi-layer compaction
description: Desired post-planning optimization for cascading parts downward and packing them beside and behind one another.
---

After initial placement, attempt controlled repacking across adjacent layers before accepting the stack. A part may move downward and trigger further downward moves; parts may also share one level both laterally and longitudinally when each remains directly accessible for unloading.

**Why:** A greedy layer-by-layer placement can leave avoidable upper layers even when a cascading move or a two-dimensional arrangement would preserve the exact unloading sequence and improve compactness.

**How to apply:** Accept a repack only when unloading access and logical order remain unchanged, every part has valid real support and a support chain, geometry remains collision-free, and weight balance does not worsen materially. A load with a bound support may move horizontally on its existing height when the support follows it, but it must never be lowered into or through that support. Center atomic shelf layouts on the physical platform, not on an asymmetric overhang allowance, or a valid compaction can be rejected by the center-of-gravity guard. Center the combined shelf widths laterally, but allow each longitudinal shelf an independent X start aligned to real platform or upper-load support edges; forcing equal X starts can unnecessarily reduce existing upper support. Treat left/right shelf mirrors as distinct when the overall load is asymmetric, and prioritize layouts that retain lateral weight distribution and upper support before movement distance. New overlap between an unchanged upper load and a moved lower load is permissible when it creates valid support and their logical unloading order remains upper-before-lower; rejecting every new overlap blocks safe compaction under existing upper layers.

Bound atomic compaction by a small per-platform time budget and a short prioritized candidate list. If the budget expires, retain the last fully validated state rather than continuing exhaustive subset search or accepting an unchecked layout.

**Why:** Independent shelf starts create many combinatorial variants; exhaustive validation can turn an otherwise short app calculation into a run lasting more than 16 minutes.

**How to apply:** Search target-level-plus-nearest-upper groups first, avoid generating layouts once merely to test feasibility and then again for validation, and stop safely at the deadline.

The PDF's reported overhang is the load's actually used overhang, not necessarily the planning coordinate window's allowed overhang. Reconstructing validation with the reported value can shift the apparent platform center and falsely reject a valid layout.

**Why:** The real F02 used less rear overhang than the permitted window; substituting the used value moved the reconstructed center-of-gravity reference even though the app's coordinates were correct.

**How to apply:** For regression fixtures and manual checks, use transport-option limits for the planning platform and derive actual overhang only as an output measurement of the placed load.