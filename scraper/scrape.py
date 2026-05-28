"""Orchestrator: runs every clinic module, validates every study, and writes
docs/studies.json — but ONLY when the result is non-empty and fully valid.

If anything is wrong (a clinic raises, a study fails validation, zero studies
overall), this exits non-zero WITHOUT touching the existing studies.json. That
way a broken scrape can never clobber the last known-good data.

Usage:
    python scraper/scrape.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python scraper/scrape.py` from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scraper.common import ScraperError, now_iso, validate_study  # noqa: E402
from scraper.clinics import spaulding  # noqa: E402


OUTPUT_PATH = REPO_ROOT / "docs" / "studies.json"

CLINIC_MODULES = [
    ("Spaulding Clinical", spaulding),
]


def main() -> int:
    all_studies: list[dict] = []
    clinic_count = 0
    for name, module in CLINIC_MODULES:
        print(f"--- scraping {name} ---")
        try:
            studies = module.scrape()
        except ScraperError as e:
            print(f"[ERROR] {name} failed: {e}", file=sys.stderr)
            print("Refusing to write docs/studies.json — keeping last good copy.",
                  file=sys.stderr)
            return 2
        except Exception as e:  # any unexpected crash — same policy
            print(f"[ERROR] {name} crashed unexpectedly: {e!r}", file=sys.stderr)
            print("Refusing to write docs/studies.json — keeping last good copy.",
                  file=sys.stderr)
            return 3
        if not isinstance(studies, list):
            print(f"[ERROR] {name}.scrape() returned {type(studies).__name__}, "
                  "expected list.", file=sys.stderr)
            return 4
        clinic_count += 1
        all_studies.extend(studies)

    if not all_studies:
        print("[ERROR] zero studies across all clinics — refusing to write empty file.",
              file=sys.stderr)
        return 5

    # Validate every study before we even consider writing.
    bad = 0
    for s in all_studies:
        problems = validate_study(s)
        if problems:
            bad += 1
            sid = s.get("id", "<no id>")
            print(f"[ERROR] invalid study {sid}: {problems}", file=sys.stderr)
    if bad:
        print(f"[ERROR] {bad} invalid study/studies — refusing to write.",
              file=sys.stderr)
        return 6

    payload = {
        "generated_at": now_iso(),
        "clinic_count": clinic_count,
        "study_count": len(all_studies),
        "studies": all_studies,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {len(all_studies)} studies from {clinic_count} clinics to "
        f"{OUTPUT_PATH.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
