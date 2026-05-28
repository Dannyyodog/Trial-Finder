# Claude Code Build Spec — Trial Finder, Phase 3

## How to use this file
Place this at **`specs/PHASE3_trial_finder_clinics_and_state.md`**. Phases 1 and 2 must already be
green (Spaulding scraping daily, automation proven). Follow the `CLAUDE.md` protocol: read
`progress.md`, the previous phase specs, and `docs/phase_current.md` first; update `progress.md`
and `docs/phase_current.md` at the end.

This phase is materially larger than Phase 2. **Build and commit clinic-by-clinic** in the order
listed in §5, not all at once. The order is chosen so that easier sources prove the architecture
before harder ones touch it.

---

## Goals

1. Add **five more clinic scrapers** to broaden coverage beyond Spaulding:
   - Fortrea Madison (Madison, WI)
   - Nucleus Network (St. Paul, MN)
   - ICON Early Phase (Lenexa, KS) — formerly PRA Health Sciences
   - Celerion (Lincoln, NE)
   - AbbVie Phase 1 (Grayslake, IL) — **requires Playwright** (JavaScript-rendered SPA)
2. Replace the **clinic dropdown** in the refine panel with a **state dropdown**. Clinic stays
   visible on each card; the dropdown is just no longer the primary filter.
3. Render long **`dates_raw`** values as a tap-to-expand collapsible block so cards stay scannable
   when a study has a multi-line cohort schedule.
4. Introduce **per-clinic isolation** in the orchestrator so a single broken scraper degrades
   gracefully instead of wiping the whole dataset.

---

## 1. Architectural changes (the rules that govern §§4–8)

### 1a. Per-clinic isolation (the most important change)

The orchestrator (`scraper/scrape.py`) currently treats any error or empty result as a fatal
failure. With 5 clinics, that's wrong — one site's redesign should not erase studies from the
other four. Replace the orchestrator's behavior with this rule:

For each clinic module:
- Run `clinic.scrape()` inside a `try/except`.
- **Success** = no exception raised. The returned list (even if empty — a clinic may legitimately
  have no current studies) is accepted.
- **Failure** = any exception. Log it loudly (full traceback to stdout, the clinic name, the URL
  attempted), continue to the next clinic, and remember that this clinic failed.

After all clinics run, decide what to do:
- **Write `docs/studies.json`** if and only if:
  - At least one clinic succeeded **AND**
  - The combined study count across successful clinics is **> 0**.
  - (Reasoning: "all five clinics succeeded but every one returned empty" is statistically a
    collective DOM change, not a real lull — treat as suspicious and refuse to write.)
- **Exit code:**
  - `0` only if **every** clinic succeeded.
  - `1` (or `2`) if any clinic failed, **even when the file was written.** This is how the Action
    stays red on partial failure: the data updates for what worked, *and* the failure is visible.

Print a clear summary at the end:
```
Spaulding         OK    4 studies
Fortrea Madison   OK    7 studies
Nucleus St. Paul  OK    3 studies
ICON Lenexa       FAIL  (HTTPError 503 on https://…)
Celerion Lincoln  OK    5 studies
AbbVie Grayslake  OK    0 studies
─────────────────────────────────
5 of 6 clinics succeeded; 19 studies total. Wrote docs/studies.json. Exiting 1 (1 failure).
```

### 1b. Schema gains `state`

The frontend's new state filter needs to know each study's US state without parsing strings.
Add a top-level field to each study:

```jsonc
"state": "WI",         // 2-letter USPS state code; never null (clinic location is always known)
```

Update `SCHEMA_KEYS` in `scraper/common.py`, the validator, and `scraper/clinics/spaulding.py`
(emit `"state": "WI"`). Every new clinic module emits its own state.

### 1c. ID conventions

Each clinic gets a stable slug used as a prefix in `id` and in the per-clinic module filename:

| Display name           | clinic slug         | location          | state |
|------------------------|---------------------|-------------------|-------|
| Spaulding Clinical     | `spaulding`         | West Bend, WI     | WI    |
| Fortrea                | `fortrea-madison`   | Madison, WI       | WI    |
| Nucleus Network        | `nucleus-stpaul`    | St. Paul, MN      | MN    |
| ICON Early Phase       | `icon-lenexa`       | Lenexa, KS        | KS    |
| Celerion               | `celerion-lincoln`  | Lincoln, NE       | NE    |
| AbbVie Phase 1         | `abbvie-grayslake`  | Grayslake, IL     | IL    |

Study `id` format stays `<clinic-slug>-<study-slug>`.

---

## 2. Schema update — full reminder

Every study in `studies.json` now has these keys (in this order is fine, but every key must be
present and the validator enforces it):

```
id, clinic, location, state, title,
compensation, compensation_raw,
study_type, nights, visits,
screening_date_raw, dates_raw,
sex, sex_notes, age_min, age_max, age_raw,
healthy, flag_spinal, flag_childbearing,
url, scraped_at
```

The only new key is `state`. All other Phase 1 rules still apply (nulls for unknowns; never
fabricate; `compensation` is the top-of-range integer; flags computed via `detect_flags`).

---

## 3. Files to add or change

```
trial-finder/
├─ .github/workflows/daily-scrape.yml      ← MODIFY (add Playwright install step)
├─ scraper/
│  ├─ common.py                            ← MODIFY (add "state" to SCHEMA_KEYS + validator)
│  ├─ scrape.py                            ← REWRITE the orchestrator loop (per §1a)
│  ├─ requirements.txt                     ← ADD playwright
│  └─ clinics/
│     ├─ spaulding.py                      ← MODIFY (emit "state": "WI")
│     ├─ fortrea_madison.py                ← NEW
│     ├─ nucleus_stpaul.py                 ← NEW
│     ├─ icon_lenexa.py                    ← NEW
│     ├─ celerion_lincoln.py               ← NEW
│     └─ abbvie_grayslake.py               ← NEW (Playwright)
├─ docs/
│  ├─ index.html                           ← MODIFY (state filter, dates collapsible)
│  └─ phase_current.md                     ← REWRITE for Phase 3
└─ specs/PHASE3_trial_finder_clinics_and_state.md   ← this file
```

---

## 4. Discovery-first rule (applies to every new clinic module)

For each new clinic, do not write selectors from imagination. Always:
1. Fetch `https://<host>/robots.txt` and respect it.
2. Find the **canonical listings page** — try sitemap.xml first (it worked for Spaulding), then
   look for an explicit "current studies" / "browse studies" / "find a trial" page.
3. Fetch one study page and read the actual DOM (`view-source` or save and inspect). Prefer
   matching on visible label text ("Compensation", "Ages", "Confinement") rather than brittle
   CSS class names that designers rename.
4. Verify against a **second** study from the same clinic — selectors that work on one page often
   fail on the next.
5. Defensive parsing: any field not confidently found is `null`. Never fabricate.
6. Build the combined text blob (title + body) and run `common.detect_flags`.
7. If a clinic's listings page layout cannot be parsed at all, **raise an exception with a clear
   message naming the URL and what was expected** — that's the signal the orchestrator catches.

Add a `if __name__ == "__main__":` block to each clinic module that calls `scrape()` and pretty-
prints the result, so each module can be tested independently with
`python -m scraper.clinics.<name>` during development.

---

## 5. Build and commit order (do this strictly)

For each clinic below: write the module → run it standalone to confirm it returns valid studies
→ run the full orchestrator → confirm `docs/studies.json` validates and renders correctly →
**commit before starting the next clinic.** This gives clean rollback points and meaningful git
history.

### Step 1 — Add `state` to schema and Spaulding (commit: "schema: add state field")
- Edit `scraper/common.py`: add `"state"` to `SCHEMA_KEYS`, update validator.
- Edit `scraper/clinics/spaulding.py`: emit `"state": "WI"` on every study.
- Re-run scraper → studies.json now has `state: "WI"` on all 4 Spaulding studies.

### Step 2 — Per-clinic isolation in scrape.py (commit: "scrape: per-clinic isolation")
- Rewrite the orchestrator per §1a.
- Smoke test by injecting a temporary `raise RuntimeError("fake")` into spaulding.scrape() and
  confirming: log says FAIL, no other clinic exists yet so no studies, exit code non-zero, file
  not overwritten. Remove the injection.

### Step 3 — Fortrea Madison (commit: "clinics: add fortrea-madison")
Site: `https://www.fortreaclinicaltrials.com/en-us/clinical-locations/madison-wisconsin` and the
clinic-wide browse page at `https://www.fortreaclinicaltrials.com/en-us/clinical-research/browse-studies`.
Listings include payouts. Inspect the DOM; Fortrea uses a fairly clean Marketing-CMS layout with
per-study URLs under `/en-us/<study-slug>` containing labeled fields (Compensation, Dates,
Visits, Healthy, etc.). Watch for:
- Studies from other Fortrea locations (Dallas TX, Daytona Beach FL) on the same browse page —
  **filter to Madison only** by location text on the study page.
- Some study pages have multiple cohorts with different compensation; take the highest as
  `compensation`, keep the original phrasing in `compensation_raw`.

### Step 4 — Nucleus Network St. Paul (commit: "clinics: add nucleus-stpaul")
Site: `https://www.nucleusnetwork.com/us/`. Currently their only US clinic. Look for a "current
studies" or "find a trial" page; per-study cards typically list "Up to $X" plus length/nights.
Confirm each parsed study is actually a St. Paul study (not their Australian sites) — Nucleus
also operates Melbourne and Brisbane and lists them on the global brand site.

### Step 5 — ICON Early Phase, Lenexa (commit: "clinics: add icon-lenexa")
Sites to investigate: `https://iconstudies.com` and `https://prastudies.com`. ICON acquired PRA;
one of these may redirect to the other. Look for the Lenexa, KS location specifically (ICON also
has units in Salt Lake City and San Antonio — exclude those). Per-study cards typically include
compensation, dates, sex/age. Some content may live behind a registration prompt; only parse
what's publicly visible.

### Step 6 — Celerion Lincoln (commit: "clinics: add celerion-lincoln")
Site: `https://helpresearch.com`. Lincoln NE is the primary unit (Phoenix AZ secondary). From
research notes: full per-study specifics often require account creation. **Do not attempt to
create or use any account.** Parse only the publicly visible listings; many fields will be `null`
and that's correct.

### Step 7 — Update workflow for Playwright (commit: "workflow: install playwright chromium")
Add Playwright dependency and browser install. See §6.

### Step 8 — AbbVie Grayslake (commit: "clinics: add abbvie-grayslake (playwright)")
Site: `https://www.abbviephase1.com`. JS-rendered SPA — `requests`/BS4 returns an empty shell.
This module imports Playwright **lazily** (import inside the function, not at module top) so the
other clinic modules don't require Playwright to be installed for their own tests. Use
`sync_playwright()` + `chromium.launch(headless=True)`, navigate, wait for the listings selector
or `networkidle`, then dump rendered HTML into BeautifulSoup as usual.

If AbbVie's site walls studies behind a login and the public landing has no listings: it's
acceptable for this scraper to return `[]` — log that no public studies are visible. The
orchestrator counts that as success-with-zero-studies, not a failure.

### Step 9 — Frontend (commit: "frontend: state filter + collapsible dates")
See §8.

### Step 10 — Bookkeeping (commit: "phase 3: progress + phase_current")
Update `docs/phase_current.md` and prepend a new entry to `progress.md`.

---

## 6. `scraper/requirements.txt` and Playwright

Add to `scraper/requirements.txt`:
```
requests
beautifulsoup4
lxml
playwright
```

Local install:
```
pip install -r scraper/requirements.txt
python -m playwright install chromium
```

The browser binary install is separate from `pip install` and must run once per machine.

---

## 7. `.github/workflows/daily-scrape.yml` — workflow update

Insert a new step between "Install dependencies" and "Run the scraper":

```yaml
      - name: Install Playwright browsers
        run: python -m playwright install --with-deps chromium
```

That's it. No browser caching across runs — the install adds ~30 seconds on a daily run, which
is fine under our 10-minute timeout. All other steps stay as written in Phase 2 (`permissions`,
`concurrency`, fingerprint diff, conditional commit, summary). The fingerprint comparator already
strips `scraped_at` per-study; that still works correctly with the new `state` field.

---

## 8. Frontend changes — `docs/index.html`

Three changes; nothing else.

### 8a. Replace the Clinic dropdown with State

- Remove the `<select id="clinic">` and its label.
- Add a `<select id="state">` in the same grid slot, with label "State".
- Populate options dynamically from the studies: `"All states"` + every unique `state` value
  present, **sorted alphabetically**, with a `(N)` suffix showing the study count in that state
  when the option is built. Example: `WI (8)`, `MN (3)`, `KS (5)`. Update the counts whenever the
  data changes (i.e., once on load — studies.json is static for the session).
- The state filter is a client-side filter exactly like the others. Default: "All states".

### 8b. Keep the clinic name on each card (no change needed)

The existing card already renders `clinic · location` under the title. Leave it alone.

### 8c. Collapsible `dates_raw`

Replace the current `dates_raw` rendering inside `.meta` with a `<details>` block. Render it only
when `dates_raw` is non-null:

```html
<details class="schedule">
  <summary>Schedule</summary>
  <div class="schedule-body">{escaped dates_raw, preserving line breaks}</div>
</details>
```

Style:
- Closed state: just the word "Schedule" with the same `▸` / `▾` chevron pattern already used for
  eligibility criteria.
- Open state: shows the full text with `white-space: pre-wrap;` so multi-line cohort schedules
  read naturally.
- Place the schedule block **below** the meta grid (full card width), not as a meta-cell, so a
  long schedule no longer cramps the grid layout.

When `dates_raw` is `null`, render nothing for it — don't show an empty "Schedule" toggle.

### 8d. Status line (small wording tweak)

The status line already reads `X shown · Y total · updated <date>`. Append clinic count after Y:
`X shown · Y total across N clinics · updated <date>`. Compute N as the number of unique
`clinic` values present in the data.

---

## 9. `docs/phase_current.md` — replace content

```markdown
# Trial Finder — current phase

## Phase 3 — Multi-clinic + state filter + dates UX — IN PROGRESS
Goal: 6 clinic scrapers (5 new), state-based filtering, collapsible cohort schedules, and per-
clinic isolation in the orchestrator.

- [ ] schema: state field added; spaulding emits it
- [ ] scrape: per-clinic isolation working (smoke-tested by injected fault)
- [ ] clinic: fortrea-madison module + studies in JSON
- [ ] clinic: nucleus-stpaul module + studies in JSON
- [ ] clinic: icon-lenexa module + studies in JSON
- [ ] clinic: celerion-lincoln module + studies in JSON
- [ ] workflow: Playwright install step added to daily-scrape.yml
- [ ] clinic: abbvie-grayslake module (Playwright) + studies in JSON (or documented zero)
- [ ] frontend: clinic dropdown replaced with state dropdown; counts shown
- [ ] frontend: dates_raw rendered as collapsible Schedule block below meta grid
- [ ] frontend: status line shows "across N clinics"
- [ ] manual scraper run produces a valid studies.json from all working clinics
- [ ] manual daily-scrape workflow run completes green and the deployed site shows the new data
- [ ] (Owner) verify on iPhone

## Phase 2 — Daily automation — DONE
First green scheduled run logged in progress.md.

## Phase 1 — Pipeline proven — DONE
```

---

## 10. Update `CLAUDE.md` — add one standing rule

Append to the "Hard rules" section of `CLAUDE.md`:

> - **Per-clinic isolation:** in the multi-clinic orchestrator, any clinic that throws is logged
>   loud, skipped, and reported in the run summary; remaining clinics still publish their data.
>   The Action exits non-zero on any clinic failure (so it goes red) but does not wipe successful
>   clinics' studies from `studies.json`.

---

## Verification checklist (work through before declaring done)

0. `CLAUDE.md`, `progress.md`, the active phase spec, and `docs/phase_current.md` were read at the
   start of the session.
1. **Schema:** `studies.json` contains `"state"` on every study; validator rejects a study with
   `state` missing.
2. **Per-clinic isolation:** with a deliberate `raise` injected into one clinic, the orchestrator
   logs FAIL, continues, writes `studies.json` from the others, and exits non-zero. Removing the
   injection produces a green run. (Smoke test, then remove the injection before commit.)
3. **Each new clinic module** has a standalone `__main__` block; running `python -m
   scraper.clinics.<name>` prints at least one valid study (or, for AbbVie, an explicit "no
   public studies visible" log line).
4. **Combined run:** `python scraper/scrape.py` finishes with a clear per-clinic summary table.
   `docs/studies.json` validates against the schema for every study.
5. **Playwright** is installed (`python -m playwright install chromium` ran locally) and the
   AbbVie module either returns studies or returns `[]` with a clear log message.
6. **Workflow:** `.github/workflows/daily-scrape.yml` includes the Playwright install step
   exactly once, between dependency install and the scraper run.
7. **Manual workflow trigger** completes green on the live runner; the Summary block shows the
   per-clinic table; a real-data run produces exactly one `data: daily refresh (N studies)`
   commit; a no-op rerun produces zero commits.
8. **Frontend:** state dropdown is populated with `(N)` counts and alphabetically sorted; "All
   states" is the default. Selecting a state filters correctly. The clinic dropdown is gone.
9. **Frontend:** every card with `dates_raw` shows a collapsible "Schedule" block below the meta
   grid; cards without `dates_raw` show no Schedule control. Status line shows
   `X shown · Y total across N clinics · updated <date>`.
10. **Mobile sanity check:** load the deployed Pages URL on a phone-width viewport (browser
    devtools), confirm cards still fit, Schedule expands on tap, no horizontal scrollbars.
11. `CLAUDE.md` updated with the per-clinic isolation rule.
12. `docs/phase_current.md` checkboxes synced; `progress.md` has a new dated entry at the top.
