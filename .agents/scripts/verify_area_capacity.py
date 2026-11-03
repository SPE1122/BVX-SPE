"""Replay the no-group input, and compare an explicit PB boundary."""
from pathlib import Path
import inspect
import json
import sys
import zipfile
import pandas as pd
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bvx_auswertung_streamlit as app
from loading_shelf_search import _respects_order

with zipfile.ZipFile("attached_assets/BVX_Verladediagnose-5_1793736113716.zip") as z:
    read = lambda n: pd.read_csv(z.open(n))
    parts, options, config = [read("eingabe/"+n+".csv") for n in ("parts", "options", "platforms")]
    manifest = json.loads(z.read("diagnose.json"))
settings = manifest["calculation"]["settings"]
kwargs = {k: v for k, v in settings.items()
          if k in inspect.signature(app.create_variant_a_loading_plan).parameters}
kwargs.update(min_support_width_ratio=settings["min_support_width_percent"]/100,
              prefer_stable_option=True, prefer_length_before_stack=True, enable_area_search=True)
for boundary in ("Aus", "PB."):
    rows, summary, decks, trips, units = app.create_variant_a_loading_plan(
        parts, options, config, manifest["calculation"]["standards"],
        **kwargs, fuhre_split_attr=boundary)
    real = rows[rows.Typ.eq("Bauteil")]
    assert len(real) == real.Einheit_ID.nunique() == len(parts)
    assert not real.Pritsche.eq("NICHT VERLADEN").any()
    assert abs(real.Gewicht_kg.sum()-parts.Gewicht_kg.sum()) < .1
    assert app.find_geometry_conflicts(rows, decks).empty
    assert app._pinned_manual_support_chain_issues(rows, decks).empty
    assert app._pinned_manual_physical_conflicts(rows).empty
    for _, group in real.groupby("Pritsche"):
        ranks = {str(r.Einheit_ID): -float(r.Logische_Reihenfolge_im_Block) for _, r in group.iterrows()}
        assert _respects_order(group, ranks)
        if boundary == "PB.":
            assert group.Ansicht_Label.str.extract(r"WP-(\d+)")[0].nunique() == 1
    print("BOUNDARY", boundary, "TRIPS", len(trips), "PLATFORMS", len(decks), flush=True)
    print(summary[["Pritsche", "Höhe genutzt_mm", "Gesamtgewicht inkl. Pritsche_kg"]].to_string(index=False), flush=True)
    wp = real[real.Ansicht_Label.astype(str).str.contains("WP-05")]
    assert len(decks) == 4
    if boundary == "PB.":
        assert wp.Pritsche.nunique() == 1
    print("WP05:", wp.groupby("Pritsche").size().to_dict(), flush=True)
    out = Path("/tmp/area-capacity-"+("none" if boundary == "Aus" else "pb"))
    out.mkdir(exist_ok=True)
    rows.to_csv(out/"positions.csv", index=False)
    decks.to_csv(out/"decks.csv", index=False)
    pdf = app.create_loading_pdf(rows, decks, summary, app.compute_loading_warnings(rows, decks),
                                 project_name="Verlad2.0 – Kapazitätsprüfung")
    (out/"result.pdf").write_bytes(pdf)
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    doc[0].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2)).save(out/"page-1.png")
print("PASS", flush=True)
