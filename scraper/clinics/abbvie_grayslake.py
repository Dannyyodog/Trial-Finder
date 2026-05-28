"""AbbVie Phase 1 — ACPRU, Grayslake, IL — abbviephase1.com.

The site is an Angular SPA hash-routed at `/#/available-trials`; `requests`
returns a near-empty shell. We use Playwright headless Chromium to render
the listings page, then parse the rendered DOM with BeautifulSoup like
every other clinic module.

Each trial appears in a `<div class="trial-row">` card with labeled values:

  <Title>
  Check In:    No Confinement | 08 June 2026 | …
  Demographic: All
  Day Visits | Overnight | Mixed
  Gender:     Men and Women | Male | Female
  BMI:        18-32
  Stipend:    Up to $2100.00*
  Age:        18-65

Per Phase 3 §8 spec: if the public site shows no listings (e.g. studies were
removed or walled), this module returns `[]` with a clear log message. The
orchestrator counts that as success-with-zero-studies, not failure.

Playwright is imported inside `scrape()` so the rest of the clinic modules
can import without requiring the playwright wheel.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from scraper.common import (
    ScraperError,
    detect_flags,
    now_iso,
    parse_age_range,
    parse_money,
    slugify,
)


SITE_URL = "https://www.abbviephase1.com/#/available-trials"
LANDING_URL = "https://www.abbviephase1.com/"
CLINIC_NAME = "AbbVie ACPRU"
LOCATION = "Grayslake, IL"
STATE = "IL"
CLINIC_SLUG = "abbvie-grayslake"

USER_AGENT = (
    "trial-finder-bot/1.0 (personal study finder; "
    "+https://github.com/local/trial-finder)"
)
PAGE_TIMEOUT_MS = 60_000
SETTLE_MS = 2_000


def scrape() -> list[dict]:
    """Render the SPA, parse trial cards. Returns [] cleanly when the site
    shows no public trials."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ScraperError(
            "playwright not installed — run `pip install -r scraper/requirements.txt` "
            f"and `python -m playwright install chromium`. ({e})"
        )

    rendered_html = _render(sync_playwright)
    soup = BeautifulSoup(rendered_html, "html.parser")
    cards = soup.select(".trial-row")
    if not cards:
        # Look for an explicit "no trials" message before failing loud — the
        # site may legitimately have no public listings right now.
        body_text = " ".join(soup.get_text(" ", strip=True).split()).lower()
        if "no trials" in body_text or "no current trial" in body_text:
            print("[abbvie-grayslake] site reports no available trials — returning []")
            return []
        # Otherwise this is real structural drift.
        raise ScraperError(
            f"No .trial-row cards on rendered {SITE_URL} — page layout likely changed."
        )

    print(f"[abbvie-grayslake] rendered {len(cards)} trial card(s)")
    studies: list[dict] = []
    for card in cards:
        study = _parse_card(card)
        if study is None:
            continue
        print(
            f"[abbvie-grayslake]   {study['title']!r} comp=${study['compensation']} "
            f"sex={study['sex']} ages={study['age_min']}-{study['age_max']} "
            f"type={study['study_type']}"
        )
        studies.append(study)
    return studies


def _render(sync_playwright) -> str:
    """Boot Chromium, load the trials route, and return rendered HTML."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=USER_AGENT)
            page = ctx.new_page()
            page.goto(SITE_URL, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
            # Angular sometimes still has a frame to settle after networkidle.
            page.wait_for_timeout(SETTLE_MS)
            try:
                page.wait_for_selector(".trial-row", timeout=10_000)
            except Exception:
                pass  # absence is handled by the caller
            return page.content()
        finally:
            browser.close()


# ---------- card parsing ----------

_LABEL_RE = re.compile(
    r"\b(?P<k>Check\s+In|Demographic|Gender|BMI|Stipend|Age)\s*:\s*"
    r"(?P<v>.+?)(?=\b(?:Check\s+In|Demographic|Gender|BMI|Stipend|Age)\s*:"
    r"|\s+Information\s+Sheet\b|\s+Email\s+a\s+Friend\b|$)",
    re.IGNORECASE,
)
_VARIANT_RE = re.compile(r"\b(No Confinement|Day Visits|Overnight|Mixed)\b", re.IGNORECASE)


def _parse_card(card) -> dict | None:
    text = " ".join(card.get_text(" ", strip=True).split())
    # First word(s) before the first "Check In:" is the trial title.
    title_match = re.match(r"(.+?)\s+Check\s+In\s*:", text)
    if not title_match:
        return None
    title = title_match.group(1).strip()
    slug = slugify(title) or "unknown"
    study_id = f"{CLINIC_SLUG}-{slug}"

    fields: dict[str, str] = {}
    for m in _LABEL_RE.finditer(text):
        fields[m.group("k").lower().replace(" ", "")] = m.group("v").strip()

    # Confinement variant — derive study_type from the badge between labels.
    variant = ""
    vm = _VARIANT_RE.search(text)
    if vm:
        variant = vm.group(1).lower()

    comp_raw = fields.get("stipend")
    compensation = parse_money(comp_raw)

    age_raw = fields.get("age")
    age_min, age_max = parse_age_range(age_raw) if age_raw else (None, None)

    gender = fields.get("gender") or ""
    sex = _classify_sex(gender)

    check_in = fields.get("checkin")
    dates_raw = f"Check In: {check_in}" if check_in else None

    nights = 0 if variant in ("no confinement", "day visits") else None
    visits = None  # AbbVie doesn't post an outpatient visit count
    if variant == "day visits":
        study_type = "outpatient"
    elif variant == "overnight":
        study_type = "inpatient"
    elif variant == "mixed":
        study_type = "mixed"
    elif variant == "no confinement":
        study_type = "outpatient"
    else:
        study_type = "unknown"

    flag_spinal, flag_childbearing = detect_flags(text + " " + title)
    healthy = True  # AbbVie ACPRU posts only healthy-volunteer trials publicly.

    return {
        "id": study_id,
        "clinic": CLINIC_NAME,
        "location": LOCATION,
        "state": STATE,
        "title": title,
        "compensation": compensation,
        "compensation_raw": comp_raw,
        "study_type": study_type,
        "nights": nights,
        "visits": visits,
        "screening_date_raw": None,
        "dates_raw": dates_raw,
        "sex": sex,
        "sex_notes": None,
        "age_min": age_min,
        "age_max": age_max,
        "age_raw": age_raw,
        "healthy": healthy,
        "flag_spinal": flag_spinal,
        "flag_childbearing": flag_childbearing,
        "url": SITE_URL,
        "scraped_at": now_iso(),
    }


def _classify_sex(gender: str) -> str:
    low = gender.lower()
    if ("men" in low and "women" in low) or ("male" in low and "female" in low):
        return "ALL"
    if "female" in low or "women" in low:
        return "FEMALE"
    if "male" in low or "men" in low:
        return "MALE"
    return "ALL"


# ---------- standalone test entrypoint ----------

if __name__ == "__main__":
    import json
    studies = scrape()
    print(json.dumps(studies, indent=2, ensure_ascii=False))
    print(f"\n{len(studies)} AbbVie trial(s).")
