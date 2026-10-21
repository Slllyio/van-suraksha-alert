"""Same-day Sentinel-2 scenes for the 30 m direction arrow from Copernicus Data Space (CDSE).

Planetary Computer, the arrow's usual source, had none of the 19 MP Sentinel-2 scenes of 18 Oct 2026 thirteen hours
after they were taken; CDSE listed every one about 5 h after the pass (L2A median 5.0 h, 90% within 6.2 h; scenes are
taken ~10:50-11:10 IST, so ~16:00 IST). Only the mid-fire scene needs to be fast: the before-fire scene is at least
3 days old and still comes from Planetary Computer.

Search is CDSE's open STAC; pixels come from the Sentinel Hub Process API on CDSE, which needs an OAuth client
(free account). Two ways to give it one, neither writes anything to disk:
  - an "OAuth 2.0 client credentials" secret in the cloud environment for sh.dataspace.copernicus.eu: the
    environment's proxy fetches the token and signs each request, and the app never sees a key (preferred);
  - CDSE_CLIENT_ID and CDSE_CLIENT_SECRET environment variables: the app fetches the token itself.
available() checks once an hour with a 1-pixel request; when it fails the arrow uses Planetary Computer alone."""
import os, threading, time
from datetime import timedelta

import numpy as np

STAC = "https://stac.dataspace.copernicus.eu/v1/search"
TOKEN = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS = "https://sh.dataspace.copernicus.eu/api/v1/process"
ON = os.environ.get("FS_CDSE", "1") == "1"
OWN_KEYS = bool(os.environ.get("CDSE_CLIENT_ID") and os.environ.get("CDSE_CLIENT_SECRET"))
_tok, _lock = {"v": None, "exp": 0}, threading.Lock()
_probe = {"ok": None, "at": 0}

EVALSCRIPT = """//VERSION=3
function setup() { return { input: [{ bands: ["B04", "B8A", "B12", "SCL"] }],
  output: { bands: 4, sampleType: "FLOAT32" } }; }
function evaluatePixel(s) { return [s.B04, s.B8A, s.B12, s.SCL]; }"""


class Scene:
    """Just what direction.arrow needs from a scene: id, datetime, and properties."""
    def __init__(self, f):
        from datetime import datetime
        self.id = f["id"]
        self.datetime = datetime.fromisoformat(f["properties"]["datetime"].replace("Z", "+00:00"))
        self.properties = f["properties"]
        self.assets = {}


def _token():
    import requests
    with _lock:
        if _tok["v"] and time.time() < _tok["exp"] - 60:
            return _tok["v"]
        r = requests.post(TOKEN, data={"grant_type": "client_credentials", "client_id": os.environ["CDSE_CLIENT_ID"],
                                       "client_secret": os.environ["CDSE_CLIENT_SECRET"]}, timeout=30)
        r.raise_for_status()
        j = r.json()
        _tok.update(v=j["access_token"], exp=time.time() + j.get("expires_in", 600))
        return _tok["v"]


def _headers():
    h = {"Accept": "image/tiff"}
    if OWN_KEYS:
        h["Authorization"] = f"Bearer {_token()}"
    return h                              # otherwise the environment's proxy adds the token


def available():
    """True when the Process API answers for us (checked at most once an hour)."""
    import requests
    if not ON:
        return False
    if time.time() - _probe["at"] < 3600 and _probe["ok"] is not None:
        return _probe["ok"]
    body = {"input": {"bounds": {"bbox": [77.0, 23.0, 77.0002, 23.0002]}, "data": [{"type": "sentinel-2-l2a"}]},
            "output": {"width": 1, "height": 1}, "evalscript": EVALSCRIPT}
    try:
        r = requests.post(PROCESS, json=body, headers=_headers(), timeout=30)
        ok = r.status_code == 200
    except Exception:
        ok = False
    _probe.update(ok=ok, at=time.time())
    return ok


def search(pt, t0, t_end):
    """Sentinel-2 L2A scenes over a point between t0 and t_end (open STAC, no login)."""
    import requests
    r = requests.post(STAC, json={"collections": ["sentinel-2-l2a"], "intersects": pt, "limit": 50,
                                  "datetime": f"{t0:%Y-%m-%dT%H:%M:%SZ}/{t_end:%Y-%m-%dT%H:%M:%SZ}"}, timeout=60)
    r.raise_for_status()
    return [Scene(f) for f in r.json().get("features", [])]


def read(scene, tr, W, H):
    """B04, B8A, B12 as reflectance on the arrow's 20 m UTM 43N grid; cloud, shadow and no-data (SCL) set to NaN."""
    import requests
    from rasterio.io import MemoryFile
    x0, y1 = tr.c, tr.f
    x1, y0 = x0 + W * tr.a, y1 + H * tr.e
    t = scene.datetime                    # Sentinel Hub's tile times differ from the STAC scene time by minutes: +-1 h window
    body = {"input": {"bounds": {"bbox": [x0, y0, x1, y1], "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/32643"}},
                      "data": [{"type": "sentinel-2-l2a", "dataFilter": {
                          "timeRange": {"from": f"{t - timedelta(hours=1):%Y-%m-%dT%H:%M:%SZ}", "to": f"{t + timedelta(hours=1):%Y-%m-%dT%H:%M:%SZ}"},
                          "mosaickingOrder": "mostRecent"}, "processing": {"upsampling": "BILINEAR"}}]},
            "output": {"width": W, "height": H, "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
            "evalscript": EVALSCRIPT}
    r = requests.post(PROCESS, json=body, headers=_headers(), timeout=120)
    r.raise_for_status()
    with MemoryFile(r.content) as m, m.open() as src:
        a = src.read().astype(np.float32)        # Sentinel Hub returns reflectance with the 2022 offset already removed
    red, nir, sw, scl = a
    bad = np.isin(scl, [0, 1, 3, 8, 9, 10]) | (nir <= 0)
    out = {"red": red, "nir": nir, "swir2": sw}
    for k in out:
        out[k] = np.where(bad, np.nan, out[k])
    return out
