"""On-demand, local diagnostic exports. Never change placement decisions."""

from collections import Counter
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import time
import zipfile

import pandas as pd

_trace = ContextVar("loading_diagnostic_trace", default=None)


def trace_event(stage, **details):
    trace = _trace.get()
    if trace is None:
        return
    trace["counts"][stage] += 1
    if len(trace["samples"]) < 300 and trace["sample_counts"][stage] < 30:
        trace["samples"].append({"stage": stage, **details})
        trace["sample_counts"][stage] += 1


def traced_loading_run(function):
    """Attach bounded traces and measured runtime to the returned plan only."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        trace = {"counts": Counter(), "samples": [], "sample_counts": Counter()}
        token = _trace.set(trace)
        started = time.perf_counter()
        try:
            result = function(*args, **kwargs)
            if result and isinstance(result[0], pd.DataFrame):
                result[0].attrs["loading_diagnostics"] = {
                    "elapsed_seconds": time.perf_counter() - started,
                    "counts": dict(trace["counts"]), "samples": trace["samples"],
                    "samples_truncated": sum(trace["counts"].values()) > len(trace["samples"]),
                }
            return result
        finally:
            _trace.reset(token)
    return wrapped


def _json(value):
    def convert(obj):
        if hasattr(obj, "item"):
            return obj.item()
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        raise TypeError(f"Unsupported diagnostic value: {type(obj).__name__}")
    # pandas normalizes NaN/NaT and numpy scalar values to valid JSON.
    return json.dumps(json.loads(pd.Series([value], dtype=object).to_json(
        orient="values", date_format="iso", default_handler=convert
    ))[0], ensure_ascii=False, indent=2)


def code_identity():
    root = Path(__file__).resolve().parent
    hashes = {}
    for name in ("bvx_auswertung_streamlit.py", "verlade_varianten_flex.py",
                 "pdf_bundle_display.py", "loading_diagnostics.py"):
        path = root / name
        if path.is_file():
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, timeout=2, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    return {"git_commit": commit, "sha256": hashes}


def make_snapshot(settings, parts, options, platforms, standards):
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "settings": json.loads(_json(settings)),
        "parts": parts.copy(deep=True), "options": options.copy(deep=True),
        "platforms": platforms.copy(deep=True),
        "standards": json.loads(_json(standards)),
        "code": code_identity(),
    }


def build_diagnostic_zip(*, snapshot, current_settings, tables, checks, metadata):
    """Export exact tables plus explicit missing/failed checks; no environment."""
    output = io.BytesIO()
    checks_status = []
    files = {}
    for name, frame in tables.items():
        if isinstance(frame, pd.DataFrame):
            files[f"tabellen/{name}.csv"] = frame.to_csv(index=False).encode("utf-8-sig")
    if snapshot:
        for key in ("parts", "options", "platforms"):
            files[f"eingabe/{key}.csv"] = snapshot[key].to_csv(index=False).encode("utf-8-sig")
    for name, callback in checks.items():
        started = time.perf_counter()
        try:
            frame = callback()
            if not isinstance(frame, pd.DataFrame):
                raise TypeError("Prüfung liefert keine Tabelle")
            files[f"pruefungen/{name}.csv"] = frame.to_csv(index=False).encode("utf-8-sig")
            checks_status.append({
                "name": name, "status": "ausgeführt", "zeilen": len(frame),
                "seconds": time.perf_counter() - started,
            })
        except Exception as exc:
            checks_status.append({
                "name": name, "status": "fehlgeschlagen",
                "error": f"{type(exc).__name__}: {exc}",
                "seconds": time.perf_counter() - started,
            })
    manifest = {
        "format": "bvx-loading-diagnostics", "version": 1,
        "export_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "pandas": pd.__version__,
        "export_code": code_identity(),
        "calculation_snapshot_available": bool(snapshot),
        "calculation": {k: v for k, v in (snapshot or {}).items()
                        if k not in ("parts", "options", "platforms")},
        "current_settings": current_settings, "checks": checks_status, **metadata,
        "limits": [
            "Kein statischer Nachweis und keine Freigabe zur Transportsicherheit.",
            "Historische Suchversuche nur bei Berechnungen mit aktiver Diagnose verfügbar.",
            "Positionsversuche sind Stichproben (maximal 300 je Planlauf); Zähler laufen vollständig weiter.",
            "Eingabetabellen enthalten normalisierte Daten, keine Originaldateien.",
            "Keine Umgebungsvariablen, Zugangsdaten oder Browser-Sitzungsdaten enthalten.",
        ],
    }
    files["diagnose.json"] = _json(manifest).encode("utf-8")
    files["LESEN.txt"] = (
        "BVX Diagnosepaket\n\n"
        "diagnose.json: Versionen, Laufzeiten, Einstellungen und Prüfstatus.\n"
        "eingabe/: Zum Berechnungsstart gesicherte Eingaben in Verladereihenfolge.\n"
        "tabellen/: Aktueller Plan mit X/Y/Z, Automatik-Ausgangsplan, Einheiten, "
        "Pritschen, Warnungen, Variantenentscheidungen und BSD-Matrix.\n"
        "pruefungen/: Zusätzliche Prüfungen beim Export. Leere Konflikttabelle = "
        "keine gemeldeten Konflikte; fehlgeschlagene Prüfungen stehen in diagnose.json.\n\n"
        "Bei alten Plänen fehlen Berechnungssnapshot und Suchhistorie ausdrücklich. "
        "Aktuelle Einstellungen dürfen nicht als damalige Einstellungen gelesen werden.\n"
        "Manuelle Änderungen sind durch Vergleich von aktuellem und automatischem Plan erkennbar.\n"
        "Das Paket enthält Projektdaten und sollte nur gezielt geteilt werden.\n"
    ).encode("utf-8")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


def support_diagnostic_table(placements, platforms, init_state, metrics_for_candidate):
    """Describe computed support for each real load without generating supports."""
    rows = []
    helpers = {"Unterbau", "Kantholz", "Einlage", "Bundeinlage", "Lagenholz"}
    for _, deck in platforms.iterrows():
        group = placements[placements["Pritsche"].astype(str).eq(str(deck["Pritsche"]))]
        state = init_state(deck, 0, 0, 0)
        state["placements"] = group.to_dict("records")
        center = float(deck["Breite_mm"]) / 2
        for _, part in group.iterrows():
            if str(part.get("Typ")) in helpers or pd.isna(part.get("X_mm")):
                continue
            x, y, z = (float(part[key]) for key in ("X_mm", "Y_mm", "Z_mm"))
            length, width = (float(part[key]) for key in ("Länge_mm", "Breite_mm"))
            values = metrics_for_candidate(state, x, y, z, length, width)
            minimum = float(state["min_support_width_ratio"])
            if "sicher" in str(state.get("support_planning_mode", "")).lower():
                minimum = max(minimum, 0.5)
            rows.append({
                "Pritsche": deck["Pritsche"], "Einheit_ID": part["Einheit_ID"],
                "Typ": part["Typ"], "X_mm": x, "Y_mm": y, "Z_mm": z,
                "Länge_mm": length, "Breite_mm": width,
                "Pritschenmitte_Y_mm": center,
                "Abstand_Teilmitte_zu_Y_Mitte_mm": y + width / 2 - center,
                "Auflage_berechnet_%": values["area_ratio"] * 100,
                "Mindestauflage_%": minimum * 100,
                "Auflageziel_erreicht": values["area_ratio"] + 1e-6 >= minimum,
                "Freier_Überhang_Länge_mm": values["free_length_mm"],
                "Freier_Überhang_seitlich_mm": values["free_side_mm"],
            })
    return pd.DataFrame(rows)


def render_diagnostic_download(ui, **kwargs):
    ui.subheader("Diagnosepaket")
    ui.caption(
        "ZIP mit Eingaben, Einstellungen, X/Y/Z-Positionen, Auflagewerten, "
        "Prüfungen und Variantenentscheidungen. Ändert den Plan nicht. "
        "Enthält Projektdaten; nur gezielt teilen."
    )
    if not kwargs.get("snapshot"):
        ui.warning(
            "Für diesen älteren oder manuellen Plan fehlt der Berechnungs-Snapshot. "
            "Aktuelle Einstellungen werden separat gekennzeichnet. Für die vollständige "
            "Suchhistorie ist eine neue Berechnung nötig."
        )
    if ui.button("Diagnosepaket erstellen", key="build_loading_diagnostic_zip"):
        try:
            with ui.spinner("Diagnose und Prüfungen werden zusammengestellt …"):
                data = build_diagnostic_zip(**kwargs)
            ui.download_button(
                "Diagnosepaket herunterladen (ZIP)", data=data,
                file_name="BVX_Verladediagnose.zip", mime="application/zip",
                key="download_loading_diagnostic_zip", on_click="ignore",
            )
        except Exception as exc:
            ui.error(f"Diagnosepaket konnte nicht erstellt werden: {type(exc).__name__}: {exc}")
