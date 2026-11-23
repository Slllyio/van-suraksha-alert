"""Weekly burn-scar report for senior officials (all of MP).

Reads the live ledger (live/events.csv + live/scars.geojson) and writes, for the 7 days ending on <end date>:
  report.html / report.md   plain-language summary, division table, biggest fires, map
  by_division.csv           alerts, scars and burned ha this week and season to date, with the normal for this date
  top_fires.csv             the 15 largest scars of the week
  scars_week.geojson        this week's scar outlines
  map.png                   MP divisions with this week's and earlier scars

"Normal for this date" = median over 2017-25 of each division's burned ha from 15 Feb to the same day,
from the all-MP history (out/set_*.csv + out/scars_*.csv). It is shown only for years the history run has finished.

Usage: python weekly_report.py [end_date YYYY-MM-DD] [live_dir] [out_root]
"""
import os, sys, glob, datetime as dt, warnings
import numpy as np, pandas as pd, geopandas as gpd, shapely

warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../../scripts"))
import live
from burned_area import burned_ha as union_ha
MP = os.path.dirname(HERE)
BEATS = os.path.join(MP, "../../ratapani/beats/mp_beats.geojson")
DIVS = os.path.join(MP, "out/mp_divisions.geojson")
SEASON = ((2, 15), (6, 15))


def season_start(d):
    return dt.date(d.year, *SEASON[0])


def divisions():
    if not os.path.exists(DIVS):
        b = gpd.read_file(BEATS)[["Division", "geometry"]]
        b["geometry"] = b.buffer(0) if b.crs.is_projected else b.to_crs(32643).buffer(0).to_crs(4326)
        d = b.dissolve("Division").reset_index()
        from shapely.geometry import Polygon, MultiPolygon
        def solid(g):   # forest beats are patchy: close gaps and holes so a division reads as one area
            g = g.buffer(1500).buffer(-1500)
            ps = g.geoms if isinstance(g, MultiPolygon) else [g]
            return MultiPolygon([Polygon(p.exterior) for p in ps if p.area > 4e6])
        d = d.to_crs(32643)
        d["geometry"] = [solid(g).simplify(300) for g in d.geometry]
        d = d.to_crs(4326)
        d.to_file(DIVS, driver="GeoJSON")
    return gpd.read_file(DIVS)


def history():
    """All-MP 2017-25 scars run so far: one row per forest fire event with division, date, scar ha."""
    out = []
    for name in ("rest_of_mp", "tiger_reserves", "sample"):
        s, r = os.path.join(MP, f"out/set_{name}.csv"), os.path.join(MP, f"out/scars_{name}.csv")
        if name == "rest_of_mp":   # since 16 Oct the run writes slim files (stats + gzipped outlines)
            r = os.path.join(MP, "out/scars_mp_hist.csv")
        if not (os.path.exists(s) and os.path.exists(r)):
            continue
        S = pd.read_csv(s, usecols=lambda c: c in ("event_id", "acq_date", "Division", "kind", "latitude", "longitude"))
        S = live.not_industry(S)   # mines, industry, solar: steady heat sources, not forest fires
        if "kind" in S:
            S = S[S.kind == "fire"]
        R = pd.read_csv(r, usecols=["event_id", "status", "scar_ha"], on_bad_lines="skip")
        redo = os.path.join(MP, "out/scars_mp_hist_redo.csv")   # 19 Oct: reruns of events that errored (network)
        if name == "rest_of_mp" and os.path.exists(redo):
            R = pd.concat([pd.read_csv(redo, usecols=["event_id", "status", "scar_ha"]), R[R.status != "error"]])
        out.append(S.merge(R.drop_duplicates("event_id"), on="event_id"))
    if not out:
        return pd.DataFrame(columns=["event_id", "acq_date", "Division", "status", "scar_ha"])
    H = pd.concat(out, ignore_index=True).drop_duplicates("event_id")
    H["acq_date"] = pd.to_datetime(H.acq_date).dt.date
    return H


def history_geoms():
    """event_id -> outline (EPSG:4326) for the 2017-25 history: slim run, tiger reserves, check sample."""
    import json
    from shapely.geometry import shape
    from read_geom import read_hist_geom
    parts = []
    if os.path.exists(os.path.join(MP, "out/scars_mp_hist_geom_part1.csv.gz")):
        g = read_hist_geom(os.path.join(MP, "out"))
        parts.append(pd.Series(shapely.from_wkt(g.geometry.values), index=g.event_id.values))
    rd = sorted(glob.glob(os.path.join(MP, "out/scars_mp_hist_redo_geom/*.csv.gz")))
    if rd:
        g = pd.concat([pd.read_csv(f) for f in rd]).drop_duplicates("event_id", keep="last")
        parts.append(pd.Series(shapely.from_wkt(g.geometry.values), index=g.event_id.values))
    f = os.path.join(MP, "out/tiger_reserve_scars.geojson")
    if os.path.exists(f):
        t = gpd.read_file(f)
        parts.append(pd.Series(t.geometry.values, index=t.event_id.values))
    f = os.path.join(MP, "out/scars_sample.csv")
    if os.path.exists(f):
        d = pd.read_csv(f, usecols=["event_id", "geometry"]).dropna()
        parts.append(pd.Series([shape(json.loads(x)) for x in d.geometry], index=d.event_id.values))
    s = pd.concat(parts) if parts else pd.Series(dtype=object)
    return s[~s.index.duplicated(keep="first")]


def normal_to_date(H, end):
    """Median over finished years of each division's burned ha from 15 Feb to the same calendar day."""
    if H.empty:
        return pd.Series(dtype=float), []
    H = H.copy()
    H["year"] = [d.year for d in H.acq_date]
    # a year counts only once the history run has covered (almost) all of its events
    planned = []
    for name in ("rest_of_mp", "tiger_reserves", "sample"):
        f = os.path.join(MP, f"out/set_{name}.csv")
        if os.path.exists(f):
            S = pd.read_csv(f, usecols=lambda c: c in ("event_id", "acq_date", "kind", "latitude", "longitude"))
            planned.append(live.not_industry(S[S.kind == "fire"] if "kind" in S else S))
    tot = pd.concat(planned).drop_duplicates("event_id").acq_date.str[:4].astype(int).value_counts()
    done = H.year.value_counts()
    years = sorted(y for y in done.index if done[y] >= 0.97 * tot.get(y, np.inf) and y < end.year)   # never the report's own year
    rows = []
    HG = history_geoms() if years else None
    for y in years:
        a, b = dt.date(y, *SEASON[0]), dt.date(y, end.month, end.day)
        h = H[(H.year == y) & (H.acq_date >= a) & (H.acq_date <= b) & (H.status == "scar")]
        hg = h.assign(_g=HG.reindex(h.event_id).values)
        u = hg[hg._g.notna()].groupby("Division")._g.apply(lambda x: union_ha(list(x)))   # counted once, as for this year
        rows.append(u.add(hg[hg._g.isna()].groupby("Division").scar_ha.sum(), fill_value=0).rename(y))
    if not rows:
        return pd.Series(dtype=float), []
    M = pd.concat(rows, axis=1).fillna(0)
    return M.median(axis=1), years


def burn_kind(E, live):
    """FSI thread's control-burn rule (ratapani/fsi/scouting/managed_early_burns.md, part C, live mode):
    before 15 Feb -> 'pre-season burn' (mostly planned burning); 15-28 Feb, daytime only, <= 2 alert points and
    max FRP <= 5 MW -> 'likely planned burn'; everything else 'fire'. Not used after 28 Feb (rule loses precision)."""
    A = pd.read_csv(os.path.join(live, "alerts.csv"), dtype={"acq_time": str})
    t = A.acq_time.str.zfill(4).str[:2].astype(int) + A.acq_time.str.zfill(4).str[2:].astype(int) / 60
    ist = A.sensor.str.startswith("fsi")
    utc = np.where(ist, (t - 5.5) % 24, t)
    A["night"] = (utc < 3) | (utc >= 15)          # MP night passes ~19-21 UTC, day passes ~07-09 UTC
    g = A.groupby("event_id").agg(n=("night", "size"), night=("night", "any"), frp=("frp", "max"))
    g = g.reindex(E.event_id)
    md = np.array([(d.month, d.day) for d in E.acq_date])
    pre = (md[:, 0] < 2) | ((md[:, 0] == 2) & (md[:, 1] < 15)) | (md[:, 0] >= 10)
    late_feb = (md[:, 0] == 2) & (md[:, 1] >= 15)
    small = (~g.night.fillna(True).astype(bool)).values & (g.n.fillna(9) <= 2).values & (g.frp.fillna(99) <= 5).values
    return np.where(pre, "pre-season burn", np.where(late_feb & small, "likely planned burn", "fire"))


def fmt(x):
    return "-" if pd.isna(x) else f"{x:,.0f}"


def main(end=None, live=os.path.join(MP, "live"), out_root=None):
    end = dt.date.fromisoformat(end) if end else dt.date.today()
    start = end - dt.timedelta(days=6)
    s0 = season_start(end)
    out = os.path.join(out_root or os.path.join(live, "reports"), end.isoformat())
    os.makedirs(out, exist_ok=True)

    E = pd.read_csv(os.path.join(live, "events.csv"))
    E["acq_date"] = pd.to_datetime(E.acq_date).dt.date
    E["division"] = E.division.fillna("outside beats")
    G = gpd.read_file(os.path.join(live, "scars.geojson")) if os.path.exists(os.path.join(live, "scars.geojson")) else gpd.GeoDataFrame()
    geom = G.set_index("event_id").geometry if len(G) else pd.Series(dtype=object)
    geom = geom[~geom.index.duplicated(keep="last")]
    E["kind"] = burn_kind(E, live)
    planned = E[E.kind != "fire"]
    E = E[E.kind == "fire"]          # wildfire totals; planned and pre-season burns are counted separately
    pw = planned[(planned.acq_date >= start) & (planned.acq_date <= end)]
    wk = E[(E.acq_date >= start) & (E.acq_date <= end)]
    se = E[(E.acq_date >= s0) & (E.acq_date <= end)] if end >= s0 else E.iloc[:0]

    def summ(df):
        return pd.DataFrame({
            "fires_alerted": df.groupby("division").size(),
            "scars_found": df[df.status == "scar"].groupby("division").size(),
            "still_waiting": df[df.status == "waiting"].groupby("division").size(),
            "burned_ha": area(df)})

    def area(df, by="division"):
        """Burned ha counted once: neighbouring events' outlines overlap, so summing scar_ha roughly doubles it.
        Falls back to the sum for scars with no outline on file."""
        d = df[df.status == "scar"]
        if not len(d):
            return pd.Series(dtype=float)
        if by is None:
            return area(d.assign(_all=1), "_all").sum()
        g = geom.reindex(d.event_id).values
        d = d.assign(_g=g)
        has = d[d._g.notna()]
        u = has.groupby(by)._g.apply(lambda x: union_ha(list(x))) if len(has) else pd.Series(dtype=float)
        return u.add(d[d._g.isna()].groupby(by).scar_ha.sum(), fill_value=0)

    T = summ(wk).add_suffix("_week").join(summ(se)[["fires_alerted", "burned_ha"]].add_suffix("_season"), how="outer")
    norm, years = normal_to_date(history(), end)
    T["normal_season_ha_to_date"] = norm.reindex(T.index)
    T["season_vs_normal"] = T.burned_ha_season / T.normal_season_ha_to_date.replace(0, np.nan)
    T = T.fillna({c: 0 for c in T.columns if c.endswith(("_week", "_season")) and c != "season_vs_normal"})
    T = T.sort_values(["burned_ha_week", "fires_alerted_week"], ascending=False)
    T.index.name = "division"
    T.to_csv(os.path.join(out, "by_division.csv"))

    top = wk[wk.status == "scar"].nlargest(15, "scar_ha")[
        ["event_id", "acq_date", "division", "range", "beat", "scar_ha", "severity", "latitude", "longitude", "post_date"]]
    top.to_csv(os.path.join(out, "top_fires.csv"), index=False)
    pw.to_csv(os.path.join(out, "planned_burns.csv"), index=False)
    gw = G[G.event_id.isin(wk.event_id)] if len(G) else G
    if len(gw):
        gw.to_file(os.path.join(out, "scars_week.geojson"), driver="GeoJSON")

    # map: divisions, earlier season scars grey, this week's red, sized by area (outlines are too small at state scale)
    D = divisions()
    fig, ax = plt.subplots(figsize=(10, 7.5), dpi=120)
    D.boundary.plot(ax=ax, color="#999", lw=0.4)
    old = se[(se.status == "scar") & (se.acq_date < start)]
    for df, col, lab in ((old, "#9a9a9a", "earlier this season"), (wk[wk.status == "scar"], "#d7301f", "this week")):
        if len(df):
            k = 3 if col != "#9a9a9a" else 1.2   # earlier fires smaller and fainter so this week stands out
            ax.scatter(df.longitude, df.latitude, s=4 + np.sqrt(df.scar_ha.fillna(1)) * k, c=col, alpha=0.7 if k == 3 else 0.35,
                       lw=0, label=f"{lab} ({len(df)})", zorder=3 if k == 3 else 2)
    w = wk[wk.status == "waiting"]
    if len(w):
        ax.scatter(w.longitude, w.latitude, s=8, facecolors="none", edgecolors="#2b6cb0", lw=0.6, label=f"waiting for clear photo ({len(w)})")
    for _, r in T.head(8).iterrows():
        if r.burned_ha_week > 0:
            c = D[D.Division == r.name].geometry.representative_point()
            if len(c):
                ax.annotate(r.name.replace("_", " "), (c.iloc[0].x, c.iloc[0].y), fontsize=7)
    ax.set_title(f"Burn scars, MP forest divisions, week {start:%d %b} - {end:%d %b %Y}", fontsize=11)
    ax.set_axis_off()
    ax.legend(loc="lower left", fontsize=8, frameon=False, title="dot size = burned area", title_fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "map.png"))
    plt.close(fig)

    # plain-language text
    n, ns, nw = len(wk), (wk.status == "scar").sum(), (wk.status == "waiting").sum()
    ha_w, ha_s = area(wk, None), area(se, None)
    nrm = norm.sum() if len(norm) else np.nan
    in_season = s0 <= end <= dt.date(end.year, *SEASON[1])
    lines = [f"# Forest fire burn scars, Madhya Pradesh: week {start:%d %b} to {end:%d %b %Y}", ""]
    if not in_season:
        lines += [f"_Outside the fire season (15 Feb to 15 Jun). Season figures are for {s0:%Y}._", ""]
    lines += [
        f"- **{n:,} forest fires** were alerted this week. **{ns:,}** already show a burn scar on satellite photos, "
        f"covering **{ha_w:,.0f} ha**. **{nw:,}** are still waiting for a clear photo (usually 3 to 10 days).",
        f"- Season so far (from 15 Feb): **{ha_s:,.0f} ha** burned"
        + (f", against a normal of about **{nrm:,.0f} ha** by this date (median of {years[0]}-{years[-1]})." if years else
           ". The normal for this date will appear once the 2017-25 history run is finished."),
        *( [f"- Not counted above: **{(pw.kind == 'pre-season burn').sum():,}** burns before the season (Oct to 14 Feb, "
            f"mostly planned burning, {area(pw[pw.kind == 'pre-season burn'], None):,.0f} ha) and "
            f"**{(pw.kind == 'likely planned burn').sum():,}** small daytime 15-28 Feb burns that look planned "
            f"({area(pw[pw.kind == 'likely planned burn'], None):,.0f} ha). "
            "They are listed in planned_burns.csv."] if len(pw) else []),
        "- A fire with no scar is **not** a false alert: small fires and fires under thick canopy often leave no visible scar.",
        "- Areas are from 20-30 m satellite photos: typically about 9% of an outline is not burned and about 20% of nearby burned ground is missed.",
        "", "![map](map.png)", "", "## By division", "",
        "| Division | Fires this week | Scars | Burned ha this week | Burned ha this season | Normal by this date | Season vs normal |",
        "|---|---|---|---|---|---|---|"]
    for d, r in T.iterrows():
        if r.fires_alerted_week == 0 and r.burned_ha_season == 0:
            continue
        ratio = "-" if pd.isna(r.season_vs_normal) else f"{r.season_vs_normal:.1f}x"
        lines.append(f"| {d.replace('_', ' ')} | {r.fires_alerted_week:.0f} | {r.scars_found_week:.0f} | {fmt(r.burned_ha_week)} | "
                     f"{fmt(r.burned_ha_season)} | {fmt(r.normal_season_ha_to_date)} | {ratio} |")
    lines += ["", "## Largest fires this week", "", "| Date | Division | Range | Beat | Burned ha | Location |", "|---|---|---|---|---|---|"]
    for _, r in top.iterrows():
        lines.append(f"| {r.acq_date:%d %b} | {str(r.division).replace('_', ' ')} | {r['range']} | {r.beat} | {r.scar_ha:,.0f} | "
                     f"[{r.latitude:.4f}, {r.longitude:.4f}](https://www.google.com/maps?q={r.latitude},{r.longitude}) |")
    if top.empty:
        lines.append("| | No scars confirmed yet for this week's fires | | | | |")
    md = "\n".join(lines) + "\n"
    open(os.path.join(out, "report.md"), "w").write(md)
    try:
        import markdown
        body = markdown.markdown(md, extensions=["tables"])
    except ImportError:
        body = "<pre>" + md + "</pre>"
    css = ("body{font-family:system-ui,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#222}"
           "table{border-collapse:collapse;font-size:14px}td,th{border:1px solid #ccc;padding:4px 8px;text-align:right}"
           "td:first-child,th:first-child{text-align:left}img{max-width:100%}")
    open(os.path.join(out, "report.html"), "w").write(f"<!doctype html><meta charset=utf-8><title>MP burn scars {end}</title><style>{css}</style>{body}")
    print("report", out, "| fires", n, "scars", ns, "ha", round(ha_w), "| season ha", round(ha_s), "| normal years", years)
    return out


if __name__ == "__main__":
    main(*sys.argv[1:4])
