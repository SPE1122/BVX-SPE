---
name: Controlled multi-layer compaction
description: Desired post-planning optimization for cascading parts downward and packing them beside and behind one another.
---

After initial placement, attempt controlled repacking across adjacent layers before accepting the stack. A part may move downward and trigger further downward moves; parts may also share one level both laterally and longitudinally when each remains directly accessible for unloading.

**Why:** A greedy layer-by-layer placement can leave avoidable upper layers even when a cascading move or a two-dimensional arrangement would preserve the exact unloading sequence and improve compactness.

**How to apply:** Accept a repack only when unloading access and logical order remain unchanged, every part has valid real support and a support chain, geometry remains collision-free, and weight balance does not worsen materially.