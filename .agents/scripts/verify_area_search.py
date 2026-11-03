"""Replay the uploaded Verlad2.0 diagnostic input through the full planner."""
import inspect
import json
from pathlib import Path
import sys
import time
import zipfile

import pandas as pd
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bvx_auswertung_streamlit as app
from loading_area_search import _metrics
from loading_shelf_search import _respects_order

with zipfile.ZipFile("attached_assets/BVX_Verladediagnose-3_1793730355159.zip") as z:
    read = lambda n: pd.read_csv(z.open(n))
    old = read("tabellen/positionen_aktuell.csv")
    parts, options, config = [read("eingabe/"+n+".csv") for n in ("parts", "options", "platforms")]
    manifest = json.loads(z.read("diagnose.json"))
settings = manifest["calculation"]["settings"]
accepted = inspect.signature(app.create_variant_a_loading_plan).parameters
kwargs = {k: v for k, v in settings.items() if k in accepted}
kwargs.update(min_support_width_ratio=settings["min_support_width_percent"]/100,
              enable_area_search=True,
              prefer_stable_option=settings["compact_transport_strategy"],
              prefer_length_before_stack=True,
              fuhre_split_attr=settings["effective_fuhre_split_attr"])
started = time.monotonic()
rows, summary, decks, trips, units = app.create_variant_a_loading_plan(
    parts, options, config, manifest["calculation"]["standards"], **kwargs)
assert len(decks) == len(trips) == 4
assert sorted(rows[rows.Typ.eq("Bauteil")].Einheit_ID) == sorted(old[old.Typ.eq("Bauteil")].Einheit_ID)
assert app.find_geometry_conflicts(rows, decks).empty
assert app._pinned_manual_support_chain_issues(rows, decks).empty
assert app._pinned_manual_physical_conflicts(rows).empty
for _, deck in decks.iterrows():
    before, after = old[old.Pritsche.eq(deck.Pritsche)], rows[rows.Pritsche.eq(deck.Pritsche)]
    actual = after[after.Typ.eq("Bauteil")]
    ranks = {str(r.Einheit_ID): -float(r.Logische_Reihenfolge_im_Block) for _, r in actual.iterrows()}
    assert _respects_order(actual, ranks)
    if int(deck.Fuhre_Nr) in (1, 2):
        # The former second-layer zigzag is gone: equal-length members align.
        bottom = actual.sort_values("Logische_Reihenfolge_im_Block", ascending=False)
        assert abs(float(bottom.iloc[0].X_mm)-float(bottom.iloc[2].X_mm)) < .1
    if int(deck.Fuhre_Nr) == 3:
        assert actual.Ansicht_Label.astype(str).str.contains("WP-05").all()
        assert len(actual) == 20
    print(deck.Pritsche, _metrics(after, deck), flush=True)
out = Path("/tmp/area-search-verification")
out.mkdir(exist_ok=True)
rows.to_csv(out/"positions.csv", index=False)
pdf = app.create_loading_pdf(rows, decks, summary, app.compute_loading_warnings(rows, decks),
                             project_name="Verlad2.0 – Flächensuche")
(out/"result.pdf").write_bytes(pdf)
doc = pymupdf.open(stream=pdf, filetype="pdf")
doc[0].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2)).save(out/"page-1.png")
print("PASS", len(actual), "last platform parts;", round(time.monotonic()-started, 2), "seconds")
