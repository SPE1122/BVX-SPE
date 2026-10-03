"""Position explanations and opt-in X suggestions; never modifies a loading plan."""

import math

import pandas as pd
import streamlit as st


def _number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Abmessungen oder Koordinaten fehlen.')
    return number


def mm_text(value):
    return f'{value:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def pair_geometry(platform, rows, coordinates):
    """All coordinates use the planner's existing effective-loading-area origin."""
    deck_start = _number(platform.get('Überhang_hinten_mm', 0.0))
    deck_length = _number(platform['Länge_mm'])
    deck_end = deck_start + deck_length
    front_limit = _number(platform.get('Überhang_vorne_mm', 0.0))
    if deck_length <= 0 or deck_start < 0 or front_limit < 0:
        raise ValueError('Pritschenabmessungen sind ungültig.')
    intervals = []
    for uid, row in rows.items():
        length = _number(row['Länge_mm'])
        if length <= 0:
            raise ValueError('Elementlängen müssen größer als null sein.')
        start = _number(coordinates[uid]['X_mm'])
        intervals.append((start, start + length, uid))
    if len(intervals) != 2:
        raise ValueError('Zwei unterschiedliche Elemente auswählen.')
    intervals.sort()
    gap = intervals[1][0] - intervals[0][1]
    return {
        'deck_start': deck_start, 'deck_end': deck_end, 'deck_length': deck_length,
        'effective_end': deck_end + front_limit, 'rear_id': intervals[0][2],
        'gap': gap,
        'overlap': max(0.0, min(item[1] for item in intervals) - intervals[1][0]),
        'rear_overhang': max(0.0, deck_start - intervals[0][0]),
        'front_overhang': max(0.0, max(item[1] for item in intervals) - deck_end),
    }


def x_suggestion(platform, rows, rear_id, gap, mode):
    """Return geometric suggestions only, within configured overhang boundaries."""
    if len(rows) != 2 or rear_id not in rows:
        raise ValueError('Zwei unterschiedliche Elemente auswählen.')
    gap = _number(gap)
    if gap < 0:
        raise ValueError('Der Abstand darf nicht negativ sein.')
    front_id = next(uid for uid in rows if uid != rear_id)
    rear_length = _number(rows[rear_id]['Länge_mm'])
    front_length = _number(rows[front_id]['Länge_mm'])
    if rear_length <= 0 or front_length <= 0:
        raise ValueError('Elementlängen müssen größer als null sein.')
    deck_start = _number(platform.get('Überhang_hinten_mm', 0.0))
    deck_length = _number(platform['Länge_mm'])
    deck_end = deck_start + deck_length
    front_limit = _number(platform.get('Überhang_vorne_mm', 0.0))
    if deck_length <= 0 or deck_start < 0 or front_limit < 0:
        raise ValueError('Pritschenabmessungen sind ungültig.')
    total_length = rear_length + gap + front_length
    if mode == 'front_flush':
        rear_start = deck_end - total_length
    elif mode == 'centered':
        rear_start = deck_start + (deck_length - total_length) / 2.0
    else:
        raise ValueError('Unbekannter Positionsvorschlag.')
    if rear_start < -1e-6 or rear_start + total_length > deck_end + front_limit + 1e-6:
        raise ValueError('Dieser Vorschlag überschreitet den erlaubten Überhangbereich.')
    return {rear_id: max(0.0, rear_start),
            front_id: max(0.0, rear_start) + rear_length + gap}


def _insert_x_values(values, widget_keys):
    # Streamlit callbacks execute before the next render, before widgets exist.
    for uid, value in values.items():
        st.session_state[widget_keys[uid]] = float(value)
    st.session_state.pop('pinned_manual_preview', None)


def render_pair_guidance(platform, rows, coordinates, labels, widget_keys):
    st.markdown('**Aktuelle Positionen verstehen**')
    try:
        geometry = pair_geometry(platform, rows, coordinates)
    except (KeyError, TypeError, ValueError) as exc:
        st.warning(f'Positionshilfe nicht berechenbar: {exc}')
        return
    st.caption(
        f"X = 0 ist der Beginn des erlaubten Ladebereichs, nicht die Pritschenkante. "
        f"Die tatsächliche Pritsche reicht von X = {mm_text(geometry['deck_start'])} mm "
        f"bis X = {mm_text(geometry['deck_end'])} mm "
        f"(Länge {mm_text(geometry['deck_length'])} mm). "
        f"Erlaubter Ladebereich: X = 0 bis {mm_text(geometry['effective_end'])} mm. "
        'Y = linke Kante des Elements, von hinten in Fahrtrichtung gesehen; '
        'Z = Unterkante, jeweils in mm.'
    )
    table = []
    for uid, row in rows.items():
        x = coordinates[uid]['X_mm']
        length = float(row['Länge_mm'])
        table.append({
            'Element': labels[uid], 'Länge mm': length, 'X Anfang mm': x,
            'X Ende mm': x + length,
            'X ab hinterer Pritschenkante mm': x - geometry['deck_start'],
        })
        if 0 < abs(x) < 20 and length >= 1000:
            st.warning(
                f'{labels[uid]}: X = {mm_text(x)} mm sind nur {x / 1000:.5f} m. '
                f'Falls du {mm_text(x)} Meter meinst, musst du '
                f'{mm_text(x * 1000)} mm eingeben. Keine automatische Umrechnung.'
            )
    st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)
    if geometry['gap'] < -0.001:
        st.error(
            f"Überlappung in X: {mm_text(geometry['overlap'])} mm. "
            'Für ein Längspaar müssen die Elemente hintereinander liegen.'
        )
    else:
        st.caption(f"Lücke zwischen den Elementen: {mm_text(max(0, geometry['gap']))} mm.")
    st.caption(
        f"Überhang des Paars hinten: {mm_text(geometry['rear_overhang'])} mm · "
        f"vorne: {mm_text(geometry['front_overhang'])} mm. "
        'Diese Angaben betreffen nur das Paar, nicht die gesamte Ladung.'
    )

    st.markdown('**Berechnete X-Vorschläge**')
    rear_id = st.selectbox(
        'Welches Element soll hinten liegen?', list(rows),
        index=list(rows).index(geometry['rear_id']), format_func=labels.get,
        key=f"pinned_manual_suggestion_rear_{'_'.join(rows)}_{geometry['rear_id']}",
    )
    gap = st.number_input(
        'Gewünschte Lücke zwischen den Elementen (mm)', min_value=0.0,
        value=0.0, step=10.0, key='pinned_manual_suggestion_gap',
        help='0 = direkt hintereinander. Nicht der Abstand zwischen den Anfangspunkten.',
    )
    for col, mode, title in zip(
        st.columns(2), ('front_flush', 'centered'),
        ('Vorne bündig', 'Geometrisch mittig'),
    ):
        with col:
            st.markdown(f'**{title}**')
            try:
                values = x_suggestion(platform, rows, rear_id, gap, mode)
            except (KeyError, TypeError, ValueError) as exc:
                st.warning(str(exc))
                continue
            for uid, x in values.items():
                st.caption(f'{labels[uid]}: X = {mm_text(x)} mm ({x / 1000:.3f} m)')
            st.button(
                f'X-Werte einsetzen: {title.lower()}',
                key=f'pinned_manual_suggestion_{mode}',
                on_click=_insert_x_values, args=(values, widget_keys),
            )
    st.caption(
        'Die Vorschläge ändern auf Klick ausschließlich die X-Eingabefelder, nicht Y/Z '
        'oder den Ladeplan. Geometrisch mittig bedeutet nicht automatisch ausgeglichener '
        'Gewichtsschwerpunkt. Auflage, Höhe, Gewicht und Restladung müssen danach über '
        '„Paar prüfen und globale Vorschau berechnen“ geprüft werden. Keine Transportfreigabe.'
    )