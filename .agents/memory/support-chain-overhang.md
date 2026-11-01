---
name: Overhang support chain
description: Domain rule for evaluating overhangs, inserts, and the physical platform footprint in the loading logic.
---

An overhang must not be classified as unsupported solely because it extends beyond the physical platform rectangle. In the real loading process, inserts, support timbers, or lower load layers can transfer the load downward; the decisive condition is whether a continuous support path reaches the physical platform footprint.

**Why:** The loading plans intentionally use load lengths greater than the physical platform length, and overhangs are secured in practice by material inserted underneath.

**How to apply:** Model the physical platform as the final base support. Treat inserts and underlay/support elements as real support geometry at their respective heights, and validate the support chain through all layers. Centre-of-gravity checks remain necessary but must not replace support validation; any post-placement shift must be revalidated.

The user can manually insert compensating timbers in the transverse Y direction:
«in Y ich kein Problem habe händisch Ausgleichholz einzulegen».

**Why:** This is part of the user's actual loading workflow; longitudinal ends
projecting into open air are a separate practical concern.

**How to apply:** Consider explicitly required compensating timbers when exploring
transverse placements. Do not equate willingness to insert timber with verified
bearing capacity, and do not invent support under an otherwise unsupported end.

Wider elements above narrower elements must be a usable loading arrangement,
not categorically excluded because the lower layer is narrow.

**Why:** The user explicitly wants this practical arrangement; manually inserting
transverse compensating timbers is part of their loading process. They requested
a working correction rather than further theoretical discussion or broad changes.
The user reviewed the resulting transverse arrangement and confirmed it was
generally good, while separately flagging a short intermediate element beneath
longer elements as a remaining longitudinal concern.

**How to apply:** Keep the distinction between transverse compensation and free
longitudinal ends. Preserve bundle membership and the user's prescribed order.