# Trial Finder — Claude Code operating rules

## At the START of every prompt
1. This file is auto-loaded — follow it.
2. Read `progress.md` (reverse-chronological log of what's been done and what's next).
3. Read the active phase spec in `specs/` and `docs/phase_current.md` for the live checklist.

## At the END of every prompt
1. Add a new entry at the TOP of `progress.md`: date, what changed, files touched, anything broken
   or deferred, and the recommended next step.
2. Update the checkboxes in `docs/phase_current.md` to match reality.
3. Never mark something done that you have not actually verified.

## Project architecture (do not drift from this)
scraper (Python) → writes ONE file `docs/studies.json` → static `docs/index.html` fetches
`./studies.json`. Same repo = same origin = no CORS = works on iPhone. ClinicalTrials.gov is
intentionally on the back burner.

## Hard rules
- The scraper must NEVER overwrite `docs/studies.json` with empty or invalid data — fail loud and
  exit non-zero instead.
- Every clinic module emits the exact schema in `scraper/common.py` (SCHEMA_KEYS). Unknown fields
  are `null` — never fabricate values.
- Respect robots.txt; throttle (~1 req/sec); send a descriptive User-Agent.
- Do not add GitHub Actions automation until a Phase 2 spec says so.
- **Per-clinic isolation:** in the multi-clinic orchestrator, any clinic that throws is logged
  loud, skipped, and reported in the run summary; remaining clinics still publish their data.
  The Action exits non-zero on any clinic failure (so it goes red) but does not wipe successful
  clinics' studies from `studies.json`.
