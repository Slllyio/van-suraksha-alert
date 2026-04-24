"""Generate one Obsidian note per forest division from the live
``/api/v2/division-overview`` endpoint. Each note contains:

- YAML frontmatter (name, center_lat/lon, alert counts, confidence tier)
- Today's alert snapshot
- Wikilinks to today's daily brief + model card + back-link to the
  division index

Typical usage (after the daily pipeline finishes)::

    python scripts/export_obsidian_divisions.py            # uses today
    python scripts/export_obsidian_divisions.py --date 2026-04-24
    python scripts/export_obsidian_divisions.py \\
        --backend http://localhost:8790

Never overwrites hand-edited officer content — the script writes an
``auto-section`` between HTML comments. If the target note exists and
has hand-written content outside the auto-section, that content is
preserved.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT_DIVISIONS = ROOT / "obsidian-vault" / "03-Divisions"

AUTO_START = "<!-- auto:division-stats START -->"
AUTO_END = "<!-- auto:division-stats END -->"
_AUTO_RE = re.compile(
    re.escape(AUTO_START) + r"[\s\S]*?" + re.escape(AUTO_END),
    flags=re.MULTILINE,
)
_FRONTMATTER_RE = re.compile(r"^---\n[\s\S]*?\n---\n", flags=re.MULTILINE)


def fetch_divisions(backend: str, target_date: str | None) -> list[dict]:
    qs = f"?date={urllib.parse.quote(target_date)}" if target_date else ""
    url = f"{backend.rstrip('/')}/api/v2/division-overview{qs}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    data = payload.get("data") or {}
    if isinstance(data, list):
        return data
    return list(data.get("divisions") or [])


def sanitize_name(name: str) -> str:
    """Obsidian accepts most chars but windows filesystem bans < > : " / \\ | ? *."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def render_frontmatter(div: dict, target_date: str) -> str:
    name = div.get("name") or "Unknown"
    conf = div.get("confidence") or "MEDIUM"
    critical = int(div.get("critical") or 0)
    alert = int(div.get("alert") or 0)
    watch = int(div.get("watch") or 0)
    total = int(div.get("total") or (critical + alert + watch))
    center_lat = div.get("center_lat")
    center_lon = div.get("center_lon")
    return (
        "---\n"
        f"division: {name}\n"
        f"confidence: {conf}\n"
        f"critical: {critical}\n"
        f"alert: {alert}\n"
        f"watch: {watch}\n"
        f"total-alerts: {total}\n"
        f"mean-risk: {float(div.get('mean_risk') or 0.0):.4f}\n"
        f"max-risk: {float(div.get('max_risk') or 0.0):.4f}\n"
        f"hawkes-high-pct: {float(div.get('hawkes_high_pct') or 0.0):.2f}\n"
        f"n-cold-start: {int(div.get('n_cold_start') or 0)}\n"
        f"silent-in-danger: {bool(div.get('silent_in_danger'))}\n"
        f"center-lat: {center_lat if center_lat is not None else 'null'}\n"
        f"center-lon: {center_lon if center_lon is not None else 'null'}\n"
        f"last-updated: {target_date}\n"
        "tags: [division, forest, mp]\n"
        "---\n\n"
    )


def render_auto_block(div: dict, target_date: str) -> str:
    name = div.get("name") or "Unknown"
    conf = div.get("confidence") or "MEDIUM"
    critical = int(div.get("critical") or 0)
    alert = int(div.get("alert") or 0)
    watch = int(div.get("watch") or 0)
    total = int(div.get("total") or (critical + alert + watch))
    organic = int(div.get("n_critical_organic") or 0)
    promoted = int(div.get("n_critical_floor_promoted") or 0)
    cold_start = int(div.get("n_cold_start") or 0)

    tier_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(conf, "⚪")

    return (
        f"{AUTO_START}\n"
        f"## Alert snapshot — {target_date}\n\n"
        f"- **Confidence tier:** {tier_emoji} {conf}\n"
        f"- **🔴 CRITICAL:** {critical}"
        f" ({organic} model-native, {promoted} floor-promoted)\n"
        f"- **🟠 ALERT:** {alert}\n"
        f"- **🟡 WATCH:** {watch}\n"
        f"- **Total:** {total}\n"
        f"- **Cold-start cells:** {cold_start} "
        f"(see [[../04-Model/Known Weaknesses|cold-start blind spot]])\n"
        f"- **Mean risk:** {float(div.get('mean_risk') or 0.0):.4f}\n"
        f"- **Max risk:** {float(div.get('max_risk') or 0.0):.4f}\n"
        f"- **Hawkes-high %:** {float(div.get('hawkes_high_pct') or 0.0):.1f}%\n\n"
        f"## Links\n\n"
        f"- Today's brief: [[../02-Operations/Daily/{target_date}]]\n"
        f"- Model: [[../04-Model/v17.5 Model Card]]\n"
        f"- Home: [[../INDEX]]\n"
        f"{AUTO_END}\n"
    )


def render_new_note(div: dict, target_date: str) -> str:
    name = div.get("name") or "Unknown"
    return (
        render_frontmatter(div, target_date)
        + f"# {name} Forest Division\n\n"
        f"> Operator-edited notes go **above** the auto-section. Anything "
        f"inside `<!-- auto:division-stats ... -->` is overwritten by\n"
        f"> `scripts/export_obsidian_divisions.py` each daily run.\n\n"
        "## Officer notes\n\n"
        "- _(add field observations, contacts, vehicle status here)_\n\n"
        + render_auto_block(div, target_date)
    )


def update_existing_note(existing: str, div: dict, target_date: str) -> str:
    """Replace the auto-section and refresh the frontmatter; preserve the
    rest of the note verbatim (officer-edited content)."""
    new_frontmatter = render_frontmatter(div, target_date)
    if _FRONTMATTER_RE.match(existing):
        body = _FRONTMATTER_RE.sub(new_frontmatter, existing, count=1)
    else:
        body = new_frontmatter + existing

    new_auto = render_auto_block(div, target_date)
    if _AUTO_RE.search(body):
        body = _AUTO_RE.sub(new_auto, body, count=1)
    else:
        body = body.rstrip() + "\n\n" + new_auto
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--backend", default="http://localhost:8790")
    parser.add_argument("--out-dir", default=str(VAULT_DIVISIONS))
    args = parser.parse_args(argv)

    try:
        divisions = fetch_divisions(args.backend, args.date)
    except urllib.error.URLError as exc:
        print(
            f"ERROR: backend unreachable at {args.backend}: {exc.reason}",
            file=sys.stderr,
        )
        return 2

    if not divisions:
        print("WARN: backend returned 0 divisions; nothing to write")
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for div in divisions:
        name = div.get("name") or "Unknown"
        filename = f"{sanitize_name(name)}.md"
        target = out_dir / filename
        if target.exists():
            try:
                existing = target.read_text(encoding="utf-8")
                body = update_existing_note(existing, div, args.date)
            except OSError as exc:
                print(f"  [{name}] read failed: {exc}; will rewrite from scratch")
                body = render_new_note(div, args.date)
        else:
            body = render_new_note(div, args.date)
        target.write_text(body, encoding="utf-8")
        written += 1

    print(f"wrote {written} division notes to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
