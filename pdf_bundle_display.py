"""Display-only bundle geometry; never feed these rows back into planning."""

import math

import pandas as pd


def _numbers(value, count):
    try:
        values = [float(v) for v in str(value).split("|")]
    except (TypeError, ValueError):
        return None
    if len(values) != count or any(not math.isfinite(v) or v <= 0 for v in values):
        return None
    return values


def expand_bundle_display_rows(rows):
    """Draw real member sizes at the bundle origin, top-to-bottom as in BSD.

    No individual lateral offsets are stored in the plan, so members share the
    bundle's X/Y origin. Missing/inconsistent metadata keeps the existing envelope
    rather than inventing dimensions. Only the configured *internal* spacing is
    respected; the inter-bundle spacer is never inserted between members.
    """
    drawn = []
    for _, row in rows.iterrows():
        if str(row.get("Typ", "")) != "Bund":
            drawn.append(row.to_dict())
            continue
        try:
            count = int(row.get("Anzahl_Bauteile", 0))
            lengths = _numbers(row.get("Einzellängen_mm", ""), count)
            widths = _numbers(row.get("Einzelbreiten_mm", ""), count)
            heights = _numbers(row.get("Einzelhöhen_mm", ""), count)
            rotation = float(row.get("Drehung", 0) or 0)
            spacing = float(row.get("Einlage_allgemein_mm", 0) or 0)
            if count < 1 or None in (lengths, widths, heights):
                raise ValueError("Missing member dimensions")
            if rotation not in (0, 90) or not math.isfinite(spacing) or spacing < 0:
                raise ValueError("Unsupported orientation/spacing")
            stacked = sum(heights) + (count - 1) * spacing
            expected = (max(lengths), stacked, max(widths)) if rotation == 90 else (
                max(lengths), max(widths), stacked
            )
            if any(abs(float(row[key]) - size) > 0.2 for key, size in zip(
                ("Länge_mm", "Breite_mm", "Höhe_mm"), expected
            )):
                raise ValueError("Member geometry does not match envelope")
        except (TypeError, ValueError, OverflowError):
            drawn.append(row.to_dict())
            continue

        labels = str(row.get("Ansicht_Liste", "")).split("|")
        if len(labels) != count or not all(labels):
            labels = str(row.get("Bauteile_Liste", "")).split("|")
        if len(labels) != count:
            labels = [str(row.get("Einheit_ID", ""))] * count
        cursor = 0.0
        for index in reversed(range(count)):
            member = row.to_dict()
            label = labels[index]
            member.update({
                "Typ": "Bauteil",
                "Anzahl_Bauteile": 1,
                "Ansicht_Label": label,
                "Ansicht_Liste": label,
                "Bauteile": label,
                "Bauteile_Liste": label,
                "Länge_mm": lengths[index],
                "Breite_mm": heights[index] if rotation == 90 else widths[index],
                "Höhe_mm": widths[index] if rotation == 90 else heights[index],
            })
            axis = "Y_mm" if rotation == 90 else "Z_mm"
            member[axis] = float(row[axis]) + cursor
            drawn.append(member)
            cursor += heights[index] + spacing
    return pd.DataFrame(drawn, columns=rows.columns).reset_index(drop=True)


def bundle_spacer_pdf_note(value):
    """Describe the configured inter-bundle spacer without a fixed 40-mm claim."""
    try:
        height = float(value)
    except (TypeError, ValueError):
        height = float("nan")
    if not math.isfinite(height):
        return "Hinweis: Bundeinlagen / Lagenholz gemäss Einstellung zwischen den Bunden einlegen."
    if height <= 0:
        return "Hinweis: Keine Bundeinlage zwischen den Bunden eingestellt."
    return f"Hinweis: Einlage {height:g} mm / Lagenholz zwischen den Bunden einlegen."
