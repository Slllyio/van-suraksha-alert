"""JwalaNetra Python SDK.

Minimal, zero-dependency client for the JwalaNetra v2 Portal API
(MP Forest Fire Early Warning System).

Quick start::

    from jwalanetra import Client, ApiError

    client = Client("http://localhost:8790")
    health = client.healthz()
    assert health["data"]["ok"] is True
"""

from __future__ import annotations

from typing import Optional, Union
from typing_extensions import TypedDict, NotRequired

from .client import ApiError, Client

__all__ = [
    "Client",
    "ApiError",
    "V17Cell",
    "DivisionSummary",
    "ValidationRow",
    "ModelTransparency",
    "ViirsFire",
    "Envelope",
    "PaginationMeta",
    "ViirsFireMeta",
]

__version__ = "0.1.0"


# ---------------------------------------------------------------------------
# Typed wrappers (TypedDict — structural, no runtime overhead)
# ---------------------------------------------------------------------------


class V17Cell(TypedDict):
    """Single ignition-risk cell from the v17 / v17.5 model output."""

    cell_id: Union[str, int]
    lat: float
    lon: float
    band: str  # "CRITICAL" | "ALERT" | "WATCH"
    ignition_risk: NotRequired[float]
    calibrated_risk: NotRequired[float]
    rank: NotRequired[float]
    stage_a_risk: NotRequired[float]
    hawkes_lambda: NotRequired[float]
    hawkes_n_recent_10km_7d: NotRequired[int]


class DivisionSummary(TypedDict):
    """Per-division alert aggregate returned by /division-overview."""

    name: str
    critical: NotRequired[int]
    alert: NotRequired[int]
    watch: NotRequired[int]
    total: NotRequired[int]
    mean_risk: NotRequired[float]
    max_risk: NotRequired[float]
    hawkes_high_pct: NotRequired[float]
    confidence: NotRequired[str]


class ValidationRow(TypedDict):
    """Per-day recall row from /season-validation data.per_day."""

    date: str
    n_events: NotRequired[int]
    n_caught_any_band: NotRequired[int]
    n_caught_critical: NotRequired[int]
    recall_any_band: NotRequired[float]
    recall_critical: NotRequired[float]
    n_critical_alerts: NotRequired[int]
    precision_critical: NotRequired[float]
    median_spatial_offset_km: NotRequired[float]
    median_temporal_offset_days: NotRequired[float]
    # Schema alias — spec calls this recall_pct, live server uses recall_any_band
    recall_pct: NotRequired[float]


class FeatureImportance(TypedDict):
    """Single feature importance entry."""

    name: str
    gain: float


class ModelTransparency(TypedDict):
    """Model card data from /model-transparency.

    Note: OpenAPI spec documents ``model_version``; the live server
    returns ``model``. Both are included here for forward compatibility.
    """

    model: NotRequired[str]       # live field: e.g. "v17_ba_pu"
    model_version: NotRequired[str]  # spec field (may be absent on live server)
    training_label: NotRequired[str]
    metrics: NotRequired[dict]
    hawkes_dependency: NotRequired[dict]
    top_features: NotRequired[list]
    trust_guidance: NotRequired[dict]


class ViirsFire(TypedDict):
    """Single FIRMS VIIRS active-fire detection (forest-clipped)."""

    lat: float
    lon: float
    date: str
    time: NotRequired[str]
    confidence: NotRequired[str]
    brightness: NotRequired[float]
    satellite: NotRequired[str]
    source: NotRequired[str]
    division: NotRequired[str]
    range: NotRequired[str]
    beat: NotRequired[str]
    frp: NotRequired[float]


class PaginationMeta(TypedDict):
    """Pagination metadata for /ignition-v17."""

    total: int
    limit: int
    offset: int
    has_next: bool
    next_cursor: Optional[str]
    prediction_date: str
    model: str
    generated_at: str


class ViirsFireMeta(TypedDict):
    """Response metadata for /viirs-fires."""

    total: int
    n_before_clip: int
    n_clipped: int
    latest_date: str
    date_range: Union[str, dict]  # live: str; spec: object


class Envelope(TypedDict):
    """Generic response envelope — ``{ data, meta?, links? }``."""

    data: Union[list, dict]
    meta: NotRequired[dict]
    links: NotRequired[dict]
