"""Chance a fire VIIRS has stopped seeing is still burning (fire-continuity thread, research/fire-continuity/README.md
"Still burning chance", c18; handed over with Akkshay's yes, 18 Oct 2026). Truth: 1,505 Sentinel-2/Landsat scenes over 865
Ratapani fires taken while VIIRS had missed the fire; held out by season. Hours since the last VIIRS dot carry almost all of
it (AUC 0.74; the full model 0.77), so the card uses the hours table. A "clear, no fire" pass does not mean the fire is out.
Officials' card only; it never holds back or closes an alert."""
from datetime import timedelta

TABLE = [(6, 12, 0.62), (12, 24, 0.33), (24, 48, 0.16), (48, 1e9, 0.09)]


def check(con, iid, now_utc):
    """None while the last VIIRS dot is under 6 h old (the next passes will tell); else {hours_dark, chance, text, note}."""
    from . import firms
    r = con.execute("""SELECT max(acq_utc) FROM detections WHERE incident_id=? AND instrument='VIIRS' AND satellite<>'FSI'
                       AND acq_utc <= ?""", (iid, firms.iso(now_utc))).fetchone()
    if not r or not r[0]:
        return None
    last = firms.parse_utc(r[0])
    h = (now_utc - last).total_seconds() / 3600
    p = next((p for lo, hi, p in TABLE if lo <= h < hi), None)
    if p is None:
        return None
    ist = last + timedelta(hours=5, minutes=30)
    return {"hours_dark": round(h, 1), "chance": p, "last_viirs_utc": r[0],
            "text": f"Not seen by VIIRS since {ist:%d %b %H:%M} IST: about {round(p * 100)}% chance still burning",
            "note": "From 30 m scenes of past Ratapani fires VIIRS had stopped seeing. A pass with no fire does not mean it is out; after 48 h treat it as out."}
