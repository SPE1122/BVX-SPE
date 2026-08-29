---
name: Streamlit preview startup
description: Non-interactive Streamlit startup behavior in the Replit preview workflow.
---

Streamlit may pause at its first-run email prompt when launched by a non-interactive workflow, so the preview can time out even though the app itself is healthy.

**Why:** A workflow cannot answer the onboarding prompt, and the platform therefore sees no open preview port in time.

**How to apply:** Start Streamlit with headless mode enabled, bind it to `0.0.0.0`, and use the preview's expected port. Verify both the workflow logs and the rendered preview after restarting.