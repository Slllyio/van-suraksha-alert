#!/usr/bin/env python3
"""
One-shot offline AI setup.

Waits for Qdrant and Ollama to be ready, pulls required models,
runs knowledge ingestion, and verifies with a test query.

Usage:
    python scripts/setup_offline.py

Prerequisites:
    docker compose --profile ai up -d
"""

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text:v1.5"
CHAT_MODEL = "llama3.2:3b"


def wait_for_service(url: str, name: str, timeout: int = 120) -> bool:
    """Wait for a service to become healthy."""
    log.info("Waiting for %s at %s (timeout: %ds)...", name, url, timeout)
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code < 500:
                log.info("%s is ready (%.1fs)", name, time.time() - start)
                return True
        except requests.ConnectionError:
            pass
        time.sleep(2)
    log.error("%s not reachable after %ds", name, timeout)
    return False


def pull_model(ollama_url: str, model: str) -> bool:
    """Pull an Ollama model if not already available."""
    log.info("Checking model: %s", model)
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=10)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        if model in models or model.split(":")[0] in [m.split(":")[0] for m in models]:
            log.info("Model %s already available", model)
            return True
    except Exception as e:
        log.debug("Could not check models: %s", e)

    log.info("Pulling model %s (this may take several minutes)...", model)
    try:
        resp = requests.post(
            f"{ollama_url}/api/pull",
            json={"name": model, "stream": False},
            timeout=1800,  # 30 min for large models
        )
        resp.raise_for_status()
        log.info("Model %s pulled successfully", model)
        return True
    except Exception as e:
        log.error("Failed to pull model %s: %s", model, e)
        return False


def run_ingest(qdrant_url: str, ollama_url: str) -> bool:
    """Run the knowledge ingestion script."""
    log.info("Running knowledge ingestion...")
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "ingest_fire_knowledge.py"),
        "--qdrant-url", qdrant_url,
        "--ollama-url", ollama_url,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, cwd=str(ROOT),
        )
        if result.returncode == 0:
            log.info("Ingestion completed successfully")
            # Print last few lines of output
            for line in result.stdout.strip().split("\n")[-5:]:
                log.info("  %s", line)
            return True
        else:
            log.error("Ingestion failed:\n%s", result.stderr[-500:])
            return False
    except subprocess.TimeoutExpired:
        log.error("Ingestion timed out after 10 minutes")
        return False
    except Exception as e:
        log.error("Ingestion error: %s", e)
        return False


def verify_query(qdrant_url: str, ollama_url: str) -> bool:
    """Run a test query to verify the RAG pipeline works end-to-end."""
    log.info("Running verification query...")
    sys.path.insert(0, str(ROOT))
    try:
        from src.analysis.local_rag import LocalRAGEngine

        rag = LocalRAGEngine(qdrant_url=qdrant_url, ollama_url=ollama_url)

        # Test search
        results = rag.search("What is FWI?", limit=3)
        if not results:
            log.error("Search returned no results — ingestion may have failed")
            return False
        log.info("Search OK: %d results, top score: %.3f", len(results), results[0]["score"])

        # Test chat (short response)
        response = rag.chat("What is FWI? Answer in one sentence.")
        if not response or len(response) < 10:
            log.error("Chat returned empty/short response: %s", response)
            return False
        log.info("Chat OK: %s", response[:120])

        return True
    except Exception as e:
        log.error("Verification failed: %s", e)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="One-shot offline AI setup (Qdrant + Ollama)"
    )
    parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--timeout", type=int, default=120, help="Service wait timeout (seconds)")
    parser.add_argument("--skip-pull", action="store_true", help="Skip model pulling")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip knowledge ingestion")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    log.info("=== Offline AI Setup ===")

    # Step 1: Wait for services
    qdrant_health = f"{args.qdrant_url}/healthz"
    ollama_health = args.ollama_url

    if not wait_for_service(qdrant_health, "Qdrant", args.timeout):
        log.error("Start Qdrant: docker compose --profile ai up -d qdrant")
        sys.exit(1)

    if not wait_for_service(ollama_health, "Ollama", args.timeout):
        log.error("Start Ollama: docker compose --profile ai up -d ollama")
        sys.exit(1)

    # Step 2: Pull models
    if not args.skip_pull:
        if not pull_model(args.ollama_url, EMBED_MODEL):
            log.error("Failed to pull embedding model")
            sys.exit(1)
        if not pull_model(args.ollama_url, CHAT_MODEL):
            log.error("Failed to pull chat model")
            sys.exit(1)
    else:
        log.info("Skipping model pull (--skip-pull)")

    # Step 3: Run ingestion
    if not args.skip_ingest:
        if not run_ingest(args.qdrant_url, args.ollama_url):
            log.error("Knowledge ingestion failed")
            sys.exit(1)
    else:
        log.info("Skipping ingestion (--skip-ingest)")

    # Step 4: Verify
    if not verify_query(args.qdrant_url, args.ollama_url):
        log.warning("Verification query failed — RAG may not be fully functional")
        sys.exit(1)

    log.info("=== Offline AI Setup Complete ===")
    log.info("The AI assistant is ready. Open the JvalaNetra dashboard to chat.")


if __name__ == "__main__":
    main()
