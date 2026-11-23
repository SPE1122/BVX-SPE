"""Conservative optional search: two short ground elements per side, end-to-end.

Works on an already valid, single-platform standard layout. It does not move
parts between platforms, split bundles, or change the logical extraction order.
The caller must still perform the application's full safety checks.
"""

from __future__ import annotations

import pandas as pd


def build_paired_short_base(placements: pd.DataFrame, platform: pd.Series,
                            gap_mm: float = 0.0) -> tuple[pd.DataFrame, str]:
    empty = pd.DataFrame()
    required = {'Typ', 'Einheit_ID', 'Logische_Reihenfolge_im_Block', 'X_mm',
                'Y_mm', 'Z_mm', 'Länge_mm', 'Breite_mm', 'Höhe_mm'}
    if placements is None or placements.empty or not required.issubset(placements.columns):
        return empty, 'Keine auswertbaren Positionsdaten'
    # No implicit relocation of support timbers or nonstandard loading units.
    if not placements['Typ'].astype(str).isin(('Bauteil', 'Bund')).all():
        return empty, 'Zusätzliche Auflager oder Sonderpositionen vorhanden'
    if placements['Einheit_ID'].astype(str).duplicated().any():
        return empty, 'Verladeeinheiten nicht eindeutig'
    if 'Pritsche' in placements.columns and placements['Pritsche'].astype(str).nunique() != 1:
        return empty, 'Mehrere Pritschen im Bauteilblock'

    deck_width = float(platform.get('Breite_mm', 0) or 0)
    deck_length = float(platform.get('Länge_mm', 0) or 0)
    deck_back = float(platform.get('Überhang_hinten_mm', 0) or 0)
    deck_front = float(platform.get('Überhang_vorne_mm', 0) or 0)
    base_z = float(platform.get('Kantholz_erste_Lage_mm', 0) or 0)
    gap = max(0.0, float(gap_mm))
    if deck_width <= 0 or deck_length <= 0:
        return empty, 'Ungültige Pritschenabmessungen'
    half = deck_width / 2.0
    rows = placements.copy()
    for column in ('X_mm', 'Y_mm', 'Z_mm', 'Länge_mm', 'Breite_mm', 'Höhe_mm',
                   'Logische_Reihenfolge_im_Block'):
        rows[column] = pd.to_numeric(rows[column], errors='coerce')
    if rows[list(required - {'Typ', 'Einheit_ID'})].isna().any().any():
        return empty, 'Ungültige Masse oder Bauteilreihenfolge'
    if (rows[['Länge_mm', 'Breite_mm', 'Höhe_mm']] <= 0).any().any():
        return empty, 'Ungültige Bauteilabmessungen'
    if rows['Logische_Reihenfolge_im_Block'].duplicated().any():
        return empty, 'Bauteilreihenfolge nicht eindeutig'
    left = rows.loc[rows.Y_mm + rows.Breite_mm <= half + 0.1].sort_values('Z_mm')
    right = rows.loc[rows.Y_mm >= half - 0.1].sort_values('Z_mm')
    if len(left) + len(right) != len(rows) or min(len(left), len(right)) < 3:
        return empty, 'Keine zwei unabhängigen Seitenstapel'

    first_four = set(rows.nlargest(4, 'Logische_Reihenfolge_im_Block').Einheit_ID.astype(str))
    chosen_four = set()
    candidate = placements.copy()
    for lane in (left, right):
        if not lane.Logische_Reihenfolge_im_Block.is_monotonic_decreasing:
            return empty, 'Entnahmereihenfolge innerhalb einer Seite nicht nachgewiesen'
        low, next_low, above = (lane.iloc[i] for i in range(3))
        chosen_four.update((str(low.Einheit_ID), str(next_low.Einheit_ID)))
        if abs(float(low.Z_mm) - base_z) > 1.0:
            return empty, 'Unterste Lage nicht direkt auf der Pritsche'
        if abs(float(low.Länge_mm) - float(next_low.Länge_mm)) > 1.0:
            return empty, 'Unterschiedliche Längen der kurzen Basiselemente'
        if abs(float(low.Höhe_mm) - float(next_low.Höhe_mm)) > 1.0:
            return empty, 'Unterschiedliche Höhen der kurzen Basiselemente'
        if (abs(float(low.Y_mm) - float(next_low.Y_mm)) > 1.0
                or abs(float(low.Y_mm) - float(above.Y_mm)) > 1.0
                or abs(float(low.Breite_mm) - float(next_low.Breite_mm)) > 1.0
                or abs(float(low.Breite_mm) - float(above.Breite_mm)) > 1.0):
            return empty, 'Lagen nicht deckungsgleich in der Breite'
        z_gap = float(next_low.Z_mm - low.Z_mm)
        if z_gap < float(low.Höhe_mm) - 1.0 or z_gap > float(low.Höhe_mm) + 80.0:
            return empty, 'Keine direkt übereinanderliegenden kurzen Basiselemente'
        if float(above.Z_mm) < float(next_low.Z_mm + next_low.Höhe_mm) - 1.0:
            return empty, 'Keine freie Lage über den kurzen Elementen'
        pair_span = float(low.Länge_mm) + gap + float(next_low.Länge_mm)
        if pair_span > float(above.Länge_mm) + 0.1 or float(above.Länge_mm) < 1.5 * float(low.Länge_mm):
            return empty, 'Darüberliegendes Element kann die Kurzteilreihe nicht überspannen'
        # Both short parts are physically on the deck and under the first long part.
        low_x = max(0.0, deck_back, float(above.X_mm))
        high_x = min(deck_back + deck_length - pair_span,
                     deck_length + deck_back + deck_front - pair_span,
                     float(above.X_mm + above.Länge_mm) - pair_span)
        if high_x < low_x - 0.1:
            return empty, 'Beide Kurzbauteile passen nicht unter die lange Auflage'
        desired = float(above.X_mm) + (float(above.Länge_mm) - pair_span) / 2.0
        x = round(min(high_x, max(low_x, desired)), 1)
        lower_id = candidate['Einheit_ID'].astype(str).eq(str(low.Einheit_ID))
        second_id = candidate['Einheit_ID'].astype(str).eq(str(next_low.Einheit_ID))
        candidate.loc[lower_id, 'X_mm'] = x
        candidate.loc[second_id, 'X_mm'] = round(x + float(low.Länge_mm) + gap, 1)
        candidate.loc[second_id, 'Z_mm'] = round(float(low.Z_mm), 1)
        higher_ids = set(lane.iloc[2:].Einheit_ID.astype(str))
        candidate.loc[candidate['Einheit_ID'].astype(str).isin(higher_ids), 'Z_mm'] = (
            candidate.loc[candidate['Einheit_ID'].astype(str).isin(higher_ids), 'Z_mm'].astype(float) - z_gap
        ).round(1)

    if chosen_four != first_four:
        return empty, 'Kurzteilbasis ist kein zusammenhängender unterster Nr.PL-Block'
    candidate['Ebene'] = (candidate.get('Ebene', pd.Series('', index=candidate.index))
                          .fillna('').astype(str) + ' / Geordnete Laengsstapel / kurze Basis hintereinander')
    return candidate, 'Kurze Basiselemente je Seite hintereinander geprüft'
