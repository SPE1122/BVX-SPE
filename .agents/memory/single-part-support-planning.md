---
name: Single-part support planning
description: Domain rules for keeping bundle controls separate from single-part loading and applying minimum support consistently.
---

When automatic bundling is disabled, every element remains an independent loading and unloading unit. Bundle-order flexibility must have no effect on element order or platform optimization.

**Why:** Treating a bundle-only search control as a general packing control masked the real support-placement issue and made platform counts change for the wrong reason.

**How to apply:** Force bundle-order flexibility to zero in single-part mode and disable the control in the UI.

Direct contact at the underside of an upper element counts as support. Candidate placement searches must include positions aligned with existing load-bearing surfaces before opening another platform.

**Why:** Excluding contact at exactly the same Z elevation or testing only coarse X positions caused valid 35% support placements to be rejected and multiplied the number of platforms.

**How to apply:** Use the same contact tolerance in planning and post-checking, include support-surface edges and centers as X candidates, and re-run both support and collision checks after post-processing.

Prefer the position with the best real support before optimizing the total load center or compactness. Hard free-overhang limits should be optional custom controls and proportional to element size, not fixed default millimeter limits.

**Why:** A fixed default limit rejected physically unavoidable overhangs on long first-layer elements and multiplied the number of platforms, while support-quality scoring improved the arrangement without creating extra platforms.

**How to apply:** Use minimum support presets as the normal modes, keep hard longitudinal/lateral overhang percentages at zero unless explicitly configured, and apply local overrides only to the selected platform during selective recalculation.

Any centering or center-of-gravity post-processing must preserve or improve the direct support of upper layers. An upper layer must not be shifted independently from its lower bearing geometry merely to look centered.

**Why:** Independent layer centering can undo a support-oriented placement and recreate a visible overhang even though a better shared position exists over the lower stack.

**How to apply:** Compare direct support before and after an upper-layer shift, retain the better-supported position, and restrict unconstrained center-of-gravity swaps to the first layer.