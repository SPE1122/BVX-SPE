---
name: Controlled multi-layer compaction
description: Desired post-planning optimization for cascading parts downward and packing them beside and behind one another.
---

After initial placement, attempt controlled repacking across adjacent layers before accepting the stack. A part may move downward and trigger further downward moves; parts may also share one level both laterally and longitudinally when each remains directly accessible for unloading.

**Why:** A greedy layer-by-layer placement can leave avoidable upper layers even when a cascading move or a two-dimensional arrangement would preserve the exact unloading sequence and improve compactness.

**How to apply:** Accept a repack only when unloading access and logical order remain unchanged, every part has valid real support and a support chain, geometry remains collision-free, and weight balance does not worsen materially. A load with a bound support may move horizontally on its existing height when the support follows it, but it must never be lowered into or through that support. Center atomic shelf layouts on the physical platform, not on an asymmetric overhang allowance, or a valid compaction can be rejected by the center-of-gravity guard. Center the combined shelf widths laterally, but allow each longitudinal shelf an independent X start aligned to real platform or upper-load support edges; forcing equal X starts can unnecessarily reduce existing upper support. Treat left/right shelf mirrors as distinct when the overall load is asymmetric, and prioritize layouts that retain lateral weight distribution and upper support before movement distance. New overlap between an unchanged upper load and a moved lower load is permissible when it creates valid support and their logical unloading order remains upper-before-lower; rejecting every new overlap blocks safe compaction under existing upper layers.

When two narrow units from adjacent layers should share a level, evaluate the complete local unloading chain rather than moving only the pair. For five consecutive equal-height units, enumerate valid 3+2 layer partitions and mirrors; all direct and transitive upper dependents join the same atomic validation.

**Why:** Moving only one narrow unit can create a geometrically supported but unloading-invalid edge beneath an intervening unit. Repacking the consecutive local window exposes the valid support chain and can also move the upper load longitudinally toward a better center of gravity.

**How to apply:** Detect consecutive, equal-height local windows by rank and dimensions rather than part numbers. Prefer logical order plus its mirror over exhaustive lateral permutations, and vary longitudinal positions mainly for upper loads. Revalidate every changed support at the configured minimum; lateral center-of-gravity tradeoffs must stay bounded and longitudinal balance must not worsen.

For a five-unit 3+2 window, equal height and non-overlap are not enough when the objective is to combine two narrow units. Prefer width-driven lateral orders that put the two narrowest compatible units in direct edge contact; a wide unit between them does not satisfy that objective.

**Why:** A geometrically valid regression once placed the narrow units on the same Z level but separated them by a wide unit, so the exported end view still contradicted the requested arrangement.

**How to apply:** Assert direct Y-edge contact in the regression and inspect the rendered front/back PDF view independently of coordinate expectations. For a terminal 3x2 base, prefer a common longitudinal position near the physical deck center so its own overhang is shared front/rear, but accept the nearest fully supported position rather than forcing exact symmetry.

Bound atomic compaction by a small per-platform time budget and a short prioritized candidate list. If the budget expires, retain the last fully validated state rather than continuing exhaustive subset search or accepting an unchecked layout.

**Why:** Independent shelf starts create many combinatorial variants; exhaustive validation can turn an otherwise short app calculation into a run lasting more than 16 minutes.

**How to apply:** Search target-level-plus-nearest-upper groups first, avoid generating layouts once merely to test feasibility and then again for validation, and stop safely at the deadline.

The PDF's reported overhang is the load's actually used overhang, not necessarily the planning coordinate window's allowed overhang. Reconstructing validation with the reported value can shift the apparent platform center and falsely reject a valid layout.

**Why:** The real F02 used less rear overhang than the permitted window; substituting the used value moved the reconstructed center-of-gravity reference even though the app's coordinates were correct.

**How to apply:** For regression fixtures and manual checks, use transport-option limits for the planning platform and derive actual overhang only as an output measurement of the placed load.