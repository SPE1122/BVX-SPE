"""Search free geometry around immutable manual loads using the normal safety gates."""

from time import perf_counter


def place_around_fixed_loads(
    state, unit, allow_beside, allow_stack, allow_rotation, *,
    orientations, candidate_x_values, can_place_stable, commit_place,
    support_metrics, planned_supports, row_box, boxes_overlap, is_real_load,
):
    deadline = state.get('_pinned_search_deadline')
    if deadline is not None and perf_counter() >= deadline:
        return None
    rows = state['placements']
    geometry = [(row, row_box(row)) for row in rows]
    geometry = [(row, box) for row, box in geometry if box is not None]
    width_limit = state['Breite_mm']
    base_z = state['base_wood_height'] + max(0.0, state['general_spacer_height'])
    weight = float(unit['Gewicht_kg'])
    center_x = state['Überhang_hinten_mm'] + state['Länge_mm'] / 2.0
    center_y = width_limit / 2.0
    real_geometry = [(row, box) for row, box in geometry if is_real_load(row.get('Typ', ''))]
    old_weight = sum(float(row.get('Gewicht_kg', 0.0) or 0.0) for row, _ in real_geometry)
    moment_x = sum(float(row.get('Gewicht_kg', 0.0) or 0.0) * (box[0] + box[1]) / 2.0
                   for row, box in real_geometry)
    moment_y = sum(float(row.get('Gewicht_kg', 0.0) or 0.0) * (box[2] + box[3]) / 2.0
                   for row, box in real_geometry)
    best = None
    for length, width, height, rotation in orientations(state, unit, allow_rotation):
        if width > width_limit or length > state['Eff_Länge_mm']:
            continue
        ys = {max(0.0, (width_limit - width) / 2.0)}
        if allow_beside:
            ys.update((0.0, width_limit - width, center_y, center_y - width))
            for _row, box in geometry:
                ys.update((box[2], box[3] - width, box[3], box[2] - width))
        ys = sorted(y for y in ys if 0.0 <= y <= width_limit - width + 1e-6)
        zs = {base_z}
        if allow_stack:
            for row, box in geometry:
                bundle = unit.get('Typ') == 'Bund' or row.get('Typ') == 'Bund'
                spacer = state['layer_spacer_height'] if bundle else state['general_spacer_height']
                zs.add(box[5] + max(0.0, spacer))
        for z in sorted(zs):
            if z + height > state['Max_Höhe_mm']:
                continue
            for y in ys:
                for x in candidate_x_values(state, 0.0, length, y=y, width=width, z=z):
                    if deadline is not None and perf_counter() >= deadline:
                        return None
                    if x < 0.0:
                        continue
                    box = (x, x + length, y, y + width, z, z + height)
                    if any(boxes_overlap(box, other, tol=0.001) for _row, other in geometry):
                        continue
                    if not allow_stack and any(
                        min(box[1], other[1]) > max(box[0], other[0]) + 0.001
                        and min(box[3], other[3]) > max(box[2], other[2]) + 0.001
                        for _row, other in real_geometry
                    ):
                        continue
                    if not can_place_stable(state, unit, x, y, z, length, width, height, weight):
                        continue
                    helpers = planned_supports(state, unit, x, y, z, length, width) or []
                    helper_boxes = [row_box(helper) for helper in helpers]
                    if any(
                        hbox is not None and any(
                            boxes_overlap(hbox, other, tol=0.001) for _row, other in geometry
                        ) for hbox in helper_boxes
                    ):
                        continue
                    metrics = support_metrics(state, x, y, z, length, width)
                    total = max(1.0, old_weight + weight)
                    delta = abs((moment_x + weight * (x + length / 2.0)) / total - center_x)
                    delta += abs((moment_y + weight * (y + width / 2.0)) / total - center_y)
                    score = (z, -metrics.get('area_ratio', 0.0), delta, x, y)
                    if best is None or score < best[0]:
                        best = (score, (x, y, z, length, width, height, rotation))
    if best is None:
        return None
    return commit_place(state, unit, *best[1], mode='Freiraum um manuell fixiertes Paar')


def largest_fitting_prefix(units, fixed, platform, planner, planner_kwargs, *, time_budget=20.0):
    """Keep logical order: try complete prefixes, physically reversed, largest first."""
    import pandas as pd

    if units.empty:
        return pd.DataFrame(), False
    deadline = perf_counter() + time_budget
    capacity = float(platform.iloc[0]['Max_Gewicht_kg'])
    capacity -= float(platform.iloc[0].get('Eigengewicht_Pritsche_kg', 0.0) or 0.0)
    capacity -= float(pd.to_numeric(fixed.get('Gewicht_kg'), errors='coerce').fillna(0).sum())
    weights = pd.to_numeric(units['Gewicht_kg'], errors='coerce').fillna(0).cumsum()
    limit = int((weights <= capacity + 1e-6).sum())
    fixed_ids = set(fixed['Einheit_ID'].astype(str))
    for count in range(limit, 0, -1):
        if perf_counter() >= deadline:
            return pd.DataFrame(), True
        physical = units.iloc[:count].iloc[::-1].copy().reset_index(drop=True)
        placements, _ = planner(
            physical, platform, **planner_kwargs,
            fixed_placements_df=fixed, search_deadline=deadline,
        )
        if placements.empty:
            continue
        wanted = set(physical['Einheit_ID'].astype(str))
        actual = set(placements.loc[
            placements['Pritsche'].ne('NICHT VERLADEN')
            & placements['Einheit_ID'].astype(str).isin(wanted), 'Einheit_ID'
        ].astype(str))
        if actual == wanted:
            return placements.loc[
                ~placements['Einheit_ID'].astype(str).isin(fixed_ids)
                & placements['Pritsche'].ne('NICHT VERLADEN')
            ].copy(), False
    return pd.DataFrame(), perf_counter() >= deadline