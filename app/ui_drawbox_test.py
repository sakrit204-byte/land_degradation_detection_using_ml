"""Playwright test of the "Draw box -> analyse" tool and the Jobs panel.

Starts its OWN server on port 8766 (never touches a server on 8765), then:
  1. draws a box with mouse events -> /api/plan result renders
  2. draws an oversized box -> the /api/plan error renders
  3. types coordinates -> preview + plan
  4. fakes a pipeline job (data/jobs/test_ui_fake.json): "running" -> Jobs panel with steps/progress/log,
     then "done" pointing at an EXISTING AOI -> app reloads aois.json and flies there
     (the aois.json response is patched in the browser so that area looks like a user area)
  5. Esc cancels drawing
"Run analysis" is NEVER clicked (it would start a real ~45 min download).
Screenshots -> outputs/screenshots/ui_drawbox/. The fake job file is always deleted.

    .venv/Scripts/python app/ui_drawbox_test.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "screenshots" / "ui_drawbox"
FAKE = ROOT / "data" / "jobs" / "test_ui_fake.json"
PORT = 8766
URL = f"http://127.0.0.1:{PORT}/"
TARGET = "KEN_baringo"            # existing AOI the fake job "produces"
ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


def write_fake(status, aoi):
    w, s, e, n = aoi["bbox"]
    now = time.time()
    msgs = [f"{time.strftime('%H:%M:%S', time.localtime(now - 300 + 30 * i))} {m}" for i, m in enumerate([
        "1 block(s) on tile 37NBA: USR_Test_area_fake_1", "static layers: WorldCover, SRTM, masks",
        "climate: ERA5-Land monthly 2017-2026", "sentinel2: searching STAC (117 months)",
        "sentinel2: 12/117 months", "sentinel2: 24/117 months", "sentinel2: 31/117 months",
        "sentinel2: 37/117 months"])]
    d = dict(id="test_ui_fake", name="Test area (fake job)", bbox=[w + 0.004, s + 0.004, e - 0.006, n - 0.005],
             status=status, stage="sentinel2", progress=0.41, detail="USR_Test_area_fake_1: 37/117 months",
             messages=msgs, keys=["USR_Test_area_fake_1"], started=now - 300, updated=now)
    if status == "done":
        d.update(stage="done", progress=1.0, keys=[TARGET], finished=now, detail=None,
                 messages=msgs + [f"{time.strftime('%H:%M:%S')} exporting maps, hotspots and charts to the app",
                                  f"{time.strftime('%H:%M:%S')} finished in 25 min"])
    tmp = FAKE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    tmp.replace(FAKE)


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
    page.wait_for_timeout(600)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    aois = json.loads((ROOT / "app" / "static" / "data" / "aois.json").read_text(encoding="utf-8"))
    target = next(a for a in aois["aois"] if a["key"] == TARGET)
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(PORT), "--log-level", "warning"],
                           cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    errors, checks = [], []
    patch_user = {"on": False}

    def check(name, ok):
        checks.append((name, bool(ok)))
        print(("PASS " if ok else "FAIL ") + name)

    try:
        assert wait_server(), "test server did not start"
        write_fake("running", target)
        with sync_playwright() as p:
            browser = p.chromium.launch(args=ARGS, channel="chromium")
            page = browser.new_page(viewport={"width": 1600, "height": 950})

            def on_console(m):
                # the 400 from /api/plan for an oversized box is expected and shown in the UI
                if m.type == "error" and "status of 400" not in m.text:
                    errors.append(f"console: {m.text}")
            page.on("console", on_console)
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

            def patch_aois(route):
                resp = route.fetch()
                body = resp.json()
                if patch_user["on"]:
                    for a in body["aois"]:
                        if a["key"] == TARGET:
                            w, s, e, n = a["bbox"]
                            a.update(user=True, landscape="Test area (fake job)", created=time.strftime("%Y-%m-%d %H:%M"),
                                     user_bbox=[w + 0.004, s + 0.004, e - 0.006, n - 0.005],
                                     warning="Model applied outside its training areas - treat as indicative.")
                route.fulfill(response=resp, json=body)
            page.route("**/data/aois.json", patch_aois)

            page.goto(URL, wait_until="domcontentloaded", timeout=180000)
            page.wait_for_selector(".aoi-card", timeout=60000)
            page.wait_for_timeout(3000)
            # look at a land area (Kenya rift) from ~45 km
            page.evaluate("() => window.__careewViewer.camera.setView({destination: Cesium.Cartesian3.fromDegrees(36.3, 0.75, 45000)})")
            tiles(page)
            check("jobs badge shows running job", page.locator("#btn-jobs.running").count() == 1)

            # 1. draw a ~4 km box by dragging
            page.click("#btn-draw")
            check("drawing mode active", page.evaluate("() => window.__careewTest.drawing()"))
            box = page.locator("#cesium canvas").bounding_box()
            cx, cy = box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.45
            page.mouse.move(cx, cy)
            page.mouse.down()
            for k in range(1, 11):
                page.mouse.move(cx + 9 * k, cy + 8 * k)
                page.wait_for_timeout(30)
            page.mouse.up()
            check("drawing finished after drag", not page.evaluate("() => window.__careewTest.drawing()"))
            check("box recorded", page.evaluate("() => !!window.__careewTest.drawnBox()"))
            page.wait_for_selector("#ap-plan.ok, #ap-plan.err", timeout=90000)
            plan_ok = page.locator("#ap-plan.ok").count() == 1
            check("plan result renders (blocks / minutes / tile)", plan_ok and "block" in page.inner_text("#ap-plan"))
            if not plan_ok:
                print("plan said:", page.inner_text("#ap-plan"))
            check("run button enabled after plan", page.is_enabled("#ap-run") == plan_ok)
            page.wait_for_timeout(500)
            page.screenshot(path=str(OUT / "01_draw_box_plan.png"))

            # 2. oversized box (click corner, click opposite corner)
            page.click("#ap-redraw")
            page.mouse.click(box["x"] + 420, box["y"] + 90)   # right of the floating panel
            page.mouse.move(box["x"] + 600, box["y"] + 400)
            page.wait_for_timeout(300)
            page.mouse.click(box["x"] + box["width"] - 300, box["y"] + box["height"] - 120)
            page.wait_for_selector("#ap-plan.err", timeout=60000)
            txt = page.inner_text("#ap-plan")
            check("oversized box error renders with suggestion", "smaller" in txt.lower())
            check("run button disabled on error", not page.is_enabled("#ap-run"))
            page.screenshot(path=str(OUT / "02_oversized_box_error.png"))

            # 3. typed coordinates
            page.click('.ap-tabs button[data-mode="coords"]')
            page.fill("#ap-lon", "36.20")
            page.fill("#ap-lat", "0.80")
            page.fill("#ap-size", "4")
            page.fill("#ap-name", "Baringo north")
            page.click("#ap-preview")
            page.wait_for_selector("#ap-plan.ok, #ap-plan.err", timeout=90000)
            page.wait_for_timeout(2500)
            tiles(page)
            check("coordinate form previews and plans", page.locator("#ap-plan.ok, #ap-plan.err").count() == 1)
            page.screenshot(path=str(OUT / "03_coordinates_form.png"))
            page.click('.ap-tabs button[data-mode="coords"]')   # stays in coords mode
            page.fill("#ap-lat", "abc")
            page.click("#ap-preview")
            check("invalid coordinates are reported", "numeric" in page.inner_text("#ap-coord-err").lower())
            page.click("#ap-close")

            # 4a. running job
            page.click("#btn-jobs")
            page.wait_for_selector("#jobs-panel .jp-card", timeout=15000)
            page.wait_for_timeout(800)
            jp = page.inner_text("#jobs-panel")
            check("jobs panel shows stage steps + detail", "Sentinel-2" in jp and "37/117" in jp)
            check("jobs panel shows log lines", page.locator("#jobs-panel .jp-log pre").count() == 1)
            check("current step highlighted", page.locator("#jobs-panel .jp-steps li.now").count() == 1)
            page.screenshot(path=str(OUT / "04_jobs_running.png"))

            # 4b. job finishes -> reload aois.json, list under "Your areas", fly there
            patch_user["on"] = True
            write_fake("done", target)
            page.wait_for_function(f"() => window.__careewTest.activeAoi() === '{TARGET}'", timeout=20000)
            page.wait_for_timeout(4500)
            tiles(page)
            check("finished job opens the new area", page.evaluate("() => window.__careewTest.activeAoi()") == TARGET)
            check('"Your areas" group with USER badge', page.locator(".group-head").first.inner_text().lower().startswith("your areas")
                  and page.locator(".aoi-card.user .user-badge").count() >= 1)
            check("warning banner shown", page.is_visible("#aoi-warning") and "indicative" in page.inner_text("#aoi-warning"))
            page.screenshot(path=str(OUT / "05_job_done_jobs_panel.png"))
            page.click("#jp-close")
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / "06_user_area_opened.png"))

            page.evaluate("() => window.__careewTest.openFirstHotspot()")
            page.wait_for_timeout(1000)
            check("hotspot panel carries the warning", page.locator("#infopanel .user-warn").count() == 1)
            page.screenshot(path=str(OUT / "07_user_area_hotspot_warning.png"))
            page.evaluate("() => window.__careewTest.closeInfo()")

            # 5. Esc cancels drawing
            page.click("#btn-draw")
            page.keyboard.press("Escape")
            check("Esc cancels drawing", not page.evaluate("() => window.__careewTest.drawing()"))
            page.click("#ap-close")

            # narrow layout with draw panel
            page.set_viewport_size({"width": 820, "height": 1000})
            page.click("#btn-draw")
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / "08_narrow_draw_panel.png"))
            page.keyboard.press("Escape")
            browser.close()
    finally:
        FAKE.unlink(missing_ok=True)
        FAKE.with_suffix(".tmp").unlink(missing_ok=True)
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()

    print("screenshots ->", OUT)
    print("fake job removed:", not FAKE.exists())
    failed = [n for n, ok in checks if not ok]
    if errors:
        print("\n".join(errors))
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed; {len(errors)} browser errors")
    sys.exit(1 if failed or errors else 0)


if __name__ == "__main__":
    main()
