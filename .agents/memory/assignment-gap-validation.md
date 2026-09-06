---
name: Assignment gap validation
description: How to distinguish a real cross-platform assignment gap from intentionally unused part numbers.
---

Platform assignment controls must compare each platform's range only with part numbers that actually exist in the project. Never infer required parts from every integer between the platform's minimum and maximum label.

**Why:** Project numbering can intentionally omit whole ranges. Treating those unused numbers as missing produces false assignment warnings even though no part was moved or lost.

**How to apply:** Build the known-number set from all placement outcomes, including not-loaded rows. Within a platform's displayed minimum/maximum range, report only known project numbers absent from that platform.