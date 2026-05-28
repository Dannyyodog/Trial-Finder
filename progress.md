# Trial Finder — progress log
Newest entry on top. One entry per work session.

---

## 2026-05-28 — Phase 1 built end-to-end (Spaulding live, 4 studies)
- Built the full Phase 1 pipeline per `specs/PHASE1_trial_finder_build.md`. Scraper runs
  manually against the live Spaulding site and writes a valid `docs/studies.json`; static
  `docs/index.html` reads that file and renders cards with sort + filter UI.
- **Selectors derived from the live DOM, not assumed.** Discoveries that changed the plan
  vs. the spec's hints:
  - The homepage no longer lists studies and `/current/` redirects to the homepage. The
    canonical index of recruiting studies is `https://www.spauldingpays.com/sitemap.xml`
    (4 entries today: opalpart2, penny, quill, thunder-2). The known-good URLs the spec
    mentioned (walden, alfie, cloud) are 404; only quill survives.
  - Study pages are Elementor (WordPress). Every study page renders the same widget
    sequence: `Study Name: X` → `Compensation` → `$amount` → sex line → `Ages: X` →
    `BMI …` → `Dates`. Field-level parsing keys off that sequence rather than fragile
    class names.
  - Per-study schedules ("Cohort 2", "Part 2", "Group 3") live inside Elementor
    *accordion* widgets, not text-editor blocks. `dates_raw` extraction handles both.
  - `screening_date_raw` is `null` for all current Spaulding studies — there are no
    per-study screening date strings on the pages, only a boilerplate explanation.
- **Two parsing bugs found and fixed on the first scrape:**
  - Nights for Quill came out as 22 instead of 11 because "12 days/11 nights" appears
    in both the Dates block and the volunteer description paragraph. Fixed by
    deduplicating `(days, nights)` pairs before summing.
  - `dates_raw` initially captured the volunteer description paragraph (because it
    contains a `days/nights` phrase). Fixed by tightening the date-shape regex to
    require Check in:/Check out:/Length of stay/Cohort N/Part N/Group N/Dates TBD/OPV
    AND explicitly excluding text containing volunteer-description phrases.
- **Fail-loud behavior verified.** Pointed the sitemap URL at a 404 endpoint;
  `scrape.py` exited non-zero (code 2), printed the error, and left `docs/studies.json`
  byte-identical (md5 unchanged).
- **Frontend smoke test passed.** Spun up `python -m http.server` on docs/, screenshotted
  the rendered page, programmatically toggled every filter and confirmed the expected
  cards survive each combination, injected a synthetic flagged study to confirm the red
  left border + amber/red badges + sex_notes + screening_date rendering. No console errors.
- **No GitHub Actions added** (Phase 2 territory). `.github/` directory does not exist.
- Files touched (this session, all new): `CLAUDE.md`, `progress.md`, `README.md`,
  `.gitignore`, `.claude/launch.json` (for local preview),
  `specs/PHASE1_trial_finder_build.md` (relocated from repo root),
  `scraper/requirements.txt`, `scraper/common.py`, `scraper/scrape.py`,
  `scraper/clinics/__init__.py`, `scraper/clinics/spaulding.py`,
  `docs/index.html`, `docs/studies.json` (seed → replaced by live data),
  `docs/phase_current.md`. Scratch `tmp/` directory (gitignored) holds the
  pretty-printed reference HTML used while writing the selectors.
- **Deferred / left for the owner**:
  - Push the repo and enable GitHub Pages on `/docs` (manual step in repo settings),
    then confirm it loads on iPhone.
  - Re-run the scraper after any noticeable change on spauldingpays.com to catch DOM
    drift before Phase 2 automation goes in.
- **Recommended next step**: owner enables GitHub Pages on `/docs` and confirms the page
  loads from the published URL on a phone. Once that's verified, write the Phase 2
  spec for the daily GitHub Action.

---

## 2026-05-28 — repo bootstrapped
- Repo created; `specs/PHASE1_trial_finder_build.md` added; `CLAUDE.md` and `progress.md` created.
- Next: build Phase 1 per the spec (Sections 1–10), then run the scraper manually.
