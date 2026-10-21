"""Headless UI smoke test + screenshots (Playwright, Chromium with SwiftShader WebGL).

Requires the server to be running:
    .venv/Scripts/python -m uvicorn app.server:app --port 8765
Then:
    .venv/Scripts/python app/ui_screenshots.py [--url http://127.0.0.1:8765] [--aoi NPL_chure]

Writes PNGs to outputs/screenshots/ui_dev/ and prints browser console errors.
Exit code 1 if the page logged errors.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

import os
OUT = Path(__file__).resolve().parents[1] / "outputs" / "screenshots" / os.environ.get("SHOT_DIR", "ui_dev")
ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
        "--enable-webgl"]


def wait_tiles(page, timeout=60000):
    """Wait until Cesium reports no pending tiles (or time out)."""
    try:
        page.wait_for_function(
            "() => window.__careewViewer && window.__careewViewer.scene.globe.tilesLoaded", timeout=timeout)
    except Exception:                       # slow tile servers should not abort the run
        print("warning: imagery tiles still loading after", timeout, "ms")
    page.wait_for_timeout(800)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765/")
    ap.add_argument("--aoi", default="NPL_chure")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=950)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=ARGS, channel="chromium")  # full Chromium (new headless) for WebGL
        page = browser.new_page(viewport={"width": a.width, "height": a.height}, device_scale_factor=1)
        page.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.url} {r.failure}"))

        # 1. globe view
        page.goto(a.url, wait_until="domcontentloaded", timeout=180000)  # CDN can be slow
        page.wait_for_selector(".aoi-card", timeout=30000)
        page.wait_for_timeout(3500)                  # home flight
        wait_tiles(page)
        page.screenshot(path=str(OUT / "01_globe.png"))

        # 2. AOI view
        page.click(f'.aoi-card[data-key="{a.aoi}"]')
        page.wait_for_timeout(3800)                  # camera flight
        wait_tiles(page)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "02_aoi_hotspots_rivers.png"))

        # 3. hotspot panel (open via the same code path as a globe click)
        page.evaluate("() => window.__careewTest.openFirstHotspot()")
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT / "03_hotspot_panel.png"))

        # 4. pixel inspector: click the canvas at the AOI centre
        page.evaluate("() => window.__careewTest.closeInfo()")
        page.evaluate("() => window.__careewTest.inspectCenter()")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "04_pixel_inspector.png"))

        # 5. river-flow tab + NDVI layer + earlier month
        page.click('.tab[data-tab="flow"]')
        page.check('[data-toggle="ndvi"]')
        page.uncheck('[data-toggle="risk"]')
        page.click("#tb-prev"); page.click("#tb-prev"); page.click("#tb-prev")
        page.wait_for_timeout(1500)
        wait_tiles(page)
        page.screenshot(path=str(OUT / "05_ndvi_riverflow.png"))

        # 6. Sentinel-2 RGB layer
        page.uncheck('[data-toggle="ndvi"]')
        page.check('[data-toggle="rgb"]')
        page.click('.tab[data-tab="ts"]')
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "06_rgb_timeseries.png"))

        # 7. model card
        page.click("#btn-model")
        page.wait_for_selector("#model-card .tiles", timeout=10000)
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "07_model_card.png"))
        page.keyboard.press("Escape")

        # 8. second AOI via search (risk layer back on)
        page.uncheck('[data-toggle="rgb"]')
        page.check('[data-toggle="risk"]')
        page.fill("#aoi-search", "brazil")
        page.press("#aoi-search", "Enter")
        page.wait_for_timeout(4000)
        wait_tiles(page)
        page.screenshot(path=str(OUT / "08_aoi_search_brazil.png"))

        # exports for field teams (current AOI)
        for fmt in ("geojson", "csv"):
            page.click("#btn-export")
            with page.expect_download() as dl:
                page.click(f'#export-menu button[data-fmt="{fmt}"]')
            path = OUT / f"export_sample.{fmt}"
            dl.value.save_as(str(path))
            print("export ok:", path.name, path.stat().st_size, "bytes")

        # 9. narrow / tablet layout
        page.set_viewport_size({"width": 820, "height": 1000})
        page.wait_for_timeout(1500)
        wait_tiles(page)
        page.screenshot(path=str(OUT / "09_narrow.png"))
        browser.close()

    print("screenshots ->", OUT)
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    print("no browser errors")


if __name__ == "__main__":
    main()
