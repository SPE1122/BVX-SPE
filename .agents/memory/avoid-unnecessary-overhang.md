---
name: Avoid unnecessary overhang
description: Safety boundary for reducing avoidable longitudinal overhang without disturbing established loading behavior.
---

Treat unnecessary-overhang reduction as an optional post-plan alignment, not as a replacement for packing, stacking, bundle formation, or the confirmed terminal-cascade logic. Center layers around the physical deck; keep deck-short layers inside it, while longer layers may use the configured reserve.

**Why:** Centering some layers in the complete permitted overhang envelope can create a staircase and extra overall load length even when most elements fit on the physical deck. Existing loading behavior must remain unchanged when the option is off.

**How to apply:** Offer the same opt-in control in main planning and selective recalculation. Preserve each complete layer, attached supports, Y/Z positions, order, and support quality; reject shifts that worsen established support. Mixed loads remain valid: long layers define necessary overhang, but short layers should not add avoidable overhang.