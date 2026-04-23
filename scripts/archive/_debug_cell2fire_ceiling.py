"""Isolate the Cell2Fire 150-220 ha ceiling.

Hypotheses:
  (A) Landscape burnability — non-burnable cells block propagation.
  (B) Fire-period coarseness — 60-min steps drop sub-period progress.
  (C) Elliptical geometry — high-wind squashes the ellipse.
  (D) Fuel-model mix — crop cells cap at GR1's slow asymptotic ROS.

Experiments (all with scenario=1 DRY, temp=33C, rh=16%, period=60 min):
  E0  baseline                     default fuels.asc (as exported), ws=7
  E1  all-F102 override            overwrite fuels.asc with all 102 (GR2), ws=7
  E2  all-F102 + high wind         all 102, ws=20 (check elliptical squash)

If E1 >> E0  -> bottleneck is landscape burnability (hypothesis A wins)
If E1 ~= E0  -> bottleneck is Cell2Fire internals; check E2/E1 ratio for squash
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import src.utils.proj_fix  # noqa: F401

from src.analysis.cell2fire.engine import (  # noqa: E402
    Cell2FireConfig,
    _make_workdir,
)
from src.analysis.cell2fire.grid_exporter import export_cell2fire_inputs  # noqa: E402
from src.analysis.cell2fire.output_parser import (  # noqa: E402
    burn_area_ha,
    burn_mask_at_horizon,
    parse_grids_directory,
)
from src.analysis.cell2fire.runner import run_cell2fire  # noqa: E402
from src.analysis.cell2fire.weather_writer import write_weather_csv  # noqa: E402


FIRE = {"fire_lat": 24.19155, "fire_lon": 76.97570}


def _overwrite_fuels_asc(path: Path, code: int) -> None:
    """Rewrite fuels.asc in place, keeping header, setting all cells = code."""
    text = path.read_text().splitlines()
    header, body_start = [], 0
    for i, line in enumerate(text):
        if line and line.lstrip()[0].isdigit() and " " in line.strip():
            # first data row
            body_start = i
            break
        header.append(line)
    data_rows = text[body_start:]
    # infer shape from first data row
    ncols = len(data_rows[0].split())
    nrows = len(data_rows)
    new_row = " ".join([str(code)] * ncols)
    new_body = "\n".join([new_row] * nrows)
    path.write_text("\n".join(header) + "\n" + new_body + "\n")


def _run_experiment(
    label: str,
    *,
    fuels_override_code: int | None,
    ws: float,
    horizon_hours: int = 24,
) -> dict:
    cfg = Cell2FireConfig(
        keep_workdir=False,
        scenario_override=1,  # DRY — not dependent on weather auto-select
    )
    workdir = _make_workdir(cfg.workdir_root)
    instance_dir = workdir / "instance"
    output_dir = workdir / "output"
    try:
        export = export_cell2fire_inputs(
            fire_lat=FIRE["fire_lat"],
            fire_lon=FIRE["fire_lon"],
            output_dir=instance_dir,
            grid_size_px=cfg.grid_size_px,
            cell_size_m=cfg.cell_size_m,
        )

        if fuels_override_code is not None:
            _overwrite_fuels_asc(export.fuels_asc, fuels_override_code)

        write_weather_csv(
            weather={
                "wind_kmh": ws, "wind_dir_deg": 259.0,
                "temp_c": 33.0, "rh_pct": 16.0,
            },
            output_path=instance_dir / "Weather.csv",
            horizon_hours=horizon_hours,
        )

        run_result = run_cell2fire(
            instance_dir=instance_dir,
            output_dir=output_dir,
            timeout_s=cfg.timeout_s,
            horizon_hours=horizon_hours,
            scenario=1,
        )
        if not run_result.success:
            return {"label": label, "error": run_result.reason}

        parsed = parse_grids_directory(output_dir=output_dir, sim_index=1)
        mask_h = burn_mask_at_horizon(parsed, horizon_hours * 60)
        area_h = burn_area_ha(mask_h, 30.0)

        msgs = output_dir / "Messages" / "MessagesFile1.csv"
        max_ros = mean_ros = 0.0
        n_msg = 0
        if msgs.exists():
            lines = msgs.read_text(encoding="ascii").splitlines()
            ros_vals = [float(ln.split(",")[3]) for ln in lines if ln]
            if ros_vals:
                max_ros = max(ros_vals)
                mean_ros = sum(ros_vals) / len(ros_vals)
                n_msg = len(ros_vals)

        return {
            "label": label,
            "horizon_hours": horizon_hours,
            "area_24h_ha": round(area_h, 2),
            "burned_cells": int(mask_h.sum()),
            "max_ros_m_min": round(max_ros, 3),
            "mean_ros_m_min": round(mean_ros, 3),
            "n_messages": n_msg,
            "burnable_fraction": round(export.burnable_fraction, 3),
            "ws": ws,
            "fuels_override": fuels_override_code,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    experiments = [
        ("E0 baseline (default fuels, scen=1, ws=7, 24h)",
         {"fuels_override_code": None, "ws": 7.0, "horizon_hours": 24}),
        ("E1 all-F102 grass (scen=1, ws=7, 24h)",
         {"fuels_override_code": 102, "ws": 7.0, "horizon_hours": 24}),
        ("E2 all-F102 high wind (scen=1, ws=20, 24h)",
         {"fuels_override_code": 102, "ws": 20.0, "horizon_hours": 24}),
        ("E3 all-F102 long horizon (scen=1, ws=20, 72h)",
         {"fuels_override_code": 102, "ws": 20.0, "horizon_hours": 72}),
    ]

    print("=" * 78)
    print("Cell2Fire ceiling diagnostic — Guna 2018-04-19 centre")
    print("=" * 78)

    results = []
    for label, kwargs in experiments:
        print(f"\n[ {label} ]")
        r = _run_experiment(label, **kwargs)
        results.append(r)
        if "error" in r:
            print(f"  ERROR: {r['error']}")
            continue
        print(f"  burnable_fraction = {r['burnable_fraction']}")
        print(f"  area_24h          = {r['area_24h_ha']} ha")
        print(f"  burned_cells      = {r['burned_cells']}")
        print(f"  max_ros           = {r['max_ros_m_min']} m/min")
        print(f"  mean_ros          = {r['mean_ros_m_min']} m/min")
        print(f"  n_messages        = {r['n_messages']}")

    out = ROOT / "data_lake" / "outputs_sample" / "c2f_ceiling_diag.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out}")

    # Verdict
    if len(results) >= 2 and "area_24h_ha" in results[0] and "area_24h_ha" in results[1]:
        e0 = results[0]["area_24h_ha"]
        e1 = results[1]["area_24h_ha"]
        print()
        print("=" * 78)
        print("VERDICT")
        print("=" * 78)
        if e1 > 2 * e0:
            print(f"  E1/E0 = {e1/max(e0,0.01):.2f}x -> LANDSCAPE bottleneck (hypothesis A)")
        elif 0.5 < e1 / max(e0, 0.01) < 2:
            print(f"  E1/E0 = {e1/max(e0,0.01):.2f}x -> Cell2Fire INTERNALS bottleneck")
            if len(results) >= 3 and "area_24h_ha" in results[2]:
                print(f"  E2 ws=20: {results[2]['area_24h_ha']} ha "
                      f"(ratio {results[2]['area_24h_ha']/max(e1,0.01):.2f}x vs E1)")
        else:
            print(f"  E1/E0 = {e1/max(e0,0.01):.2f}x -> unexpected, inspect manually")

    return 0


if __name__ == "__main__":
    sys.exit(main())
