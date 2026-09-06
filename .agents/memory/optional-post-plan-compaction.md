---
name: Optional post-plan compaction
description: Product boundary for adding controlled compaction without changing established loading and bundle construction.
---

The established loading algorithm and bundle-building logic must remain unchanged. Controlled multi-layer compaction is a separate, explicitly selectable post-plan option.

**Why:** The existing assignment and bundle behavior is relied upon; compaction should improve a completed valid plan without changing how bundles are originally formed or which parts they contain.

**How to apply:** Offer the same compaction option in the main automatic planning flow and in “V116: einzelne Fuhre / Pritsche neu berechnen”. In bundle mode, move only complete bundles as indivisible units; never dissolve or internally reorder a bundle. If no safe improvement is found, retain the original valid plan.