# Trial Finder — current phase

## Phase 3.3 — Spaulding sitemap recovery mode — IN PROGRESS
- [x] scraper/clinics/spaulding.py uses etree.XMLParser(recover=True)
- [x] Log emitted when recovery engages (so intermittent bug remains visible)
- [x] Verified against synthesized bad-entity sitemap: URLs still extract, exit 0
- [x] Verified against live (good-day) sitemap: 5 studies parse, no regressions
- [ ] (Owner) watch the next 1–2 weeks of scheduled runs; confirm Spaulding
      no longer intermittently disappears from the deployed site

## Phase 3.2 — Workflow + Spaulding hotfix — DONE (engineering)
- [x] scraper/clinics/spaulding.py uses lxml parser; 4 Spaulding studies parse locally
- [x] daily-scrape.yml diff and commit steps run `if: always()` (commit also gated by `changed`)
- [x] commit message includes clinic_count from studies.json
- [ ] (Owner) trigger daily-scrape manually after push; confirm green with 6 clinics OK and one
      commit from trial-finder-bot with the new message format
- [ ] (Owner) inject a temporary fault into one clinic, trigger the workflow, confirm: job goes
      RED, the other 5 clinics' data deploys, a partial-refresh commit lands, then revert

## Phase 3.1 — Derived-field extraction (Fortrea + cross-clinic check) — DONE (engineering)
Fortrea nights/visits derived from prose; per-clinic spot check turned up real bugs in Nucleus
(closed-status filter) and Celerion (nights regex hyphen requirement). Owner item — verify on
deployed site that Fortrea cards now show populated fields — still pending the next workflow run.

## Phase 3 — Multi-clinic + state filter + dates UX — DONE
6 clinic scrapers, state-based filtering, collapsible cohort schedules, and per-clinic
isolation in the orchestrator.

## Phase 2 — Daily automation — DONE
First green scheduled run logged in progress.md.

## Phase 1 — Pipeline proven — DONE
