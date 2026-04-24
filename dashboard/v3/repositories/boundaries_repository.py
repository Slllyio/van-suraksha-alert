"""Division / beat boundary GeoJSON access.

Serves the pre-baked dissolved + simplified division polygons (much
smaller than the 179 MB beat-level GeoJSON — see commit 5d485957).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal


DEFAULT_AOI_DIR = Path(__file__).resolve().parents[3] / "data" / "aoi"

Resolution = Literal["ultra", "high"]


class BoundariesRepository:
    """Load pre-baked division polygon FeatureCollections."""

    def __init__(self, aoi_dir: Path | None = None) -> None:
        aoi = Path(aoi_dir) if aoi_dir else DEFAULT_AOI_DIR
        self.paths: dict[Resolution, Path] = {
            "ultra": aoi / "mp_divisions_ultra.geojson",
            "high":  aoi / "mp_divisions_simplified.geojson",
        }

    def available_resolutions(self) -> list[Resolution]:
        return sorted(self.paths.keys())  # type: ignore[return-value]

    def path_for(self, resolution: Resolution) -> Path | None:
        return self.paths.get(resolution)

    def load(self, resolution: Resolution = "ultra") -> dict:
        """Return the parsed GeoJSON FeatureCollection.

        Raises FileNotFoundError if the baked file is missing (caller
        should translate to 404) or ValueError on invalid JSON / bad
        resolution (caller should translate to 400/500).
        """
        path = self.paths.get(resolution)
        if path is None:
            raise ValueError(
                f"unknown resolution {resolution!r}; "
                f"valid: {self.available_resolutions()}"
            )
        if not path.exists():
            raise FileNotFoundError(
                f"boundary file missing: {path.name}. "
                "Rebuild via scripts/build_division_boundaries.py."
            )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"boundaries unreadable: {exc}") from exc
