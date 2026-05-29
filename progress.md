# Trial Finder — progress log
Newest entry on top. One entry per work session.

---

## 2026-05-29 — Phase 3.1 prose-derived fields + cross-clinic spot check
- Built Phase 3.1 per `specs/PHASE3.1_trial_finder_derived_fields.md`. Three real changes
  + bookkeeping; one fell out of §1 (Fortrea), two fell out of §2 (Nucleus + Celerion).
- **Fortrea Madison**: added `_derive_from_additional_details()` that parses
  Check-in / Check-out dates with `python-dateutil` and counts comma- and ampersand-
  separated tokens under "Follow up Visits:" (plus the inline "Potential Follow-ups:"
  subsection). Phone Calls explicitly do NOT count. Day-only tokens like "24" or "29"
  inherit the most recent month name in the same bullet, so "June 21, 24" correctly
  counts as 2 dates. `study_type` is now recomputed from the new values: nights≥1
  + visits≥1 → "mixed", nights≥1 → "inpatient", visits≥1 → "outpatient", else
  "unknown". 5 of 6 Fortrea studies now have populated `nights` and 4 have populated
  `visits`. Manual sanity-check confirmed against the live site:
  - 781667: spec said nights=2, visits=11 → matches.
  - 778100: Check-in: June 2 / Check-out: June 7 (5 nights); 4 bullets totaling 5
    visits (June 21 + July 5 + Sep 14 + Oct 12 & 26) → matches.
  - 782291 is the lone outlier with no Check-in/out in its prose — `nights=null`
    is correct, that's what the schema says null means.
- **`python-dateutil` added to `scraper/requirements.txt`.** Used only by Fortrea.
- **Cross-clinic spot check (spec §2) per-clinic findings:**
  - **Spaulding** — confirmed the existing parser is already correct.
    Quill's `dates_raw` = "Length of stay: 1 in house stays, lasting 12 days/11 nights"
    (already populated, nights=11 already correct). Quill's `visits=null` is correct
    because the page only describes the confinement stay — no outpatient visits.
    Penny's `dates_raw` = "Group 3: Dates TBD" is legitimate (Spaulding's own page
    has no dates yet for Penny). Opal Part 2's `visits=null` is correct — the page
    mentions a follow-up phone call, not a visit, and per schema phone calls don't
    count. **No fix needed.**
  - **Nucleus St. Paul** — found and fixed a real bug. The status filter accepted any
    Phase value containing "recruit", which matched "Recruitment Closed" too. Six
    closed trials were being kept (kidney-studies-free-heath-screening and others).
    Replaced the positive `/recruit/` gate with a negative
    `/closed|completed|finished|no longer recruiting|not recruiting/` gate. Spot
    check also confirmed the 7 remaining trials all show Location = "Minneapolis,
    United States" (no Australia bleed). **Fix committed:
    `clinics: nucleus-stpaul drop "Recruitment Closed" trials`.**
  - **ICON Lenexa** — every Lenexa study already has `nights`, `visits`, AND
    `dates_raw` populated (18 nights / 1 visit, 6/1, 50/3, 15/1). The Phase 3
    parser was already complete. **No fix needed.**
  - **Celerion Lincoln** — found and fixed a real bug. The "Study Length" regex
    required a hyphen between the night count and "Night Stay", so studies with
    "8 Night Stay & 14 Returns" parsed `nights=null` while studies with
    "20 - Night Stay & 2 Returns" parsed correctly. Made the hyphen optional;
    ca50599-4a now has `nights=8` (was null). **Fix committed:
    `clinics: celerion-lincoln nights regex no longer requires a hyphen`.**
  - **AbbVie Grayslake** — public cards genuinely show only Check In date,
    Demographic, Day Visits / Overnight badge, Gender, BMI, Stipend, Age. There's
    no Check-out date for Overnight studies (Celery) and no visit count anywhere.
    Buffalo's `study_type=outpatient` and Celery's `study_type=inpatient` are
    already correctly inferred from the "Day Visits" / "Overnight" badge. The
    "Information Sheet" link goes to a PDF, which is out of scope. `nights=null`
    and `visits=null` here are the schema's correct "unknown" value.
    **No fix needed.**
- **Net data change**: 32 → 26 studies (six closed Nucleus trials removed), with the
  remaining 26 carrying more populated fields. Fortrea cards in particular went from
  mostly null Nights/Visits to mostly populated.
- **Files touched**: `specs/PHASE3.1_trial_finder_derived_fields.md` (new),
  `scraper/requirements.txt` (add python-dateutil),
  `scraper/clinics/fortrea_madison.py` (derive nights/visits),
  `scraper/clinics/nucleus_stpaul.py` (status filter fix),
  `scraper/clinics/celerion_lincoln.py` (nights regex hyphen-optional),
  `docs/studies.json` (regenerated), `docs/phase_current.md`, this `progress.md`.
  Four commits on `main`.
- **Verification (spec checklist):** §0 done; §1 Fortrea standalone returns 6 studies
  with 5 nights / 4 visits populated; §2 manual sanity check matches; §3 combined
  scrape exits 0 with all 6 clinics OK; §4 validator clean; §5 per-clinic findings
  documented here; §7 phase_current.md + progress.md updated. §6 (frontend on
  deployed site shows populated fields) requires push + Pages rebuild — owner step.
- **Owner action item**: push the Phase 3.1 commits, wait for the next workflow run
  (or trigger manually), and visually confirm the Fortrea cards on the deployed
  site now show populated Nights / Visits and that the Nucleus card list dropped
  the six "Recruitment Closed" entries.

---

## 2026-05-28 — Phase 3 multi-clinic + state filter + collapsible schedule
- Built Phase 3 end-to-end per `specs/PHASE3_trial_finder_clinics_and_state.md`. Committed
  step-by-step in the order the spec mandates so each clinic has a clean rollback point.
- **Schema gained `state`** (2-letter USPS code). `SCHEMA_KEYS` updated, validator now
  rejects studies whose state is missing or not `[A-Z]{2}`. Spaulding emits `WI`; every
  new clinic emits its own.
- **Per-clinic isolation in `scrape.py`**. The orchestrator now runs each clinic inside
  `try/except`; failures are logged with traceback + URL context and surfaced in a
  summary table:
  ```
  Spaulding Clinical  OK    4 studies
  Fortrea Madison     OK    6 studies
  Nucleus St. Paul    OK    13 studies
  ICON Lenexa         OK    4 studies
  Celerion Lincoln    OK    3 studies
  AbbVie Grayslake    OK    2 studies
  6 of 6 clinics succeeded; 32 studies total. Wrote docs/studies.json. Exiting 0.
  ```
  Write rules: ≥1 clinic OK AND total studies > 0; exit 0 only if every clinic
  succeeded, otherwise non-zero even when the file was written (Action stays red,
  data still updates for what worked). Smoke-tested by injecting `raise` into
  spaulding.scrape(): orchestrator caught it, kept previous studies.json
  (md5 unchanged), exited 5.
- **Five new clinic modules** (selectors derived from the live DOM, not assumed):
  - **fortrea-madison** (6 studies). Discovery: `/en-us/clinical-research/browse-studies`
    (12 candidate URLs → filtered to Madison via the per-page Location card → 6 kept).
    Parses labeled `.info` cells (Compensation/Gender/Age/Dates) + "Additional Details"
    block.
  - **nucleus-stpaul** (13 studies). Discovery: WordPress `/post-trial-sitemap.xml` (57
    trials → kept only those whose Location card mentions United States / Minneapolis /
    St. Paul / MN). Fields from header card (Phase/Remuneration/Location) + the
    "Are you a match?" eligibility card (Age, Gender, Commitment).
  - **icon-lenexa** (4 studies). Discovery: homepage + `/All-Clinical-Research-Studies/`
    (`/Lenexa/Clinical-Research-Study/<id>/`). Pages aren't structured, so anchored
    regexes parse the prose: title after "STUDY DETAILS", "Up to $X", "1 stay of X
    nights and Y outpatient visits", "Age N - M", "Male/Female". `flag_childbearing`
    fires on the "non-childbearing potential" boilerplate.
  - **celerion-lincoln** (3 studies). Discovery:
    `/location/clinical-trials-lincoln-nebraska`. helpresearch.com sets
    `Crawl-delay: 10` so the module sleeps an extra 9s before each request on top
    of common.fetch's 1s baseline. Labeled fields (Stipend / Study Length /
    Requirement / Age / Start/End Date) parsed with lookahead terminators so values
    don't bleed; "Study Length: 20 - Night Stay & 2 Returns" → nights=20, visits=2.
  - **abbvie-grayslake** (2 studies). The site is an Angular SPA hash-routed at
    `/#/available-trials`; requests/BS4 returns an empty shell. Module lazy-imports
    Playwright inside `scrape()`, boots headless Chromium, navigates, waits for
    networkidle + a settle window + the `.trial-row` selector, then hands the
    rendered HTML to BeautifulSoup like any other module. Returns `[]` cleanly if
    the public site shows no trials. Current run: 2 trials (Buffalo + Celery).
- **Workflow updated** with the Playwright install step between `Install dependencies`
  and `Run the scraper`: `python -m playwright install --with-deps chromium`. Adds
  ~30s to a cold daily run; nothing else in the workflow changed (permissions,
  concurrency, fingerprint diff, conditional commit all untouched).
- **Frontend** got the three Phase 3 §8 changes:
  - **Clinic dropdown → State dropdown** with `(N)` counts, alphabetically sorted.
    Today: `IL (2)`, `KS (4)`, `MN (13)`, `NE (3)`, `WI (10)`.
  - **Collapsible `<details class="schedule">`** below the meta grid, full card
    width, `white-space: pre-wrap` so multi-line cohort schedules read naturally.
    Closed shows `▸ Schedule`; open shows `▾ Schedule` and the body. Cards with
    `dates_raw=null` get no Schedule control at all (today: 12 of 32 cards).
  - **Status line**: `"X shown · Y total across N clinics · updated <date>"`
    (today: `32 shown · 32 total across 6 clinics · updated May 28, 2026`).
  - Verified by spinning up the preview server, programmatically setting filters
    and reading back the visible cards: WI filter → 10 cards, KS filter → 4 cards
    (both match dropdown counts).
- **CLAUDE.md** gained the per-clinic isolation rule under Hard rules.
- **Files touched**: `CLAUDE.md`, `progress.md`, `docs/phase_current.md`,
  `docs/index.html`, `docs/studies.json` (now 32 studies × 6 clinics),
  `scraper/common.py`, `scraper/scrape.py`, `scraper/requirements.txt`,
  `scraper/clinics/spaulding.py` (emit state), `.github/workflows/daily-scrape.yml`
  (Playwright step), and **new**: `scraper/clinics/fortrea_madison.py`,
  `scraper/clinics/nucleus_stpaul.py`, `scraper/clinics/icon_lenexa.py`,
  `scraper/clinics/celerion_lincoln.py`, `scraper/clinics/abbvie_grayslake.py`,
  `specs/PHASE3_trial_finder_clinics_and_state.md`. Eight commits on `main`,
  one per spec §5 step.
- **Verification deferred to the owner** (can't be done locally):
  - Push and re-run the daily workflow manually. Confirm: (a) no-op rerun
    produces zero commits + "No change" in the summary; (b) data updates land
    as `data: daily refresh (N studies)` commits authored by `trial-finder-bot`;
    (c) iPhone view of the deployed site works (state filter, Schedule
    expansion, no horizontal scrollbars).
- **Recommended next step**: owner pushes the branch, triggers
  `daily-scrape.yml` once manually, watches the summary table appear, and
  confirms a green/red signal. Phase 4 candidates: per-state aggregate cards
  on the index, search-by-keyword, or a dedicated "near me" geo filter.

---

## 2026-05-28 — Phase 2 daily-scrape Action built and locally simulated
- Built the single Phase 2 file per `specs/PHASE2_trial_finder_automation.md`:
  **`.github/workflows/daily-scrape.yml`**. Nothing in `scraper/`, `docs/`, or `CLAUDE.md`
  was modified — Phase 1 is the contract and stays as-is.
- Workflow spec conformance (parsed and checked against §3 programmatically): cron
  `0 5 * * *`, `workflow_dispatch`, `permissions: contents: write` only (no job-level
  override), `concurrency: { group: daily-scrape, cancel-in-progress: false }`,
  `runs-on: ubuntu-latest`, `timeout-minutes: 10`, seven step blocks in spec order
  (checkout v4 fetch-depth 1, setup-python v5 / 3.12 with pip cache keyed on
  `scraper/requirements.txt`, install, scrape, fingerprint diff, conditional commit
  + push, always-on run summary).
- **Fingerprint diff** — Python inline, exactly as the spec example shows: hash the
  `studies` array with `scraped_at` stripped from each entry. Two robustness tweaks
  on top of the spec example: sort the stripped list by `id` so a sitemap reorder
  alone doesn't trigger a commit, and use `printf '%s\n'` with env-var passing for the
  multiline slug list in the summary step so values can't shell-inject.
- **Verified locally** (what's possible without a real Actions run):
  - YAML parses cleanly; every spec §3 check ticked.
  - Diff Scenario A (no real change, only new timestamps): `changed=false`,
    `slugs=[]` — exactly what a daily no-op run produces. No commit path taken.
  - Diff Scenario B (one study's `nights` flipped in the "old" copy): `changed=true`,
    `slugs=['spaulding-thunder-2']` — only the truly-different slug listed.
  - Diff Scenario C (no previous file): treated as `changed=true`, all 4 slugs listed.
  - Fail-loud re-confirmed end-to-end: pointing `SITEMAP_URL` at a 404 endpoint
    makes `scrape.py` exit 2 and leave `docs/studies.json` byte-identical (md5
    unchanged before/after). The workflow runs `python scraper/scrape.py` without
    any `continue-on-error`, so that exit code propagates and the Action goes red.
- **Verification steps that need an actual Actions run** (cannot be done locally;
  the owner runs these once after pushing):
  - Spec step 2 — manual `workflow_dispatch` on the no-op path; summary reads
    "No change — 4 studies, fingerprint unchanged"; no new commit on `main`.
  - Spec step 3 — temporary commit that flips a `nights` value to a clearly-wrong
    number, manual dispatch, confirm the bot commit lands and Pages rebuilds.
  - Spec step 4 — temporarily push a broken `SITEMAP_URL`, manual dispatch, confirm
    the Action goes red and no commit appears. Revert.
- Files touched (this session): **new** `.github/workflows/daily-scrape.yml`;
  **rewritten** `docs/phase_current.md` per spec §5; **prepended** this entry to
  `progress.md`. `docs/studies.json` was overwritten by an interim local scraper
  rerun during simulation but the study data is identical to the previous commit
  (only timestamps differ — that's the no-op scenario the workflow is designed to
  catch and *not* commit).
- **Owner action items** (cannot be done by Claude — only the owner can):
  1. **GitHub repo settings → Actions → General → Workflow permissions = "Read and
     write permissions"**, and leave "Allow GitHub Actions to create and approve
     pull requests" **unchecked**. The `GITHUB_TOKEN` needs write to push the
     daily commit; PR scope is intentionally not used.
  2. Push the repo, then trigger `daily-scrape.yml` once manually from the Actions
     tab to verify the no-op path (run completes green, no new commit). Wait one
     calendar day and confirm the 05:00 UTC scheduled run also fires.
  3. (Carry-over from Phase 1) Enable GitHub Pages on `/docs` if not already done,
     and confirm the page loads on iPhone. Pages auto-rebuilds whenever
     `docs/studies.json` changes on `main`, so this is the trigger for the daily
     refresh to be visible.
- **Recommended next step**: owner does the workflow-permissions toggle, pushes,
  and triggers a manual run. Once both green-on-dispatch and red-on-broken-sitemap
  are confirmed in the Actions tab, mark the remaining Phase 2 checkboxes done and
  start drafting the Phase 3 spec (multi-clinic + state filter + dates_raw rendering).

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
