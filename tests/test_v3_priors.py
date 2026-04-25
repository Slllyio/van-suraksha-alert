"""Tests for the hardened /api/v2/historical-burn-{priors,density} endpoints.

Spins up the v3 backend on an ephemeral port in a background thread and
hits real HTTP so the cache, ETag/304 short-circuit, error scrubbing,
and validation are all exercised end-to-end.

Coverage:
  - filter at min_seasons=3 (default, slim file)
  - filter at min_seasons=5 (in-memory filter applied)
  - 400 on invalid min_seasons (4 variants: non-int, out-of-range,
    negative, repeated query param)
  - 404 with no path/exception leakage when files are missing
  - ETag → 304 short-circuit (priors + density)
  - cache hit skips json.loads on second request
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

# Path setup so we can import dashboard/v3/serve.py
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard" / "v3"))


# ---------- fixtures ---------------------------------------------------


@pytest.fixture
def feed_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pre-populate a synthetic outputs/dashboard_feed/ matching the
    real schema produced by build_historical_burn_priors.py, then point
    serve.ROOT at the temp parent so the handler reads from here."""
    feed = tmp_path / "outputs" / "dashboard_feed"
    feed.mkdir(parents=True)

    # Records simulating what the real builder produces. Mix of
    # n_seasons_burned values so the filter logic has something to do.
    full_records = [
        {"cell_id": "r0010_c0010", "lat": 21.26, "lon": 74.24,
         "total_fires_5y": 50, "n_seasons_burned": 5,
         "seasons_burned": [2021, 2022, 2023, 2024, 2025]},
        {"cell_id": "r0020_c0020", "lat": 21.44, "lon": 74.43,
         "total_fires_5y": 30, "n_seasons_burned": 4,
         "seasons_burned": [2021, 2022, 2023, 2025]},
        {"cell_id": "r0030_c0030", "lat": 21.62, "lon": 74.63,
         "total_fires_5y": 15, "n_seasons_burned": 3,
         "seasons_burned": [2023, 2024, 2025]},
        {"cell_id": "r0040_c0040", "lat": 21.80, "lon": 74.83,
         "total_fires_5y": 5, "n_seasons_burned": 2,
         "seasons_burned": [2024, 2025]},
        {"cell_id": "r0050_c0050", "lat": 21.99, "lon": 75.03,
         "total_fires_5y": 1, "n_seasons_burned": 1,
         "seasons_burned": [2025]},
    ]
    full_payload = {
        "metadata": {
            "seasons": [2021, 2022, 2023, 2024, 2025],
            "fire_months": [2, 3, 4, 5],
            "n_cells_total": 5,
            "n_cells_3plus_seasons": 3,
            "n_cells_5_seasons": 1,
            # The whitelist drop must remove this — proves the
            # tampered-metadata defense works.
            "evil_extra_key": "should_not_propagate",
        },
        "records": full_records,
    }
    (feed / "historical_burn_priors.json").write_text(
        json.dumps(full_payload), encoding="utf-8",
    )

    # Slim file = only n_seasons_burned >= 3
    slim_payload = {
        "metadata": {**full_payload["metadata"], "filter": "n_seasons_burned >= 3"},
        "records": [r for r in full_records if r["n_seasons_burned"] >= 3],
    }
    (feed / "historical_burn_priors_3plus.json").write_text(
        json.dumps(slim_payload), encoding="utf-8",
    )

    # Density (lat, lon, weight)
    density_payload = {
        "metadata": {"seasons": [2021, 2022, 2023, 2024, 2025], "filter": "total_fires_5y >= 2"},
        "points": [
            {"lat": r["lat"], "lon": r["lon"], "w": r["total_fires_5y"]}
            for r in full_records if r["total_fires_5y"] >= 2
        ],
    }
    (feed / "historical_burn_density.json").write_text(
        json.dumps(density_payload), encoding="utf-8",
    )

    # Repoint serve.ROOT (and clear the module-level cache between tests)
    import serve  # noqa: E402

    monkeypatch.setattr(serve, "ROOT", tmp_path)
    serve._JSON_CACHE.clear()
    return feed


@pytest.fixture
def server(feed_dir: Path):
    """Boot the real v3 handler on an ephemeral port; tear down after."""
    import serve  # noqa: E402

    # Pick a free port the OS assigns
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    httpd = HTTPServer(("127.0.0.1", port), serve.PortalHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    # Brief readiness wait — Windows socket bind is fast but not instant
    time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(url: str, headers: dict[str, str] | None = None):
    """Tiny helper: returns (status, body_str, response_headers_dict)."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


# ---------- tests ------------------------------------------------------


def test_priors_default_min_seasons_3_returns_slim_records(server):
    status, body, hdrs = _get(f"{server}/api/v2/historical-burn-priors")
    assert status == 200
    payload = json.loads(body)
    # Only n_seasons_burned >= 3 (slim file)
    assert all(r["n_seasons_burned"] >= 3 for r in payload["data"]["records"])
    assert payload["meta"]["served_min_seasons"] == 3
    assert payload["meta"]["served_records"] == 3
    assert payload["meta"]["source_file"] == "historical_burn_priors_3plus.json"
    # Whitelist defense — tampered key must not propagate
    assert "evil_extra_key" not in payload["meta"]
    # Hardening headers
    assert hdrs.get("ETag")
    assert "max-age" in hdrs.get("Cache-Control", "")
    assert hdrs.get("X-Content-Type-Options") == "nosniff"


def test_priors_min_seasons_5_filters_in_memory(server):
    status, body, _ = _get(f"{server}/api/v2/historical-burn-priors?min_seasons=5")
    assert status == 200
    payload = json.loads(body)
    # Only the n_seasons_burned == 5 record survives
    assert len(payload["data"]["records"]) == 1
    assert payload["data"]["records"][0]["cell_id"] == "r0010_c0010"
    assert payload["meta"]["served_min_seasons"] == 5


@pytest.mark.parametrize("qs,reason", [
    ("?min_seasons=foo", "non-integer"),
    ("?min_seasons=99", "above range"),
    ("?min_seasons=0",  "below range"),
    ("?min_seasons=-3", "negative"),
    ("?min_seasons=1&min_seasons=2", "repeated param"),
])
def test_priors_invalid_min_seasons_returns_400(server, qs, reason):
    status, body, _ = _get(f"{server}/api/v2/historical-burn-priors{qs}")
    assert status == 400, f"expected 400 for {reason} input"
    err = json.loads(body)["error"]
    assert err["code"] == "invalid_min_seasons"
    # No leaked path/repr info in user-facing message
    assert "outputs" not in err["message"]
    assert "Traceback" not in err["message"]


def test_priors_404_does_not_leak_paths(tmp_path, monkeypatch):
    """When both files are missing, 404 body must not contain absolute
    paths or rebuild commands (info-disclosure defense)."""
    import serve  # noqa: E402

    # Empty feed dir — no files
    feed = tmp_path / "outputs" / "dashboard_feed"
    feed.mkdir(parents=True)
    monkeypatch.setattr(serve, "ROOT", tmp_path)
    serve._JSON_CACHE.clear()

    # Spin a server inline
    sock = socket.socket(); sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]; sock.close()
    httpd = HTTPServer(("127.0.0.1", port), serve.PortalHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.05)

    try:
        status, body, _ = _get(f"http://127.0.0.1:{port}/api/v2/historical-burn-priors")
        assert status == 404
        msg = json.loads(body)["error"]["message"]
        # Hardening: no path leakage, no rebuild command
        assert "outputs" not in msg
        assert ".json" not in msg
        assert "scripts/" not in msg
        assert "python" not in msg.lower()
    finally:
        httpd.shutdown(); httpd.server_close()


def test_priors_etag_returns_304(server):
    """Second request with matching If-None-Match → 304 with no body."""
    status1, _, hdrs1 = _get(f"{server}/api/v2/historical-burn-priors")
    assert status1 == 200
    etag = hdrs1["ETag"]
    assert etag

    status2, body2, hdrs2 = _get(
        f"{server}/api/v2/historical-burn-priors",
        headers={"If-None-Match": etag},
    )
    assert status2 == 304
    assert body2 == ""  # 304 has no body
    assert hdrs2.get("ETag") == etag


def test_density_etag_returns_304(server):
    status1, _, hdrs1 = _get(f"{server}/api/v2/historical-burn-density")
    assert status1 == 200
    etag = hdrs1["ETag"]

    status2, body2, _ = _get(
        f"{server}/api/v2/historical-burn-density",
        headers={"If-None-Match": etag},
    )
    assert status2 == 304
    assert body2 == ""


def test_cache_hit_skips_json_parse(server):
    """Second hit on the same file should not re-invoke json.loads
    (the mtime-keyed cache returns the previous parse)."""
    import serve  # noqa: E402

    # Prime the cache via a regular request
    status1, _, _ = _get(f"{server}/api/v2/historical-burn-priors")
    assert status1 == 200

    # Patch json.loads in the serve module's namespace and confirm it
    # is NOT called when a fresh request hits the same cached file.
    with patch.object(serve.json, "loads", wraps=serve.json.loads) as spy:
        status2, _, _ = _get(f"{server}/api/v2/historical-burn-priors")
        assert status2 == 200
        # Cache hit means _load_cached_json never re-parses the file.
        # The only json.loads calls during the request body should be
        # zero (the response body uses json.dumps, not loads).
        for call in spy.call_args_list:
            arg = call.args[0] if call.args else ""
            assert "metadata" not in str(arg), (
                "expected cache hit but json.loads was called with file content"
            )
