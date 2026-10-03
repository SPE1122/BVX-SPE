"""Opt-in horizontal shifts for one load, with an unchanged platform and height."""

import hashlib

import pandas as pd
import streamlit as st

from pinned_pair_guidance import mm_text


def render_single_shift(real, platforms, labels):
    uid = st.selectbox(
        'Element / Bund verschieben', real['Einheit_ID'].astype(str).tolist(),
        format_func=labels.get, key='pinned_manual_single',
    )
    row = real.loc[real['Einheit_ID'].astype(str).eq(uid)].iloc[0]
    target = str(row['Pritsche'])
    deck = platforms.loc[platforms['Pritsche'].astype(str).eq(target)].iloc[0]
    original = {f'{axis}_mm': float(row[f'{axis}_mm']) for axis in ('X', 'Y', 'Z')}
    # Reset offsets when the source position changes, so a released move isn't applied twice.
    source_key = hashlib.sha256(repr((uid, target, original)).encode()).hexdigest()[:12]
    st.caption(f"Pritsche: {target} · Z bleibt bei {mm_text(original['Z_mm'])} mm.")
    st.caption(
        'Versatz in mm: 0 = unverändert. Positives X = nach vorne, negatives X = nach hinten. '
        'Positives Y = nach rechts, negatives Y = nach links, von hinten in Fahrtrichtung gesehen. '
        'Beispiel: 200 mm = 0,20 m.'
    )
    columns = st.columns(2)
    shifted = dict(original)
    for column, axis in zip(columns, ('X', 'Y')):
        delta = column.number_input(
            f'Versatz {axis} (mm)', value=0.0, step=10.0,
            key=f'pinned_manual_single_{uid}_{source_key}_{axis}',
            help='Nur diese Achse verändern; 0 lässt sie unverändert. Negative Werte sind erlaubt.',
        )
        shifted[f'{axis}_mm'] += delta
    st.dataframe(pd.DataFrame([
        {'Position': 'Bisher', **original},
        {'Position': 'Nach Verschiebung', **shifted},
    ]), hide_index=True, use_container_width=True)
    deck_start = float(deck.get('Überhang_hinten_mm', 0))
    deck_end = deck_start + float(deck['Länge_mm'])
    st.caption(
        f'X = 0 ist der Anfang des erlaubten Ladebereichs inklusive Überhang. '
        f'Tatsächliche Pritsche: X = {mm_text(deck_start)} bis {mm_text(deck_end)} mm. '
        f"Elementende nach Verschiebung: X = {mm_text(shifted['X_mm'] + float(row['Länge_mm']))} mm · "
        f"Y = {mm_text(shifted['Y_mm'] + float(row['Breite_mm']))} mm. "
        f"Pritschenbreite: {mm_text(float(deck['Breite_mm']))} mm."
    )
    st.caption(
        'Noch keine Planänderung. Nach Prüfung und Bestätigung bleibt diese Einzelposition fixiert; '
        'nur die nicht fixierte Restladung wird neu geplant. Zugeordnete Auflager werden mitverschoben. '
        'Schwerpunkt, Auflage und Entladung bleiben manuell zu beurteilen – keine Transportfreigabe.'
    )
    return [uid], target, {uid: shifted}