# Claude Code Build Spec — Trial Finder, Phase 1

## How to use this file
This file lives in the repo at **`specs/PHASE1_trial_finder_build.md`** and Claude Code reads it
directly. It runs inside a freshly-cloned **public** GitHub repo named `trial-finder`.

**Do Section 0 (operating protocol) FIRST** — create `CLAUDE.md` and `progress.md` before building
anything else. Then build everything in Sections 1–10 and work through the **Verification
checklist** at the bottom before declaring done.

**Do not** set up any GitHub Actions / automation in this phase — that is Phase 2, on purpose, so
any scraper bugs are visible on a manual run instead of being hidden behind a cron job.

---

## 0. Operating protocol — set this up FIRST, before building anything

This project uses four kinds of doc. Keep their jobs separate; do **not** duplicate content across them:
- **`CLAUDE.md`** (repo root) — the standing rules of engagement. Claude Code auto-loads it at the
  start of every session. Small and stable.
- **`progress.md`** (repo root) — a reverse-chronological log. You **read** it at the start of every
  prompt and **add a new dated entry at the top** at the end of every prompt.
- **`specs/PHASE*.md`** — the build instructions for each phase (this file is the Phase 1 spec). The
  "what to build."
- **`docs/phase_current.md`** — the checkbox status of the *active* phase only.

### Step 0a — create `CLAUDE.md` at the repo root with exactly this content:

```markdown
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
```

### Step 0b — create `progress.md` at the repo root with this starter content:

```markdown
# Trial Finder — progress log
Newest entry on top. One entry per work session.

---

## <date> — repo bootstrapped
- Repo created; `specs/PHASE1_trial_finder_build.md` added; `CLAUDE.md` and `progress.md` created.
- Next: build Phase 1 per the spec (Sections 1–10), then run the scraper manually.
```

Only after both files exist, proceed to Section 1.

---

## 1. Context — what we're building and why

A family member participates in **paid healthy-volunteer clinical studies** (Phase 1 trials, the
kind people do for income). She needs to find studies filtered by the things that actually matter
to a paid participant — **payout, number of overnight stays, number of visits** — on top of medical
filters: **no spinal taps / lumbar punctures, her age, her sex, and childbearing/contraception
requirements**.

We already learned the hard constraint: **ClinicalTrials.gov has no payment data.** The dollar
amounts live on each clinic's (CRO's) own recruitment website. A pure browser-side HTML page
**cannot** read those sites — they don't send CORS headers, and several render listings with
JavaScript so a plain fetch gets an empty shell. ClinicalTrials.gov is deliberately on the back
burner for now.

**Therefore the architecture is:**

```
scraper (Python, runs on a schedule)  →  writes ONE file: docs/studies.json
                                                  │
static HTML page (docs/index.html)  ──reads──────┘   (same repo = same origin = no CORS,
                                                       and it works on her iPhone)
```

The frontend stays "dumb": it only reads a local JSON file. All scraping happens upstream and is
frozen into `studies.json`. In Phase 1 we run the scraper **by hand**; Phase 2 adds the daily
GitHub Action; Phase 3 adds more clinics.

**This phase ships exactly one clinic: Spaulding Clinical (West Bend, WI)** — it's both the
highest-paying option near her *and* the cleanest to scrape (standard server-rendered pages,
per-study URLs, dollar amounts printed on the page). Proving the full pipeline end-to-end with one
clean source is the whole point of Phase 1.

---

## 2. Repo layout to create

```
trial-finder/
├─ CLAUDE.md                   ← standing rules; Claude Code auto-loads this every session
├─ progress.md                 ← running log; READ at start of each prompt, UPDATE at end
├─ specs/
│  └─ PHASE1_trial_finder_build.md   ← this file (and future PHASE2…, PHASE3… specs)
├─ docs/                       ← GitHub Pages will serve THIS folder (set later, by hand)
│  ├─ index.html               ← the frontend
│  ├─ studies.json             ← scraped data (seed sample now; scraper overwrites it)
│  └─ phase_current.md         ← checkbox status of the active phase
├─ scraper/
│  ├─ scrape.py                ← orchestrator: runs each clinic module, writes docs/studies.json
│  ├─ clinics/
│  │  ├─ __init__.py
│  │  └─ spaulding.py          ← the one clinic module for this phase
│  ├─ common.py                ← shared helpers (HTTP, $ parsing, flag detection, schema validate)
│  └─ requirements.txt
├─ .gitignore
└─ README.md
```

Do **not** create `.github/workflows/` in this phase.

---

## 3. The data schema (the one decision that matters most)

Every clinic module must emit a list of study dicts in exactly this shape. Getting this right makes
adding clinics later trivial. Write the schema once in `scraper/common.py` as a constant + a
validator function, and have the frontend assume exactly these keys.

```jsonc
{
  "generated_at": "2026-05-28T12:00:00Z",   // ISO 8601 UTC, when scrape.py ran
  "clinic_count": 1,                          // number of clinics represented
  "study_count": 7,                           // len(studies)
  "studies": [
    {
      "id": "spaulding-walden",               // "<clinic-slug>-<study-slug>", stable & unique
      "clinic": "Spaulding Clinical",
      "location": "West Bend, WI",
      "title": "Walden",
      "compensation": 15250,                  // INTEGER for sorting (top of range if a range); null if unknown
      "compensation_raw": "Up to $15,250",    // STRING exactly as shown on the page; null if unknown
      "study_type": "inpatient",              // "inpatient" | "outpatient" | "mixed" | "unknown"
      "nights": 12,                           // confinement/overnight nights; integer; null if unknown
      "visits": 3,                            // outpatient/follow-up visits; integer; null if unknown
      "screening_date_raw": "Screening: Jun 3–5, 2026",  // string as shown; null if not listed
      "dates_raw": "Study: Jun 14–26, 2026",  // main study dates as shown; null if not listed
      "sex": "ALL",                           // "ALL" | "FEMALE" | "MALE"
      "sex_notes": "Postmenopausal or surgically sterile women", // string; null if none
      "age_min": 18,                          // integer years; null if unknown
      "age_max": 55,                          // integer years; null if unknown
      "age_raw": "18–55 years",               // string as shown; null if unknown
      "healthy": true,                        // healthy volunteers accepted (Spaulding: essentially always true)
      "flag_spinal": false,                   // true if text mentions lumbar puncture / spinal tap / intrathecal / CSF
      "flag_childbearing": false,             // true if text mentions contraception / pregnancy / childbearing requirements
      "url": "https://www.spauldingpays.com/study/walden/",
      "scraped_at": "2026-05-28T12:00:00Z"
    }
  ]
}
```

**Field rules:**
- Anything genuinely not found on the page is `null` (numbers) or `null` (strings) — **never guess
  or fabricate a value.** A missing payout is `compensation: null`, not `0`.
- `compensation` is the integer used for sorting. If the page shows a range ("$2,280–$5,000"), take
  the **top** value (that's what these sites headline and what participants anchor on); keep the
  full text in `compensation_raw`.
- `flag_spinal` / `flag_childbearing` are computed by scanning the combined study text with the
  regexes in §5 (keep them identical to the frontend's original logic).
- `study_type`: if there are overnight nights → `inpatient`; if only daytime visits → `outpatient`;
  if both → `mixed`; if you can't tell → `unknown`.

---

## 4. Scraper spec

### 4a. `scraper/requirements.txt`
```
requests
beautifulsoup4
lxml
```
(Use `requests` + BeautifulSoup. Do **not** pull in Selenium/Playwright for Spaulding — its pages
are server-rendered and don't need a headless browser. Keep this phase dependency-light.)

### 4b. `scraper/common.py`
Shared helpers used by every clinic module:
- `SCHEMA_KEYS` — the exact set of study keys above.
- `fetch(url)` — GET with:
  - a descriptive `User-Agent` like `trial-finder-bot/1.0 (personal study finder; +https://github.com/<owner>/trial-finder)`
  - a timeout, and a polite delay (`time.sleep(1.0)`) between requests.
  - simple retry (2 retries on transient errors).
- `check_robots(base_url)` — fetch `/robots.txt`, parse with `urllib.robotparser`, and expose a
  function that asserts a given path is allowed before fetching it. If robots disallows a path,
  **skip it and log a warning** rather than scraping it.
- `parse_money(text) -> int | None` — pull the highest dollar amount from a string (`$15,250` →
  `15250`; ranges → top value); return `None` if no dollar figure present.
- `parse_age_range(text) -> (int|None, int|None)` — extract min/max ages in years.
- `detect_flags(text) -> (bool, bool)` — run the §5 regexes, return `(flag_spinal, flag_childbearing)`.
- `slugify(s) -> str`.
- `validate_study(d) -> list[str]` — return a list of problems (missing keys, wrong types); empty
  list means valid. `scrape.py` will refuse to write output if any study is invalid.

### 4c. `scraper/clinics/spaulding.py`
Exposes `def scrape() -> list[dict]:` returning study dicts in the schema.

**IMPORTANT — discover the real structure, don't assume it.** Before writing selectors, actually
fetch and read the live HTML:
1. Fetch `https://www.spauldingpays.com/robots.txt` first; respect it.
2. Find the **index of current studies.** Start at `https://www.spauldingpays.com/` and look for a
   "current studies" / "studies" listing section, and collect every link matching
   `https://www.spauldingpays.com/study/<slug>/`. (Known-good examples that have existed:
   `/study/walden/`, `/study/alfie/`, `/study/cloud/`, `/study/quill/` — use these to confirm your
   per-study parser, but the live index is the source of truth for which studies are current.)
3. For each study page, parse the fields in the schema. Field labels on the page (compensation,
   confinement/nights, visits, dates, age, sex, etc.) may be in headings, definition lists, tables,
   or labeled spans — **inspect the actual DOM and write resilient selectors** (prefer matching on
   visible label text like "Compensation", "Dates", "Eligible Ages" over brittle CSS class names).
4. Build the combined text blob (title + all visible study body text) and run `detect_flags`.
5. Set `healthy=True` for Spaulding studies unless a page clearly indicates a patient population.
6. Return the list. Log how many studies were found and a one-line summary per study to stdout.

Be defensive: if the index page layout isn't recognized, fail loudly with a clear message naming
the URL and what was expected — do **not** silently return an empty list (an empty list would wipe
`studies.json`).

### 4d. `scraper/scrape.py` (orchestrator)
- Import each clinic module (just `spaulding` this phase), call `scrape()`, collect all studies.
- Run `validate_study` on each; if **any** study is invalid, print the problems and **exit non-zero
  without writing the file** (don't clobber good data with bad).
- If the total study count is **0**, also exit non-zero without writing (a scrape that finds nothing
  is almost always a breakage, not a real empty result).
- Otherwise assemble the top-level object (`generated_at`, `clinic_count`, `study_count`, `studies`)
  and write pretty-printed JSON to `docs/studies.json`.
- Print a clear summary: `Wrote N studies from M clinics to docs/studies.json`.

---

## 5. Flag-detection regexes (keep identical to the original frontend)

Apply case-insensitively to the combined study text:
- **Spinal:** `lumbar punctur|spinal tap|intrathecal|cerebrospinal|\bcsf\b`
- **Childbearing/contraception:** `contracept|childbearing|child-bearing|wocbp|surgically steril|postmenopausal|negative pregnancy|highly effective method|must not be pregnant|intrauterine device|agree to use (a )?(birth|contracep)`

---

## 6. Frontend spec — `docs/index.html`

Single self-contained file (inline CSS + JS, no build step, no external libs except Google Fonts).
On load it does `fetch('./studies.json')` (relative path — same origin) and renders. **No
ClinicalTrials.gov calls in this phase.**

**Reuse the existing visual design** from the earlier version of this tool so it stays consistent:
- Fonts: **Fraunces** (display/headings) + **Hanken Grotesk** (body), via Google Fonts.
- Warm "paper" background (`#f6f2e9`), ink `#20251f`, deep teal-green accent `#0e5c52`, soft accent
  `#d7e7e2`. Warning red `#b23a16` (spinal), amber `#8a5a00` (childbearing), green `#2f6b3d`
  (healthy). Rounded cards, soft shadow, subtle staggered fade-in on results.

**Layout:**
- Masthead: kicker + "Trial Finder" (the word "Finder" in italic teal) + one-line subtitle that now
  says it searches paid healthy-volunteer studies and shows a "Last updated <generated_at>" line
  read from the JSON.
- **Refine panel** (all instant, client-side):
  - **Sort by**: `Payout (high → low)` [default], `Payout (low → high)`, `Fewest nights`,
    `Fewest visits`.
  - **Clinic**: dropdown built dynamically from the clinics present in the data (plus "All clinics").
    (One option this phase, but build it data-driven so Phase 3 needs no frontend change.)
  - **Open to**: Anyone [default] / Women (sex ALL or FEMALE) / Men (sex ALL or MALE).
  - **My age** (number, optional): hides studies whose [age_min, age_max] excludes it.
  - **Min payout** (number, optional): hides studies below it; studies with `compensation: null`
    are hidden when a min payout is set (and shown otherwise).
  - **Max nights** (number, optional) and **Max visits** (number, optional).
  - Checkboxes: **Hide spinal-tap / lumbar-puncture studies** [checked by default],
    **Hide contraception / pregnancy-requirement studies** [unchecked], **Healthy volunteers only**
    [unchecked].
- **Results**: one card per study. **Compensation is the hero element** — large, top-right or as a
  prominent badge. Each card shows: title (links to `url`, opens new tab), clinic + location,
  compensation (raw string, with the parsed number used for sort), study_type, nights, visits,
  screening_date_raw, dates_raw, sex (+ sex_notes if present), age_raw, and badges:
  `Healthy volunteers OK` (green), `Mentions spinal tap / LP` (red, also tint the card's left
  border red), `Contraception / pregnancy terms` (amber). Show `—` for any null field rather than
  hiding it.
- **Status line**: `X shown · Y total · updated <date>`.
- **Empty/error states**: if `studies.json` fails to load, show a friendly message (e.g. "Couldn't
  load study data — if you just opened the file directly, view it through the published web link
  instead"). If filters hide everything, say so and suggest loosening.

Keep the HTML-escaping helper for all injected text. No `localStorage`/`sessionStorage`. State in
plain JS variables.

---

## 7. Seed `docs/studies.json`

Commit a small **sample** `studies.json` now (2–3 plausible Spaulding-shaped entries, clearly fake)
so that (a) GitHub Pages renders something before the first real scrape and (b) the frontend can be
tested independently of the scraper. Put `"_note": "SAMPLE seed data — overwritten by scraper"` at
the top level. The real scraper run will replace it.

---

## 8. `docs/phase_current.md`

Create it with this content (update the checkboxes as you complete them):

```markdown
# Trial Finder — current phase

## Phase 1 — Prove the pipeline (Spaulding only, manual run) — IN PROGRESS
Goal: scraper → docs/studies.json → static frontend reads it, working on desktop + iPhone via
GitHub Pages. No automation yet.

- [ ] Repo structure created
- [ ] scraper/common.py (schema, validator, $/age parsing, flag detection, robots check)
- [ ] scraper/clinics/spaulding.py (live-structure-driven, defensive)
- [ ] scraper/scrape.py (validates; refuses to write empty/invalid output)
- [ ] docs/index.html (reads ./studies.json; $ sort + payout/nights/visits + age/sex/spinal/childbearing filters)
- [ ] docs/studies.json seed committed
- [ ] Manual `python scraper/scrape.py` run produces valid studies.json from the live site
- [ ] Verified locally via `python -m http.server` in docs/
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
```

---

## 9. `README.md` and `.gitignore`
- `README.md`: one paragraph on what it is, the scraper→json→frontend architecture, how to run the
  scraper (`pip install -r scraper/requirements.txt` then `python scraper/scrape.py`), and how to
  preview the frontend (`cd docs && python -m http.server 8000`). Note Pages is served from `/docs`.
- `.gitignore`: Python (`__pycache__/`, `*.pyc`, `.venv/`, etc.).

---

## 10. Scraping etiquette (must follow)
- Honor `robots.txt`; skip disallowed paths.
- One descriptive `User-Agent`; ~1 request/second; small retry budget.
- These CROs *want* applicants, so reading their public study listings is fine — but be gentle and
  don't hammer. No login-walled or paywalled content.

---

## Verification checklist (work through before declaring done)
0. `CLAUDE.md` and `progress.md` exist at the repo root with the Section 0 content; this spec sits
   at `specs/PHASE1_trial_finder_build.md`.
1. `pip install -r scraper/requirements.txt` succeeds.
2. `python scraper/scrape.py` runs against the **live** Spaulding site and prints a per-study
   summary and `Wrote N studies … to docs/studies.json` with **N ≥ 1**.
3. Open `docs/studies.json`: top-level has `generated_at`, `clinic_count`, `study_count`,
   `studies`; every study has **all** schema keys; `compensation` is int-or-null; `compensation_raw`
   preserved; `nights`/`visits`/`age_min`/`age_max` int-or-null; `study_type` is one of the four
   allowed values; flags are booleans.
4. Deliberately break a selector (or point at a bad URL) and confirm `scrape.py` **exits non-zero
   and does NOT overwrite** `studies.json` (empty/invalid result must not clobber good data).
5. `cd docs && python -m http.server 8000`, open the page:
   - studies render; **compensation is visually prominent**; sort defaults to payout high→low.
   - changing Sort reorders instantly; Min payout / Max nights / Max visits filter correctly.
   - "My age" hides out-of-range studies; "Open to" sex filter works (ALL counts as eligible).
   - "Hide spinal-tap" is **on by default** and removes flagged studies; flagged-but-shown studies
     get the red badge + red left border when the box is unchecked.
   - screening dates, study dates, study_type, sex_notes all display (`—` when null).
   - no console errors; works when the seed JSON is replaced by the freshly scraped one.
6. `docs/phase_current.md` checkboxes updated to reflect reality.
7. **Confirm NO `.github/workflows/` exists** — automation is Phase 2.
8. End-of-session bookkeeping done: a new dated entry added to the TOP of `progress.md`, and
   `docs/phase_current.md` checkboxes updated to match reality.
