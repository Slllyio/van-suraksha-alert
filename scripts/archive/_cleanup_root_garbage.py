"""
Cleanup root-folder garbage left by broken heredoc/here-string commands.

Scans project root non-recursively. Any file whose name is neither:
  - in the allowlist of known real files/dirs, nor
  - matching a conservative safe-name pattern
gets moved (never deleted) into .trash/2026_04_08/<name>.

Dirs are left alone. This is deliberately conservative: when in doubt, keep.

Usage:
    python scripts/_cleanup_root_garbage.py           # dry run, prints plan
    python scripts/_cleanup_root_garbage.py --apply   # actually move
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# Windows cp1252 cannot print arbitrary Unicode file names; force UTF-8 stdout.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
TRASH = ROOT / ".trash" / "2026_04_08"

# Explicit allowlist of file names that must never be touched.
ALLOWLIST_FILES: set[str] = {
    "CLAUDE.md",
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "requirements.txt",
    "requirements.docker.txt",
    "config.yaml",
    "pyrightconfig.json",
    "mempalace.yaml",
    ".env",
    ".env.example",
    ".gitignore",
    ".gitattributes",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "package-lock.json",
    "register_scheduled_task.ps1",
    "start_dashboard.ps1",
    "fire-threat-model.md",
    "implementation_plan.md",  # will be moved to docs/ later, but keep safe now
    "check_preds.py",
    "dense_threshold_sweep.py",
    "verify_thresholds.py",
    "verify_thresholds_cpu.py",
    "extract_failures.py",
    "entities.json",
}

# Conservative safe-name pattern: must start with [A-Za-z0-9_.], only
# ASCII letters/digits/dot/underscore/dash, and end in a known extension.
SAFE_NAME_RE = re.compile(
    r"^[A-Za-z0-9_.][A-Za-z0-9_.\-]*\."
    r"(py|md|yaml|yml|toml|txt|cfg|ini|json|sh|bat|ps1|lock|log|csv|"
    r"parquet|pkl|tif|geojson|png|jpg|jpeg|html|pdf|docx|tex)$"
)

# Explicit junk-name substrings that always mark a file as garbage even if
# the extension pattern matches (defensive backstop for tricky tokens).
JUNK_HINTS: tuple[str, ...] = (
    "{n_pca}",
    "(weather_df",
    "best_thr).astype",
    "list[tuple[float",
    "tuple[datetime",
    "np.percentile",
    "pd.DataFrame",
    "Optional[str]",
    "gate_threshold,+",
    "thr).sum(),",
    "best_score",
    "3km,+",
    "grid_id.,",
)


def is_garbage(name: str) -> bool:
    """Decide whether a root-level file name is garbage."""
    if name in ALLOWLIST_FILES:
        return False
    for hint in JUNK_HINTS:
        if hint in name:
            return True
    return not SAFE_NAME_RE.match(name)


def plan() -> list[Path]:
    """Return ordered list of root files flagged as garbage."""
    victims: list[Path] = []
    for entry in sorted(ROOT.iterdir()):
        if not entry.is_file():
            continue
        if is_garbage(entry.name):
            victims.append(entry)
    return victims


def apply_moves(victims: list[Path]) -> None:
    TRASH.mkdir(parents=True, exist_ok=True)
    for src in victims:
        dst = TRASH / src.name
        # Avoid clobbering if re-run
        if dst.exists():
            stem, sep, suffix = src.name.partition(".")
            dst = TRASH / f"{stem}_{id(src)}{sep}{suffix}"
        shutil.move(str(src), str(dst))
        print(f"moved: {src.name} -> {dst.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move files. Without this, prints the plan only.",
    )
    args = parser.parse_args()

    victims = plan()
    if not victims:
        print("No garbage found at repo root.")
        return 0

    print(f"Found {len(victims)} garbage files at repo root:")
    for v in victims:
        print(f"  - {v.name}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to move them into .trash/2026_04_08/")
        return 0

    print(f"\nMoving into {TRASH.relative_to(ROOT)}/ ...")
    apply_moves(victims)
    print(f"\nDone. Review {TRASH.relative_to(ROOT)}/ before deleting anything.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
