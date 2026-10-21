"""Smoke test: run aoi_context/features on partially downloaded S2 parts (missing months = NaN)."""
import sys, time, numpy as np, pandas as pd, xarray as xr
sys.path.insert(0, ".")
from care_ew import s2 as s2mod, dataset
from care_ew.config import PROC, S2_START, S2_END
key = sys.argv[1]
months = pd.period_range(S2_START, S2_END, freq="M")
part = PROC / key / "s2_parts"
x0, y0, n = s2mod._grid(s2mod.AOI_BY_KEY[key])
data = {}
for k in s2mod.INDICES:
    arr = np.full((len(months), n, n), np.nan, np.float32)
    for i, m in enumerate(months):
        f = part / f"{m}.npz"
        if f.exists(): arr[i] = np.load(f)[k]
    data[k] = (("time", "y", "x"), arr)
ds = xr.Dataset(data, coords={"time": months.to_timestamp()})
print("months present", sum((part / f"{m}.npz").exists() for m in months))
s2mod.load = lambda k: ds
t = time.time()
ctx = dataset.aoi_context(key, save_cube=False)
print("ctx", round(time.time() - t, 1), "s  N=", ctx["N"], "climate model", ctx["cm_info"])
F, R = dataset.features_for(ctx, np.arange(0, ctx["N"], 200))
bad = {k: float(np.isinf(np.asarray(v, float)).mean()) for k, v in F.items() if np.isinf(np.asarray(v, float)).any()}
print("features", len(F), "inf:", bad, "onsets", int(ctx["onset"].sum()), "label rate", float(np.nanmean(np.where(ctx["eligible"], ctx["y"], np.nan))))
