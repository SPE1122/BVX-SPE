"""Zusätzliche, abschaltbare Varianten für die BVX-Verladeplanung.

Die bisherige Standard- und Längsstapel-Logik wird nicht verändert.
Jede Platzierung nutzt die bestehenden Auflage-, Gewichts- und Kollisionsprüfungen.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations_with_replacement
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd



def seitenbalance_kennzahl(placements: pd.DataFrame, platform: pd.Series) -> float:
    """Hoehendifferenz links/rechts, getrennt hinten und vorne, in mm.

    Nur echte Bauteile werden bewertet. Ueber die Mitte reichende Elemente
    zaehlen auf beiden Seiten. Hohe Einzelstapel auf einer Seite fallen auf,
    auch wenn der Laengsschwerpunkt exakt mittig ist.
    """
    if placements is None or placements.empty or 'Typ' not in placements.columns:
        return float('inf')
    deck_length = float(platform.get('Länge_mm', 0.0))
    deck_width = float(platform.get('Breite_mm', 0.0))
    back = float(platform.get('Überhang_hinten_mm', 0.0))
    if deck_length <= 0.0 or deck_width <= 0.0:
        return float('inf')
    mid_x = back + deck_length * 0.5
    mid_y = deck_width * 0.5
    # 2x2: links/rechts, hinten/vorne
    top = [[0.0, 0.0], [0.0, 0.0]]
    used = False
    helpers = {'Unterbau', 'Kantholz', 'Bundeinlage', 'Einlage', 'Lagenholz'}
    for _, row in placements.iterrows():
        if str(row.get('Typ', '')).strip() in helpers:
            continue
        if str(row.get('Pritsche', '')) != str(platform.get('Pritsche', '')):
            continue
        x = float(row.get('X_mm', 0.0))
        y = float(row.get('Y_mm', 0.0))
        z = float(row.get('Z_mm', 0.0))
        length = float(row.get('Länge_mm', 0.0))
        width = float(row.get('Breite_mm', 0.0))
        height = float(row.get('Höhe_mm', 0.0))
        if min(length, width, height) <= 0:
            continue
        used = True
        for part, (start, end) in enumerate(((back, mid_x), (mid_x, back + deck_length))):
            if min(x + length, end) - max(x, start) <= 1.0:
                continue
            for side, (lower, upper) in enumerate(((0.0, mid_y), (mid_y, deck_width))):
                if min(y + width, upper) - max(y, lower) > 1.0:
                    top[part][side] = max(top[part][side], z + height)
    if not used:
        return float('inf')
    differences = [abs(halves[0] - halves[1]) for halves in top]
    return 0.5 * max(differences) + 0.5 * sum(differences) / len(differences)


def flaechenverteilung_kennzahl(placements: pd.DataFrame, platform: pd.Series) -> float:
    """Ungleichgewicht der belegten Grundflaeche in vier Pritschenquadranten.

    Projektion echter Bauteile in die Pritschenebene; ein gemeinsames
    Bauteil wird ueberlappungsproportional auf die Quadranten aufgeteilt.
    Die Kennzahl ist ausschliesslich eine Optimierungsbewertung.
    """
    length = float(platform.get('Länge_mm', 0.0))
    width = float(platform.get('Breite_mm', 0.0))
    back = float(platform.get('Überhang_hinten_mm', 0.0))
    if length <= 0 or width <= 0:
        return float('inf')
    x_bounds = ((back, back + length / 2), (back + length / 2, back + length))
    y_bounds = ((0.0, width / 2), (width / 2, width))
    occupation = [[0.0, 0.0], [0.0, 0.0]]
    ignored = {'Unterbau', 'Kantholz', 'Bundeinlage', 'Einlage', 'Lagenholz'}
    for _, part in placements.iterrows():
        if str(part.get('Typ', '')) in ignored:
            continue
        if str(part.get('Pritsche', '')) != str(platform.get('Pritsche', '')):
            continue
        x, y = float(part.get('X_mm', 0.0)), float(part.get('Y_mm', 0.0))
        x_end = x + float(part.get('Länge_mm', 0.0))
        y_end = y + float(part.get('Breite_mm', 0.0))
        for i, (x0, x1) in enumerate(x_bounds):
            dx = max(0.0, min(x_end, x1) - max(x, x0))
            for j, (y0, y1) in enumerate(y_bounds):
                dy = max(0.0, min(y_end, y1) - max(y, y0))
                occupation[i][j] += dx * dy
    total = sum(sum(row) for row in occupation)
    if not total:
        return float('inf')
    # 0 = gleiche Belegung, 1000 = starke Ungleichverteilung.
    return sum(abs(value / total - 0.25) for row in occupation for value in row) * 1000.0


def _width_profiles(records: List[pd.Series], deck_width: float,
                    two_lane: bool, flexible_width: bool,
                    prefer_side_balance: bool = False) -> List[Tuple[float, ...]]:
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
    candidates = sorted(counts, key=lambda w: (-counts[w], -w))[:(12 if prefer_side_balance else 8)]
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
    # Bei Seitenbalance auch asymmetrische Paare aus schmalen und breiten
    # Elementen pruefen. Ihre Spiegelbilder folgen weiter unten.
    if prefer_side_balance:
        for w in candidates:
            residual = deck_width - w
            if residual > 0.01:
                for other in widths:
                    if other <= residual + 0.01:
                        profiles.add((w, round(other, 1)))
                        profiles.add((round(other, 1), w))
    eligible = [p for p in profiles if rank(p)[0] >= 0.0]
    if two_lane:
        # Filter VOR dem Limit auf die besten Profile. Zuvor gingen
        # die passenden zwei Spuren im Ranking der 3-/4-Spurprofile
        # verloren und wurden erst nach der Begrenzung herausgefiltert.
        eligible = [p for p in eligible
                    if len(p) == 2 and max(p) <= half + 0.01]
    eligible.sort(key=rank, reverse=True)
    if two_lane and fixed in eligible:
        # Die gemeinsame Mittellinie und zwei voll nutzbare Haelften
        # zuerst pruefen, ohne schmalere passende Alternativen auszuschliessen.
        eligible.remove(fixed)
        eligible.insert(0, fixed)
    if not prefer_side_balance:
        return eligible[:12]
    # Auch spiegelverkehrte Belegungen testen: breite Elemente sonst
    # immer links, obwohl rechts ggf. ein hoeherer Stapel steht.
    mirrored = []
    for p in eligible[:16]:
        if p not in mirrored:
            mirrored.append(p)
        if p[::-1] not in mirrored:
            mirrored.append(p[::-1])
    return mirrored[:32]


def _assign_to_stacks(records: List[pd.Series], widths: Tuple[float, ...],
                      deck_length: float, max_height: float, base_height: float,
                      gap: float, layer_gap: float, general_gap: float,
                      strategy: str, allow_stack: bool = True,
                      balance_sides: bool = False) -> Optional[List[List[pd.Series]]]:
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
            if stack and not allow_stack:
                continue
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
            if strategy == 'seitenbalance' and balance_sides:
                trial_heights = heights.copy()
                trial_heights[i] = next_height
                lane_left = max((max(trial_heights[2*j:2*j+2])
                                 for j in range((len(widths)+1)//2)), default=base_height)
                lane_right = max((max(trial_heights[2*j:2*j+2])
                                  for j in range((len(widths)+1)//2, len(widths))), default=base_height)
                score = abs(lane_left - lane_right) * 4.0 + next_height * 0.2 + width_waste * 0.05
            elif strategy == 'hoehe':
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



def _dynamic_spatial_layout(records, platform_row, *, init_platform_state,
                            can_place_stable, commit_place, base_default,
                            layer_default, general_default, gap_default,
                            prevent_wide_on_narrow, min_support_ratio,
                            max_unsupported_length_mm, max_unsupported_side_mm,
                            max_unsupported_length_percent,
                            max_unsupported_side_percent,
                            prefer_support_quality, allow_stack):
    """Freie X/Y-Stellflaechen statt einer festen Zahl von Stapeln.

    Die Eingabereihenfolge bleibt die physische Stapelreihenfolge (unten zuerst).
    Die bestehenden Platzierungspruefungen entscheiden verbindlich ueber
    Auflager, Abmessungen, Gewicht und Kollisionen.
    """
    deck_l = float(platform_row['Länge_mm'])
    deck_w = float(platform_row['Breite_mm'])
    back = float(platform_row.get('Überhang_hinten_mm', 0.0))
    front = float(platform_row.get('Überhang_vorne_mm', 0.0))
    usable_l = deck_l + back + front
    base_z = float(platform_row.get('Kantholz_erste_Lage_mm', base_default))
    gap_z = float(platform_row.get('Einlage_allgemein_mm', general_default))
    layer_z = float(platform_row.get('Einlage_zwischen_Lagen_mm', layer_default))
    results = []

    # Verschiedene deterministische Gewichtungen statt einer starren
    # Vier-Stapel-Aufteilung. Keine Aenderung der Pak-/Einheitenfolge.
    for balance_weight, stack_weight in ((8.0, 0.6), (15.0, 1.0), (5.0, 2.0)):
        state = init_platform_state(platform_row, base_default, layer_default, gap_default)
        state.update({
            'prevent_wide_on_narrow': bool(prevent_wide_on_narrow),
            'min_support_width_ratio': float(min_support_ratio),
            'max_unsupported_length_mm': float(max_unsupported_length_mm),
            'max_unsupported_side_mm': float(max_unsupported_side_mm),
            'max_unsupported_length_percent': float(max_unsupported_length_percent),
            'max_unsupported_side_percent': float(max_unsupported_side_percent),
            'prefer_support_quality': bool(prefer_support_quality),
        })
        placed = []
        total_mass = 0.0
        moment_x = 0.0
        moment_y = 0.0
        success = True
        for unit in records:
            length = float(unit['Länge_mm'])
            width = float(unit['Breite_mm'])
            height = float(unit['Höhe_mm'])
            mass = float(unit['Gewicht_kg'])
            if length > usable_l + 0.01 or width > deck_w + 0.01:
                success = False
                break
            # Positionen an realen Kanten und mittig: ermoeglicht beliebig
            # viele nebeneinander und hintereinander liegende Stapel.
            xs = {0.0, back, max(0.0, (usable_l-length)/2),
                  max(0.0, usable_l-length)}
            ys = {0.0, max(0.0, (deck_w-width)/2), max(0.0, deck_w-width)}
            for p in placed:
                px, py, pz, pl, pw, ph = p
                xs.update((px, px+pl+gap_default, px-length-gap_default,
                           px+(pl-length)/2))
                ys.update((py, py+pw, py-width, py+(pw-width)/2))
            xs = sorted({round(x, 1) for x in xs if -0.01 <= x <= usable_l-length+0.01})
            ys = sorted({round(y, 1) for y in ys if -0.01 <= y <= deck_w-width+0.01})
            # Suchbudget begrenzen: auch bei vielen schmalen Bauteilen
            # keine quadratisch anwachsenden X/Y-Kombinationen.
            # Schwerpunktnahe und vorhandene Kantenpositionen bevorzugen.
            x_mid = back + (deck_l-length)/2.0
            y_mid = (deck_w-width)/2.0
            xs = sorted(sorted(xs, key=lambda v: (abs(v-x_mid), v))[:7])
            ys = sorted(sorted(ys, key=lambda v: (abs(v-y_mid), v))[:7])
            # Die oberen Auflageebenen sind ebenfalls dynamisch.
            zs = {base_z}
            if allow_stack:
                for _, _, pz, _, _, ph in placed:
                    zs.add(round(pz+ph+gap_z, 1))
                    zs.add(round(pz+ph+layer_z, 1))
            # Die fuenf tiefsten Hoehenkandidaten pruefen.
            # Andere Anordnungen bleiben ueber die alte Bahnsuche moeglich.
            options = []
            for z in sorted(zs)[:5]:
                for x in xs:
                    for y in ys:
                        if not can_place_stable(state, unit, x, y, z,
                                                length, width, height, mass):
                            continue
                        new_total = total_mass + mass
                        cx = (moment_x + mass*(x+length/2))/new_total
                        cy = (moment_y + mass*(y+width/2))/new_total
                        # Schwerpunkt in beiden Achsen, niedrige Ladehoehe
                        # und kompakte Position gleichermassen beurteilen.
                        score = (balance_weight*abs(cy-deck_w/2)
                                 + 2.0*abs(cx-(back+deck_l/2))
                                 + stack_weight*z
                                 + 0.01*(x+y))
                        options.append((score, z, x, y))
            if not options:
                success = False
                break
            _, z, x, y = min(options)
            commit_place(state, unit, x, y, z, length, width, height, 0,
                         'Dynamische Stellflaechensuche X/Y')
            placed.append((x, y, z, length, width, height))
            total_mass += mass
            moment_x += mass*(x+length/2)
            moment_y += mass*(y+width/2)
        if success and placed:
            results.append(pd.DataFrame(state['placements']))
    return results


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
    allow_stack: bool = True,
    allow_beside: bool = True,
    prefer_side_balance: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    """Sucht zusätzliche flexible Breiten-/Längslagen, ohne bestehende Pläne zu ändern.

    Die ursprüngliche Reihenfolge wird innerhalb jeder der unabhängigen
    Stapelbahnen beibehalten. Breite Elemente ohne passende Bahn werden nicht
    erzwungen: die aufrufende Hauptlogik fällt dann auf Standard zurück.
    """
    empty = pd.DataFrame()
    if physical_units is None or physical_units.empty:
        return empty, empty, 'Keine Verladeeinheiten'
    if not allow_beside:
        return empty, empty, 'Nebeneinander-Verladung deaktiviert'

    records = [row for _, row in physical_units.iterrows()]
    deck_len = float(platform_row.get('Länge_mm', 0.0))
    deck_width = float(platform_row.get('Breite_mm', 0.0))
    deck_height = float(platform_row.get('Max_Höhe_mm', 0.0))
    deck_back = float(platform_row.get('Überhang_hinten_mm', 0.0))
    effective_length = deck_len + deck_back + float(platform_row.get('Überhang_vorne_mm', 0.0))
    base_z = float(platform_row.get('Kantholz_erste_Lage_mm', base_default))
    layer_gap = float(platform_row.get('Einlage_zwischen_Lagen_mm', layer_default))
    general_gap = float(platform_row.get('Einlage_allgemein_mm', general_default))
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

    profiles = _width_profiles(records, deck_width, two_lane, flexible_width, prefer_side_balance)
    if two_lane:
        # Zwei getrennte Spuren links und rechts der festen Mittellinie.
        # Die Spuren duerfen unterschiedlich breit sein: erzwungene
        # 1225/1225 mm haben im realen Test A3-24 eine weitere Pritsche
        # erfordert. Die starre Aufteilung ist deshalb KEINE harte Vorgabe.
        half_width = deck_width / 2.0
        profiles = [
            p for p in profiles
            if len(p) == 2
            and p[0] <= half_width + 0.01
            and p[1] <= half_width + 0.01
        ]
    if not profiles:
        return empty, empty, 'Keine passende Breitenaufteilung'
    platform_df = pd.DataFrame([platform_row])
    best_df, best_summary = empty, empty
    best_score: Optional[float] = None
    diagnostics = Counter()

    for profile_index, profile in enumerate(profiles):
        # Nach acht vollstaendig untersuchten Profilen bei Erfolg
        # abbrechen. Wenn KEIN Profil eine gueltige Verladung ergab,
        # werden ALLE weiteren Profile geprueft: keine stille
        # Verringerung der packbaren Bauteilmenge durch ein hartes Limit.
        if profile_index >= 8 and not best_df.empty:
            break
        strategies = ('hoehe', 'breite', 'folge', 'seitenbalance') if prefer_side_balance else ('hoehe', 'breite', 'folge')
        for strategy in strategies:
            stacks = _assign_to_stacks(
                records, profile, effective_length, deck_height, base_z,
                gap, layer_gap, general_gap, strategy, allow_stack, prefer_side_balance
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

            # Auch freie Randflaechen nutzen: Profile alternativ links,
            # mittig oder rechts positionieren. Jeder Versuch muss danach
            # dieselben Auflage-, Kollisions- und Sicherheitspruefungen bestehen.
            # Die Pritschenmitte ist die feste Trennlinie fuer links/rechts.
            # Niemals das komplette zweispurige Profil an den Rand verschieben:
            # sonst ist die linke/rechte Spur fuer 1200-mm-Elemente blockiert.
            center_y = deck_width / 2.0
            if len(profile) >= 2:
                split = (len(profile) + 1) // 2
                left_span = sum(profile[:split])
                right_span = sum(profile[split:])
                if left_span > center_y + 0.01 or right_span > center_y + 0.01:
                    diagnostics['Spuren passen nicht beidseits der Mitte'] += 1
                    continue
                # Erste Wahl: JEDES Element an der festen Y-Mittellinie
                # ansetzen, links bis zur Mitte / rechts ab der Mitte.
                # Alte Bahnzentrierung bleibt nur als sichere Rueckfallebene.
                offsets = ([(center_y - left_span, 'innen'), (center_y - left_span, 'bahn')]
                           if two_lane and len(profile) == 2
                           else [(center_y - left_span, 'bahn')])
            else:
                offsets = [((deck_width - sum(profile)) / 2.0, 'bahn')]
            for offset_y, y_mode in offsets:
                state = init_platform_state(platform_row, base_default, layer_default, gap_default)
                state['prevent_wide_on_narrow'] = bool(prevent_wide_on_narrow)
                state['min_support_width_ratio'] = float(min_support_ratio)
                state['max_unsupported_length_mm'] = float(max_unsupported_length_mm)
                state['max_unsupported_side_mm'] = float(max_unsupported_side_mm)
                state['max_unsupported_length_percent'] = float(max_unsupported_length_percent)
                state['max_unsupported_side_percent'] = float(max_unsupported_side_percent)
                state['prefer_support_quality'] = bool(prefer_support_quality)

                # Breitenbahnen gehen von der festen Pritschenmitte aus.
                # Links und rechts bleiben getrennte Haelften.
                y_start = offset_y
                y_lanes: List[float] = []
                for lane_width in profile:
                    y_lanes.append(y_start)
                    y_start += lane_width

                # Von unten nach oben über ALLE Bahnen einfügen. Andernfalls
                # würde die obere Lage von Bahn A als Bezug für Bahn B gelten.
                placement_order = []
                for stack_index, stack in enumerate(stacks):
                    z = base_z
                    previous = None
                    for unit in stack:
                        if previous is not None:
                            z += layer_gap if (
                                str(previous.get('Typ', '')) == 'Bund'
                                or str(unit.get('Typ', '')) == 'Bund'
                            ) else general_gap
                        placement_order.append((z, stack_index, unit))
                        z += float(unit['Höhe_mm'])
                        previous = unit
                placement_order.sort(key=lambda entry: (entry[0], entry[1]))
                valid = True
                for z, stack_index, unit in placement_order:
                    lane = stack_index // 2
                    length = float(unit['Länge_mm'])
                    width = float(unit['Breite_mm'])
                    height = float(unit['Höhe_mm'])
                    weight = float(unit['Gewicht_kg'])
                    x = round(anchors[stack_index] + (x_lengths[stack_index] - length) / 2.0, 1)
                    if y_mode == 'innen':
                        # Y=0 ist der linke Pritschenrand, Mitte=Breite/2.
                        # Kein Zentrieren schmaler Elemente innerhalb
                        # einer asymmetrischen, verschobenen Breitenbahn.
                        y = round(center_y - width if lane == 0 else center_y, 1)
                    else:
                        y = round(y_lanes[lane] + (profile[lane] - width) / 2.0, 1)
                    if not can_place_stable(state, unit, x, y, z, length, width, height, weight):
                        diagnostics['Auflage / Platzierung'] += 1
                        valid = False
                        break
                    commit_place(
                        state, unit, x, y, z, length, width, height, 0,
                        ('Flexible Verladung / Y ab Pritschenmitte links/rechts'
                         if y_mode == 'innen' else
                         'Flexible Verladung / getrennte Breiten- und Längsbahnen')
                    )
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
                    if str(r.get('Typ', '')).strip() not in {'Unterbau', 'Kantholz', 'Bundeinlage', 'Einlage', 'Lagenholz'}
                )
                wanted_ids = sorted(str(r['Einheit_ID']) for r in records)
                if real_ids != wanted_ids:
                    diagnostics['Unvollständige Verladung'] += 1
                    continue
                quality = load_quality(candidate, platform_row)
                score = float(quality['score'])
                if two_lane and len(profile) == 2:
                    # Nur Elemente links/rechts verteilen. Weder den
                    # gewichteten Y-Schwerpunkt noch eine Gesamtverschiebung
                    # der Ladung auf die andere Seite optimieren.
                    left_count = sum(len(stack) for stack in stacks[:2])
                    right_count = sum(len(stack) for stack in stacks[2:])
                    score += abs(left_count - right_count) * 20.0
                    # Bei ansonsten gleichwertiger Verladung die feste
                    # Mittel-Anlage vor der alten Bahnzentrierung waehlen.
                    if y_mode != 'innen':
                        score += 50.0
                elif prefer_side_balance:
                    score += seitenbalance_kennzahl(candidate, platform_row) * 6.0
                    score += flaechenverteilung_kennzahl(candidate, platform_row) * 2.0
                if best_score is None or score < best_score:
                    best_score = score
                    best_df = candidate
                    best_summary = recompute_summary(candidate, platform_df)
                # Die gleiche Verteilung nochmals mitten in den Bahnen
                # zu pruefen ist unnoetig, wenn die gewuenschte Anlage
                # ab Y-Mitte bereits alle Sicherheitspruefungen besteht.
                if two_lane and y_mode == 'innen':
                    break

    # Zweiter, unabhaengiger Suchweg: dynamische freie Stellflaechen.
    # Er ersetzt die vorhandenen Bahnen nicht und uebernimmt nur Kandidaten,
    # welche die identischen abschliessenden Sicherheitspruefungen bestehen.
    if prefer_side_balance and flexible_width and not two_lane and len(records) <= 12:
        spatial_candidates = _dynamic_spatial_layout(
            records, platform_row,
            init_platform_state=init_platform_state,
            can_place_stable=can_place_stable,
            commit_place=commit_place,
            base_default=base_default, layer_default=layer_default,
            general_default=general_default, gap_default=gap_default,
            prevent_wide_on_narrow=prevent_wide_on_narrow,
            min_support_ratio=min_support_ratio,
            max_unsupported_length_mm=max_unsupported_length_mm,
            max_unsupported_side_mm=max_unsupported_side_mm,
            max_unsupported_length_percent=max_unsupported_length_percent,
            max_unsupported_side_percent=max_unsupported_side_percent,
            prefer_support_quality=prefer_support_quality,
            allow_stack=allow_stack,
        )
        wanted_ids = sorted(str(r['Einheit_ID']) for r in records)
        ignored = {'Unterbau', 'Kantholz', 'Bundeinlage', 'Einlage', 'Lagenholz'}
        for candidate in spatial_candidates:
            real_ids = sorted(str(r['Einheit_ID']) for _, r in candidate.iterrows()
                              if str(r.get('Typ', '')).strip() not in ignored)
            if real_ids != wanted_ids:
                continue
            if not find_geometry_conflicts(candidate, platform_df).empty:
                continue
            if not support_chain_issues(candidate, platform_df).empty:
                continue
            if not physical_conflicts(candidate).empty:
                continue
            quality = load_quality(candidate, platform_row)
            score = (float(quality['score'])
                     + seitenbalance_kennzahl(candidate, platform_row)*6.0
                     + flaechenverteilung_kennzahl(candidate, platform_row)*2.0)
            if best_score is None or score < best_score:
                best_score = score
                best_df = candidate
                best_summary = recompute_summary(candidate, platform_df)

    if best_df.empty:
        reason = ', '.join(f'{name}: {n}' for name, n in diagnostics.most_common(3))
        return empty, empty, reason or 'Keine gültige zusätzliche Anordnung'
    return best_df, best_summary, 'Gültige flexible Anordnung'
