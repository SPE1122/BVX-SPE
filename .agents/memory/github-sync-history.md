---
name: GitHub sync history
description: Why a newly created project can show an unrecognized Git error when connecting to an existing GitHub repository.
---

When a project is created with a platform starter commit and then connected to an existing GitHub repository, the local and remote histories may be unrelated. Git can report a generic “Unknown Git Error” instead of explaining that the branches have no common ancestor.

**Why:** Remote Updates cannot perform a normal fast-forward or merge when the histories are unrelated, especially when the GitHub repository is intended to be the source of truth.

**How to apply:** Confirm the user wants the GitHub branch as the source before replacing the local starter state. Preserve a backup, align the local branch to the selected remote branch, remove leftover starter files, and verify that local HEAD equals the remote branch before declaring sync complete.