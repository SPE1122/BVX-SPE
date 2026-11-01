---
name: Within-stack shared shelves
description: Scope and rationale for filling free transverse space without replacing the accepted loading plan.
---

Shared-shelf packing is an additional part of the flexible-width search, separate
from the optional multi-layer compaction checkbox.

**Why:** The user accepted the existing overall plan and declined further
compaction, then explicitly approved a targeted extension to use free width
beside narrow elements. Do not turn that request into a general planner rewrite.

**How to apply:** Keep the accepted plan as fallback, preserve the incoming
loading/unloading order and complete bundles, and do not add trips or platforms
for this optimization. Consider more than two members when the space permits;
do not introduce mandatory pair objects.

Different thicknesses require real height-compensation material, not an implicit
vertical offset or a minimal contact patch concentrated at one end.

**Why:** The lower-surface planning heuristic can see sufficient projected area
across a vertical gap, whereas the final support-chain check requires actual
contact or declared inserts. A shared shelf must not exploit that difference.

**How to apply:** Represent compensation as supported physical geometry and keep
the same final collision and support-chain checks. Restrict the stricter padding
handling to the shared-shelf candidate; do not silently change normal inserts.
