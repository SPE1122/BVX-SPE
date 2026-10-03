"""Streamlit controls for a validated longitudinal pair and global replan preview."""

import pandas as pd
import streamlit as st
import hashlib
from pinned_pair_guidance import mm_text, render_pair_guidance
from pinned_plan_identity import pin_requests, platform_changes
from pinned_single_ui import render_single_shift


def _show_advisory_issues(issues):
    if isinstance(issues, pd.DataFrame) and not issues.empty:
        st.markdown('**Hinweise zur manuellen Beurteilung (keine Transportfreigabe)**')
        st.dataframe(issues, use_container_width=True, hide_index=True)


def _manual_override_warning():
    st.warning(
        'Manuelle Beurteilung aktiv: Schwerpunkt, Auflage und Entladung werden nicht '
        'sicherheitstechnisch bestätigt. Die Transport- und Ladungssicherheit muss '
        'eigenverantwortlich beurteilt werden.'
    )


def render_pinned_manual_replanning(
    placements, platforms, parts, options, platform_stock, standards, settings,
    *, validate_pair, preview_plan, apply_plan, draw_view, is_real_load,
):
    """Keep preview state separate from the accepted plan; commit only on confirmation."""
    with st.expander('Element verschieben / Längspaar fixieren / übrige Fuhren neu planen', expanded=False):
        st.caption(
            'Ein einzelnes Element / einen Bund in X/Y verschieben oder zwei bereits verladene '
            'Bauteile/Bunde längs hintereinander in derselben Lage positionieren. X ist die Längsrichtung, Y die '
            'Querrichtung, Z die Unterkante. Alle Angaben in mm. Importierte Nr.PL bleiben '
            'unverändert. Alle nicht fixierten Bauteile werden neu geplant. Bereits bestätigte '
            'Einzelpositionen und Paare bleiben exakt an ihrer Position. Geometrie- und '
            'Gewichtsfehler bleiben auch bei manueller Beurteilung Ausschlussgründe.'
        )
        pin = st.session_state.get('pinned_manual_active')
        retained_pairs = pin_requests(pin)
        if isinstance(pin, dict):
            if pin.get('manual_pair_override', False):
                _manual_override_warning()
            st.success(
                f"{len(retained_pairs)} Fixierung(en) – bestätigte Positionen bleiben geschützt."
            )
            st.dataframe(pin.get('pinned_placements_df', pd.DataFrame()), hide_index=True)
            _show_advisory_issues(pin.get('advisory_issues'))
            st.caption('Weitere Einzelpositionen oder Paare können unten ergänzt werden. Andere Planänderungen bleiben gesperrt. '
                       'Lösen behält Positionen bei, hebt aber ihren Schutz bei der nächsten Neuplanung auf.')
            if len(retained_pairs) > 1:
                for index, request in enumerate(retained_pairs):
                    if st.button(
                        f"Fixierung lösen: {request['target_platform']} – {', '.join(request['unit_ids'])}",
                        key=f'pinned_manual_release_pair_{index}',
                    ):
                        remaining = retained_pairs[:index] + retained_pairs[index + 1:]
                        updated = dict(pin)
                        updated['pin_requests'] = remaining
                        keep_ids = {uid for item in remaining for uid in item['unit_ids']}
                        updated['pinned_placements_df'] = pin['pinned_placements_df'][
                            pin['pinned_placements_df']['Einheit_ID'].astype(str).isin(keep_ids)
                        ].copy()
                        st.session_state['pinned_manual_active'] = updated
                        st.session_state.pop('pinned_manual_preview', None)
                        st.rerun()
                        return
            if st.button(
                'Alle Fixierungen lösen (Positionen beibehalten)' if len(retained_pairs) > 1
                else 'Fixierung lösen (Positionen beibehalten)',
                key='pinned_manual_release',
            ):
                st.session_state.pop('pinned_manual_active', None)
                st.session_state.pop('pinned_manual_preview', None)
                st.rerun()
                return

        real = placements[
            placements.get('Typ', pd.Series(index=placements.index, dtype=str)).apply(is_real_load)
            & placements.get('Pritsche', pd.Series(index=placements.index, dtype=str)).astype(str).ne('NICHT VERLADEN')
        ].copy()
        fixed_ids = {str(uid) for request in retained_pairs for uid in request['unit_ids']}
        real = real[~real['Einheit_ID'].astype(str).isin(fixed_ids)]
        if real.empty or platforms.empty:
            st.info('Keine weiteren unfixierten Bauteile verfügbar.' if retained_pairs
                    else 'Zuerst Bauteile verladen und den Ladeplan berechnen.')
            return
        # This is an explicitly manual flow. Do not let a retained widget value
        # silently restore the strict stability gates requested for automation.
        if not isinstance(pin, dict) or not pin.get('manual_pair_override', False):
            _manual_override_warning()
        request_settings = dict(settings)
        request_settings['manual_pair_override'] = True
        if retained_pairs:
            request_settings['retained_pairs'] = retained_pairs
        mode = st.selectbox(
            'Art der Anpassung', ['pair', 'single'],
            index=0 if len(real) >= 2 else 1,
            format_func=lambda value: 'Längspaar positionieren' if value == 'pair'
            else 'Einzelnes Element / Bund in X/Y verschieben',
            key='pinned_manual_mode',
        )
        if mode == 'pair' and len(real) < 2:
            st.info('Für ein Längspaar werden zwei unfixierte Einheiten benötigt. '
                    'Wähle die Einzelverschiebung für das verbleibende Element.')
            return
        st.info('Eingabe in Millimetern: 6,54 m = 6540 mm · 1,98 m = 1980 mm. '
                'Bitte 6540 beziehungsweise 1980 eingeben, nicht 6,54 oder 1,98.')
        ids = real['Einheit_ID'].astype(str).tolist()
        labels = {
            str(row['Einheit_ID']): f"{row['Einheit_ID']} | {row.get('Bauteile', '')} | {row.get('Pritsche', '')}"
            for _, row in real.iterrows()
        }
        if mode == 'single':
            request_settings['manual_placement_mode'] = 'single'
            selected, target, coordinates = render_single_shift(real, platforms, labels)
        else:
            request_settings.pop('manual_placement_mode', None)
            names = platforms['Pritsche'].astype(str).tolist()
            target = st.selectbox('Zielpritsche für das Längspaar', names, key='pinned_manual_target')
            cols = st.columns(2)
            selected = [
                cols[0].selectbox('Erstes Bauteil / Bund', ids, format_func=labels.get, key='pinned_manual_first'),
                cols[1].selectbox('Zweites Bauteil / Bund', ids, index=1, format_func=labels.get, key='pinned_manual_second'),
            ]
            coordinates = {}
            selected_rows = {}
            x_widget_keys = {}
            for col, unit_id, position in zip(cols, selected, ('first', 'second')):
                row = real[real['Einheit_ID'].astype(str).eq(unit_id)].iloc[0]
                selected_rows[unit_id] = row
                col.caption(
                    f"Länge {mm_text(float(row['Länge_mm']))} mm · "
                    f"Breite {mm_text(float(row['Breite_mm']))} mm · "
                    f"Höhe {mm_text(float(row['Höhe_mm']))} mm"
                )
                coordinates[unit_id] = {}
                x_widget_keys[unit_id] = f'pinned_manual_{position}_{unit_id}_X'
                for axis in ('X', 'Y', 'Z'):
                    raw = pd.to_numeric(row.get(f'{axis}_mm'), errors='coerce')
                    default = float(raw) if pd.notna(raw) else 0.0
                    coordinates[unit_id][f'{axis}_mm'] = col.number_input(
                        f'{axis} mm – {labels[unit_id]}', value=default, step=10.0,
                        key=f'pinned_manual_{position}_{unit_id}_{axis}',
                        help={
                            'X': 'Millimeter eingeben: z. B. 6540 für 6,54 m. '
                                 'X ist der Anfang des Elements im Ladebereich inklusive Überhang.',
                            'Y': 'Linke Elementkante in mm, von hinten in Fahrtrichtung gesehen.',
                            'Z': 'Unterkante des Elements in mm; erforderliche Auflager prüfen.',
                        }[axis],
                    )
            target_row = platforms.loc[platforms['Pritsche'].astype(str).eq(str(target))].iloc[0]
            render_pair_guidance(target_row, selected_rows, coordinates, labels, x_widget_keys)
        request = {'unit_ids': selected, 'target_platform': target, 'coordinates': coordinates}
        preview_title = ('Position prüfen und globale Vorschau berechnen' if mode == 'single'
                         else 'Paar prüfen und globale Vorschau berechnen')
        if st.button(preview_title, key='pinned_manual_preview_button'):
            spinner_text = (
                'Geometrie und Gewicht prüfen; Schwerpunkt, Auflage und Entladung manuell beurteilen; '
                'Rest neu planen …'
            )
            with st.spinner(spinner_text):
                validation_options = {'placement_mode': 'single'} if mode == 'single' else {}
                validation = validate_pair(
                    placements, platforms, selected, coordinates, target,
                    include_destination_loads=False,
                    manual_pair_override=request_settings['manual_pair_override'],
                    **validation_options,
                )
                if not validation['ok']:
                    st.session_state['pinned_manual_preview'] = {
                        'ok': False,
                        'issues': validation['issues'],
                        'advisory_issues': validation.get('advisory_issues', pd.DataFrame()),
                    }
                else:
                    st.session_state['pinned_manual_preview'] = preview_plan(
                        placements, platforms, parts, options, platform_stock, standards,
                        request_settings, selected, target, coordinates,
                    )
            st.session_state['pinned_manual_preview']['_manual_ui_request'] = {
                **request, 'settings': request_settings,
            }
        preview = st.session_state.get('pinned_manual_preview')
        if not isinstance(preview, dict):
            return
        current_request = {**request, 'settings': request_settings}
        stale_failure = (
            not preview.get('ok')
            and preview.get('_manual_ui_request') != current_request
        )
        strict_preview = (
            'settings' in preview
            and not preview['settings'].get('manual_pair_override', False)
        )
        if stale_failure or strict_preview:
            st.session_state.pop('pinned_manual_preview', None)
            st.info(
                'Die frühere Vorschau gehört nicht zur aktuellen manuellen Eingabe. '
                f'Bitte „{preview_title}“ erneut drücken.'
            )
            return
        if not preview.get('ok'):
            st.error('Keine gültige Fixierung / Neuplanung. Der bisherige Plan bleibt unverändert.')
            st.dataframe(preview.get('issues', pd.DataFrame()), hide_index=True, use_container_width=True)
            _show_advisory_issues(preview.get('advisory_issues'))
        else:
            same_request = all(preview.get(key) == value for key, value in request.items())
            checked = apply_plan(
                preview, placements, platforms, parts, options, platform_stock, request_settings,
            )
            can_apply = same_request and bool(checked.get('applied'))
            st.success('Vorschau berechnet. Noch keine Änderungen übernommen.')
            if not can_apply:
                st.warning(
                    'Auswahl, Koordinaten, Prüfmodus oder Ausgangsdaten wurden geändert. '
                    'Bitte Vorschau neu berechnen.'
                )
            if preview.get('deviation'):
                st.warning(preview['deviation'])
            _show_advisory_issues(preview.get('advisory_issues'))
            st.markdown('**Alle fixierten Positionen in der Vorschau**')
            st.dataframe(preview['pinned_placements_df'], use_container_width=True, hide_index=True)
            st.markdown('**Fuhren nach der globalen Neuplanung**')
            target_real = preview['placements_df'].loc[
                preview['placements_df']['Typ'].apply(is_real_load)
                & preview['placements_df']['Pritsche'].astype(str).eq(str(target))
                & ~preview['placements_df']['Einheit_ID'].astype(str).isin(selected)
            ]
            before_trips = platforms['Fuhre_Nr'].nunique() if 'Fuhre_Nr' in platforms else len(platforms)
            after_platforms = preview['platforms_df']
            after_trips = (
                after_platforms['Fuhre_Nr'].nunique()
                if 'Fuhre_Nr' in after_platforms else len(after_platforms)
            )
            additional_parts = sum(
                len(str(value).split('|')) for value in target_real['Bauteile_Liste']
            ) if not target_real.empty else 0
            st.caption(
                f'{target}: {additional_parts} weitere Bauteile zusätzlich zur aktuellen Fixierung. '
                f'Fuhren bisher: {before_trips} · Vorschau: {after_trips}. '
                'Die Suche prüft freie Plätze; eine global minimale Fuhrenzahl ist nicht garantiert.'
            )
            st.caption(
                f'Pritschen bisher: {len(platforms)} · Vorschau: {len(after_platforms)}. '
                'Eine höhere Fuhrennummer allein bedeutet keine zusätzliche Fuhre. '
                'Vorhandene Nummern werden wiederverwendet; bei anderem Pritschentyp kann sich der Name ändern.'
            )
            st.dataframe(platform_changes(platforms, after_platforms),
                         use_container_width=True, hide_index=True)
            st.dataframe(preview['summary_df'], use_container_width=True, hide_index=True)
            st.markdown('**Bauteil-Zuordnung bisher / Vorschau**')
            before = placements[placements['Typ'].apply(is_real_load)]
            after = preview['placements_df'][preview['placements_df']['Typ'].apply(is_real_load)]
            # A full outer comparison also exposes regrouped bundles instead of hiding them.
            compare_cols = ['Bauteile_Liste', 'Pritsche', 'X_mm', 'Y_mm', 'Z_mm']
            before_cols = [c for c in compare_cols if c in before.columns]
            after_cols = [c for c in compare_cols if c in after.columns]
            if 'Bauteile_Liste' in before_cols and 'Bauteile_Liste' in after_cols:
                comparison = before[before_cols].merge(
                    after[after_cols], on='Bauteile_Liste', how='outer',
                    suffixes=('_bisher', '_Vorschau'),
                )
                st.dataframe(comparison, use_container_width=True, hide_index=True)
            view_names = list(dict.fromkeys(
                platforms['Pritsche'].astype(str).tolist()
                + preview['platforms_df']['Pritsche'].astype(str).tolist()
            ))
            view_target = st.selectbox('Fuhre / Pritsche vergleichen', view_names, key='pinned_manual_compare')
            left, right = st.columns(2)
            with left:
                st.caption('Bisher – Draufsicht')
                if view_target in platforms['Pritsche'].astype(str).values:
                    st.plotly_chart(draw_view(placements, platforms, view_target, 'top'),
                                    use_container_width=True, key='pinned_manual_before')
                else:
                    st.info('Diese Pritsche existiert bisher nicht.')
            with right:
                st.caption('Vorschau – Draufsicht')
                if view_target in preview['platforms_df']['Pritsche'].astype(str).values:
                    st.plotly_chart(draw_view(preview['placements_df'], preview['platforms_df'], view_target, 'top'),
                                    use_container_width=True, key='pinned_manual_after')
                else:
                    st.info('Diese Pritsche entfällt in der Vorschau.')
            confirmation_text = (
                'Ich übernehme die manuelle Verantwortung für Schwerpunkt, Auflage und Entladung '
                'und bestätige: Änderungen aller Fuhren geprüft – Positionen fixieren und Vorschau übernehmen'
            )
            confirmation_key = f"pinned_manual_confirm_{preview['source_signature']}"
            if preview.get('_preview_artifact_signature'):
                confirmation_key += '_' + hashlib.sha256(
                    preview['_preview_artifact_signature'].encode()
                ).hexdigest()[:12]
            confirm = st.checkbox(confirmation_text, value=False, key=confirmation_key)
            if st.button('Bestätigte Vorschau übernehmen', disabled=not (can_apply and confirm),
                         key='pinned_manual_apply'):
                # Recheck directly before the atomic session-state update.
                accepted = apply_plan(
                    preview, placements, platforms, parts, options, platform_stock, request_settings,
                )
                if not accepted.get('applied'):
                    st.error('Vorschau ist nicht mehr gültig. Es wurde nichts übernommen.')
                else:
                    accepted_pin = dict(accepted)
                    accepted_pin['manual_pair_override'] = request_settings['manual_pair_override']
                    st.session_state.update({
                        'manual_placements_df': accepted['placements_df'].copy(deep=True),
                        'manual_platforms_df': accepted['platforms_df'].copy(deep=True),
                        'manual_plan_ready_v84': True,
                        'pinned_manual_active': accepted_pin,
                    })
                    st.session_state.pop('pinned_manual_preview', None)
                    st.session_state.pop('v113_recalc_preview', None)
                    st.rerun()
        if st.button('Vorschau verwerfen', key='pinned_manual_discard'):
            st.session_state.pop('pinned_manual_preview', None)
            st.rerun()