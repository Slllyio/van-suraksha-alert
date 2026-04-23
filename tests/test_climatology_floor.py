"""Tests for apply_climatology_watch_floor in scripts.build_operational_alerts.

Covers:
1. Null-input safety — missing CLIMATOLOGY_PARQUET returns (alerts, 0) + warning
2. No-overwrite invariant — beats with any alert are not promoted again
3. Threshold: percentile_in_week < 0.90 — NOT promoted
4. Threshold: total_fires < 5 — NOT promoted
5. Promotion fields — correct trust_level, band, climatology_* metadata
6. Highest-rank cell selected when multiple cells exist in a target beat
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.build_operational_alerts as boa


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clim_row(
    division: str,
    beat: str,
    week_of_year: int,
    total_fires: int,
    n_years_with_fire: int,
    percentile_in_week: float,
    mean_fires_per_year: float = 2.0,
    max_frp_seen: float = 45.0,
) -> dict[str, Any]:
    return {
        "Division": division,
        "Range": "TestRange",
        "Beat": beat,
        "week_of_year": week_of_year,
        "total_fires": total_fires,
        "n_years_with_fire": n_years_with_fire,
        "mean_fires_per_year": mean_fires_per_year,
        "max_frp_seen": max_frp_seen,
        "percentile_in_week": percentile_in_week,
    }


def _make_cell(
    cell_id: str,
    rank: float,
    ignition_risk: float = 0.5,
    hawkes_n: int = 0,
) -> dict[str, Any]:
    return {
        "cell_id": cell_id,
        "ignition_risk": ignition_risk,
        "rank": rank,
        "hawkes_n_recent_10km_7d": hawkes_n,
    }


def _make_cell_meta(
    cell_id: str,
    division: str,
    beat: str,
    lat: float = 24.0,
    lon: float = 77.0,
) -> dict[str, Any]:
    return {
        cell_id: {
            "division": division,
            "range": "TestRange",
            "beat": beat,
            "lat": lat,
            "lon": lon,
        }
    }


def _week_of_year(d: date) -> int:
    return int(pd.Timestamp(d).isocalendar().week)


# ---------------------------------------------------------------------------
# 1. Null-input safety — CLIMATOLOGY_PARQUET missing
# ---------------------------------------------------------------------------

class TestNullInputSafety:
    def test_returns_original_alerts_and_zero_when_parquet_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the climatology parquet does not exist the function must not raise
        and must return the original alert list unchanged with n_promoted=0."""
        nonexistent = tmp_path / "no_such_file.parquet"
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", nonexistent)

        original_alerts: list[dict[str, Any]] = [
            {"cell_id": "C001", "band": "CRITICAL", "division": "Singrauli",
             "beat": "Suidih", "ignition_risk": 0.9, "rank": 0.99,
             "budget_tier": "CRITICAL"}
        ]

        result_alerts, n_promoted = boa.apply_climatology_watch_floor(
            original_alerts, [], {}, date(2026, 4, 10)
        )

        assert n_promoted == 0
        assert result_alerts is original_alerts  # same object, no copy needed
        assert len(result_alerts) == 1

    def test_emits_warning_when_parquet_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        nonexistent = tmp_path / "no_such_file.parquet"
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", nonexistent)

        import logging
        with caplog.at_level(logging.WARNING):
            boa.apply_climatology_watch_floor([], [], {}, date(2026, 4, 10))

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Climatology parquet missing" in m or "climatology" in m.lower()
                   for m in warning_messages), (
            f"Expected a WARNING about missing climatology parquet; got: {warning_messages}"
        )


# ---------------------------------------------------------------------------
# 2. No-overwrite invariant — beats already covered must NOT be promoted
# ---------------------------------------------------------------------------

class TestNoOverwriteInvariant:
    @pytest.mark.parametrize("existing_band", ["CRITICAL", "ALERT", "WATCH"])
    def test_beat_with_existing_alert_not_promoted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        existing_band: str,
    ) -> None:
        """Beats that already carry any alert band must not receive a second promotion."""
        target = date(2026, 4, 10)
        woy = _week_of_year(target)

        # Climatology says this beat is hot (top 95%)
        clim_df = pd.DataFrame([
            _make_clim_row("Rewa", "Kakredi_West", woy,
                           total_fires=20, n_years_with_fire=4,
                           percentile_in_week=0.95,
                           mean_fires_per_year=4.0)
        ])
        clim_path = tmp_path / "beat_fire_climatology.parquet"
        clim_df.to_parquet(clim_path, index=False)
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", clim_path)

        # But the beat already has an alert
        existing_alert: dict[str, Any] = {
            "cell_id": "C_EXISTING",
            "band": existing_band,
            "budget_tier": existing_band,
            "division": "Rewa",
            "range": "TestRange",
            "beat": "Kakredi_West",
            "ignition_risk": 0.7,
            "rank": 0.95,
        }
        all_cells = [_make_cell("C_CANDIDATE", rank=0.80)]
        cell_meta = _make_cell_meta("C_CANDIDATE", "Rewa", "Kakredi_West")

        alerts_before = [existing_alert]
        result_alerts, n_promoted = boa.apply_climatology_watch_floor(
            alerts_before, all_cells, cell_meta, target
        )

        assert n_promoted == 0, (
            f"Beat with existing {existing_band} alert should not be promoted; "
            f"got n_promoted={n_promoted}"
        )
        assert len(result_alerts) == 1


# ---------------------------------------------------------------------------
# 3. Threshold: percentile_in_week < 0.90 — NOT promoted
# ---------------------------------------------------------------------------

class TestPercentileThreshold:
    def test_below_threshold_not_promoted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = date(2026, 4, 10)
        woy = _week_of_year(target)

        clim_df = pd.DataFrame([
            _make_clim_row("Damoh", "Ghoghra", woy,
                           total_fires=10, n_years_with_fire=4,
                           percentile_in_week=0.85,  # below 0.90 threshold
                           mean_fires_per_year=2.0)
        ])
        clim_path = tmp_path / "beat_fire_climatology.parquet"
        clim_df.to_parquet(clim_path, index=False)
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", clim_path)

        all_cells = [_make_cell("C001", rank=0.60)]
        cell_meta = _make_cell_meta("C001", "Damoh", "Ghoghra")

        result_alerts, n_promoted = boa.apply_climatology_watch_floor(
            [], all_cells, cell_meta, target
        )

        assert n_promoted == 0
        assert len(result_alerts) == 0

    def test_at_threshold_boundary_is_promoted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """percentile_in_week == 0.90 should pass (>= threshold)."""
        target = date(2026, 4, 10)
        woy = _week_of_year(target)

        clim_df = pd.DataFrame([
            _make_clim_row("Damoh", "Ghoghra", woy,
                           total_fires=10, n_years_with_fire=4,
                           percentile_in_week=0.90,  # exactly at boundary
                           mean_fires_per_year=2.0)
        ])
        clim_path = tmp_path / "beat_fire_climatology.parquet"
        clim_df.to_parquet(clim_path, index=False)
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", clim_path)

        all_cells = [_make_cell("C001", rank=0.60)]
        cell_meta = _make_cell_meta("C001", "Damoh", "Ghoghra")

        result_alerts, n_promoted = boa.apply_climatology_watch_floor(
            [], all_cells, cell_meta, target
        )

        assert n_promoted == 1


# ---------------------------------------------------------------------------
# 4. Threshold: total_fires < 5 — NOT promoted
# ---------------------------------------------------------------------------

class TestTotalFiresThreshold:
    def test_below_min_fires_not_promoted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = date(2026, 4, 10)
        woy = _week_of_year(target)

        clim_df = pd.DataFrame([
            _make_clim_row("Singrauli", "Suidih", woy,
                           total_fires=4,  # below minimum of 5
                           n_years_with_fire=3,
                           percentile_in_week=0.95,
                           mean_fires_per_year=0.8)
        ])
        clim_path = tmp_path / "beat_fire_climatology.parquet"
        clim_df.to_parquet(clim_path, index=False)
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", clim_path)

        all_cells = [_make_cell("C001", rank=0.55)]
        cell_meta = _make_cell_meta("C001", "Singrauli", "Suidih")

        result_alerts, n_promoted = boa.apply_climatology_watch_floor(
            [], all_cells, cell_meta, target
        )

        assert n_promoted == 0

    def test_at_min_fires_boundary_is_promoted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """total_fires == 5 should pass (>= threshold)."""
        target = date(2026, 4, 10)
        woy = _week_of_year(target)

        clim_df = pd.DataFrame([
            _make_clim_row("Singrauli", "Suidih", woy,
                           total_fires=5,  # exactly at boundary
                           n_years_with_fire=3,
                           percentile_in_week=0.95,
                           mean_fires_per_year=1.0)
        ])
        clim_path = tmp_path / "beat_fire_climatology.parquet"
        clim_df.to_parquet(clim_path, index=False)
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", clim_path)

        all_cells = [_make_cell("C001", rank=0.55)]
        cell_meta = _make_cell_meta("C001", "Singrauli", "Suidih")

        result_alerts, n_promoted = boa.apply_climatology_watch_floor(
            [], all_cells, cell_meta, target
        )

        assert n_promoted == 1


# ---------------------------------------------------------------------------
# 5. Promotion produces correct fields and trust tier
# ---------------------------------------------------------------------------

class TestPromotionFields:
    def test_promoted_alert_has_correct_metadata(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A successfully promoted alert must carry the full set of required fields."""
        target = date(2026, 4, 10)
        woy = _week_of_year(target)

        n_years = 4
        mean_fires = 6.0
        pct = 0.93

        clim_df = pd.DataFrame([
            _make_clim_row(
                "Rewa", "Kakredi_West", woy,
                total_fires=30, n_years_with_fire=n_years,
                percentile_in_week=pct,
                mean_fires_per_year=mean_fires,
            )
        ])
        clim_path = tmp_path / "beat_fire_climatology.parquet"
        clim_df.to_parquet(clim_path, index=False)
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", clim_path)

        all_cells = [_make_cell("C_PROMO", rank=0.72, ignition_risk=0.55)]
        cell_meta = _make_cell_meta("C_PROMO", "Rewa", "Kakredi_West",
                                    lat=24.5, lon=76.8)

        result_alerts, n_promoted = boa.apply_climatology_watch_floor(
            [], all_cells, cell_meta, target
        )

        assert n_promoted == 1
        assert len(result_alerts) == 1

        promoted = result_alerts[0]

        # Trust tier and band
        assert promoted["trust_level"] == "CLIMATOLOGY_FLOOR", (
            f"Expected trust_level='CLIMATOLOGY_FLOOR', got {promoted['trust_level']!r}"
        )
        assert promoted["climatology_floor"] is True
        assert promoted["band"] == "WATCH"
        assert promoted["budget_tier"] == "WATCH"

        # Climatology metadata fields
        assert promoted["climatology_n_years_with_fire"] == n_years
        assert abs(promoted["climatology_mean_fires_per_year"] - mean_fires) < 1e-6
        assert abs(promoted["climatology_percentile"] - pct) < 1e-6

        # Division / beat correctly propagated
        assert promoted["division"] == "Rewa"
        assert promoted["beat"] == "Kakredi_West"

    def test_promoted_alert_is_not_marked_floor_promoted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """climatology_floor alerts are NOT the same as division-coverage-floor
        alerts — floor_promoted must remain False."""
        target = date(2026, 4, 10)
        woy = _week_of_year(target)

        clim_df = pd.DataFrame([
            _make_clim_row("Rewa", "Kakredi_West", woy,
                           total_fires=12, n_years_with_fire=3,
                           percentile_in_week=0.92, mean_fires_per_year=2.4)
        ])
        clim_path = tmp_path / "beat_fire_climatology.parquet"
        clim_df.to_parquet(clim_path, index=False)
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", clim_path)

        all_cells = [_make_cell("C001", rank=0.65)]
        cell_meta = _make_cell_meta("C001", "Rewa", "Kakredi_West")

        result_alerts, _ = boa.apply_climatology_watch_floor(
            [], all_cells, cell_meta, target
        )

        assert result_alerts[0].get("floor_promoted") is False


# ---------------------------------------------------------------------------
# 6. Highest-rank cell selected when multiple candidates exist in a beat
# ---------------------------------------------------------------------------

class TestHighestRankCellSelection:
    def test_highest_rank_cell_is_chosen(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When multiple cells map to the same target beat, the one with the
        highest `rank` score must be the one promoted."""
        target = date(2026, 4, 10)
        woy = _week_of_year(target)

        clim_df = pd.DataFrame([
            _make_clim_row("Mandla", "Mohgaon", woy,
                           total_fires=18, n_years_with_fire=5,
                           percentile_in_week=0.96, mean_fires_per_year=3.6)
        ])
        clim_path = tmp_path / "beat_fire_climatology.parquet"
        clim_df.to_parquet(clim_path, index=False)
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", clim_path)

        # Three candidate cells in the same beat with different ranks
        low_rank_cell = _make_cell("C_LOW", rank=0.50, ignition_risk=0.40)
        mid_rank_cell = _make_cell("C_MID", rank=0.70, ignition_risk=0.55)
        high_rank_cell = _make_cell("C_HIGH", rank=0.88, ignition_risk=0.75)

        all_cells = [low_rank_cell, mid_rank_cell, high_rank_cell]

        # All three cells map to the same division/beat
        cell_meta: dict[str, dict[str, Any]] = {}
        for cid in ("C_LOW", "C_MID", "C_HIGH"):
            cell_meta[cid] = {
                "division": "Mandla",
                "range": "TestRange",
                "beat": "Mohgaon",
                "lat": 22.5,
                "lon": 78.0,
            }

        result_alerts, n_promoted = boa.apply_climatology_watch_floor(
            [], all_cells, cell_meta, target
        )

        assert n_promoted == 1, f"Expected 1 promotion, got {n_promoted}"
        assert len(result_alerts) == 1
        promoted = result_alerts[0]
        assert promoted["cell_id"] == "C_HIGH", (
            f"Expected the highest-rank cell 'C_HIGH' to be promoted, "
            f"got '{promoted['cell_id']}'"
        )

    def test_only_one_cell_promoted_per_beat(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even with multiple qualifying climatology rows for the same beat, only
        the first promotion sticks — subsequent candidates are skipped because
        the beat is then in covered_beats."""
        target = date(2026, 4, 10)
        woy = _week_of_year(target)

        # Single beat in climatology
        clim_df = pd.DataFrame([
            _make_clim_row("Mandla", "Mohgaon", woy,
                           total_fires=15, n_years_with_fire=4,
                           percentile_in_week=0.94, mean_fires_per_year=3.0)
        ])
        clim_path = tmp_path / "beat_fire_climatology.parquet"
        clim_df.to_parquet(clim_path, index=False)
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", clim_path)

        all_cells = [
            _make_cell("C_A", rank=0.80),
            _make_cell("C_B", rank=0.60),
        ]
        cell_meta: dict[str, dict[str, Any]] = {
            "C_A": {"division": "Mandla", "range": "R", "beat": "Mohgaon",
                    "lat": 22.5, "lon": 78.0},
            "C_B": {"division": "Mandla", "range": "R", "beat": "Mohgaon",
                    "lat": 22.6, "lon": 78.1},
        }

        result_alerts, n_promoted = boa.apply_climatology_watch_floor(
            [], all_cells, cell_meta, target
        )

        assert n_promoted == 1
        assert len(result_alerts) == 1


# ---------------------------------------------------------------------------
# Integration: multiple beats, mixed eligibility
# ---------------------------------------------------------------------------

class TestIntegrationMixedBeats:
    def test_multiple_beats_correct_promotions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With 5 beats in the climatology (various eligibility combinations),
        only the fully-qualifying ones without existing alerts are promoted."""
        target = date(2026, 4, 10)
        woy = _week_of_year(target)

        clim_rows = [
            # Row 0: eligible — should be promoted
            _make_clim_row("Div_A", "Beat_Eligible", woy,
                           total_fires=12, n_years_with_fire=4,
                           percentile_in_week=0.92, mean_fires_per_year=2.4),
            # Row 1: already covered — should NOT be promoted
            _make_clim_row("Div_B", "Beat_Covered", woy,
                           total_fires=15, n_years_with_fire=5,
                           percentile_in_week=0.95, mean_fires_per_year=3.0),
            # Row 2: percentile too low — should NOT be promoted
            _make_clim_row("Div_C", "Beat_LowPct", woy,
                           total_fires=10, n_years_with_fire=4,
                           percentile_in_week=0.80, mean_fires_per_year=2.0),
            # Row 3: fires too low — should NOT be promoted
            _make_clim_row("Div_D", "Beat_LowFires", woy,
                           total_fires=3, n_years_with_fire=2,
                           percentile_in_week=0.93, mean_fires_per_year=0.6),
            # Row 4: eligible but different week — should NOT be promoted
            _make_clim_row("Div_E", "Beat_WrongWeek", woy + 1,
                           total_fires=12, n_years_with_fire=4,
                           percentile_in_week=0.92, mean_fires_per_year=2.4),
        ]
        clim_df = pd.DataFrame(clim_rows)
        clim_path = tmp_path / "beat_fire_climatology.parquet"
        clim_df.to_parquet(clim_path, index=False)
        monkeypatch.setattr(boa, "CLIMATOLOGY_PARQUET", clim_path)

        # One cell per beat
        all_cells = [
            _make_cell("C_ELIGIBLE", rank=0.70),
            _make_cell("C_COVERED", rank=0.75),
            _make_cell("C_LOWPCT", rank=0.65),
            _make_cell("C_LOWFIRE", rank=0.60),
            _make_cell("C_WRONGWEEK", rank=0.68),
        ]
        cell_meta: dict[str, dict[str, Any]] = {
            "C_ELIGIBLE": {"division": "Div_A", "range": "R", "beat": "Beat_Eligible",
                           "lat": 23.0, "lon": 77.0},
            "C_COVERED": {"division": "Div_B", "range": "R", "beat": "Beat_Covered",
                          "lat": 23.1, "lon": 77.1},
            "C_LOWPCT": {"division": "Div_C", "range": "R", "beat": "Beat_LowPct",
                         "lat": 23.2, "lon": 77.2},
            "C_LOWFIRE": {"division": "Div_D", "range": "R", "beat": "Beat_LowFires",
                          "lat": 23.3, "lon": 77.3},
            "C_WRONGWEEK": {"division": "Div_E", "range": "R", "beat": "Beat_WrongWeek",
                            "lat": 23.4, "lon": 77.4},
        }

        # Beat_Covered already has an ALERT — must not be touched
        existing_alert: dict[str, Any] = {
            "cell_id": "C_COVERED",
            "band": "ALERT",
            "budget_tier": "ALERT",
            "division": "Div_B",
            "range": "R",
            "beat": "Beat_Covered",
            "ignition_risk": 0.65,
            "rank": 0.75,
        }

        result_alerts, n_promoted = boa.apply_climatology_watch_floor(
            [existing_alert], all_cells, cell_meta, target
        )

        assert n_promoted == 1, f"Expected exactly 1 promotion, got {n_promoted}"
        clim_alerts = [a for a in result_alerts if a.get("climatology_floor")]
        assert len(clim_alerts) == 1
        assert clim_alerts[0]["division"] == "Div_A"
        assert clim_alerts[0]["beat"] == "Beat_Eligible"
        assert clim_alerts[0]["band"] == "WATCH"
        assert clim_alerts[0]["trust_level"] == "CLIMATOLOGY_FLOOR"
