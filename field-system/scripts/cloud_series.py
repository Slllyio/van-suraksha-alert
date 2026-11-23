"""Statewide cloud input series for pc_models/daily_run.py (field-system thread, 19 Oct 2026), all 87 divisions:
  gfs     pc_models/cloud_series/gfs_daily_<season>.csv   division, date, t_mean, t_max, rh_mean, wind_mean, prcp (app/cloud_gfs)
  soil    pc_models/cloud_series/swvl1_<season>.csv       division, date, swvl1 (ERA5 from ARCO, app/cloud_soil; NOT ERA5-Land)
  modis   pc_models/cloud_series/modis_<season>.npz       cells, dates, ndvi/ndmi/lst int16 (x1e4, x1e4, x50; -32768 = none)
          for composites starting 1 Sep (S-1) .. 31 May S (app/cloud_inputs.modis_frames turns it into the sr_/lst_ tables
          build_day_features.py reads; Sep-Dec give the leaf-fall peak, Nov-Dec the early-season as-of values)
Season S = 1 Oct (S-1) .. 30 Jun S. Usage: python cloud_series.py <season> gfs|soil|modis [threads]
Parts are cached in $CS_TMP (default /tmp/cloud_series) so a killed run resumes."""
import os, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import cloud_gfs, cloud_soil, cloud_modis
from app.cloud_build import hull
from app.cloud_inputs import bbox

OUT = Path(__file__).resolve().parent.parent / "pc_models" / "cloud_series"
TMP = Path(os.environ.get("CS_TMP", "/tmp/cloud_series")); TMP.mkdir(parents=True, exist_ok=True)
season, what = int(sys.argv[1]), sys.argv[2]
NT = int(sys.argv[3]) if len(sys.argv) > 3 else 6
st = pd.read_parquet(OUT.parent / "static_inputs.parquet", columns=["cell", "division"])
DIVS = {dv: np.sort(g.cell.to_numpy()) for dv, g in st.groupby("division")}
days = pd.date_range(f"{season - 1}-10-01", f"{season}-06-30")


def run(fn, items, name):
    def one(d):
        f = TMP / f"{name}_{pd.Timestamp(d).date()}.csv"
        if not f.exists():
            try:
                fn(d).to_csv(f, index=False)
            except Exception as e:
                print("failed", name, d, str(e)[:100], flush=True)
                return
        return f
    with ThreadPoolExecutor(NT) as ex:
        files = [f for f in ex.map(one, items) if f]
    print(name, len(files), "of", len(items), flush=True)
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


if what == "gfs":
    H = {dv: hull(c) for dv, c in DIVS.items()}
    g = run(lambda d: cloud_gfs.daily(d, H), days, f"gfs{season}")
    g.sort_values(["division", "date"]).to_csv(OUT / f"gfs_daily_{season}.csv", index=False)
elif what == "soil":
    W = {dv: cloud_gfs.weights(hull(c)) for dv, c in DIVS.items()}
    s = run(lambda d: pd.DataFrame([dict(division=k, date=pd.Timestamp(d), swvl1=v) for k, v in cloud_soil.daily(d, W).items()]),
            pd.date_range(days[0] - pd.Timedelta(days=7), days[-1]), f"soil{season}")
    s.sort_values(["division", "date"]).to_csv(OUT / f"swvl1_{season}.csv", index=False)
elif what == "modis":
    cells = np.unique(np.concatenate(list(DIVS.values())))
    bb = bbox(cells)
    f = TMP / f"modis{season}_v2.npz"
    if not f.exists():
        vals = cloud_modis.load(cells, bb, f"{season - 1}-09-01", f"{season}-05-31")
        ks = sorted(vals)
        V = np.stack([vals[k] for k in ks])
        q = lambda a, s: np.where(np.isfinite(a), np.round(a * s), -32768).astype(np.int16)
        np.savez_compressed(f, cells=cells.astype(np.int32), dates=np.array([str(k.date()) for k in ks]), ndvi=q(V[..., 0], 1e4),
                            ndmi=q(V[..., 1], 1e4), lst=q(V[..., 2] - 250, 50))
    import shutil
    shutil.copy(f, OUT / f"modis_{season}.npz")
    print("modis", season, "done", flush=True)
