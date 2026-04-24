"""JwalaNetra v2 API client.

Uses only stdlib (urllib.request) — zero runtime dependencies.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Optional


class ApiError(Exception):
    """Raised for any non-2xx response from the JwalaNetra API.

    Attributes:
        code:    Machine-readable error code (e.g. "invalid_cursor").
        message: Human-readable explanation from the server.
        status:  HTTP status code.
    """

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(f"[{status}] {code}: {message}")
        self.code = code
        self.message = message
        self.status = status


class Client:
    """Thin, synchronous client for the JwalaNetra v2 Portal API.

    Parameters:
        base_url: Root URL of the portal backend, no trailing slash.
        timeout:  Socket timeout in seconds for all requests.

    Example::

        from jwalanetra import Client, ApiError

        client = Client("http://localhost:8790")
        health = client.healthz()
        assert health["data"]["ok"] is True

        page1 = client.ignition_v17(limit=5)
        cursor = page1["meta"]["next_cursor"]
        page2 = client.ignition_v17(limit=5, cursor=cursor)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8790",
        timeout: float = 30.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        """Execute a GET request and return the parsed JSON body.

        Raises:
            ApiError: If the server returns a non-2xx status.
        """
        url = self._base + path
        if params:
            # Filter out None values so callers can pass None for optional params.
            clean = {k: str(v) for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)

        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            self._raise_from_body(body, exc.code)

        return json.loads(body)

    @staticmethod
    def _raise_from_body(body: str, status: int) -> None:
        """Parse error envelope and raise ApiError."""
        try:
            payload = json.loads(body)
            err = payload.get("error", {})
            code = err.get("code", "unknown_error")
            message = err.get("message", body)
        except (json.JSONDecodeError, AttributeError):
            code = "unknown_error"
            message = body or f"HTTP {status}"
        raise ApiError(code=code, message=message, status=status)

    # ------------------------------------------------------------------
    # Public API methods — one per OpenAPI operation
    # ------------------------------------------------------------------

    def healthz(self) -> dict[str, Any]:
        """GET /api/v2/healthz — liveness + cache warmup status.

        Returns the full envelope::

            {
                "data": {
                    "ok": True,
                    "portal_uptime_s": 378,
                    "beat_polygons_loaded": True,
                    "firms_nrt_age_hours": 5.2,
                    "firms_nrt_max_date": "2026-04-24",
                    ...
                }
            }
        """
        return self._get("/api/v2/healthz")

    def ignition_v17(
        self,
        *,
        date: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> dict[str, Any]:
        """GET /api/v2/ignition-v17 — paginated v17 banded alerts.

        Parameters:
            date:   Prediction date as "YYYY-MM-DD". Defaults to latest.
            limit:  Page size 1–2000 (server clamps higher values to 2000).
            cursor: Opaque cursor from ``meta.next_cursor`` of the previous page.

        Returns the full envelope::

            {
                "data": [V17Cell, ...],
                "meta": {
                    "total": 1305,
                    "limit": 3,
                    "offset": 0,
                    "has_next": True,
                    "next_cursor": "Mw==",
                    "prediction_date": "2026-04-25",
                    "model": "v17_ba_pu",
                    "generated_at": "2026-04-24T23:52:30.305454"
                },
                "links": {"self": "...", "next": "..."}
            }

        Raises:
            ApiError: code="invalid_limit" if limit is not an integer string.
            ApiError: code="invalid_cursor" if cursor is not a valid opaque token.
        """
        return self._get(
            "/api/v2/ignition-v17",
            {"date": date, "limit": limit, "cursor": cursor},
        )

    def division_overview(self) -> dict[str, Any]:
        """GET /api/v2/division-overview — 87 forest divisions with alert counts.

        Note: The actual ``data`` field is a dict with keys
        ``divisions``, ``total_alerts``, ``prediction_date``, etc.
        The ``data.divisions`` list is the per-division array described
        by the OpenAPI spec (spec lists ``data`` as the array directly,
        but the live server wraps it).

        Returns the full envelope.
        """
        return self._get("/api/v2/division-overview")

    def season_validation(self) -> dict[str, Any]:
        """GET /api/v2/season-validation — rolling 2026 season recall stats.

        Note: The actual ``data`` field is a dict with keys
        ``summary``, ``per_trust_tier``, ``per_day``, ``per_division``.
        The ``data.per_day`` list contains per-date recall rows.

        Returns the full envelope.
        """
        return self._get("/api/v2/season-validation")

    def model_transparency(self) -> dict[str, Any]:
        """GET /api/v2/model-transparency — honest v17.5 metrics and feature importance.

        Note: Spec says ``data.model_version``; the live server uses ``data.model``.
        Both contain the LightGBM model identifier (e.g. ``"v17_ba_pu"``).

        Returns the full envelope.
        """
        return self._get("/api/v2/model-transparency")

    def viirs_fires(
        self,
        *,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """GET /api/v2/viirs-fires — forest-clipped FIRMS VIIRS detections.

        Parameters:
            from_date: Start date "YYYY-MM-DD" (inclusive).
            to_date:   End date "YYYY-MM-DD" (inclusive).

        Returns the full envelope::

            {
                "data": [ViirsFire, ...],
                "meta": {
                    "total": 151,
                    "n_before_clip": 1199,
                    "n_clipped": 1048,
                    "latest_date": "2026-04-24",
                    "date_range": "2026-04-07 to 2026-04-07"
                }
            }
        """
        params: dict[str, Any] = {}
        if from_date is not None:
            params["from"] = from_date
        if to_date is not None:
            params["to"] = to_date
        return self._get("/api/v2/viirs-fires", params or None)

    def beats_boundary(self) -> dict[str, Any]:
        """GET /api/v2/beats-boundary — 8,973 MP forest-beat MultiPolygons.

        Warning: response is ~179 MB. Fetch once and cache the result.

        Returns the full envelope with ``data`` as a GeoJSON FeatureCollection.

        Raises:
            ApiError: code from server if boundary file is missing (404/500).
        """
        return self._get("/api/v2/beats-boundary")
