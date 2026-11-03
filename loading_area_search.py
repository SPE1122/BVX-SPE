"""Bounded, additive floor-first packing without fixed tower centres."""
from __future__ import annotations

import time
import pandas as pd

from loading_diagnostics import trace_event
from loading_shelf_search import HELPERS, _respects_order


def _real(rows):
    return rows.loc[~rows.Typ.isin(HELPERS)]


def _metrics(rows, deck):
    real = _real(rows)
    mass = real.Gewicht_kg.clip(lower=0)
    total = float(mass.sum())
    if total <= 0:
        mass = pd.Series(1., index=real.index)
        total = float(len(real))
    back = float(deck.get("Überhang_hinten_mm", 0))
    length, width = float(deck["Länge_mm"]), float(deck["Breite_mm"])
    return {
        "x": abs(float(((real.X_mm + real.Länge_mm / 2) * mass).sum() / total) - back - length / 2),
        "y": abs(float(((real.Y_mm + real.Breite_mm / 2) * mass).sum() / total) - width / 2),
        "z": float(((real.Z_mm + real.Höhe_mm / 2) * mass).sum() / total),
        "height": float((real.Z_mm + real.Höhe_mm).max()),
        "overhang": max(0., back - real.X_mm.min()) + max(0., (real.X_mm + real.Länge_mm).max() - back - length),
    }


def try_area_layout(rows, deck, *, make_state, can_place, commit, validate,
                    seconds=8., clock=time.monotonic):
    """Keep platform membership, atomic units and physical order unchanged.

    Every candidate is built bottom-up in reverse logical unloading order.
    New members can never be inserted underneath an earlier member. Candidate
    heights follow actual overlapping surfaces rather than a fixed tower.
    Only complete, validated, non-worsening improvements are returned.
    """
    real = _real(rows).copy()
    rank_col = "Logische_Reihenfolge_im_Block"
    if real.empty or rank_col not in real:
        return rows
    ranks = pd.to_numeric(real[rank_col], errors="coerce")
    if ranks.isna().any() or ranks.duplicated().any() or real.Einheit_ID.duplicated().any():
        return rows
    # Do not move manual/pinned placements, even if other parts are automatic.
    if ("Manuelle_Zone" in real
            and real.Manuelle_Zone.fillna("").astype(str).str.strip().ne("").any()):
        return rows
    if ("Manuelle_Reihenfolge" in real
            and pd.to_numeric(real.Manuelle_Reihenfolge, errors="coerce").fillna(0).ne(0).any()):
        return rows
    real[rank_col] = ranks
    units = [r for _, r in real.sort_values(rank_col, ascending=False).iterrows()]
    physical_ranks = {str(r.Einheit_ID): i for i, r in enumerate(units)}
    original = _metrics(rows, deck)
    best, best_metrics = rows, original
    deadline = clock() + seconds
    back = float(deck.get("Überhang_hinten_mm", 0))
    length, width = float(deck["Länge_mm"]), float(deck["Breite_mm"])
    end = back + length
    usable = end + float(deck.get("Überhang_vorne_mm", 0))
    attempts = 0
    for direction in ("front", "rear", "balanced"):
        state = make_state()
        placed = []
        mass_sum = mx = my = 0.
        complete = True
        for unit in units:
            if clock() >= deadline:
                complete = False
                break
            l, w, h, mass = (float(unit[k]) for k in ("Länge_mm", "Breite_mm", "Höhe_mm", "Gewicht_kg"))
            gap = float(state.get("gap_length", 0))
            xs = {0., back, end-l, usable-l, back+(length-l)/2}
            ys = {0., width-w, (width-w)/2}
            for px, py, pz, pl, pw, ph, _ in placed:
                xs.update((px, px+pl-l, px+pl+gap, px-l-gap))
                ys.update((py, py+pw-w, py+pw, py-w))
            xs = sorted({round(x, 1) for x in xs if -.01 <= x <= usable-l+.01})
            ys = sorted({round(y, 1) for y in ys if -.01 <= y <= width-w+.01})
            if len(xs) > 40:
                xs = sorted(set(xs[:4] + xs[-4:] + sorted(
                    xs, key=lambda x: abs(x+l/2-back-length/2))[:32]))
            if len(ys) > 24:
                ys = sorted(set(ys[:4] + ys[-4:] + sorted(
                    ys, key=lambda y: abs(y+w/2-width/2))[:16]))
            options = []
            for x in xs:
                if clock() >= deadline:
                    break
                for y in ys:
                    overlaps = [p for p in placed
                                if min(x+l, p[0]+p[3])-max(x, p[0]) > .1
                                and min(y+w, p[1]+p[4])-max(y, p[1]) > .1]
                    z = float(state["base_wood_height"])
                    if overlaps:
                        if not state.get("area_allow_stack", True):
                            continue
                        top = max(p[2]+p[5] for p in overlaps)
                        bundle = str(unit.Typ) == "Bund" or any(
                            p[6] == "Bund" for p in overlaps if abs(p[2]+p[5]-top) < .1)
                        z = top + float(state["layer_spacer_height"] if bundle
                                        else state["general_spacer_height"])
                    if z+h > original["height"]+.1:
                        continue
                    overhang = max(0., back-x) + max(0., x+l-end)
                    denominator = max(.01, mass_sum+mass)
                    balance = abs((mx+mass*(x+l/2))/denominator-(back+length/2))
                    side = abs((my+mass*(y+w/2))/denominator-width/2)
                    # Lowest feasible surface first; deck coverage before
                    # overhang. Edge starts leave usable contiguous floor.
                    anchor = (abs(x-(end-l)) if direction == "front" else
                              abs(x-back) if direction == "rear" else balance)
                    # Do not chase the partial load's centre after each member.
                    # Align bearing edges; balance is judged on the complete load.
                    alignment = min((min(abs(x-p[0]), abs(x+l-p[0]-p[3]))
                                     for p in overlaps), default=0.)
                    score = (z, alignment, anchor+side*4, overhang, x, y)
                    options.append((score, x, y, z))
            chosen = None
            for _, x, y, z in sorted(options):
                if clock() >= deadline:
                    break
                attempts += 1
                if can_place(state, unit, x, y, z, l, w, h, mass):
                    chosen = (x, y, z)
                    break
            if chosen is None:
                complete = False
                break
            x, y, z = chosen
            commit(state, unit, x, y, z, l, w, h, int(unit.get("Drehung", 0)),
                   "Flächenorientiert / freie X-Y-Lagen")
            placed.append((x, y, z, l, w, h, str(unit.Typ)))
            mass_sum += mass
            mx += mass*(x+l/2)
            my += mass*(y+w/2)
        if not complete:
            trace_event("Flächensuche_Kandidat", Richtung=direction,
                        Pritsche=str(deck.get("Pritsche", "")),
                        Grund="Unvollständig", Geladen=len(placed))
            continue
        candidate = pd.DataFrame(state["placements"])
        actual = _real(candidate)
        if (sorted(actual.Einheit_ID.astype(str)) != sorted(real.Einheit_ID.astype(str))
                or abs(actual.Gewicht_kg.sum()-real.Gewicht_kg.sum()) > .01
                or not _respects_order(actual, physical_ranks)):
            continue
        # Preserve trip identity and all source metadata; commit supplies the
        # geometry and newly generated supports, never stale old helper rows.
        for col in ("Fuhre_Nr", "Fuhrenoption", "Pritschenname"):
            if col in rows:
                candidate[col] = rows.iloc[0][col]
        # Translate the complete load (supports included), never individual
        # layers, to balance its final mass within the configured envelope.
        masses = actual.Gewicht_kg.clip(lower=0)
        hard_overhang = any(float(state.get(key, 0) or 0) > 0 for key in (
            "max_unsupported_length_percent", "max_unsupported_side_percent",
            "max_unsupported_length_mm", "max_unsupported_side_mm",
        ))
        if masses.sum() > 0 and not hard_overhang:
            cx = float(((actual.X_mm+actual.Länge_mm/2)*masses).sum()/masses.sum())
            dx = back+length/2-cx
            dx = min(max(dx, -float(candidate.X_mm.min())),
                     usable-float((candidate.X_mm+candidate.Länge_mm).max()))
            shifted = candidate.copy()
            shifted["X_mm"] += dx
            if validate(shifted):
                candidate = shifted
        quality = _metrics(candidate, deck)
        nonworse = all(quality[k] <= original[k]+1. for k in ("z", "height"))
        # A virtually exact old X centre must not veto a much lower layout.
        # Permit a small centre band only for a substantial height reduction;
        # all hard support, deck, weight and collision limits remain unchanged.
        x_limit = original["x"]+1.
        if quality["height"] <= original["height"]-100. and quality["z"] < original["z"]:
            x_limit = max(x_limit, length*.02)
        nonworse = nonworse and quality["x"] <= x_limit
        nonworse = nonworse and quality["y"] <= original["y"]+1.
        score = lambda q: q["z"]*2 + q["height"] + q["x"]*2 + q["y"]*4 + q["overhang"]
        trace_event("Flächensuche_Kandidat", Richtung=direction,
                    Pritsche=str(deck.get("Pritsche", "")),
                    Qualität=quality, Vergleich_bestanden=nonworse)
        if (nonworse and score(quality) < score(best_metrics)-1.
                and validate(candidate)):
            best, best_metrics = candidate, quality
    trace_event("Flächensuche", Pritsche=str(deck.get("Pritsche", "")),
                übernommen=best is not rows, vorher=original, nachher=best_metrics,
                Platzierungsprüfungen=attempts, Zeitbudget_erreicht=clock() >= deadline)
    return best
