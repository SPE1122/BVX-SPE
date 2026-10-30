"""Integration regression: the optional packer must not change the normal plan."""
import unittest

import pandas as pd
import bvx_auswertung_streamlit as app


def make_parts():
    return pd.DataFrame([
        {'Index': i, 'Bauteilnummer': f'BODM_{i:03d}', 'Pak': str(100+i),
         'Länge_mm': length, 'Breite_mm': width, 'Höhe_mm': 140.0,
         'Gewicht_kg': round(length * width * 140 * 4.5e-7, 3),
         'Volumen_m3': length * width * 140 / 1e9}
        for i, (length, width) in enumerate([
            (3556,1200), (3556,1200), (3556,1200), (3556,1117),
            (2316,1200), (2316,1200), (1184,1200), (3229,538),
            (3229,662), (3556,1200), (3556,1200), (3556,1200),
        ],1)
    ])


def make_platform(width=2450):
    return pd.DataFrame([{
        'Fuhrenoption':'Auflieger','Pritschen_Reihenfolge':1,
        'Pritschenname':'Auflieger','Pritsche':'Auflieger','Freigabe':True,
        'Länge_mm':7600.0,'Breite_mm':float(width),'Max_Höhe_mm':2800.0,
        'Max_Gewicht_kg':20000.0,'Eigengewicht_Pritsche_kg':0.0,
        'Überhang_hinten_mm':0.0,'Überhang_vorne_mm':0.0,
        'Drehen_90_erlaubt':False,'Runge_aktiv':False,
        'Mindest_Stützbreite_%':35.0,'Kantholz_erste_Lage_mm':80.0,
        'Einlage_zwischen_Lagen_mm':40.0,'Einlage_allgemein_mm':0.0,
        'Auflager_bei_Verladeplanung_beruecksichtigen':False,
    }])


def plan(parts, **settings):
    options=pd.DataFrame([{'Freigegeben':True,'Priorität':1,'Fuhrenoption':'Auflieger'}])
    standards={'Standard_Kantholz_erste_Lage':80.0,
               'Standard_Einlage_zwischen_Lagen':40.0,
               'Standard_Einlage_allgemein':0.0,
               'Längenversatz_je_Lage':100.0}
    return app.create_variant_a_loading_plan(
        parts, options, make_platform(), standards,
        allow_beside=True,allow_stack=True,allow_rotation=False,
        use_bundles=False, min_support_width_ratio=0.35,
        **settings
    )


def real_ids(placements):
    return placements.loc[
        placements['Typ'].apply(app._is_real_load_type_value)
        & placements['Pritsche'].astype(str).ne('NICHT VERLADEN'),
        'Bauteile'
    ].astype(str).tolist()


class FlexibleIntegrationTests(unittest.TestCase):
    def test_all_modes_preserve_bauteil_identity(self):
        parts=make_parts()
        for setting in ({},
                        {'flexible_lane_compare':True},
                        {'flexible_width_compare':True},
                        {'flexible_lane_compare':True,'flexible_width_compare':True},
                        {'prefer_length_before_stack':True}):
            with self.subTest(mode=setting):
                placements,summary,used,log,units=plan(parts,**setting)
                self.assertEqual(sorted(real_ids(placements)),
                                 sorted(parts['Bauteilnummer'].astype(str).tolist()))
                self.assertTrue(app.find_geometry_conflicts(placements,used).empty)
                self.assertTrue(app._pinned_manual_support_chain_issues(placements,used).empty)
                self.assertTrue(app._pinned_manual_physical_conflicts(placements).empty)

    def test_mode_off_is_identical(self):
        parts=make_parts()
        original=plan(parts)
        explicit_off=plan(parts,flexible_lane_compare=False,
                              flexible_width_compare=False)
        pd.testing.assert_frame_equal(original[0],explicit_off[0])
        pd.testing.assert_frame_equal(original[2],explicit_off[2])


if __name__=='__main__':
    unittest.main()
