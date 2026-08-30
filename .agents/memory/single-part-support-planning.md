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