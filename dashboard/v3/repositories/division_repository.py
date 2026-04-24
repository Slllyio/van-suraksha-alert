"""Division-overview data access.

Today ``serve._build_division_overview`` + ``serve._enrich_division_overview``
do the work inline. This class wraps them so route handlers can depend on
an abstract interface and tests can mock with synthetic division rows.
"""
from __future__ import annotations

from typing import Callable


class DivisionRepository:
    """Serve the per-division alert rollup."""

    def __init__(
        self,
        build_overview: Callable[[dict], dict],
        enrich_overview: Callable[[dict], dict],
        v17_loader: Callable[[str | None], dict],
    ) -> None:
        self._build = build_overview
        self._enrich = enrich_overview
        self._load_v17 = v17_loader

    def overview(self, target_date: str | None = None) -> dict:
        v17_payload = self._load_v17(target_date)
        base = self._build(v17_payload)
        return self._enrich(base)
