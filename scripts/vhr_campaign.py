"""Blind VHR check of warnings (PROJECT_LOG D-029).

  python scripts/vhr_campaign.py sample     -> data/vhr/points.json  (+ data/vhr/key.json, hidden class labels)
  python scripts/vhr_campaign.py fetch      -> data/vhr/chips/<id>_{a,b}.png  + data/vhr/pairs.json
  python scripts/vhr_campaign.py analyze    -> data/vhr/result.json  (needs data/vhr/answers.json)

Imagery: Esri World Imagery Wayback releases (data/vhr/waybackconfig.json). For each point the tile at zoom 17 is
read from ~one release per half-year; identical tiles are one "version"; each version's acquisition date comes
from the metadata layer of the release that first shows it. Requests are cached on disk and rate-limited.
"""
import sys, json, re, time, hashlib, io, random, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd, requests
from pyproj import Transformer
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from care_ew.config import AOIS, PROC  # noqa: E402

VHR = ROOT / "data" / "vhr"; CACHE = VHR / "tiles"; CHIPS = VHR / "chips"
SEED, N_PER, Z = 29, 6, 17
T0, T1 = "2023-01", "2024-06"
MIN_SEP_PX = 10                         # 100 m
S = requests.Session(); S.headers["User-Agent"] = "CARE-EW research (blind VHR check)"
_last = [0.0]
_rl = threading.Lock()


def get(url, binary=True, tries=4):
    for k in range(tries):
        with _rl:                          # global rate limit across threads: <= ~6 requests / s
            dt = time.time() - _last[0]
            if dt < 0.16:
                time.sleep(0.16 - dt)
            _last[0] = time.time()
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200:
                return r.content if binary else r.json()
            if r.status_code in (404, 400):
                return None
        except (requests.RequestException, ValueError):
            pass
        time.sleep(3 * (k + 1))
    return None


# ----------------------------------------------------------------------------- sampling
def lonlat(aoi_key, r, c):
    g = json.load(open(PROC / aoi_key / "grid.json"))
    x = g["x0"] + 10 * c + 5; y = g["y0"] + g["n"] * 10 - 10 * r - 5
    return Transformer.from_crs(g["epsg"], 4326, always_xy=True).transform(x, y)


def _spread(rng, cand_r, cand_c, n):
    out = []
    for i in rng.permutation(len(cand_r)):
        if all((cand_r[i] - cand_r[j]) ** 2 + (cand_c[i] - cand_c[j]) ** 2 >= MIN_SEP_PX ** 2 for j in out):
            out.append(i)
            if len(out) == n:
                break
    return out


def sample():
    rng = np.random.default_rng(SEED)
    pts, key = [], {}
    for a in AOIS:
        z = np.load(ROOT / "outputs" / "predictions" / f"{a.key}_risk.npz", allow_pickle=True)
        months = pd.PeriodIndex(z["months"], freq="M")
        win = (months >= pd.Period(T0, "M")) & (months <= pd.Period(T1, "M"))
        st = z["status"][win]; mw = months[win]
        warn = (st == 1)
        first = np.where(warn.any(0), warn.argmax(0), -1)
        ctrl = (st == 0).all(0)
        wi = np.where(first >= 0)[0]; ci = np.where(ctrl)[0]
        rr, cc = z["rr"], z["cc"]
        sw = wi[_spread(rng, rr[wi], cc[wi], N_PER)] if len(wi) else []
        sc = ci[_spread(rng, rr[ci], cc[ci], N_PER)] if len(ci) else []
        onsets = [str(mw[first[i]]) for i in sw]
        for cls, idxs in (("warning", sw), ("control", sc)):
            for j, i in enumerate(idxs):
                t = onsets[j] if cls == "warning" else (str(rng.choice(onsets)) if onsets else T0)
                lon, lat = lonlat(a.key, int(rr[i]), int(cc[i]))
                pid = hashlib.sha1(f"{SEED}{a.key}{i}".encode()).hexdigest()[:8]
                pts.append(dict(id=pid, aoi=a.key, row=int(rr[i]), col=int(cc[i]), lon=round(lon, 6), lat=round(lat, 6), t=t))
                key[pid] = cls
        print(a.key, "warnings", len(sw), "controls", len(sc), flush=True)
    random.Random(SEED).shuffle(pts)
    VHR.mkdir(parents=True, exist_ok=True)
    json.dump(pts, open(VHR / "points.json", "w"), indent=1)
    json.dump(key, open(VHR / "key.json", "w"), indent=1)
    print("points", len(pts))


# ----------------------------------------------------------------------------- imagery
def releases():
    cfg = json.load(open(VHR / "waybackconfig.json"))
    rel = []
    for num, v in cfg.items():
        d = re.search(r"(\d{4}-\d{2}-\d{2})", v["itemTitle"]).group(1)
        rel.append(dict(num=num, date=d, url=v["itemURL"], meta=v["metadataLayerUrl"]))
    rel.sort(key=lambda r: r["date"])
    # last release of each half-year from 2017 on, plus the newest
    pick = {}
    for r in rel:
        if r["date"] >= "2017":
            pick[(r["date"][:4], int(r["date"][5:7]) > 6)] = r
    out = sorted(pick.values(), key=lambda r: r["date"])
    return out


def tile_xy(lon, lat, z=Z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - np.log(np.tan(np.radians(lat)) + 1 / np.cos(np.radians(lat))) / np.pi) / 2 * n
    return x, y


def tile(rel, z, x, y):
    f = CACHE / rel["num"] / f"{z}_{x}_{y}.jpg"
    if f.exists():
        return f.read_bytes() or None
    b = get(rel["url"].format(level=z, row=y, col=x))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b or b"")
    return b


def acq_date(rel, lon, lat):
    f = CACHE / "meta" / f"{rel['num']}_{lon:.5f}_{lat:.5f}.json"
    if f.exists():
        return json.load(open(f))
    out = None                             # one identify over all resolution layers; finest dated layer wins
    d = get(f"{rel['meta']}/identify?geometry={lon},{lat}&geometryType=esriGeometryPoint&sr=4326&layers=all&tolerance=0"
            f"&mapExtent={lon - .01},{lat - .01},{lon + .01},{lat + .01}&imageDisplay=400,400,96&returnGeometry=false&f=json",
            binary=False)
    for hit in sorted((d or {}).get("results") or [], key=lambda h: h["layerId"]):
        a = hit["attributes"]; dt = str(a.get("SRC_DATE", ""))
        if re.fullmatch(r"\d{8}", dt):
            out = dict(date=dt, res=a.get("SRC_RES"), src=a.get("NICE_DESC"))
            break
    f.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(f, "w"))
    return out


def chip(rel, lon, lat, size=256):
    fx, fy = tile_xy(lon, lat)
    x0, y0 = int(fx), int(fy)
    canvas = Image.new("RGB", (768, 768))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            b = tile(rel, Z, x0 + dx, y0 + dy)
            if b:
                canvas.paste(Image.open(io.BytesIO(b)).convert("RGB"), ((dx + 1) * 256, (dy + 1) * 256))
    px, py = (fx - x0 + 1) * 256, (fy - y0 + 1) * 256
    im = canvas.crop((int(px - size / 2), int(py - size / 2), int(px + size / 2), int(py + size / 2))).resize((512, 512), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    m_per_px = 156543.03 * np.cos(np.radians(lat)) / 2 ** Z / 2     # after 2x upscale
    h = max(4, 5 / m_per_px)                                         # 10 m cell -> half-width 5 m
    for w, col in ((3, (0, 0, 0)), (1, (255, 230, 0))):
        d.rectangle((256 - h - 6, 256 - h - 6, 256 + h + 6, 256 + h + 6), outline=col, width=w)
    return im


def fetch():
    pts = json.load(open(VHR / "points.json"))
    rel = releases()
    print("releases used", len(rel), rel[0]["date"], "...", rel[-1]["date"], flush=True)
    CHIPS.mkdir(parents=True, exist_ok=True)
    pairs, dropped, lock, done = [], [], threading.Lock(), [0]

    def one(p):
        fx, fy = tile_xy(p["lon"], p["lat"])
        versions = []                      # (first release, hash)
        for r in rel:
            b = tile(r, Z, int(fx), int(fy))
            if not b:
                continue
            h = hashlib.md5(b).hexdigest()
            if not versions or versions[-1][1] != h:
                versions.append((r, h))
        dated = []
        for r, h in versions:
            m = acq_date(r, p["lon"], p["lat"])
            if m and (not dated or dated[-1][1]["date"] != m["date"]):
                dated.append((r, m))
        t = pd.Period(p["t"], "M")
        to_p = lambda m: pd.Period(f"{m['date'][:4]}-{m['date'][4:6]}", "M")
        before = [x for x in dated if to_p(x[1]) <= t]
        after = [x for x in dated if to_p(x[1]) >= t + 6]
        with lock:
            done[0] += 1
        if not before or not after:
            with lock:
                dropped.append(dict(id=p["id"], reason="no before" if not before else "no after", n_versions=len(dated)))
            print(f"[{done[0]}/{len(pts)}] {p['id']} dropped ({dropped[-1]['reason']}, {len(dated)} versions)", flush=True)
            return
        rb, mb = before[-1]; ra, ma = after[-1]
        chip(rb, p["lon"], p["lat"]).save(CHIPS / f"{p['id']}_a.png")
        chip(ra, p["lon"], p["lat"]).save(CHIPS / f"{p['id']}_b.png")
        with lock:
            pairs.append(dict(id=p["id"], aoi=p["aoi"], lon=p["lon"], lat=p["lat"], t=p["t"],
                              before=dict(date=mb["date"], res=mb["res"], src=mb["src"], release=rb["date"]),
                              after=dict(date=ma["date"], res=ma["res"], src=ma["src"], release=ra["date"])))
        print(f"[{done[0]}/{len(pts)}] {p['id']} before {mb['date']} after {ma['date']}", flush=True)

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(one, pts))
    order = {p["id"]: k for k, p in enumerate(pts)}          # keep the shuffled review order
    pairs.sort(key=lambda q: order[q["id"]])
    json.dump(dict(pairs=pairs, dropped=dropped), open(VHR / "pairs.json", "w"), indent=1)
    print("usable pairs", len(pairs), "dropped", len(dropped))


# ----------------------------------------------------------------------------- analysis
def analyze(answers_file=None):
    from scipy.stats import fisher_exact
    key = json.load(open(VHR / "key.json"))
    ans_all = json.load(open(answers_file or VHR / "answers.json"))
    res = {}
    for who, ans in ans_all.items():
        rows = [(key[i], a) for i, a in ans.items() if a in ("yes", "no", "unsure")]
        df = pd.DataFrame(rows, columns=["cls", "a"])
        use = df[df.a != "unsure"]
        y = {c: (use[use.cls == c].a == "yes").values for c in ("warning", "control")}
        rng = np.random.default_rng(0)
        boots = [rng.choice(y["warning"], len(y["warning"])).mean() - rng.choice(y["control"], len(y["control"])).mean()
                 for _ in range(5000)]
        tab = [[y["warning"].sum(), (~y["warning"]).sum()], [y["control"].sum(), (~y["control"]).sum()]]
        res[who] = dict(n=dict(df.groupby(["cls", "a"]).size().unstack(fill_value=0).to_dict("index")),
                        yes_rate_warning=float(y["warning"].mean()), yes_rate_control=float(y["control"].mean()),
                        diff=float(y["warning"].mean() - y["control"].mean()),
                        ci95=[float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
                        fisher_p=float(fisher_exact(tab, alternative="greater")[1]))
        print(who, json.dumps(res[who], indent=1))
    json.dump(res, open(VHR / "result.json", "w"), indent=1)


if __name__ == "__main__":
    {"sample": sample, "fetch": fetch, "analyze": analyze}[sys.argv[1]](*sys.argv[2:])
