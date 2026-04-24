"""V17 ignition-prediction data access.

Wraps ``outputs/dashboard_feed/ignition_risk_v17_<date>.json`` reads.
See :func:`serve._load_v17_predictions` for the current implementation;
this class is the intended long-term interface.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any


DEFAULT_FEED_DIR = Path(__file__).resolve().parents[3] / "outputs" / "dashboard_feed"


class V17Repository:
    """Load and paginate v17 banded alerts from the daily prediction JSON.

    Args:
        feed_dir: folder containing ``ignition_risk_v17_<YYYY-MM-DD>.json``.
                  Defaults to the project's ``outputs/dashboard_feed/``.
    """

    def __init__(self, feed_dir: Path | None = None) -> None:
        self.feed_dir = Path(feed_dir) if feed_dir else DEFAULT_FEED_DIR

    # ---- Paths ----

    def _path_for(self, target_date: str | None) -> Path:
        if target_date:
            dated = self.feed_dir / f"ignition_risk_v17_{target_date}.json"
            if dated.exists():
                return dated
        return self.feed_dir / "ignition_risk_v17.json"

    # ---- Read ----

    def load(self, target_date: str | None = None) -> dict:
        """Return the full prediction JSON (metadata + banded_alerts list).

        Returns an empty dict if no file exists so callers can consistently
        handle missing-data by checking `.get("banded_alerts", [])`.
        """
        path = self._path_for(target_date)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def list_alerts(self, target_date: str | None = None) -> list[dict]:
        """Return just the banded_alerts list (possibly empty)."""
        payload = self.load(target_date)
        alerts = payload.get("banded_alerts")
        return list(alerts) if isinstance(alerts, list) else []

    # ---- Pagination ----

    @staticmethod
    def encode_cursor(offset: int) -> str:
        return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")

    @staticmethod
    def decode_cursor(cursor: str | None) -> int:
        """Return a 0-based offset from an opaque cursor, or 0 if none.

        Raises ValueError on malformed input so the caller can 400-out.
        """
        if not cursor:
            return 0
        try:
            decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")
            offset = int(decoded)
            if offset < 0:
                raise ValueError("negative offset")
            return offset
        except (ValueError, OSError) as exc:
            raise ValueError(f"invalid cursor: {exc}") from exc

    def page(
        self,
        target_date: str | None = None,
        offset: int = 0,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Return one page of alerts plus pagination metadata.

        Caller can encode ``meta["next_cursor"]`` back to base64 opaque form
        via ``V17Repository.encode_cursor`` (already done below).
        """
        payload = self.load(target_date)
        all_alerts = payload.get("banded_alerts") or []
        total = len(all_alerts) if isinstance(all_alerts, list) else 0
        data = all_alerts[offset : offset + limit] if isinstance(all_alerts, list) else []
        has_next = offset + limit < total
        return {
            "data": data,
            "meta": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_next": has_next,
                "next_cursor": (
                    self.encode_cursor(offset + limit) if has_next else None
                ),
                "prediction_date": payload.get("prediction_date"),
                "model": payload.get("model"),
                "generated_at": payload.get("generated_at"),
            },
        }
