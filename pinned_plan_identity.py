"""Stable trip identifiers and serializable requests for cumulative manual pins."""

import pandas as pd


def pin_requests(pin):
    if not isinstance(pin, dict):
        return []
    if 'pin_requests' in pin:
        return list(pin['pin_requests'])
    if not pin.get('unit_ids'):
        return []
    coordinates = pin.get('coordinates', {})
    if not coordinates:
        frame = pin.get('pinned_placements_df', pd.DataFrame())
        coordinates = {
            str(row['Einheit_ID']): {f'{axis}_mm': float(row[f'{axis}_mm'])
                                    for axis in ('X', 'Y', 'Z')}
            for _, row in frame.iterrows()
        }
    return [{'unit_ids': list(pin['unit_ids']),
             'target_platform': str(pin['target_platform']), 'coordinates': coordinates}]


def restore_trip_names(frames, source_platforms, retained_platforms):
    """Reuse available source trip numbers; never offset by the selected trip number."""
    placements, summary, used, log, units = frames
    if used.empty:
        return
    retained = set(pd.to_numeric(retained_platforms['Fuhre_Nr']).astype(int))
    source_numbers = sorted(set(pd.to_numeric(source_platforms['Fuhre_Nr']).astype(int)))
    available = [number for number in source_numbers if number not in retained]
    old_numbers = sorted(set(pd.to_numeric(used['Fuhre_Nr']).astype(int)))
    next_number = max(source_numbers + list(retained) + [0]) + 1
    while len(available) < len(old_numbers):
        available.append(next_number)
        next_number += 1
    number_map = dict(zip(old_numbers, available))
    name_map = {}
    for _, row in used.iterrows():
        number = number_map[int(row['Fuhre_Nr'])]
        matching = source_platforms[
            pd.to_numeric(source_platforms['Fuhre_Nr']).eq(number)
            & source_platforms['Pritschenname'].astype(str).eq(str(row['Pritschenname']))
        ]
        name_map[str(row['Pritsche'])] = (
            str(matching.iloc[0]['Pritsche']) if len(matching) == 1
            else f"F{number:02d} {row['Pritschenname']}"
        )
    for frame in frames:
        if frame is None or frame.empty:
            continue
        if 'Fuhre_Nr' in frame:
            frame['Fuhre_Nr'] = frame['Fuhre_Nr'].map(
                lambda value: number_map.get(int(value), value) if pd.notna(value) else value
            )
        if 'Pritsche' in frame:
            frame['Pritsche'] = frame['Pritsche'].astype(str).map(lambda value: name_map.get(value, value))
        if 'Pritschen' in frame:
            frame['Pritschen'] = frame['Pritschen'].astype(str).map(
                lambda value: ', '.join(name_map.get(name.strip(), name.strip())
                                       for name in value.split(','))
            )


def platform_changes(before, after):
    old = set(before['Pritsche'].astype(str))
    new = set(after['Pritsche'].astype(str))
    return pd.DataFrame([
        {'Pritsche': name, 'Status': ('Beibehalten' if name in old & new
                                     else 'Neu' if name in new else 'Entfällt')}
        for name in sorted(old | new)
    ])