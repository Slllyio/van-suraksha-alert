#!/usr/bin/env python3
"""
Ingest fire knowledge into Qdrant for local RAG.

Seeds the vector database with:
  - Fire SOPs and protocols
  - FWI interpretation guide
  - Species fire risk profiles (teak, tendu, mahua, bamboo)
  - Guna Division geography
  - Project documentation
  - Recent alert summaries

Usage:
    python scripts/ingest_fire_knowledge.py
    python scripts/ingest_fire_knowledge.py --alerts-days 180
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATA_LAKE = ROOT / "data_lake"
DOCS_DIR = ROOT / "docs"


# ── Embedded Knowledge Base ──────────────────────────────────────────────────
# These are ingested as text chunks so the LLM can reference them.

FIRE_SOP = """
STANDARD OPERATING PROCEDURE: FOREST FIRE RESPONSE — GUNA DIVISION

1. DETECTION PHASE
- Monitor FIRMS VIIRS satellite alerts (375m resolution, 6-hourly updates)
- Check FWI dashboard daily during fire season (Feb-Jun)
- Report any smoke sighting to Range Forest Officer immediately
- Verify satellite detections via ground patrol within 2 hours

2. ALERT CLASSIFICATION
- RED (Operational): FWI > 38 OR FRP > 50 MW — immediate response required
- ORANGE (Critical): FWI 24-38 OR FRP 20-50 MW — enhanced monitoring
- YELLOW (Watch): FWI 12-24 — routine patrols increased
- GREEN (Advisory): FWI < 12 — normal operations

3. RESPONSE PROTOCOL
- Beat Guard: Report to RFO, establish perimeter, alert nearby villages
- RFO: Mobilize fire crew (minimum 15 persons), establish Counter Fire Lines (CFL)
- DFO: Coordinate across ranges, request aerial support if spread > 50 ha
- CFL Priority: P1 lines along settlements, P2 along teak plantations

4. POST-FIRE ASSESSMENT
- Document burn scar extent using Sentinel-2 imagery (NBR index)
- Estimate biomass loss and CO2 emissions
- Update fire history database for future risk modeling
- Submit Form-5 fire report to State Forest Department within 48 hours

5. PREVENTION
- Controlled burns before fire season (January-February)
- Maintain 10m firebreaks along roads and settlements
- Community awareness campaigns in forest-fringe villages
- Monitor tendu leaf collection areas (high fire risk during collection season)
"""

FWI_GUIDE = """
FIRE WEATHER INDEX (FWI) INTERPRETATION GUIDE — GUNA DIVISION

The Canadian FWI System rates fire danger using weather observations:
- Temperature, relative humidity, wind speed, and 24-hour precipitation

COMPONENT BREAKDOWN:
1. FFMC (Fine Fuel Moisture Code): Moisture of surface litter (1-101)
   - > 87: Surface fuels ignite easily from any spark
   - 70-87: Moderate drying, fires possible in afternoon
   - < 70: Fuels too moist for sustained burning

2. DMC (Duff Moisture Code): Moisture of decomposed organic material (0-300+)
   - > 60: Deep duff layer will sustain fire even after rain
   - 20-60: Moderate drought, fire possible in duff
   - < 20: Duff too wet to burn

3. DC (Drought Code): Long-term drought indicator (0-800+)
   - > 300: Extreme drought, deep burning likely
   - 100-300: Moderate drought
   - < 100: Recent significant rainfall

4. ISI (Initial Spread Index): Expected fire spread rate (0-50+)
   - Combines FFMC and wind speed
   - > 12: Rapid spread, difficult to control

5. BUI (Buildup Index): Total fuel available (0-200+)
   - Combines DMC and DC
   - > 80: Heavy fuel loading for intense fires

6. FWI (Fire Weather Index): General fire intensity (0-100+)
   - < 5: LOW — fires unlikely
   - 5-12: MODERATE — fires possible in open areas
   - 12-24: HIGH — forest fires likely, enhanced patrols
   - 24-38: VERY HIGH — aggressive fire behavior, crews on standby
   - > 38: EXTREME — explosive fire growth, evacuations possible

GUNA DIVISION SPECIFICS:
- Dry deciduous forest: Peak fire season March-June
- Monsoon (July-September): FWI drops to < 5
- Post-monsoon (October-November): Controlled burn window
- Winter (December-February): Moderate risk from agricultural burning
- Historical extreme events: Mean 45 extreme days/year (2013-2025)
"""

SPECIES_FIRE_RISK = """
TREE SPECIES FIRE RISK PROFILES — GUNA DIVISION DRY DECIDUOUS FOREST

1. TEAK (Tectona grandis)
- Fire resistance: HIGH (thick bark, deciduous habit)
- Fire risk factor: MODERATE — leaf litter creates surface fuel load
- Dry season behavior: Drops leaves Dec-Feb, creating 5-15 cm litter layer
- Recovery: Survives most surface fires; crown fire damages canopy
- Management: Annual controlled burn of teak plantations reduces fuel load
- Economic value: Rs 15,000-40,000 per cubic meter (highest priority protection)

2. TENDU (Diospyros melanoxylon)
- Fire resistance: LOW-MODERATE
- Fire risk factor: VERY HIGH — tendu leaf collection involves deliberate burning
- Collection season: April-May (coincides with peak fire season)
- Cultural practice: Collectors burn understory to facilitate leaf picking
- Impact: 40% of forest fires in MP linked to tendu collection
- Management: Coordinate with tendu contractors, designated collection zones

3. MAHUA (Madhuca longifolia)
- Fire resistance: MODERATE
- Fire risk factor: HIGH — fallen flowers are alcohol source, collection involves fire
- Flowering: March-April (flowers fall and ferment on ground)
- Cultural practice: Night fires for visibility during flower collection
- Impact: Accidental fires from flower collection camps
- Management: Designate mahua collection points away from dense forest

4. BAMBOO (Dendrocalamus strictus)
- Fire resistance: VERY LOW
- Fire risk factor: EXTREME — bamboo is highly combustible, creates fire ladders
- Dry season behavior: Bamboo culms crack and splinter, creating kindling
- Gregarious flowering: Every 40-50 years, mass die-off creates extreme fire hazard
- Impact: Bamboo fires spread fastest, enable crown fire transition
- Management: Firebreaks around bamboo patches, priority for controlled burns

5. SAL (Shorea robusta) — limited in Guna, found in wetter microhabitats
- Fire resistance: MODERATE-HIGH
- Fire risk: LOW in normal conditions, HIGH in extreme drought
- Management: Maintain moisture corridors along sal patches
"""

GUNA_GEOGRAPHY = """
GUNA FOREST DIVISION — GEOGRAPHIC CONTEXT

LOCATION: Central Madhya Pradesh, India
- District: Guna (part of Guna-Ashoknagar-Shivpuri landscape)
- Latitude: 23.80°N to 24.95°N
- Longitude: 76.45°E to 77.85°E
- Total area: ~2,144 sq km (214,400 hectares)

ADMINISTRATIVE STRUCTURE:
- Division: Guna Forest Division (under CCF Bhopal)
- Ranges: 8 (Bamori, Aron, Raghogarh, Chachoda, Myana, Binaganj, Kumbhraj, Fatehgarh)
- Beats: 139 patrol beats across all ranges
- Staff: ~150 forest guards, 8 Range Officers, 1 DFO

TERRAIN:
- Vindhyan plateau: 400-600m elevation
- Gentle undulations with rocky outcrops (trap basalt)
- Major rivers: Parvati, Betwa tributaries
- Soil: Black cotton soil (vertisol) in valleys, laterite on plateaus

FOREST TYPE: 5A/C1b — Dry Deciduous (Champion & Seth classification)
- Canopy density: 20-60% (degraded in many areas)
- Dominant species: Teak, Tendu, Mahua, Salai, Bamboo
- Understory: Lantana camara (invasive), seasonal grasses
- Annual rainfall: 800-1100mm (concentrated July-September)

FIRE SEASON:
- Peak: March-June (hot, dry, wind speeds 15-25 km/h)
- Secondary: November (post-monsoon agricultural burning)
- Low risk: July-October (monsoon), December-February (cool, moderate humidity)

KEY FIRE CORRIDORS:
- Bamori-Aron interface: Dense bamboo understory, historical hotspot
- Raghogarh hills: Rocky terrain limits access for fire crews
- Chachoda-Myana: Tendu collection belt, highest human-caused fire rate
- River valleys: Wind channeling increases fire spread in dry season

INFRASTRUCTURE:
- Fire watchtowers: 12 (manned during fire season)
- Fire stations: 3 (Guna, Aron, Raghogarh)
- Water sources: 45 check dams, seasonal streams
- Road density: 0.8 km/sq km (low — access challenges for fire response)
"""


def ingest_embedded_knowledge(rag) -> int:
    """Ingest the hardcoded fire knowledge base."""
    total = 0

    knowledge_items = [
        (FIRE_SOP, {"source": "fire_sop", "category": "protocol"}),
        (FWI_GUIDE, {"source": "fwi_guide", "category": "technical"}),
        (SPECIES_FIRE_RISK, {"source": "species_fire_risk", "category": "ecology"}),
        (GUNA_GEOGRAPHY, {"source": "guna_geography", "category": "geography"}),
    ]

    for text, metadata in knowledge_items:
        n = rag.ingest_text(text, metadata)
        total += n
        log.info("  %s: %d chunks", metadata["source"], n)

    return total


def ingest_project_docs(rag) -> int:
    """Ingest project documentation files."""
    total = 0
    doc_files = [
        DOCS_DIR / "ARCHITECTURE.md",
        DOCS_DIR / "VANAAGNI_SYSTEM_NOTE.md",
        ROOT / "README.md",
    ]

    for doc_path in doc_files:
        if doc_path.exists():
            n = rag.ingest_file(doc_path)
            total += n
            log.info("  %s: %d chunks", doc_path.name, n)
        else:
            log.debug("  %s: not found, skipping", doc_path.name)

    return total


def ingest_alert_summaries(rag, days: int = 180) -> int:
    """Ingest recent alert summaries from the data lake."""
    total = 0
    alerts_dir = DATA_LAKE / "alerts"
    if not alerts_dir.exists():
        log.warning("Alerts directory not found: %s", alerts_dir)
        return 0

    cutoff = datetime.now() - timedelta(days=days)

    for alert_file in sorted(alerts_dir.glob("*_alert.json")):
        # Parse date from filename (e.g., 2025-04-22_alert.json)
        try:
            date_str = alert_file.stem.split("_alert")[0]
            alert_date = datetime.strptime(date_str, "%Y-%m-%d")
            if alert_date < cutoff:
                continue
        except ValueError:
            if alert_file.name == "latest_alert.json":
                pass  # Always ingest latest
            else:
                continue

        n = rag.ingest_file(alert_file)
        total += n

    log.info("  Alert summaries: %d chunks from %d days", total, days)
    return total


def main():
    parser = argparse.ArgumentParser(
        description="Ingest fire knowledge into Qdrant vector DB"
    )
    parser.add_argument(
        "--alerts-days",
        type=int,
        default=180,
        help="Number of days of alert history to ingest (default: 180)",
    )
    parser.add_argument(
        "--qdrant-url",
        default="",
        help="Qdrant URL (default: from env or http://localhost:6333)",
    )
    parser.add_argument(
        "--ollama-url",
        default="",
        help="Ollama URL (default: from env or http://localhost:11434)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Import after logging setup
    sys.path.insert(0, str(ROOT))
    from src.analysis.local_rag import LocalRAGEngine

    rag = LocalRAGEngine(
        qdrant_url=args.qdrant_url,
        ollama_url=args.ollama_url,
    )

    if not rag.is_available():
        log.error(
            "Local RAG services not available. Start them with:\n"
            "  docker compose --profile ai up -d"
        )
        sys.exit(1)

    log.info("Starting knowledge ingestion...")
    total = 0

    log.info("1. Ingesting fire SOPs and guides...")
    total += ingest_embedded_knowledge(rag)

    log.info("2. Ingesting project documentation...")
    total += ingest_project_docs(rag)

    log.info("3. Ingesting alert summaries (last %d days)...", args.alerts_days)
    total += ingest_alert_summaries(rag, args.alerts_days)

    # Stats
    stats = rag.collection_stats()
    log.info("Ingestion complete!")
    log.info("  Total chunks: %d", total)
    log.info("  Collection: %s", stats)

    # Quick verification
    log.info("4. Verification query...")
    results = rag.search("What is FWI and how is it calculated?", limit=3)
    for r in results:
        log.info("  [%.3f] %s: %s...", r["score"], r["source"], r["text"][:80])

    log.info("OK: %d chunks ingested into '%s'", total, rag.collection)


if __name__ == "__main__":
    main()
