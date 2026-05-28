# Trial Finder — current phase

## Phase 1 — Prove the pipeline (Spaulding only, manual run) — IN PROGRESS
Goal: scraper → docs/studies.json → static frontend reads it, working on desktop + iPhone via
GitHub Pages. No automation yet.

- [x] Repo structure created
- [x] scraper/common.py (schema, validator, $/age parsing, flag detection, robots check)
- [x] scraper/clinics/spaulding.py (live-structure-driven, defensive)
- [x] scraper/scrape.py (validates; refuses to write empty/invalid output)
- [x] docs/index.html (reads ./studies.json; $ sort + payout/nights/visits + age/sex/spinal/childbearing filters)
- [x] docs/studies.json seed committed
- [x] Manual `python scraper/scrape.py` run produces valid studies.json from the live site
- [x] Verified locally via `python -m http.server` in docs/
- [ ] (Owner) GitHub Pages enabled on /docs, confirmed loading on iPhone

## Architecture (the source of truth)
scraper (Python) → docs/studies.json (committed) → docs/index.html fetches ./studies.json.
Same repo = same origin = no CORS = works on iPhone. ClinicalTrials.gov intentionally on back
burner.

## Schema
See SCHEMA_KEYS in scraper/common.py. Every clinic module emits that exact shape. compensation =
integer (top of range) for sorting; compensation_raw = original string; nulls for unknowns, never
guesses.

## Next phases
- Phase 2: GitHub Action runs scrape.py once daily, commits studies.json only when changed.
- Phase 3: add Fortrea Madison module (proves multi-clinic schema), then Nucleus / ICON / others.
