"""Checks that a field report is real: the photos were taken at the fire, after the alert.

Per photo we keep two locations: the phone's GPS when the photo was attached (sent by
the field page) and the GPS written inside the photo (EXIF), when the camera kept it.
Flags are advisory: a supervisor accepts or sends the report back.
"""
import hashlib, io, math
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageOps
Image.MAX_IMAGE_PIXELS = 60_000_000   # phone photos are <= 50 MP; refuses decompression bombs
try:
    from pillow_heif import register_heif_opener   # iPhone HEIC, when the package is installed
    register_heif_opener()
except ImportError:
    pass
from . import config
from .geo import haversine_km

GPS_IFD, EXIF_IFD = 0x8825, 0x8769


def num(x, lo=-180, hi=180):
    """A finite float in [lo, hi], else None (NaN, inf, text, 0/0 EXIF rationals)."""
    try:
        x = float(x)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return x if math.isfinite(x) and lo <= x <= hi else None


def _deg(v, ref):
    d, m, s = (float(x) for x in v)
    x = d + m / 60 + s / 3600
    return num(-x if ref in ("S", "W") else x)


def read_exif(img):
    out = {}
    try:
        ex = img.getexif()
        gps = ex.get_ifd(GPS_IFD)
        if gps and 2 in gps and 4 in gps:
            lat, lon = _deg(gps[2], gps.get(1, "N")), _deg(gps[4], gps.get(3, "E"))
            if lat is not None and lon is not None and abs(lat) <= 90 and not (lat == 0 and lon == 0):
                out["lat"], out["lon"] = lat, lon      # 0/0 rationals (no fix) are no position, not a strong one
    except Exception:
        pass
    try:   # time on its own, so a bad GPS block does not also drop the time
        ex = img.getexif()
        t = ex.get_ifd(EXIF_IFD).get(36867) or ex.get(306)
        if t:
            # Camera clocks are local time; field phones in India are IST.
            local = datetime.strptime(str(t).strip("\x00"), "%Y:%m:%d %H:%M:%S")
            out["taken_utc"] = (local - timedelta(hours=5, minutes=30)).replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return out


class BadPhoto(ValueError):
    pass


def load_photo(raw):
    """Decode once, before anything is stored: (img, thumbnail, sha256, exif), or BadPhoto (HEIC without pillow_heif,
    a cut-off upload, not an image, a decompression bomb)."""
    sha = hashlib.sha256(raw).hexdigest()
    try:
        img = Image.open(io.BytesIO(raw))
        if img.width * img.height > Image.MAX_IMAGE_PIXELS:
            raise ValueError("image too large")
        ex = read_exif(img)
        img.draft("RGB", (960, 960))                      # JPEG: decode at reduced size
        th = ImageOps.exif_transpose(img).convert("RGB")
        th.thumbnail((480, 480))
    except Exception as e:
        raise BadPhoto(f"photo could not be read ({type(e).__name__}); send a JPEG or PNG photo") from e
    return img, th, sha, ex


def save_photo(loaded, raw, dest_dir, stem):
    """Save original + 480 px thumbnail; return (path, thumb, sha256, exif dict)."""
    img, th, sha, ex = loaded
    ext = (img.format or "jpg").lower().replace("jpeg", "jpg")
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{stem}.{ext}"
    path.write_bytes(raw)
    thumb = dest_dir / f"{stem}_t.jpg"
    th.save(thumb, quality=80)
    return path, thumb, sha, ex


def nearest_km(lat, lon, dets):
    return min(haversine_km(lat, lon, d["lat"], d["lon"]) for d in dets) if lat is not None else None


def check_photo(meta, ex, place, first_seen, seen_hash, now_utc=None):
    """meta: dev_lat/dev_lon/dev_utc from the phone; place: pilot.Place (fire points, or a predicted cell).
    Returns (distance_km, flags, taken)."""
    flags = []
    meta = dict(meta, dev_lat=num(meta.get("dev_lat"), -90, 90), dev_lon=num(meta.get("dev_lon")))
    if meta["dev_lat"] is None or meta["dev_lon"] is None:
        meta["dev_lat"] = meta["dev_lon"] = None
    lat, lon = ex.get("lat"), ex.get("lon")
    if lat is None:
        lat, lon = meta.get("dev_lat"), meta.get("dev_lon")
    km = place.km(lat, lon)
    if km is None:
        flags.append("no_location")
    elif km > place.photo_km:
        flags.append("outside_cell" if place.geom is not None else "far_from_fire")
    if ex.get("lat") is not None and meta.get("dev_lat") is not None:
        if haversine_km(ex["lat"], ex["lon"], meta["dev_lat"], meta["dev_lon"]) > 1.0:
            flags.append("photo_gps_differs_from_phone")
    taken = ex.get("taken_utc")
    if taken is None and meta.get("dev_utc"):
        taken = datetime.fromisoformat(meta["dev_utc"].replace("Z", "+00:00"))
    if taken is None:
        flags.append("no_time")
    elif taken < first_seen - timedelta(hours=1):
        flags.append("photo_before_alert")
    elif now_utc is not None and taken > now_utc + timedelta(minutes=10):
        flags.append("photo_time_in_future")
    if seen_hash:
        flags.append("photo_reused")
    return km, flags, taken


def grade(report_km, photo_flags_list, n_photos):
    """strong = at the fire with clean photos; weak = some doubt; none = no proof."""
    all_flags = sorted({f for fl in photo_flags_list for f in fl})
    if n_photos == 0:
        all_flags.append("no_photo")
    bad = {"far_from_fire", "outside_cell", "photo_before_alert", "photo_reused", "photo_time_in_future"}
    if n_photos == 0 or (report_km is None and all(("no_location" in fl) for fl in photo_flags_list)):
        return "none", all_flags
    if bad & set(all_flags):
        return "weak", all_flags
    if any("no_location" in fl or "no_time" in fl for fl in photo_flags_list):
        return "weak", all_flags
    return "strong", all_flags
