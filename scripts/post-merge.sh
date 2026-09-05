#!/usr/bin/env bash
set -euo pipefail

# Task-Merges können requirements.txt verändern. Replits Paketmanager
# installiert daraus idempotent in .pythonlibs statt in den Nix-Store.
upm install --lang python3-pip --quiet

# Früh und eindeutig abbrechen, falls ein Merge ungültigen Python-Code enthält.
python -m py_compile bvx_auswertung_streamlit.py