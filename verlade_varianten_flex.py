"""Zusätzliche, abschaltbare Varianten für die BVX-Verladeplanung.

Die bisherige Standard- und Längsstapel-Logik wird nicht verändert.
Jede Platzierung nutzt die bestehenden Auflage-, Gewichts- und Kollisionsprüfungen.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations_with_replacement
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd


def _width_profiles(records: List[pd.Series], deck_width: float,
                    two_lane: bool, flexible_width: bool) -> List[Tuple[float, ...]]:
    widths = [float(row['Breite_mm']) for row in records]
    if not widths or min(widths) <= 0.0 or max(widths) > deck_width + 0.01:
        return []
    half = deck_width / 2.0
    fixed = (half, half)
    if not flexible_width:
        return [fixed] if two_lane and max(widths) <= half + 0.01 else []

    # Die Kandidaten stammen aus tatsächlich vorkommenden Elementbreiten.
    # Keine starre Unterteilung in 1'225-mm-Bahnen.
    counts = Counter(round(w, 1) for w in widths)
    candidates = sorted(counts, key=lambda w: (-counts[w], -w))[:8]
    profiles = {(deck_width,), fixed}
    for count in range(2, 5):
        for profile in combinations_with_replacement(candidates, count):
            if sum(profile) <= deck_width + 0.01:
                profiles.add(tuple(sorted(profile, reverse=True)))

    def rank(profile: Tuple[float, ...]) -> Tuple[float, float, float]:
        if any(all(width > lane + 0.01 for lane in profile) for width in widths):
            return (-1.0, 0.0, 0.0)
        # Enge Passung und mehrere nutzbare Breitenbahnen bevorzugen.
        wasted = sum(min(lane - width for lane in profile if lane + 0.01 >= width)
                     for width in widths) / len(widths)
        return (float(len(profile)) * 150.0 - wasted * 0.12,
                -float(deck_width - sum(profile)), -float(len(profile)))
    eligible = [p for p in profiles if rank(p)[0] >= 0.0]
    eligible.sort(key=rank, reverse=True)
    return eligible[:12]


def _assign_to_stacks(records: List[pd.Series], widths: Tuple[float, ...],
                      deck_length: float, max_height: float, base_height: float,
                      gap: float, layer_gap: float, general_gap: float,
                      strategy: str) -> Optional[List[List[pd.Series]]]:
    # Zwei Längsstapel pro Breitenbahn, unabhängig gefüllt.
    stacks: List[List[pd.Series]] = [[] for _ in widths for _ in range(2)]
    heights = [base_height] * len(stacks)
    lengths = [0.0] * len(stacks)

    for row in records:
        width = float(row['Breite_mm'])
        length = float(row['Länge_mm'])
        height = float(row['Höhe_mm'])
        viable: List[Tuple[float, int, float, float]] = []
        for i, stack in enumerate(stacks):
            lane = i // 2
            if width > widths[lane] + 0.01:
                continue
            old = stack[-1] if stack else None
            spacer = (layer_gap if old is not None and (
                str(old.get('Typ', '')) == 'Bund' or str(row.get('Typ', '')) == 'Bund'
            ) else general_gap if old is not None else 0.0)
            next_height = heights[i] + height + spacer
            next_length = max(lengths[i], length)
            other_length = lengths[i ^ 1]
            if (next_height > max_height + 0.01
                    or next_length + (gap if other_length else 0.0)
                    + other_length > deck_length + 0.01):
                continue

            # Breite passend ausnutzen, Höhen gleichmässig verteilen.
            width_waste = widths[lane] - width
            if strategy == 'hoehe':
                score = next_height + width_waste * 0.22
            elif strategy == 'breite':
                score = width_waste * 2.0 + next_height * 0.25
            else:
                # Zunächst vorhandene Stapel auffüllen (Reihenfolge je Stapel).
                score = next_height * 0.4 + width_waste * 0.45 - (650.0 if stack else 0.0)
            # Kleine deterministische Präferenz; keine Veränderung der Bauteilfolge.
            score += i * 0.002
            viable.append((score, i, next_height, next_length))
        if not viable:
            return None
        _, index, next_height, next_length = min(viable)
        stacks[index].append(row)
        heights[index] = next_height
        lengths[index] = next_length
    return stacks


def calculate_flexible_loading(
    physical_units: pd.DataFrame,
    platform_row: pd.Series,
    *,
    two_lane: bool,
    flexible_width: bool,
    init_platform_state: Callable[..., Dict[str, Any]],
    can_place_stable: Callable[..., bool],
    commit_place: Callable[..., Dict[str, Any]],
    find_geometry_conflicts: Callable[..., pd.DataFrame],
    support_chain_issues: Callable[..., pd.DataFrame],
    physical_conflicts: Callable[..., pd.DataFrame],
    recompute_summary: Callable[..., pd.DataFrame],
    load_quality: Callable[..., Dict[str, float]],
    base_default: float,
    layer_default: float,
    general_default: float,
    gap_default: float,
    prevent_wide_on_narrow: bool,
    min_support_ratio: float,
    max_unsupported_length_mm: float,
    max_unsupported_side_mm: float,
    max_unsupported_length_percent: float,
    max_unsupported_side_percent: float,
    prefer_support_quality: bool,
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    """Sucht zusätzliche flexible Breiten-/Längslagen, ohne bestehende Pläne zu ändern.

    Die ursprüngliche Reihenfolge wird innerhalb jeder der unabhängigen
    Stapelbahnen beibehalten. Breite Elemente ohne passende Bahn werden nicht
    erzwungen: die aufrufende Hauptlogik fällt dann auf Standard zurück.
    """
    empty = pd.DataFrame()
    if physical_units is None or physical_units.empty:
        return empty, empty, 'Keine Verladeeinheiten'

    records = [row for _, row in physical_units.iterrows()]
    deck_len = float(platform_row.get('Länge_mm', 0.0))
    deck_width = float(platform_row.get('Breite_mm', 0.0))
    deck_height = float(platform_row.get('Max_Höhe_mm', 0.0))
    deck_back = float(platform_row.get('Überhang_hinten_mm', 0.0))
    effective_length = deck_len + deck_back + float(platform_row.get('Überhang_vorne_mm', 0.0))
    base_z = float(platform_row.get('Kantholz_erste_Lage_mm', base_default))
    gap = max(0.0, float(gap_default))
    if min(deck_len, deck_width, deck_height) <= 0 or deck_height <= base_z:
        return empty, empty, 'Ungültige Pritschenmasse'
    if any(min(float(r['Länge_mm']), float(r['Breite_mm']), float(r['Höhe_mm'])) <= 0
           or float(r['Länge_mm']) > effective_length + 0.01 for r in records):
        return empty, empty, 'Bauteilmass ausserhalb der Pritschengrenzen'
    if (sum(float(r['Gewicht_kg']) for r in records)
            + float(platform_row.get('Eigengewicht_Pritsche_kg', 0.0))
            > float(platform_row.get('Max_Gewicht_kg', 0.0)) + 0.01):
        return empty, empty, 'Gewichtsgrenze'

    profiles = _width_profiles(records, deck_width, two_lane, flexible_width)
    if not profiles:
        return empty, empty, 'Keine passende Breitenaufteilung'
    platform_df = pd.DataFrame([platform_row])
    best_df, best_summary = empty, empty
    best_score: Optional[float] = None
    diagnostics = Counter()

    for profile in profiles:
        for strategy in ('hoehe', 'breite', 'folge'):
            stacks = _assign_to_stacks(
                records, profile, effective_length, deck_height, base_z,
                gap, layer_default, general_default, strategy
            )
            if stacks is None:
                diagnostics['Breite, Höhe oder Länge'] += 1
                continue
            # X-Position je Bahn ermitteln. Die zwei Längsstapel einer Bahn
            # benötigen nie mehr als die konfigurierte Nutzlänge.
            anchors: List[float] = []
            x_lengths: List[float] = []
            for stack in stacks:
                x_lengths.append(max((float(r['Länge_mm']) for r in stack), default=0.0))
            for lane_index in range(len(profile)):
                first = x_lengths[lane_index * 2]
                second = x_lengths[lane_index * 2 + 1]
                span = first + (gap if first and second else 0.0) + second
                center = deck_back + deck_len / 2.0
                start = min(max(0.0, center - span / 2.0), max(0.0, effective_length - span))
                anchors.extend([start, start + first + (gap if first and second else 0.0)])

            state = init_platform_state(platform_row, base_default, layer_default, gap_default)
            state['prevent_wide_on_narrow'] = bool(prevent_wide_on_narrow)
            state['min_support_width_ratio'] = float(min_support_ratio)
            state['max_unsupported_length_mm'] = float(max_unsupported_length_mm)
            state['max_unsupported_side_mm'] = float(max_unsupported_side_mm)
            state['max_unsupported_length_percent'] = float(max_unsupported_length_percent)
            state['max_unsupported_side_percent'] = float(max_unsupported_side_percent)
            state['prefer_support_quality'] = bool(prefer_support_quality)

            # Unterschiedliche Profilbreiten werden über die Pritschenmitte
            # ausgerichtet, unbenutzter Seitenraum bleibt gleichmässig.
            y_start = (deck_width - sum(profile)) / 2.0
            y_lanes: List[float] = []
            for lane_width in profile:
                y_lanes.append(y_start)
                y_start += lane_width

            valid = True
            for stack_index, stack in enumerate(stacks):
                lane = stack_index // 2
                z = base_z
                previous = None
                for unit in stack:
                    length = float(unit['Länge_mm'])
                    width = float(unit['Breite_mm'])
                    height = float(unit['Höhe_mm'])
                    weight = float(unit['Gewicht_kg'])
                    if previous is not None:
                        z += layer_default if (
                            str(previous.get('Typ', '')) == 'Bund'
                            or str(unit.get('Typ', '')) == 'Bund'
                        ) else general_default
                    x = round(anchors[stack_index] + (x_lengths[stack_index] - length) / 2.0, 1)
                    y = round(y_lanes[lane] + (profile[lane] - width) / 2.0, 1)
                    if not can_place_stable(state, unit, x, y, z, length, width, height, weight):
                        diagnostics['Auflage / Platzierung'] += 1
                        valid = False
                        break
                    commit_place(
                        state, unit, x, y, z, length, width, height, 0,
                        'Flexible Verladung / getrennte Breiten- und Längsbahnen'
                    )
                    z += height
                    previous = unit
                if not valid:
                    break
            if not valid:
                continue
            candidate = pd.DataFrame(state['placements'])
            if candidate.empty:
                continue
            if not find_geometry_conflicts(candidate, platform_df).empty:
                diagnostics['Geometrie'] += 1
                continue
            if not support_chain_issues(candidate, platform_df).empty:
                diagnostics['Auflagekette'] += 1
                continue
            if not physical_conflicts(candidate).empty:
                diagnostics['Physische Kollision'] += 1
                continue
            # Einschliesslich Helferzeilen: keine Einheiten verlieren.
            real_ids = sorted(
                str(r['Einheit_ID']) for _, r in candidate.iterrows()
                if str(r.get('Typ', '')) in ('Bund', 'Einzelteil')
            )
            wanted_ids = sorted(str(r['Einheit_ID']) for r in records)
            if real_ids != wanted_ids:
                diagnostics['Unvollständige Verladung'] += 1
                continue
            quality = load_quality(candidate, platform_row)
            score = float(quality['score'])
            if best_score is None or score < best_score:
                best_score = score
                best_df = candidate
                best_summary = recompute_summary(candidate, platform_df)

    if best_df.empty:
        reason = ', '.join(f'{name}: {n}' for name, n in diagnostics.most_common(3))
        return empty, empty, reason or 'Keine gültige zusätzliche Anordnung'
    return best_df, best_summary, 'Gültige flexible Anordnung'
