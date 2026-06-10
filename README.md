# Trial Finder

A small daily-updating site that aggregates paid healthy-volunteer clinical studies from six CRO recruitment websites into one filterable view. Filters cover the things that matter to a paid participant: payout, overnight stays, follow-up visits, age, sex, spinal-tap flags, and contraception flags.

Built as a personal tool for a family member who participates in Phase 1 studies for income. Existing options (manually checking each CRO's site, a Telegram channel, the JustAnotherLabRat forum) leak signal and waste time. ClinicalTrials.gov was the obvious starting point but has no compensation data, so each clinic's recruitment site is the actual source of truth. Each one has a different DOM, several require JavaScript rendering, and none offer an API.

Live: https://dannyyodog.github.io/Trial-Finder/

## What it does

* Scrapes six Phase 1 CRO recruitment sites once a day via a scheduled GitHub Action
* Normalizes everything to a single schema (compensation as an integer for sorting, raw string preserved, structured nights/visits/age/sex, flag booleans for spinal-tap and childbearing requirements)
* Commits the result to `docs/studies.json` only when the data actually changed
* A static page in the same repo reads that JSON. Same origin, no CORS, works on mobile, no hosting needed beyond GitHub Pages

## Architecture

```
six clinic scrapers (Python)  ->  docs/studies.json  ->  docs/index.html (static)
        (one module per clinic, isolated)
                  |
                  +--  GitHub Action runs daily, commits only on real change
```

Three decisions worth calling out:

**Same-origin static site.** The frontend is a single HTML file that reads `./studies.json` from its own repo. No backend, no CORS dance, no auth surface. Works identically on iPhone and desktop. The whole live site is a Pages deployment of `/docs`.

**Per-clinic isolation.** With six independent sources, any one of them can break at any time (DOM changes, sitemap format shifts, content moves behind a login). The orchestrator runs each clinic in a try/except. A failing clinic is logged loudly, the others still publish their data, and the Action exits non-zero so the failure shows red in the UI. A broken Spaulding scraper does not wipe Fortrea's studies.

**Fingerprint-based diff before commit.** The Action only commits when the *study data* changed, ignoring the per-run timestamps that would otherwise produce a noisy commit every day. Implementation strips `generated_at` and `scraped_at` from each study, sorts by stable ID, hashes the result, and compares to the committed version's fingerprint. Quiet days produce no commits. Real changes produce one commit with a message like `data: daily refresh (23 studies, 5 clinics)`.

## Sources

| Clinic               | Location          | Tech            |
|----------------------|-------------------|-----------------|
| Spaulding Clinical   | West Bend, WI     | requests + lxml |
| Fortrea              | Madison, WI       | requests        |
| Nucleus Network      | St. Paul, MN      | requests        |
| ICON Early Phase     | Lenexa, KS        | requests        |
| Celerion             | Lincoln, NE       | requests        |
| AbbVie Phase 1       | Grayslake, IL     | Playwright      |

AbbVie is a JavaScript-rendered SPA. Requests + BeautifulSoup return an empty shell. The orchestrator imports Playwright lazily so the other clinic modules don't require a headless browser to be installed for their own tests.

## Patterns demonstrated

* Discovery-first scraping: each clinic module starts by fetching the real DOM (often via the site's sitemap) and writing selectors from what's actually there, rather than guessing
* Defensive schema enforcement: a validator rejects writes if any study is missing required keys or has wrong types. Unknowns are explicit `null`, never fabricated values
* Two layers of fail-loud: scraper exits non-zero on empty or invalid output, orchestrator exits non-zero on any clinic failure even when others succeeded
* GitHub Action with `if: always()` on the diff and commit steps so partial-failure days still deploy good data while staying visibly red
* Cross-source data quality work. Example: Nucleus's "Recruitment Closed" trials matched the same `recruit` substring as recruiting trials, which had been silently leaking closed studies into results until a spot check caught it

## Run it locally

```bash
git clone https://github.com/Dannyyodog/Trial-Finder.git
cd Trial-Finder

# scraper
pip install -r scraper/requirements.txt
python -m playwright install chromium   # only needed for AbbVie
python scraper/scrape.py                 # writes docs/studies.json

# frontend
cd docs && python -m http.server 8000    # then open http://localhost:8000
```

## Status

Daily automation has been running on schedule since deployment. Latest bot commit on `main` reflects the most recent scrape.

---

*Personal project. Not affiliated with any of the listed clinics. The directory pulls from each clinic's own public recruitment site.*
