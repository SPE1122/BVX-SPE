"""Additional within-stack shelf packing; never replaces a valid plan on failure."""
from __future__ import annotations

import pandas as pd

from loading_diagnostics import trace_event

HELPERS = {"Unterbau", "Kantholz", "Bundeinlage", "Einlage", "Lagenholz"}


def _respects_order(rows, ranks):
    """No new bearing/vertical obstruction may reverse the input unit order."""
    records = rows.to_dict("records")
    for lower in records:
        for upper in records:
            if lower["Z_mm"] + lower["Höhe_mm"] > upper["Z_mm"] + .1:
                continue
            if (min(lower["X_mm"] + lower["Länge_mm"], upper["X_mm"] + upper["Länge_mm"])
                    - max(lower["X_mm"], upper["X_mm"]) <= 1):
                continue
            if (min(lower["Y_mm"] + lower["Breite_mm"], upper["Y_mm"] + upper["Breite_mm"])
                    - max(lower["Y_mm"], upper["Y_mm"]) <= 1):
                continue
            if ranks[str(lower["Einheit_ID"])] > ranks[str(upper["Einheit_ID"])]:
                return False
    return True


def try_side_by_side_shelves(placements, platform, units, *, make_state,
                            can_place_stable, commit_place, validate):
    """Pack consecutive atomic units beside one another inside their existing half.

    Platform membership, X positions, rotations and unit internals are unchanged.
    Shorter members are raised to a shared top only when real generated packing
    timbers can support them. Existing supports are regenerated, never left behind.
    """
    real = placements[~placements.Typ.isin(HELPERS)].copy()
    unit_by_id = {str(unit["Einheit_ID"]): unit for unit in units}
    ranks = {str(unit["Einheit_ID"]): i for i, unit in enumerate(units)}
    if (real.empty or real.Einheit_ID.astype(str).duplicated().any()
            or set(real.Einheit_ID.astype(str)) != set(unit_by_id)):
        return placements
    reference = real.copy()
    half = float(platform["Breite_mm"]) / 2.
    # Existing longitudinal stacks have a common X centre, not a common start.
    real["_center_x"] = (real.X_mm + real.Länge_mm / 2.).round(1)
    real["_side"] = (real.Y_mm + real.Breite_mm / 2. >= half).astype(int)
    real["_height_pad_mm"] = 0.
    state = make_state()
    supports_enabled = bool(state.get("consider_generated_supports", False))
    groups = []
    for (center_x, side), stack in real.groupby(["_center_x", "_side"], sort=False):
        stack = stack.sort_values("Z_mm", kind="stable")
        indices = list(stack.index)
        cursor = float(stack.iloc[0].Z_mm)
        i = 0
        while i < len(indices):
            first = real.loc[indices[i]]
            shelf = [indices[i]]
            span = float(first.Breite_mm)
            j = i + 1
            while j < len(indices):
                previous = real.loc[indices[j-1]]
                following = real.loc[indices[j]]
                consecutive = ranks[str(following.Einheit_ID)] == ranks[str(previous.Einheit_ID)] + 1
                touching_layers = abs(float(following.Z_mm - previous.Z_mm - previous.Höhe_mm)) <= .1
                heights = [float(real.loc[idx, "Höhe_mm"]) for idx in shelf] + [float(following.Höhe_mm)]
                if (not consecutive or not touching_layers
                        or span + float(following.Breite_mm) > half + .01
                        or (max(heights) - min(heights) > .1 and not supports_enabled)):
                    break
                shelf.append(indices[j])
                span += float(following.Breite_mm)
                j += 1
            height = max(float(real.loc[idx, "Höhe_mm"]) for idx in shelf)
            y_cursor = half
            for idx in shelf:
                row = real.loc[idx]
                real.loc[idx, "Z_mm"] = cursor + height - float(row.Höhe_mm)
                if len(shelf) > 1:
                    real.loc[idx, "_height_pad_mm"] = height - float(row.Höhe_mm)
                if len(shelf) > 1:
                    if side == 0:
                        y_cursor -= float(row.Breite_mm)
                    real.loc[idx, "Y_mm"] = y_cursor
                    if side == 1:
                        y_cursor += float(row.Breite_mm)
            if len(shelf) > 1:
                groups.append([str(real.loc[idx, "Einheit_ID"]) for idx in shelf])
            cursor += height
            # Preserve every original inter-layer gap outside a merged shelf.
            if j < len(indices):
                old_top = float(reference.loc[indices[j-1], "Z_mm"] + reference.loc[indices[j-1], "Höhe_mm"])
                cursor += max(0., float(reference.loc[indices[j], "Z_mm"]) - old_top)
            i = j
    if not groups:
        return placements
    if not _respects_order(real, ranks):
        trace_event("Nebeneinander_Lage_abgelehnt", Grund="Entnahmereihenfolge", Gruppen=groups)
        return placements
    masses = pd.to_numeric(reference.Gewicht_kg, errors="coerce").fillna(0).clip(lower=0)
    if masses.sum() > 0:
        old_y = ((reference.Y_mm + reference.Breite_mm / 2.) * masses).sum() / masses.sum()
        new_y = ((real.Y_mm + real.Breite_mm / 2.) * masses).sum() / masses.sum()
        if (abs(new_y - half) > abs(old_y - half) + 10.
                or (real.Z_mm * masses).sum() >= (reference.Z_mm * masses).sum() - .01):
            trace_event("Nebeneinander_Lage_abgelehnt", Grund="Gewichtsverteilung", Gruppen=groups)
            return placements
    if (real.Z_mm + real.Höhe_mm).max() > (reference.Z_mm + reference.Höhe_mm).max() + .1:
        return placements
    # Rebuild in physical bottom-up order, including required height compensation.
    for _, row in real.sort_values("Z_mm", kind="stable").iterrows():
        unit = unit_by_id[str(row.Einheit_ID)]
        args = (float(row.X_mm), float(row.Y_mm), float(row.Z_mm),
                float(row.Länge_mm), float(row.Breite_mm), float(row.Höhe_mm))
        # A raised short member needs physical timber, not the legacy nearest
        # lower-surface heuristic across an undeclared vertical gap.
        state["exact_support_contact"] = float(row["_height_pad_mm"]) > .1
        state["height_compensation_mm"] = float(row["_height_pad_mm"])
        if not can_place_stable(state, unit, *args, float(row.Gewicht_kg)):
            trace_event("Nebeneinander_Lage_abgelehnt", Grund="Auflage oder Platzierung",
                        Einheit_ID=str(row.Einheit_ID), Gruppen=groups)
            return placements
        commit_place(state, unit, *args, int(row.get("Drehung", 0)),
                     "Flexible Verladung / Nebeneinander je Lage")
    candidate = pd.DataFrame(state["placements"])
    actual = candidate[~candidate.Typ.isin(HELPERS)]
    if (sorted(actual.Einheit_ID.astype(str)) != sorted(reference.Einheit_ID.astype(str))
            or abs(actual.Gewicht_kg.sum() - reference.Gewicht_kg.sum()) > .01):
        return placements
    if masses.sum() > 0:
        old_x = ((reference.X_mm + reference.Länge_mm / 2.) * masses).sum() / masses.sum()
        new_x = ((actual.X_mm + actual.Länge_mm / 2.) * actual.Gewicht_kg).sum() / masses.sum()
        if abs(new_x - old_x) > 1.:
            return placements
    if not validate(candidate):
        trace_event("Nebeneinander_Lage_abgelehnt", Grund="Abschlussprüfung", Gruppen=groups)
        return placements
    trace_event("Nebeneinander_Lage_übernommen", Gruppen=groups,
                Ersparnis_Summe_Z_mm=float((reference.Z_mm - real.Z_mm).sum()))
    return candidate
