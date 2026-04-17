"""GDELT article-level geocoding pilot: can we extract village-level locations
from fire news articles to upgrade district-centroid coordinates?

Pilot design: fetch 50 fire-season GDELT source URLs, extract location names
via regex + keyword matching, geocode via Nominatim, measure upgrade rate.

Pass criterion: >= 30% of articles yield village-level coordinates (vs 0% now).
"""
from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

ROOT = Path(__file__).resolve().parents[1]
GDELT_PATH = ROOT / "data_lake" / "weak_labels" / "gdelt_mp_fire_events.parquet"

MP_DISTRICTS = [
    "bhopal", "indore", "jabalpur", "gwalior", "ujjain", "sagar", "rewa",
    "satna", "chhindwara", "betul", "hoshangabad", "narmadapuram", "seoni",
    "mandla", "balaghat", "dindori", "shahdol", "anuppur", "sidhi",
    "singrauli", "panna", "damoh", "katni", "narsinghpur", "raisen",
    "vidisha", "guna", "shivpuri", "sheopur", "morena", "bhind",
    "datia", "tikamgarh", "chhatarpur", "dewas", "dhar", "jhabua",
    "alirajpur", "barwani", "khargone", "khandwa", "burhanpur",
    "mandsaur", "neemuch", "ratlam", "agar", "shajapur", "rajgarh",
    "sehore", "harda", "ashoknagar", "umaria",
]

FIRE_KEYWORDS = re.compile(
    r"\b(forest fire|jungle fire|wildfire|blaze|fire broke out|fire engulf|"
    r"burn[ts]?\b.*forest|fire spread|inferno|fire incident|fire rage|"
    r"आग|जंगल|दावानल|आग लग)",
    re.IGNORECASE,
)

VILLAGE_PATTERN = re.compile(
    r"\b(?:village|gram|gaon|town|tehsil|block|range|near|area of|forest of|"
    r"beat|division)\s+(?:of\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
    re.IGNORECASE,
)


def fetch_article_text(url: str, timeout: int = 15) -> str | None:
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (research bot, fire-prediction project)"
        })
        if r.status_code != 200:
            return None
        from html.parser import HTMLParser
        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.skip = False
            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "header", "footer"):
                    self.skip = True
            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "header", "footer"):
                    self.skip = False
            def handle_data(self, data):
                if not self.skip:
                    self.text.append(data.strip())
        ext = TextExtractor()
        ext.feed(r.text[:50000])
        return " ".join(t for t in ext.text if len(t) > 2)
    except Exception:
        return None


def extract_locations(text: str) -> list[str]:
    matches = VILLAGE_PATTERN.findall(text)
    locations = []
    for m in matches:
        m = m.strip()
        if len(m) < 3 or m.lower() in ("the", "and", "for", "has", "was", "are"):
            continue
        if m.lower() not in [d for d in MP_DISTRICTS]:
            locations.append(m)
    return list(set(locations))


def geocode_nominatim(location: str, state: str = "Madhya Pradesh") -> dict | None:
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", params={
            "q": f"{location}, {state}, India",
            "format": "json",
            "limit": 1,
            "countrycodes": "in",
        }, headers={"User-Agent": "JwalaNetra-fire-research"}, timeout=10)
        if r.status_code != 200:
            return None
        results = r.json()
        if not results:
            return None
        best = results[0]
        lat, lon = float(best["lat"]), float(best["lon"])
        if 21.0 <= lat <= 27.0 and 74.0 <= lon <= 83.0:
            return {"lat": lat, "lon": lon, "display_name": best.get("display_name", ""),
                    "type": best.get("type", "")}
        return None
    except Exception:
        return None


def main() -> int:
    log.info("=== GDELT ARTICLE-LEVEL GEOCODING PILOT ===\n")

    g = pd.read_parquet(GDELT_PATH)
    g["sqldate"] = pd.to_datetime(g["sqldate"].astype(str))
    fire = g[g["sqldate"].dt.month.isin([2, 3, 4, 5])].copy()
    log.info("Fire-season GDELT events: %d, unique URLs: %d", len(fire), fire["source_url"].nunique())

    urls = fire.drop_duplicates("source_url").sample(50, random_state=42)
    log.info("Sampling 50 URLs for pilot\n")

    results = []
    n_fetched = n_fire_relevant = n_locations = n_geocoded = 0

    for i, (_, row) in enumerate(urls.iterrows()):
        url = row["source_url"]
        text = fetch_article_text(url)
        fetched = text is not None and len(text) > 100

        fire_relevant = False
        locs = []
        geocoded_locs = []

        if fetched:
            n_fetched += 1
            fire_relevant = bool(FIRE_KEYWORDS.search(text[:3000]))
            if fire_relevant:
                n_fire_relevant += 1
                locs = extract_locations(text[:5000])
                if locs:
                    n_locations += 1
                    for loc in locs[:3]:
                        geo = geocode_nominatim(loc)
                        if geo:
                            geocoded_locs.append({**geo, "query": loc})
                            n_geocoded += 1
                        time.sleep(1.1)  # Nominatim rate limit

        results.append({
            "url": url,
            "date": row["sqldate"],
            "gdelt_lat": row["action_lat"],
            "gdelt_lon": row["action_lon"],
            "fetched": fetched,
            "fire_relevant": fire_relevant,
            "locations_found": locs,
            "n_locations": len(locs),
            "geocoded": geocoded_locs,
            "n_geocoded": len(geocoded_locs),
        })

        if (i + 1) % 10 == 0:
            log.info("  [%d/50] fetched=%d fire_relevant=%d has_locations=%d geocoded=%d",
                     i + 1, n_fetched, n_fire_relevant, n_locations, n_geocoded)

    log.info("\n=== PILOT RESULTS ===")
    log.info("URLs attempted: 50")
    log.info("Successfully fetched: %d (%.0f%%)", n_fetched, n_fetched / 50 * 100)
    log.info("Fire-relevant (keyword match): %d (%.0f%% of fetched)", n_fire_relevant,
             n_fire_relevant / max(n_fetched, 1) * 100)
    log.info("Has extractable village names: %d (%.0f%% of fire-relevant)", n_locations,
             n_locations / max(n_fire_relevant, 1) * 100)
    log.info("Successfully geocoded to MP: %d (%.0f%% of those with locations)", n_geocoded,
             n_geocoded / max(n_locations, 1) * 100)

    yield_rate = n_geocoded / 50
    log.info("\nOverall yield: %d/50 = %.0f%%", n_geocoded, yield_rate * 100)
    log.info("[%s] Pass criterion: >= 30%% yield", "PASS" if yield_rate >= 0.30 else "FAIL")

    if geocoded_locs := [r for r in results if r["n_geocoded"] > 0]:
        log.info("\nSample geocoded fires:")
        for r in geocoded_locs[:5]:
            for g in r["geocoded"]:
                log.info("  %s -> lat=%.4f lon=%.4f (%s)",
                         g["query"], g["lat"], g["lon"], g.get("display_name", "")[:60])

    out = ROOT / "data_lake" / "weak_labels" / "gdelt_geocode_pilot.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info("\nSaved: %s", out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
