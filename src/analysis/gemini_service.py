"""
VanAagni Gemini LLM Service
============================
Unified interface for Google Gemini API calls across all AI modules:
  - VLM Auditor (Vision)
  - Forest Chat (Text RAG)
  - AI Dispatcher (Translation)
  - Anomaly Analysis (Structured output)

Requires: GEMINI_API_KEY environment variable.
Falls back to offline heuristics if API key is missing.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

log = logging.getLogger(__name__)

_client = None
_model_text = None
_model_vision = None


def _ensure_client():
    """Lazy-initialize Gemini client on first use."""
    global _client, _model_text, _model_vision
    if _client is not None:
        return True

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("GEMINI_API_KEY not set — AI features will use offline heuristics.")
        return False

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        _client = genai
        _model_text = genai.GenerativeModel("gemini-2.0-flash")
        _model_vision = genai.GenerativeModel("gemini-2.0-flash")
        log.info("Gemini API initialized (model: gemini-2.0-flash)")
        return True
    except Exception as e:
        log.error(f"Failed to initialize Gemini: {e}")
        return False


def is_available() -> bool:
    """Check if Gemini API is available."""
    return _ensure_client()


def generate_text(prompt: str, temperature: float = 0.3) -> Optional[str]:
    """Generate text response from Gemini."""
    if not _ensure_client():
        return None
    try:
        response = _model_text.generate_content(
            prompt,
            generation_config={"temperature": temperature, "max_output_tokens": 1024},
        )
        return response.text.strip()
    except Exception as e:
        log.error(f"Gemini text generation failed: {e}")
        return None


def generate_json(prompt: str, temperature: float = 0.1) -> Optional[Dict]:
    """Generate structured JSON response from Gemini."""
    if not _ensure_client():
        return None
    try:
        full_prompt = (
            prompt
            + "\n\nIMPORTANT: Return ONLY valid JSON, no markdown fences, no extra text."
        )
        response = _model_text.generate_content(
            full_prompt,
            generation_config={"temperature": temperature, "max_output_tokens": 1024},
        )
        text = response.text.strip()
        # Strip markdown fences if model adds them despite instructions
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
        return json.loads(text)
    except json.JSONDecodeError as e:
        log.error(f"Gemini returned invalid JSON: {e}")
        return None
    except Exception as e:
        log.error(f"Gemini JSON generation failed: {e}")
        return None


def analyze_image(image_path: Path, prompt: str) -> Optional[str]:
    """Analyze an image using Gemini Vision."""
    if not _ensure_client():
        return None
    try:
        import PIL.Image
        img = PIL.Image.open(image_path)
        response = _model_vision.generate_content(
            [prompt, img],
            generation_config={"temperature": 0.2, "max_output_tokens": 1024},
        )
        return response.text.strip()
    except Exception as e:
        log.error(f"Gemini vision analysis failed: {e}")
        return None


def analyze_image_json(image_path: Path, prompt: str) -> Optional[Dict]:
    """Analyze an image and return structured JSON."""
    if not _ensure_client():
        return None
    try:
        import PIL.Image
        img = PIL.Image.open(image_path)
        full_prompt = (
            prompt
            + "\n\nIMPORTANT: Return ONLY valid JSON, no markdown fences, no extra text."
        )
        response = _model_vision.generate_content(
            [full_prompt, img],
            generation_config={"temperature": 0.2, "max_output_tokens": 1024},
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        return json.loads(text.strip())
    except Exception as e:
        log.error(f"Gemini vision JSON failed: {e}")
        return None


def translate_to_hindi(text: str) -> Optional[str]:
    """Translate English text to Hindi using Gemini."""
    if not _ensure_client():
        return None
    prompt = (
        "You are a professional translator for Indian Forest Service communications. "
        "Translate the following tactical fire alert dispatch order from English to Hindi. "
        "Keep technical terms, numbers, coordinates, and unit names in English. "
        "Use formal Hindi (Devanagari script). Return ONLY the Hindi translation.\n\n"
        f"{text}"
    )
    return generate_text(prompt, temperature=0.1)
