---
name: Loading block search
description: Performance constraints for finding the largest valid continuous loading block without changing the resulting platform allocation.
---

Do not assume that validity of continuous loading blocks is monotonic, even when every load unit is an individual part. Search optimizations must still find the exact largest valid block.

**Why:** The logical part block is physically loaded in reverse order. Adding one part therefore changes the complete physical sequence, so a smaller block may fail while a larger one succeeds. A binary search was faster but changed the allocation from four to five platforms.

**How to apply:** Derive a hard upper bound from weight, test candidate block sizes from that upper bound downward, and stop at the first fully valid result. Remove simulations only when there is genuinely no alternative unit or target platform to choose.