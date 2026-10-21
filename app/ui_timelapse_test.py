"""Playwright test of the hotspot Sentinel-2 time-lapse.

Starts its OWN server on port 8766 (never touches 8765), opens KEN_baringo, CLICKS an active_degradation
hotspot on the globe and checks that:
  * the panel has the time-lapse section, ON by default;
  * an imagery layer clipped to exactly the hotspot rectangle is shown and the AOI overlays are hidden;
  * stepping / play / same-season stepping change the month;
  * closing the panel removes the layer and restores the overlays.
Screenshots -> outputs/screenshots/ui_timelapse/.   One headless browser only.

    .venv/Scripts/python app/ui_timelapse_test.py [--label H12]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "screenshots" / "ui_timelapse"
PORT = 8766
URL = f"http://127.0.0.1:{PORT}/"
AOI = "KEN_baringo"
ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


def wait_server(timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(URL + "api/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def tiles(page, timeout=40000):
    try:
        page.wait_for_function("() => window.__careewViewer && window.__careewViewer.scene.globe.tilesLoaded", timeout=timeout)
    except Exception:
        print("warning: tiles still loading")
    page.wait_for_timeout(500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default=None, help="hotspot label (default: active_degradation with most months below)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    hs = json.loads((ROOT / "app/static/data/aois" / AOI / "hotspots.geojson").read_text(encoding="utf-8"))["features"]
    act = [f for f in hs if f["properties"]["status"] == "active_degradation"]
    feat = next(f for f in hs if f["properties"]["label"] == a.label) if a.label else \
        max(act, key=lambda f: (f["properties"].get("area_ha", 0) > 5, f["properties"].get("months_below", 0)))
    label = feat["properties"]["label"]
    ring = feat["geometry"]["coordinates"][0]
    box = [min(c[0] for c in ring), min(c[1] for c in ring), max(c[0] for c in ring), max(c[1] for c in ring)]
    print("hotspot", label, feat["properties"]["status"], box)

    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(PORT), "--log-level", "warning"],
                           cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    errors, checks = [], []

    def check(name, ok):
        checks.append((name, bool(ok)))
        print(("PASS " if ok else "FAIL ") + name)

    try:
        assert wait_server(), "test server did not start"
        with sync_playwright() as p:
            browser = p.chromium.launch(args=ARGS, channel="chromium")
            page = browser.new_page(viewport={"width": 1600, "height": 950})
            page.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.goto(URL + f"#aoi={AOI}", wait_until="domcontentloaded", timeout=180000)
            page.wait_for_function(f"() => window.__careewTest && window.__careewTest.activeAoi() === '{AOI}'", timeout=180000)
            page.wait_for_timeout(4500)
            tiles(page)

            # click the hotspot on the globe (centre of its box)
            xy = page.evaluate("""([lon, lat]) => {
                const v = window.__careewViewer;
                const w = Cesium.SceneTransforms.worldToWindowCoordinates(v.scene, Cesium.Cartesian3.fromDegrees(lon, lat, 2));
                const r = v.scene.canvas.getBoundingClientRect();
                return w ? [r.left + w.x, r.top + w.y] : null; }""", [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])
            clicked = False
            if xy:
                page.mouse.click(*xy)
                try:
                    page.wait_for_selector("#infopanel .tl", timeout=6000)
                    clicked = True
                except Exception:
                    pass
            if not clicked:                              # e.g. covered by a label: same code path via hook
                print("note: direct click missed the box; opening via hook")
                page.evaluate(f"() => window.__careewTest.showHotspotByLabel('{label}')")
            page.wait_for_selector("#infopanel .tl", timeout=10000)
            check("hotspot opened by clicking the globe", clicked)
            check("time-lapse section ON by default", page.is_checked("#infopanel .tl-on"))
            page.wait_for_function("() => window.__careewTest.timelapse.layer && window.__careewTest.timelapse.layer.ready !== false", timeout=30000)
            page.wait_for_timeout(2200)                  # camera flight
            tiles(page)
            rect = page.evaluate("""() => { const r = window.__careewTest.timelapse.layer.rectangle;
                return [r.west, r.south, r.east, r.north].map(Cesium.Math.toDegrees); }""")
            check("layer rectangle == hotspot box", all(abs(x - y) < 1e-6 for x, y in zip(rect, box)))
            check("AOI overlays hidden while time-lapse is on", page.evaluate("() => window.__careewTest.overlaysShown().length") == 0)
            m0 = page.inner_text("#infopanel .tl-month")
            check("starts at first available month", m0 == "2019-01" or m0[:4] == "2019")
            page.wait_for_timeout(600)
            page.screenshot(path=str(OUT / f"01_{label}_early_{m0}.png"))

            # step
            page.click("#infopanel .tl-next")
            page.wait_for_timeout(900)
            m1 = page.inner_text("#infopanel .tl-month")
            check("next button steps one available month", m1 > m0)
            # play a few frames
            page.click("#infopanel .tl-play")
            page.wait_for_timeout(3200)
            page.click("#infopanel .tl-play")
            m2 = page.inner_text("#infopanel .tl-month")
            check("play advances frames (~1.5/s)", m2 > m1)
            # same season only
            page.check("#infopanel .tl-same")
            page.click("#infopanel .tl-next")
            page.wait_for_timeout(900)
            m3 = page.inner_text("#infopanel .tl-month")
            check("same-season step keeps the calendar month", m3[5:] == m2[5:] and m3[:4] > m2[:4])
            page.uncheck("#infopanel .tl-same")
            # jump to the latest frame
            page.evaluate("""() => { const r = document.querySelector('#infopanel .tl-range');
                r.value = r.max; r.dispatchEvent(new Event('input', { bubbles: true })); }""")
            page.wait_for_function("() => !document.querySelector('#infopanel .tl-state').classList.contains('is-loading')", timeout=30000)
            page.wait_for_timeout(900)
            m4 = page.inner_text("#infopanel .tl-month")
            check("slider jumps to latest month", m4 >= "2026")
            page.screenshot(path=str(OUT / f"02_{label}_late_{m4}.png"))
            # a middle month near the change, for the record
            page.evaluate("""() => { const r = document.querySelector('#infopanel .tl-range');
                r.value = Math.round(r.max * 0.6); r.dispatchEvent(new Event('input', { bubbles: true })); }""")
            page.wait_for_timeout(1500)
            page.screenshot(path=str(OUT / f"03_{label}_mid_{page.inner_text('#infopanel .tl-month')}.png"))
            # panel crop (the time-lapse controls)
            page.locator("#infopanel .tl").screenshot(path=str(OUT / "04_timelapse_controls.png"))

            # toggle off -> overlays back; on again
            page.click("#infopanel .tl-head .switch")
            page.wait_for_timeout(500)
            check("toggle off removes layer and restores overlays",
                  page.evaluate("() => !window.__careewTest.timelapse.layer && window.__careewTest.overlaysShown().length > 0"))
            page.click("#infopanel .tl-head .switch")
            page.wait_for_timeout(1200)

            # close panel -> everything restored
            page.click("#infopanel .ip-close")
            page.wait_for_timeout(800)
            check("closing panel removes time-lapse layer",
                  page.evaluate("() => !window.__careewTest.timelapse.layer && window.__careewTest.timelapse.ds.entities.values.length === 0"))
            check("closing panel restores risk overlay", "risk" in page.evaluate("() => window.__careewTest.overlaysShown()"))
            page.screenshot(path=str(OUT / "05_closed_restored.png"))

            # narrow layout
            page.set_viewport_size({"width": 820, "height": 1000})
            page.evaluate(f"() => window.__careewTest.showHotspotByLabel('{label}')")
            page.wait_for_timeout(3000)
            page.screenshot(path=str(OUT / "06_narrow.png"))
            browser.close()
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()
    failed = [n for n, ok in checks if not ok]
    if errors:
        print("\n".join(errors))
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed; {len(errors)} browser errors; screenshots -> {OUT}")
    sys.exit(1 if failed or errors else 0)


if __name__ == "__main__":
    main()
