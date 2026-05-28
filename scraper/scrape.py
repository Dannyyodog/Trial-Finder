"""Orchestrator: runs every clinic module under per-clinic isolation, validates
every returned study, and writes docs/studies.json — but only if at least one
clinic produced data and the combined study count is non-zero.

Per-clinic isolation rules (Phase 3 §1a):
- Each clinic runs inside try/except. A clinic raising an exception is logged
  with full traceback + URL context and counted as FAIL; remaining clinics still
  run.
- A clinic returning [] is a legitimate "no current studies" — counted as OK.
- docs/studies.json is written iff at least one clinic succeeded AND the
  combined study count across successful clinics is > 0 (all-empty-from-all-OK
  is treated as suspicious DOM drift and refuses to write).
- Exit code 0 only if every clinic succeeded. Any failure exits non-zero, even
  when the file was written — that's how the Action stays red on partial
  failure while the data still updates for what worked.

Usage: python scraper/scrape.py
"""

from __future__ import annotations

import importlib
import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

# Allow `python scraper/scrape.py` from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scraper.common import now_iso, validate_study  # noqa: E402


OUTPUT_PATH = REPO_ROOT / "docs" / "studies.json"


# Each entry is (display name, module path). The orchestrator imports the
# module lazily so a broken import in one clinic doesn't crash the whole run.
CLINIC_MODULES: list[tuple[str, str]] = [
    ("Spaulding Clinical",   "scraper.clinics.spaulding"),
    ("Fortrea Madison",      "scraper.clinics.fortrea_madison"),
    ("Nucleus St. Paul",     "scraper.clinics.nucleus_stpaul"),
    ("ICON Lenexa",          "scraper.clinics.icon_lenexa"),
    ("Celerion Lincoln",     "scraper.clinics.celerion_lincoln"),
    ("AbbVie Grayslake",     "scraper.clinics.abbvie_grayslake"),
]


@dataclass
class ClinicResult:
    name: str
    ok: bool
    count: int
    error: str | None = None  # short one-line summary for the table


def _run_clinic(name: str, module_path: str) -> tuple[ClinicResult, list[dict]]:
    """Run one clinic. Catches and logs everything. Never raises."""
    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        traceback.print_exc()
        return ClinicResult(name, ok=False, count=0,
                            error=f"import failed: {e}"), []
    if not hasattr(module, "scrape"):
        return ClinicResult(name, ok=False, count=0,
                            error="module has no scrape() function"), []
    try:
        studies = module.scrape()
    except Exception as e:
        print(f"[{name}] FAILURE — exception during scrape():", file=sys.stderr)
        traceback.print_exc()
        return ClinicResult(name, ok=False, count=0,
                            error=f"{type(e).__name__}: {e}"), []
    if not isinstance(studies, list):
        return ClinicResult(name, ok=False, count=0,
                            error=f"scrape() returned {type(studies).__name__}, expected list"), []
    return ClinicResult(name, ok=True, count=len(studies)), studies


def _print_summary(results: list[ClinicResult],
                   total_studies: int,
                   wrote_file: bool,
                   exit_code: int) -> None:
    """Print the spec §1a summary table to stdout."""
    name_w = max((len(r.name) for r in results), default=10)
    print()
    print("=" * (name_w + 30))
    for r in results:
        status = "OK" if r.ok else "FAIL"
        if r.ok:
            print(f"  {r.name:<{name_w}}  {status:<5} {r.count} studies")
        else:
            print(f"  {r.name:<{name_w}}  {status:<5} ({r.error})")
    print("-" * (name_w + 30))
    ok_n = sum(1 for r in results if r.ok)
    fail_n = sum(1 for r in results if not r.ok)
    wrote = (
        f"Wrote docs/studies.json."
        if wrote_file
        else "DID NOT write docs/studies.json (kept previous version)."
    )
    fail_clause = f" ({fail_n} failure{'s' if fail_n != 1 else ''})." if fail_n else "."
    print(
        f"  {ok_n} of {len(results)} clinics succeeded; "
        f"{total_studies} studies total. {wrote} "
        f"Exiting {exit_code}{fail_clause}"
    )


def main() -> int:
    results: list[ClinicResult] = []
    all_studies: list[dict] = []

    for name, module_path in CLINIC_MODULES:
        print(f"--- {name} ({module_path}) ---")
        result, studies = _run_clinic(name, module_path)
        results.append(result)
        if result.ok:
            all_studies.extend(studies)

    # Validate every study from successful clinics.
    invalid = 0
    for s in all_studies:
        problems = validate_study(s)
        if problems:
            invalid += 1
            print(f"[ERROR] invalid study {s.get('id', '<no id>')}: {problems}",
                  file=sys.stderr)
    if invalid:
        # Any validation problem is a schema-drift bug we don't want shipping.
        # Refuse to write — but the failing clinic(s) still appear as OK in the
        # table because they didn't raise. Mark them as FAIL post-hoc for the
        # summary's exit-code computation by treating the whole run as failure.
        print(f"[ERROR] {invalid} invalid study/studies after isolation pass.",
              file=sys.stderr)
        _print_summary(results, len(all_studies),
                       wrote_file=False, exit_code=6)
        return 6

    ok_any = any(r.ok for r in results)
    all_ok = all(r.ok for r in results)
    total = len(all_studies)
    # Write decision per spec §1a: need ≥1 success AND combined count > 0.
    wrote_file = ok_any and total > 0
    if wrote_file:
        payload = {
            "generated_at": now_iso(),
            "clinic_count": sum(1 for r in results if r.ok and r.count > 0),
            "study_count": total,
            "studies": all_studies,
        }
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    exit_code = 0 if all_ok else 1
    if ok_any and not total:
        # Every successful clinic returned []. Spec calls this suspicious.
        print("[WARN] every successful clinic returned zero studies — refusing "
              "to write docs/studies.json (treating as collective DOM drift).",
              file=sys.stderr)
        exit_code = max(exit_code, 1)
    if not ok_any:
        # Every single clinic failed → loudest possible signal.
        exit_code = max(exit_code, 5)

    _print_summary(results, total, wrote_file, exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
