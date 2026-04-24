"""Contract tests for the JwalaNetra v2 Portal API.

Hits the live backend at http://localhost:8790.
All tests verify envelope conformance against the OpenAPI spec
(openapi.yaml) while noting confirmed spec drift.

Run with:
    cd E:/FIRE && pytest tests/test_api_v2_contract.py -v
"""

from __future__ import annotations

import sys
import os
import urllib.request
import urllib.error

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: make the SDK importable without installing it
# ---------------------------------------------------------------------------
SDK_ROOT = os.path.join(os.path.dirname(__file__), "..", "sdk", "python")
if SDK_ROOT not in sys.path:
    sys.path.insert(0, SDK_ROOT)

from jwalanetra import Client, ApiError  # noqa: E402

BASE_URL = "http://localhost:8790"


# ---------------------------------------------------------------------------
# Session-scoped fixture: one Client for all tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def client() -> Client:
    """Return a Client instance and skip the entire session if server is down."""
    c = Client(BASE_URL, timeout=15.0)
    try:
        resp = c.healthz()
    except Exception as exc:
        pytest.skip(f"Backend not reachable at {BASE_URL}: {exc}")
    if not resp.get("data", {}).get("ok"):
        pytest.skip("Backend /healthz returned ok=False")
    return c


# ---------------------------------------------------------------------------
# Test 1 — healthz envelope
# ---------------------------------------------------------------------------


def test_healthz_envelope(client: Client) -> None:
    """GET /api/v2/healthz returns 200 with data.ok == True."""
    resp = client.healthz()

    assert "data" in resp, "Response must have 'data' key"
    data = resp["data"]
    assert isinstance(data, dict), "data must be a dict"
    assert data.get("ok") is True, f"data.ok must be True, got {data.get('ok')!r}"


# ---------------------------------------------------------------------------
# Test 2 — ignition-v17 envelope shape
# ---------------------------------------------------------------------------


def test_ignition_envelope_shape(client: Client) -> None:
    """GET /api/v2/ignition-v17?limit=3 returns 3 cells, meta.total > 100."""
    resp = client.ignition_v17(limit=3)

    # Top-level keys
    assert "data" in resp
    assert "meta" in resp

    data = resp["data"]
    meta = resp["meta"]

    # Exactly 3 cells
    assert isinstance(data, list), f"data must be a list, got {type(data).__name__}"
    assert len(data) == 3, f"Expected 3 cells, got {len(data)}"

    # Cell shape: required fields per spec
    for cell in data:
        assert "cell_id" in cell, "V17Cell must have cell_id"
        assert "lat" in cell, "V17Cell must have lat"
        assert "lon" in cell, "V17Cell must have lon"
        assert "band" in cell, "V17Cell must have band"
        assert cell["band"] in ("CRITICAL", "ALERT", "WATCH"), (
            f"band must be CRITICAL/ALERT/WATCH, got {cell['band']!r}"
        )

    # Pagination meta
    assert meta.get("total", 0) > 100, (
        f"meta.total must be > 100 (whole MP state), got {meta.get('total')}"
    )
    assert "next_cursor" in meta, "meta must contain next_cursor key"
    nc = meta["next_cursor"]
    assert nc is None or isinstance(nc, str), (
        f"next_cursor must be str or null, got {type(nc).__name__}"
    )


# ---------------------------------------------------------------------------
# Test 3 — cursor walk (non-overlapping pages)
# ---------------------------------------------------------------------------


def test_ignition_cursor_walk(client: Client) -> None:
    """Fetch page 1 (limit=5), follow next_cursor, confirm non-overlapping cell_ids."""
    page1 = client.ignition_v17(limit=5)
    cursor = page1["meta"].get("next_cursor")

    if cursor is None:
        pytest.skip("Only one page of results — cursor walk not applicable")

    page2 = client.ignition_v17(limit=5, cursor=cursor)

    ids1 = {cell["cell_id"] for cell in page1["data"]}
    ids2 = {cell["cell_id"] for cell in page2["data"]}

    overlap = ids1 & ids2
    assert not overlap, (
        f"Pages must not share cell_ids; overlapping: {overlap}"
    )

    # Second page must also be a valid envelope
    assert "meta" in page2
    assert isinstance(page2["data"], list)


# ---------------------------------------------------------------------------
# Test 4 — invalid limit returns 400 invalid_limit
# ---------------------------------------------------------------------------


def test_ignition_invalid_limit(client: Client) -> None:
    """?limit=notanumber returns 400 with error.code == 'invalid_limit'."""
    # We must bypass the SDK's type coercion and send the raw string
    url = f"{BASE_URL}/api/v2/ignition-v17?limit=notanumber"
    req = urllib.request.Request(url)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=10)

    err_resp = exc_info.value
    assert err_resp.code == 400, f"Expected 400, got {err_resp.code}"

    import json
    body = json.loads(err_resp.read().decode())
    assert "error" in body
    assert body["error"]["code"] == "invalid_limit", (
        f"Expected 'invalid_limit', got {body['error']['code']!r}"
    )


# ---------------------------------------------------------------------------
# Test 5 — invalid cursor returns 400 invalid_cursor
# ---------------------------------------------------------------------------


def test_ignition_invalid_cursor(client: Client) -> None:
    """?cursor=@@@ returns 400 with error.code == 'invalid_cursor'."""
    url = f"{BASE_URL}/api/v2/ignition-v17?cursor=%40%40%40"
    req = urllib.request.Request(url)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=10)

    err_resp = exc_info.value
    assert err_resp.code == 400, f"Expected 400, got {err_resp.code}"

    import json
    body = json.loads(err_resp.read().decode())
    assert "error" in body
    assert body["error"]["code"] == "invalid_cursor", (
        f"Expected 'invalid_cursor', got {body['error']['code']!r}"
    )


# ---------------------------------------------------------------------------
# Test 6 — limit clamping: 99999 accepted but clamped to 2000
# ---------------------------------------------------------------------------


def test_ignition_limit_clamping(client: Client) -> None:
    """?limit=99999 is accepted (not 400) and meta.limit == 2000."""
    # The server clamps large limits to 2000 rather than rejecting them.
    url = f"{BASE_URL}/api/v2/ignition-v17?limit=99999"
    req = urllib.request.Request(url)

    # Should not raise (not a 4xx)
    with urllib.request.urlopen(req, timeout=30) as resp:
        import json
        body = json.loads(resp.read().decode())

    assert resp.status == 200, f"Expected 200, got {resp.status}"  # type: ignore[attr-defined]
    meta = body.get("meta", {})
    assert meta.get("limit") == 2000, (
        f"Clamped limit must be 2000, got {meta.get('limit')}"
    )


# ---------------------------------------------------------------------------
# Test 7 — division-overview has 'division' (or 'name') key in each entry
# ---------------------------------------------------------------------------


def test_division_overview_envelope(client: Client) -> None:
    """GET /api/v2/division-overview: data.divisions is a list, each item has a name key.

    Spec drift: spec says data is a list of DivisionSummary;
    live server returns data as dict with key 'divisions' containing the list.
    Both the spec field 'division' and live field 'name' are checked.
    """
    resp = client.division_overview()

    assert "data" in resp

    data = resp["data"]
    # Accommodate both spec (list) and live (dict) shapes
    if isinstance(data, list):
        divisions = data
    elif isinstance(data, dict):
        divisions = data.get("divisions", [])
    else:
        pytest.fail(f"data must be a list or dict, got {type(data).__name__}")

    assert isinstance(divisions, list), "Divisions collection must be a list"
    assert len(divisions) > 0, "Divisions list must not be empty"

    # Each entry must have 'division' (spec) or 'name' (live)
    for entry in divisions:
        has_key = ("division" in entry) or ("name" in entry)
        assert has_key, (
            f"Each division entry must have 'division' or 'name' key; got keys: {list(entry.keys())}"
        )


# ---------------------------------------------------------------------------
# Test 8 — season-validation: per_day rows have a numeric recall field
# ---------------------------------------------------------------------------


def test_season_validation_has_recall(client: Client) -> None:
    """Every per-day row in season-validation has a numeric recall field.

    Spec drift: spec says data is a flat list with recall_pct field;
    live server returns data as dict with per_day containing recall_any_band.
    Test accepts either shape.
    """
    resp = client.season_validation()
    assert "data" in resp

    data = resp["data"]

    # Resolve rows from either flat list or nested dict shape
    if isinstance(data, list):
        rows = data
        recall_key = "recall_pct"
    elif isinstance(data, dict):
        rows = data.get("per_day", [])
        recall_key = "recall_any_band"  # live server field name
    else:
        pytest.fail(f"data must be list or dict, got {type(data).__name__}")

    assert len(rows) > 0, "season-validation must contain at least one row"

    for row in rows:
        # Accept either spec key (recall_pct) or live key (recall_any_band)
        value = row.get(recall_key) if recall_key in row else row.get("recall_pct")
        assert value is not None, (
            f"Row missing recall field (tried {recall_key!r} and 'recall_pct'): {row}"
        )
        assert isinstance(value, (int, float)), (
            f"recall must be numeric, got {type(value).__name__}: {value!r}"
        )


# ---------------------------------------------------------------------------
# Test 9 — viirs-fires: meta.n_before_clip >= meta.total (clipping monotonic)
# ---------------------------------------------------------------------------


def test_viirs_meta_populated(client: Client) -> None:
    """GET /api/v2/viirs-fires has meta.n_before_clip >= meta.total (clipping is monotonic)."""
    resp = client.viirs_fires(from_date="2026-04-07", to_date="2026-04-07")

    assert "meta" in resp
    meta = resp["meta"]

    n_before = meta.get("n_before_clip")
    total = meta.get("total")

    assert n_before is not None, "meta.n_before_clip must be present"
    assert total is not None, "meta.total must be present"
    assert isinstance(n_before, (int, float)), "n_before_clip must be numeric"
    assert isinstance(total, (int, float)), "total must be numeric"
    assert n_before >= total, (
        f"Clipping must be monotonic: n_before_clip ({n_before}) >= total ({total})"
    )


# ---------------------------------------------------------------------------
# Test 10 — model-transparency: data model identifier starts with "v17"
# ---------------------------------------------------------------------------


def test_model_transparency_schema(client: Client) -> None:
    """GET /api/v2/model-transparency: model identifier starts with 'v17'.

    Spec drift: spec documents data.model_version; live server uses data.model.
    Test checks both fields to handle either shape.
    """
    resp = client.model_transparency()

    assert "data" in resp
    data = resp["data"]
    assert isinstance(data, dict), f"data must be a dict, got {type(data).__name__}"

    # Accept either field name (spec: model_version, live: model)
    model_id = data.get("model_version") or data.get("model")
    assert model_id is not None, (
        "data must have 'model_version' (spec) or 'model' (live) key"
    )
    assert isinstance(model_id, str), f"model identifier must be a string, got {type(model_id).__name__}"
    assert model_id.startswith("v17"), (
        f"model identifier must start with 'v17', got {model_id!r}"
    )
