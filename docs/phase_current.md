# Trial Finder — current phase

## Phase 2 — Daily automation (Spaulding only) — IN PROGRESS
Goal: a daily GitHub Action runs the scraper and commits studies.json only when the study data
actually changed, with loud failures.

- [x] .github/workflows/daily-scrape.yml created per spec
- [ ] Workflow runs cleanly on manual dispatch (Actions tab → Run workflow)
- [ ] Fingerprint diff verified: a no-op run produces NO commit
- [ ] Change-detection verified: a forced data change produces ONE commit with the right message
- [ ] Fail-loud verified: a deliberately broken scraper makes the Action go red
- [ ] (Owner) Settings → Actions → General → Workflow permissions = Read and write
- [ ] (Owner) Confirm scheduled 05:00 UTC run fires the next day

## Phase 1 — Prove the pipeline (Spaulding, manual run) — DONE (engineering)
All engineering checkboxes complete. Open owner item carried over from Phase 1: enable
GitHub Pages on `/docs` and confirm the page loads on iPhone (Pages URL will be
`https://<owner>.github.io/<repo>/` after enablement).

## Next phases
- Phase 3: add more clinic scrapers (Fortrea Madison, Nucleus St. Paul, AbbVie Grayslake, then
  ICON Lenexa / Celerion Lincoln); replace clinic dropdown with a STATE filter; fix dates_raw
  rendering (collapsed schedule block, expand on tap).
