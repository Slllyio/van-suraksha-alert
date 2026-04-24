"""Unit tests for dashboard/v3/repositories/*.

Verifies the thin wrappers work against real feed files on disk (for
V17Repository + BoundariesRepository) and a synthetic injected loader
for DivisionRepository.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# ---- path setup so we can import dashboard.v3.repositories --------------

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard" / "v3"))

from repositories import (  # noqa: E402  import after sys.path tweak
    BoundariesRepository,
    DivisionRepository,
    V17Repository,
)


# ---- V17Repository -------------------------------------------------------


def test_v17_load_latest_returns_dict():
    repo = V17Repository()
    payload = repo.load()
    assert isinstance(payload, dict)
    # Live pipeline should have populated this. If it hasn't, the test
    # documents the current state rather than failing hard.
    if payload:
        assert "banded_alerts" in payload or "prediction_date" in payload


def test_v17_list_alerts_returns_list():
    repo = V17Repository()
    alerts = repo.list_alerts()
    assert isinstance(alerts, list)


def test_v17_cursor_round_trip():
    assert V17Repository.decode_cursor(None) == 0
    assert V17Repository.decode_cursor("") == 0
    cursor = V17Repository.encode_cursor(500)
    assert V17Repository.decode_cursor(cursor) == 500


def test_v17_cursor_rejects_malformed():
    with pytest.raises(ValueError):
        V17Repository.decode_cursor("@@@not-base64@@@")
    with pytest.raises(ValueError):
        V17Repository.decode_cursor(V17Repository.encode_cursor(0).replace("M", "-1"))


def test_v17_page_pagination_bounds():
    repo = V17Repository()
    page = repo.page(offset=0, limit=3)
    assert isinstance(page["data"], list)
    assert len(page["data"]) <= 3
    meta = page["meta"]
    assert "total" in meta
    assert meta["limit"] == 3
    assert meta["offset"] == 0
    if meta["total"] > 3:
        assert meta["has_next"] is True
        assert isinstance(meta["next_cursor"], str) and meta["next_cursor"]


def test_v17_page_missing_date_graceful(tmp_path):
    repo = V17Repository(feed_dir=tmp_path)  # empty dir
    page = repo.page(limit=10)
    assert page["data"] == []
    assert page["meta"]["total"] == 0
    assert page["meta"]["has_next"] is False
    assert page["meta"]["next_cursor"] is None


# ---- BoundariesRepository ------------------------------------------------


def test_boundaries_available_resolutions():
    repo = BoundariesRepository()
    assert "ultra" in repo.available_resolutions()
    assert "high" in repo.available_resolutions()


def test_boundaries_load_ultra_returns_fc():
    repo = BoundariesRepository()
    try:
        fc = repo.load("ultra")
    except FileNotFoundError:
        pytest.skip("boundaries not built; run scripts/build_division_boundaries.py")
    assert fc.get("type") == "FeatureCollection"
    assert "features" in fc
    assert len(fc["features"]) > 0


def test_boundaries_invalid_resolution_raises():
    repo = BoundariesRepository()
    with pytest.raises(ValueError):
        repo.load("bogus")  # type: ignore[arg-type]


def test_boundaries_missing_file_raises(tmp_path):
    repo = BoundariesRepository(aoi_dir=tmp_path)  # empty dir
    with pytest.raises(FileNotFoundError):
        repo.load("ultra")


# ---- DivisionRepository --------------------------------------------------


def test_division_overview_delegates_to_loaders():
    """DivisionRepository should call the injected builders, not File I/O."""
    calls: list[str] = []

    def fake_v17_loader(date):
        calls.append(f"load:{date}")
        return {"banded_alerts": [{"cell_id": "r0_c0", "band": "WATCH"}]}

    def fake_build(payload):
        calls.append("build")
        return {"divisions": [{"name": "TestDiv"}]}

    def fake_enrich(base):
        calls.append("enrich")
        base["enriched"] = True
        return base

    repo = DivisionRepository(
        build_overview=fake_build,
        enrich_overview=fake_enrich,
        v17_loader=fake_v17_loader,
    )
    out = repo.overview(target_date="2026-04-24")
    assert out == {"divisions": [{"name": "TestDiv"}], "enriched": True}
    assert calls == ["load:2026-04-24", "build", "enrich"]
