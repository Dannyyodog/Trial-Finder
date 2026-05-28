# Trial Finder — current phase

## Phase 3 — Multi-clinic + state filter + dates UX — IN PROGRESS
Goal: 6 clinic scrapers (5 new), state-based filtering, collapsible cohort schedules, and per-
clinic isolation in the orchestrator.

- [x] schema: state field added; spaulding emits it
- [x] scrape: per-clinic isolation working (smoke-tested by injected fault)
- [x] clinic: fortrea-madison module + studies in JSON
- [x] clinic: nucleus-stpaul module + studies in JSON
- [x] clinic: icon-lenexa module + studies in JSON
- [x] clinic: celerion-lincoln module + studies in JSON
- [x] workflow: Playwright install step added to daily-scrape.yml
- [x] clinic: abbvie-grayslake module (Playwright) + studies in JSON (or documented zero)
- [x] frontend: clinic dropdown replaced with state dropdown; counts shown
- [x] frontend: dates_raw rendered as collapsible Schedule block below meta grid
- [x] frontend: status line shows "across N clinics"
- [x] manual scraper run produces a valid studies.json from all working clinics
- [ ] manual daily-scrape workflow run completes green and the deployed site shows the new data
- [ ] (Owner) verify on iPhone

## Phase 2 — Daily automation — DONE
First green scheduled run logged in progress.md.

## Phase 1 — Pipeline proven — DONE
