"""Reproduce the user's exact 99-part settings and check the added shelf search."""
from pathlib import Path
import inspect
import io
import json
import sys
import time
import zipfile

import pandas as pd
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import bvx_auswertung_streamlit as app
from loading_shelf_search import try_side_by_side_shelves


def load_reference():
    with zipfile.ZipFile(ROOT / "attached_assets/BVX_Verladediagnose-2_1793532541747.zip") as archive:
        read = lambda name: pd.read_csv(io.BytesIO(archive.read(name)))
        return (
            read("tabellen/positionen_automatik.csv"),
            read("tabellen/pritschen_verwendet.csv"),
            read("tabellen/verladeeinheiten.csv"),
            read("eingabe/parts.csv"), read("eingabe/options.csv"),
            read("eingabe/platforms.csv"), json.loads(archive.read("diagnose.json")),
        )


def make_state(deck):
    state = app.init_platform_state(deck, 80, 40, 100)
    state.update(allow_transverse_supports=True, prevent_wide_on_narrow=True,
                 min_support_width_ratio=.35, prefer_support_quality=True)
    return state


def valid(rows, decks):
    return (app.find_geometry_conflicts(rows, decks).empty
            and app._pinned_manual_support_chain_issues(rows, decks).empty
            and app._pinned_manual_physical_conflicts(rows).empty)


def check_pair(rows):
    a = rows[rows.Bauteile.astype(str).eq("315")].iloc[0]
    b = rows[rows.Bauteile.astype(str).eq("400")].iloc[0]
    assert min(a.Y_mm + a.Breite_mm, b.Y_mm + b.Breite_mm) <= max(a.Y_mm, b.Y_mm) + .1
    assert abs(a.Z_mm + a.Höhe_mm - b.Z_mm - b.Höhe_mm) < .1
    assert abs(a.Z_mm - b.Z_mm) == 20
    print("315/400", rows[rows.Einheit_ID.isin([a.Einheit_ID, b.Einheit_ID])][
        ["Bauteile", "X_mm", "Y_mm", "Z_mm", "Länge_mm", "Breite_mm", "Höhe_mm"]
    ].to_dict("records"), flush=True)
    print("400 PACKING", rows[rows.get("Auflager_fuer", pd.Series(dtype=str)).eq(b.Einheit_ID)][
        ["X_mm", "Y_mm", "Z_mm", "Länge_mm", "Breite_mm", "Höhe_mm"]
    ].to_dict("records"), flush=True)


def main():
    old, decks, units, parts, options, config, manifest = load_reference()
    started = time.perf_counter()
    if "--full" in sys.argv:
        settings = manifest["calculation"]["settings"]
        accepted = inspect.signature(app.create_variant_a_loading_plan).parameters
        kwargs = {key: value for key, value in settings.items() if key in accepted}
        kwargs.update(
            same_attrs=settings["bundle_match_attrs"],
            min_support_width_ratio=settings["min_support_width_percent"] / 100,
            prefer_stable_option=settings["compact_transport_strategy"],
            prefer_length_before_stack=True,
            fuhre_split_attr=settings["effective_fuhre_split_attr"],
        )
        rows, summary, decks, trips, units = app.create_variant_a_loading_plan(
            parts, options, config, manifest["calculation"]["standards"], **kwargs
        )
        assert len(trips) == 1 and len(decks) == 2
    else:
        result = []
        for _, deck in decks.iterrows():
            previous = old[old.Pritsche.eq(deck.Pritsche)].copy()
            block = units[units.Einheit_ID.isin(previous.Einheit_ID)].sort_values(
                "Einheit_ID", ascending=False, kind="stable"
            )
            result.append(try_side_by_side_shelves(
                previous, deck, [unit for _, unit in block.iterrows()],
                make_state=lambda: make_state(deck),
                can_place_stable=app.can_place_stable, commit_place=app.commit_place,
                validate=lambda candidate: valid(candidate, pd.DataFrame([deck])),
            ))
        rows = pd.concat(result, ignore_index=True)
        summary = app.recompute_summary_from_placements(rows, decks)
    real = rows[~rows.Typ.isin(["Unterbau", "Kantholz", "Einlage", "Bundeinlage", "Lagenholz"])]
    assert len(real) == real.Einheit_ID.nunique() == 99
    assert sorted(real.Einheit_ID) == sorted(old[old.Typ.ne("Unterbau")].Einheit_ID)
    assert abs(real.Gewicht_kg.sum() - old[old.Typ.ne("Unterbau")].Gewicht_kg.sum()) < .05
    assert valid(rows, decks)
    check_pair(rows)
    out = Path("/tmp/side-by-side-shelf-verification")
    out.mkdir(exist_ok=True)
    rows.to_csv(out / "positions.csv", index=False)
    decks.to_csv(out / "platforms.csv", index=False)
    summary.to_csv(out / "summary.csv", index=False)
    pdf = app.create_loading_pdf(rows, decks, summary, app.compute_loading_warnings(rows, decks),
                                 project_name="02.0_fuer_Nesting – Nebeneinander")
    (out / "result.pdf").write_bytes(pdf)
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    for i in (0, 2):
        doc[i].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(out / f"page-{i+1}.png")
    print("OK: 99 parts, 2 platforms, 315/400 beside each other, 20-mm packing,"
          f" geometry/support/collision checks clear; {time.perf_counter()-started:.2f}s", flush=True)


if __name__ == "__main__":
    main()
