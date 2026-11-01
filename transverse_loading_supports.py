"""Grounded transverse packing timbers, separate from the legacy support search."""
import math


def _merge_padding_cells(cells):
    """Coalesce adjacent equal-height cells without bridging any empty space."""
    cells = list(cells)
    changed = True
    while changed:
        changed = False
        for i, (h, a, b, c, d, bottom) in enumerate(cells):
            for j in range(i + 1, len(cells)):
                hh, aa, bb, cc, dd, other_bottom = cells[j]
                if abs(h-hh) > .001 or abs(bottom-other_bottom) > .001:
                    continue
                if abs(c-cc) < .001 and abs(d-dd) < .001 and (
                        abs(b-aa) < .001 or abs(bb-a) < .001):
                    merged = (h, min(a, aa), max(b, bb), c, d, bottom)
                elif abs(a-aa) < .001 and abs(b-bb) < .001 and (
                        abs(d-cc) < .001 or abs(dd-c) < .001):
                    merged = (h, a, b, min(c, cc), max(d, dd), bottom)
                else:
                    continue
                cells[i] = merged
                cells.pop(j)
                changed = True
                break
            if changed:
                break
    return cells


def transverse_support_rows(state, unit, x, y, z, length, width, target_area,
                            direct_rects, union_area, box_values):
    """Fill missing bearing area in free cells, on the deck or lower loads.

    Only actual free vertical volumes are used. A timber cannot float, intersect
    another item, or create support outside the physical deck's X footprint.
    """
    rows = state.get("placements", [])
    base = float(state.get("base_wood_height", 0))
    deck_x = float(state.get("Überhang_hinten_mm", 0))
    xmin, xmax = max(x, deck_x), min(x + length, deck_x + float(state["Länge_mm"]))
    ymin, ymax = max(y, 0), min(y + width, float(state["Breite_mm"]))
    boxes = [box for row in rows if (box := box_values(row)) is not None]
    xs, ys = {xmin, xmax}, {ymin, ymax}
    for a, b, c, d, _, _ in boxes:
        if a < xmax and b > xmin and c < ymax and d > ymin:
            xs.update(v for v in (a, b) if xmin < v < xmax)
            ys.update(v for v in (c, d) if ymin < v < ymax)
    xs, ys = sorted(xs), sorted(ys)
    cells = []
    padding = float(state.get("height_compensation_mm", 0))
    for a, b in zip(xs, xs[1:]):
        for c, d in zip(ys, ys[1:]):
            if b - a < 20 or d - c < 20:
                continue
            below = [box for box in boxes if
                     min(b, box[1]) - max(a, box[0]) > .01 and
                     min(d, box[3]) - max(c, box[2]) > .01]
            if any(box[5] > z + .01 for box in below):
                continue
            bottom = max([base] + [box[5] for box in below])
            if z - bottom < .1:
                continue
            if padding > .1 and abs(z - bottom - padding) > .1:
                continue
            cells.append((z - bottom, a, b, c, d, bottom))
    if padding > .1:
        cells = _merge_padding_cells(cells)
        # Use the available lower footprint, not a minimum-area patch at just
        # one end of a raised member. The centre must have a real bearing surface.
        cx, cy = x + length / 2., y + width / 2.
        if not any(a <= cx <= b and c <= cy <= d for _, a, b, c, d, _ in cells):
            return None
        available = sum((b-a) * (d-c) for _, a, b, c, d, _ in cells)
        if available + 1e-6 < target_area:
            return None
        target_area = available
    covered = list(direct_rects)
    planned = []
    uid = str(unit.get("Einheit_ID", ""))
    for height, a, b, c, d, bottom in sorted(cells):
        remaining = target_area - union_area(covered)
        if remaining <= 1e-6:
            break
        # Round upwards, never leave a numerically undersized support.
        take = min(b - a, max(20., math.ceil(remaining / (d - c) * 10) / 10))
        if a + take > b + .001:
            continue
        rect = (a, a + take, c, d)
        if union_area(covered + [rect]) <= union_area(covered) + 1e-6:
            continue
        planned.append({
            "Fuhre_Nr": state.get("Fuhre_Nr"), "Fuhrenoption": state.get("Fuhrenoption", ""),
            "Pritschenname": state.get("Pritschenname", ""), "Pritsche": state.get("Pritsche", ""),
            "Einheit_ID": f"UBY_{uid}_{len(planned)+1}", "Typ": "Unterbau",
            "Anzahl_Bauteile": 0, "Bauteile": "Ausgleich Y", "Bauteile_Liste": "Ausgleich Y",
            "Ansicht_Label": "Ausgleich Y", "Ansicht_Liste": "Ausgleich Y",
            "X_mm": a, "Y_mm": c, "Z_mm": bottom,
            "Länge_mm": take, "Breite_mm": d - c, "Höhe_mm": height,
            "Gewicht_kg": 0., "Drehung": 0, "Ebene": "Seitlicher Ausgleich erforderlich",
            "Auflager_fuer": uid, "Auflager_Offset_X_mm": a - x, "Auflager_Offset_Y_mm": c - y,
        })
        covered.append(rect)
    return planned if union_area(covered) + 1e-6 >= target_area else None
