"""Compare width candidates against the supplied 99-part diagnostic fixture."""
import io
import inspect
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
import zipfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import bvx_auswertung_streamlit as app
import verlade_varianten_flex as flex


def calculate(units, deck):
    return flex.calculate_flexible_loading(
        units, deck, two_lane=True, flexible_width=True,
        init_platform_state=app.init_platform_state,
        can_place_stable=app.can_place_stable, commit_place=app.commit_place,
        find_geometry_conflicts=app.find_geometry_conflicts,
        support_chain_issues=app._pinned_manual_support_chain_issues,
        physical_conflicts=app._pinned_manual_physical_conflicts,
        recompute_summary=app.recompute_summary_from_placements,
        load_quality=app._loading_layout_quality,
        base_default=80, layer_default=40, general_default=0, gap_default=0,
        prevent_wide_on_narrow=True, min_support_ratio=.35,
        max_unsupported_length_mm=0, max_unsupported_side_mm=0,
        max_unsupported_length_percent=0, max_unsupported_side_percent=0,
        prefer_support_quality=True, prefer_side_balance=True,
    )


def main():
    with zipfile.ZipFile(ROOT / "attached_assets/BVX_Verladediagnose_1793530474636.zip") as archive:
        read = lambda name: pd.read_csv(io.BytesIO(archive.read(name)))
        old = read("tabellen/positionen_automatik.csv")
        decks = read("tabellen/pritschen_verwendet.csv")
        units = read("tabellen/verladeeinheiten.csv")
        manifest = json.loads(archive.read("diagnose.json"))
        parts = read("eingabe/parts.csv")
        options = read("eingabe/options.csv")
        config = read("eingabe/platforms.csv")
    if "--full" in sys.argv:
        settings = manifest["calculation"]["settings"]
        supported = inspect.signature(app.create_variant_a_loading_plan).parameters
        kwargs = {key: value for key, value in settings.items() if key in supported}
        kwargs.update(
            same_attrs=settings["bundle_match_attrs"],
            min_support_width_ratio=settings["min_support_width_percent"] / 100,
            prefer_stable_option=settings["compact_transport_strategy"],
            prefer_length_before_stack=True,
            fuhre_split_attr=settings["effective_fuhre_split_attr"],
        )
        started = time.perf_counter()
        result, summary, used, trips, generated_units = app.create_variant_a_loading_plan(
            parts, options, config, manifest["calculation"]["standards"], **kwargs
        )
        elapsed = time.perf_counter() - started
        real = result[~result.Typ.isin(["Unterbau", "Kantholz", "Einlage", "Bundeinlage", "Lagenholz"])]
        assert len(real) == 99 and len(used) == 2 and len(trips) == 1
        assert not real.Pritsche.eq("NICHT VERLADEN").any()
        assert real.Einheit_ID.nunique() == 99
        for name, check in (
            ("geometry", app.find_geometry_conflicts(result, used)),
            ("support", app._pinned_manual_support_chain_issues(result, used)),
            ("physical", app._pinned_manual_physical_conflicts(result)),
        ):
            assert check.empty, (name, check.to_dict("records"))
        out = Path("/tmp/width-fix-verification")
        out.mkdir(exist_ok=True)
        for name, frame in (("positions", result), ("summary", summary), ("platforms", used)):
            frame.to_csv(out / f"{name}.csv", index=False)
        pdf = app.create_loading_pdf(
            result, used, summary, app.compute_loading_warnings(result, used),
            project_name="02.0_fuer_Nesting – Breitenkorrektur",
        )
        (out / "result.pdf").write_bytes(pdf)
        import pymupdf
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        for i in range(0, len(doc), 2):
            doc[i].get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(out / f"page-{i+1}.png")
        print(f"FULL: 99 parts, 1 trip, 2 platforms, {elapsed:.2f}s, all geometry/support/physical checks clear", flush=True)
        for _, deck in used.iterrows():
            placed = result[result.Pritsche.eq(deck.Pritsche)]
            actual = placed[placed.Typ.ne("Unterbau")]
            print(deck.Pritsche, "parts", len(actual), "timbers", len(placed)-len(actual),
                  "quality", app._loading_layout_quality(placed, deck),
                  "side", flex.seitenbalance_kennzahl(placed, deck), flush=True)
        return
    for _, deck in decks.iterrows():
        previous = old[old.Pritsche.eq(deck.Pritsche)]
        block = units[units.Einheit_ID.isin(previous.Einheit_ID)].sort_values(
            "Einheit_ID", ascending=False, kind="stable"
        )
        for mode in ("current", "full-half-candidate"):
            started = time.perf_counter()
            if mode == "full-half-candidate":
                with patch.object(flex, "_width_profiles", return_value=[(1225., 1225.)]):
                    result, _, reason = calculate(block, deck)
            else:
                result, _, reason = calculate(block, deck)
            print(deck.Pritsche, mode, reason, f"{time.perf_counter()-started:.2f}s")
            if not result.empty:
                print("parts", len(result), "quality", app._loading_layout_quality(result, deck),
                      "side", flex.seitenbalance_kennzahl(result, deck))
                print("Y/width", result.groupby(["Y_mm", "Breite_mm"]).size().to_dict())


if __name__ == "__main__":
    main()
