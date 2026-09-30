---
name: Logical loads and physical supports
description: Keep transport-block membership distinct from generated physical support geometry.
---

Treat generated supports as physical geometry, not as logical loading units when deciding whether a requested block was completely loaded. Validate the presence of the requested loads separately, and preserve the supports for subsequent support-chain checks.

**Why:** Even a tiny nonzero spacer can generate a support beneath the first short part. Comparing all placed row identifiers against the requested load identifiers then rejects an otherwise fully placed block merely because an extra support exists, causing unnecessary trip splits.

**How to apply:** Any completeness, assignment, or block-acceptance check must distinguish logical load rows from support/helper rows. Exercise both zero and small nonzero spacer cases; do not infer the cause of a rejected larger block from the final smaller load's height.