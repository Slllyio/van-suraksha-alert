"""
3-Day Fire Danger Outlook — Guna Division, MP.
Combines GFS forecasts with Van Wagner FWI to produce a 72-h outlook and
optionally per-cell risk maps via the trained predictive LightGBM model.

Outputs:
  outputs/dashboard_feed/fire_danger_forecast.json
  outputs/predictive_fire_risk/risk_map_forecast_+{24|48|72}h.csv

Usage:
  python scripts/forecast_fire_danger.py [--date YYYY-MM-DD] [--no-risk-maps]
"""

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
from src.utils.proj_fix import setup_proj_env; setup_proj_env()
del _os, _sys

import argparse, importlib.util, json, subprocess, sys, warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

warnings.filterwarnings("ignore")

ROOT           = Path(__file__).resolve().parent.parent
FWI_PARQUET    = ROOT / "data_lake" / "fire_weather" / "fwi_daily.parquet"
GFS_DIR        = ROOT / "data_lake" / "weather" / "gfs_0p25"
DASHBOARD_FEED = ROOT / "outputs" / "dashboard_feed"
RISK_MAP_DIR   = ROOT / "outputs" / "predictive_fire_risk"
SCRIPTS_DIR    = ROOT / "scripts"

GUNA_LAT = 24.4
GUNA_LON = 77.15
LEADS    = [24, 48, 72]
FFMC0, DMC0, DC0 = 85.0, 6.0, 15.0   # Van Wagner 1987 spring startup


def _fwi_mod():
    """Lazy-load compute_fwi without polluting sys.modules."""
    spec = importlib.util.spec_from_file_location("compute_fwi", SCRIPTS_DIR / "compute_fwi.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _gfs_exists(run_date: date, lead: int) -> bool:
    p = GFS_DIR / str(run_date.year) / f"{run_date.month:02d}" / f"{run_date.day:02d}" / f"gfs_f{lead:03d}.nc"
    return p.exists()


# ── GFS forecast collection ───────────────────────────────────────────────────

def _try_download(run_date: date) -> None:
    """Best-effort: call weather_ingest.py to fetch today's GFS files."""
    ingest = SCRIPTS_DIR / "weather_ingest.py"
    if not ingest.exists():
        print("  [warn] weather_ingest.py not found"); return
    try:
        r = subprocess.run([sys.executable, str(ingest), "--date", run_date.isoformat()],
                           capture_output=True, text=True, timeout=300)
        print(f"  GFS download: {'OK' if r.returncode == 0 else f'rc={r.returncode}'}")
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  GFS download failed: {exc}")


def collect_gfs_forecasts(run_date: date) -> dict[int, dict]:
    """Return {lead: wx_dict} for leads 24/48/72. Falls back to previous day."""
    mod = _fwi_mod()

    def _get(rd: date, lead: int) -> Optional[dict]:
        return mod.extract_gfs_weather(GFS_DIR, rd, GUNA_LAT, GUNA_LON, lead)

    missing = [l for l in LEADS if not _gfs_exists(run_date, l)]
    if missing:
        print(f"  Missing GFS leads {missing} — attempting download...")
        _try_download(run_date)

    out: dict[int, dict] = {}
    prev = run_date - timedelta(days=1)
    for lead in LEADS:
        rec = _get(run_date, lead)
        if rec is None:
            # Yesterday's run shifted forward by 24h has the same valid time
            rec = _get(prev, lead + 24) or _get(prev, lead)
            if rec:
                rec["source"] = f"GFS {prev} f{lead:03d} (fallback)"
        if rec:
            out[lead] = rec
    return out


# ── FWI state ─────────────────────────────────────────────────────────────────

def load_fwi_state(base_date: date) -> dict:
    """Most recent FWI row on or before base_date; falls back to startup values."""
    default = {"date": base_date, "ffmc": FFMC0, "dmc": DMC0, "dc": DC0,
               "fwi": 0.0, "isi": 0.0, "bui": 0.0, "danger_class": "Low"}
    if not FWI_PARQUET.exists():
        print(f"  [warn] fwi_daily.parquet not found — using startup values")
        return default
    df = pd.read_parquet(FWI_PARQUET)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    past = df[df["date"] <= base_date]
    if past.empty:
        past = df
    row = past.sort_values("date").iloc[-1]
    return {k: (float(row.get(k, v)) if isinstance(v, float) else row.get(k, v))
            for k, v in default.items()}


# ── Forward FWI integration ───────────────────────────────────────────────────

def integrate_fwi(base: dict, gfs: dict[int, dict], base_date: date) -> list[dict]:
    """
    Chain Van Wagner equations for +24h, +48h, +72h.
    Each step seeds moisture codes from the previous step's output.
    """
    mod = _fwi_mod()
    ffmc, dmc, dc = base["ffmc"], base["dmc"], base["dc"]
    clim = {"temp_c": 35.0, "rh_pct": 30.0, "wind_kmh": 12.0, "precip_mm": 0.0}
    steps: list[dict] = []

    for lead in LEADS:
        vd = (base_date + timedelta(hours=lead))
        valid_date = vd.date() if hasattr(vd, "date") else vd
        wx = gfs.get(lead, (clim if not steps else
                            {k: steps[-1]["weather"][k] for k in clim}))
        if steps and lead not in gfs:
            print(f"  [warn] no forecast +{lead}h — repeating previous step")

        T, H = float(wx["temp_c"]), float(max(0.0, min(100.0, wx["rh_pct"])))
        W, ro, mo = float(max(0.0, wx["wind_kmh"])), float(max(0.0, wx["precip_mm"])), valid_date.month

        ffmc = mod._ffmc(T, H, W, ro, ffmc)
        dmc  = mod._dmc(T, H, ro, dmc, mo)
        dc   = mod._dc(T, ro, dc, mo)
        isi  = mod._isi(W, ffmc)
        bui  = mod._bui(dmc, dc)
        fwi  = mod._fwi(isi, bui)

        steps.append({
            "lead_hours": lead,
            "date": valid_date.isoformat(),
            "weather": {"temp_c": round(T, 1), "rh_pct": round(H, 1),
                        "wind_kmh": round(W, 1), "precip_mm": round(ro, 1),
                        "source": wx.get("source", f"GFS f{lead:03d}")},
            "fwi": {"value": round(fwi, 1), "danger": mod.fwi_class(fwi),
                    "ffmc": round(ffmc, 1), "dmc": round(dmc, 1), "dc": round(dc, 1),
                    "isi": round(isi, 1), "bui": round(bui, 1)},
        })
    return steps


# ── Per-cell risk maps ────────────────────────────────────────────────────────

def generate_risk_maps(steps: list[dict]) -> dict[int, dict]:
    """Delegate to train_predictive_fire_risk.py --predict DATE for each horizon."""
    script = SCRIPTS_DIR / "train_predictive_fire_risk.py"
    if not script.exists():
        print("  [warn] predictive model script not found — skipping risk maps")
        return {}
    out: dict[int, dict] = {}
    for step in steps:
        lead, target = step["lead_hours"], step["date"]
        print(f"  Risk map +{lead}h ({target})...")
        try:
            r = subprocess.run([sys.executable, str(script), "--predict", target],
                               capture_output=True, text=True, timeout=600)
            csv = RISK_MAP_DIR / f"risk_map_{target}.csv"
            if r.returncode == 0 and csv.exists():
                df = pd.read_csv(csv)
                s = {
                    "n_critical": int((df["risk_level"] == "CRITICAL").sum()),
                    "n_high":     int((df["risk_level"] == "HIGH").sum()),
                    "n_moderate": int((df["risk_level"] == "MODERATE").sum()),
                }
                dst = RISK_MAP_DIR / f"risk_map_forecast_+{lead}h.csv"
                csv.rename(dst)
                print(f"    -> {dst.name}  CRITICAL={s['n_critical']} HIGH={s['n_high']}")
                out[lead] = s
            else:
                print(f"    [warn] rc={r.returncode}" + (f"\n    {r.stderr[:200]}" if r.stderr else ""))
                out[lead] = {"n_critical": -1, "n_high": -1, "n_moderate": -1}
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"    [warn] {exc}")
            out[lead] = {"n_critical": -1, "n_high": -1, "n_moderate": -1}
    return out


# ── Trend, alert, print ───────────────────────────────────────────────────────

def compute_trend(cur_fwi: float, steps: list[dict]) -> str:
    if not steps: return "STABLE"
    d = steps[-1]["fwi"]["value"] - cur_fwi
    return "INCREASING" if d > 3.0 else ("DECREASING" if d < -3.0 else "STABLE")


def compute_alert(steps: list[dict]) -> Optional[str]:
    for s in steps:
        v, danger, lead, dt = s["fwi"]["value"], s["fwi"]["danger"], s["lead_hours"], s["date"]
        if v >= 38:   return f"FWI expected to reach EXTREME ({v:.1f}) by +{lead}h ({dt})"
        if v >= 21.3: return f"FWI expected to reach {danger} ({v:.1f}) by +{lead}h ({dt})"
    return None


def print_summary(base_date: date, cur: dict, steps: list[dict],
                  summaries: dict[int, dict], trend: str, alert: Optional[str]) -> None:
    sep = "=" * 65
    print(f"\n{sep}\n  GUNA DIVISION — 3-DAY FIRE DANGER OUTLOOK")
    print(f"  Base date : {base_date}  (Lat {GUNA_LAT}N  Lon {GUNA_LON}E)\n{sep}")
    print(f"\n  Current FWI : {cur['fwi']:.1f}  [{cur['danger_class']}]  "
          f"FFMC={cur['ffmc']:.0f}  DMC={cur['dmc']:.0f}  DC={cur['dc']:.0f}")
    print(f"\n  {'Lead':>6}  {'Date':^12}  {'T°C':>5}  {'RH%':>4}  {'Wind':>6}  "
          f"{'Rain':>5}  {'FWI':>6}  Danger\n  " + "-" * 68)
    for s in steps:
        wx, f = s["weather"], s["fwi"]
        bar = "#" * min(int(f["value"] / 2), 20)
        print(f"  +{s['lead_hours']:>4}h  {s['date']:^12}  {wx['temp_c']:>5.1f}  "
              f"{wx['rh_pct']:>4.0f}  {wx['wind_kmh']:>5.1f}k  {wx['precip_mm']:>5.1f}  "
              f"{f['value']:>6.1f}  {f['danger']:<12}  {bar}")
    print(f"\n  Trend : {trend}")
    print(f"  Alert : {alert or 'None'}")
    if summaries:
        print(f"\n  {'Lead':>6}  {'CRITICAL':>10}  {'HIGH':>8}  {'MODERATE':>10}\n  " + "-" * 38)
        for lead, s in sorted(summaries.items()):
            if s.get("n_critical", -1) < 0:
                print(f"  +{lead:>4}h  {'(failed)':>10}")
            else:
                print(f"  +{lead:>4}h  {s['n_critical']:>10}  {s['n_high']:>8}  {s['n_moderate']:>10}")
    print(f"\n{sep}\n")


# ── JSON output ───────────────────────────────────────────────────────────────

def save_forecast_json(base_date: date, cur: dict, steps: list[dict],
                       summaries: dict[int, dict], trend: str, alert: Optional[str]) -> Path:
    payload = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "base_date": base_date.isoformat(),
        "current_fwi": {
            "value": round(cur["fwi"], 1), "danger": cur["danger_class"],
            "ffmc": round(cur["ffmc"], 1), "dmc": round(cur["dmc"], 1), "dc": round(cur["dc"], 1),
        },
        "forecast": [
            {"date": s["date"], "lead_hours": s["lead_hours"], "weather": s["weather"],
             "fwi": s["fwi"], "risk_summary": summaries.get(s["lead_hours"], {})}
            for s in steps
        ],
        "trend": trend,
        "alert": alert,
    }
    DASHBOARD_FEED.mkdir(parents=True, exist_ok=True)
    out = DASHBOARD_FEED / "fire_danger_forecast.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="3-day fire danger outlook — Guna Division (GFS + Van Wagner FWI)"
    )
    p.add_argument("--date", default=None, help="Base date YYYY-MM-DD (default: today)")
    p.add_argument("--no-risk-maps", action="store_true", help="Skip per-cell risk maps")
    args = p.parse_args()

    base_date: date = (datetime.strptime(args.date, "%Y-%m-%d").date()
                       if args.date else date.today())
    print(f"\nFire Danger Forecast — {base_date}\n{'=' * 65}")

    print("\n[1] Loading FWI state...")
    cur = load_fwi_state(base_date)
    print(f"  State from {cur['date']}: FWI={cur['fwi']:.1f} [{cur['danger_class']}]  "
          f"FFMC={cur['ffmc']:.0f}  DMC={cur['dmc']:.0f}  DC={cur['dc']:.0f}")

    print("\n[2] Collecting GFS forecasts...")
    gfs = collect_gfs_forecasts(base_date)
    if gfs:
        for lead, wx in sorted(gfs.items()):
            print(f"  +{lead:>2}h  T={wx['temp_c']:.1f}C  RH={wx['rh_pct']:.0f}%  "
                  f"W={wx['wind_kmh']:.1f}km/h  P={wx['precip_mm']:.1f}mm"
                  + (f"  [{wx['source']}]" if "fallback" in wx.get("source","") else ""))
    else:
        print("  No GFS data — using climatological defaults (T=35C, RH=30%, W=12km/h)")

    print("\n[3] Integrating Van Wagner FWI (+24/+48/+72h)...")
    steps = integrate_fwi(cur, gfs, base_date)
    for s in steps:
        f = s["fwi"]
        print(f"  +{s['lead_hours']:>2}h  {s['date']}  FWI={f['value']:.1f} [{f['danger']}]  "
              f"FFMC={f['ffmc']:.0f}  DMC={f['dmc']:.0f}  DC={f['dc']:.0f}")

    summaries: dict[int, dict] = {}
    if not args.no_risk_maps:
        print("\n[4] Generating per-cell risk maps...")
        summaries = generate_risk_maps(steps)
    else:
        print("\n[4] Risk maps skipped (--no-risk-maps)")

    trend = compute_trend(cur["fwi"], steps)
    alert = compute_alert(steps)
    print_summary(base_date, cur, steps, summaries, trend, alert)

    out = save_forecast_json(base_date, cur, steps, summaries, trend, alert)
    print(f"[5] Saved: {out}")

    if alert and "EXTREME" in alert:
        sys.exit(2)


if __name__ == "__main__":
    main()
