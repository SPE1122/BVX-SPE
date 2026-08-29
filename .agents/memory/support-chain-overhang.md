---
name: Overhang support chain
description: Domain rule for evaluating overhangs, inserts, and the physical platform footprint in the loading logic.
---

An overhang must not be classified as unsupported solely because it extends beyond the physical platform rectangle. In the real loading process, inserts, support timbers, or lower load layers can transfer the load downward; the decisive condition is whether a continuous support path reaches the physical platform footprint.

**Why:** The loading plans intentionally use load lengths greater than the physical platform length, and overhangs are secured in practice by material inserted underneath.

**How to apply:** Model the physical platform as the final base support. Treat inserts and underlay/support elements as real support geometry at their respective heights, and validate the support chain through all layers. Centre-of-gravity checks remain necessary but must not replace support validation; any post-placement shift must be revalidated.