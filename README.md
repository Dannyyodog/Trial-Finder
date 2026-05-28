# Trial Finder

A tiny tool for finding **paid healthy-volunteer clinical studies**, filtered by the things
that actually matter to a paid participant — payout, overnight stays, follow-up visits — on
top of medical filters (age, sex, spinal-tap / lumbar-puncture flags, childbearing /
contraception flags). Phase 1 covers one clinic: **Spaulding Clinical** (West Bend, WI).

## Architecture
```
scraper (Python)  →  docs/studies.json (committed)  →  docs/index.html (fetches ./studies.json)
```
Same repo = same origin = no CORS = works on a phone. ClinicalTrials.gov is intentionally on
the back burner because it has no payout data.

## Run the scraper (manual, Phase 1)
```
pip install -r scraper/requirements.txt
python scraper/scrape.py
```
The scraper hits the live Spaulding site (one request/second, descriptive User-Agent, honors
robots.txt) and overwrites `docs/studies.json` — but only if it found a non-empty, fully
valid set of studies. A broken scrape exits non-zero and leaves the last good file in place.

## Preview the frontend locally
```
cd docs && python -m http.server 8000
```
Then open <http://localhost:8000>. (GitHub Pages will be configured to serve from `/docs`.)

## What's in this repo
- `CLAUDE.md` — operating rules for Claude Code (auto-loaded each session).
- `progress.md` — reverse-chronological log of what's been done.
- `specs/PHASE1_trial_finder_build.md` — the build spec for this phase.
- `docs/` — static frontend + data file + the active phase's checklist.
- `scraper/` — Python scraper (orchestrator + per-clinic modules + shared helpers).
