"""Celerion (Lincoln, NE) — helpresearch.com.

Celerion runs Phase 1 units in Lincoln NE (primary), Phoenix AZ, and Belfast
Northern Ireland. This module keeps only the Lincoln trials. We use the
clinic's own location page `/location/clinical-trials-lincoln-nebraska` as
the listing index — every /medical-study/<slug> linked from there is a
Lincoln cohort.

The site's robots.txt sets `Crawl-delay: 10`, so we add an extra 9-second
sleep between requests (on top of the 1s baseline in `common.fetch`) to keep
to ~10s per request as requested.

Some Celerion content lives behind a participant account; per Phase 3 spec
we only parse what's publicly visible. Many fields will be null on some
studies — that's correct.
"""

from __future__ import annotations

import re
import time

from bs4 import BeautifulSoup

from scraper.common import (
    ScraperError,
    detect_flags,
    fetch,
    now_iso,
    parse_age_range,
    parse_money,
    robots_allows,
    slugify,
)


BASE = "https://helpresearch.com"
LINCOLN_INDEX_URL = BASE + "/location/clinical-trials-lincoln-nebraska"
CLINIC_NAME = "Celerion"
LOCATION = "Lincoln, NE"
STATE = "NE"
CLINIC_SLUG = "celerion-lincoln"
EXTRA_DELAY_SECONDS = 9  # on top of common.fetch's 1s baseline

_STUDY_PATH_RE = re.compile(r"^/medical-study/[^/?#]+/?$")


def scrape() -> list[dict]:
    if not robots_allows(BASE, BASE + "/"):
        raise ScraperError(f"robots.txt disallows {BASE}/")
    if not robots_allows(BASE, LINCOLN_INDEX_URL):
        raise ScraperError(f"robots.txt disallows {LINCOLN_INDEX_URL}")

    _polite_sleep()
    index_html = fetch(LINCOLN_INDEX_URL)
    study_urls = _discover_study_urls(index_html)
    if not study_urls:
        # Celerion legitimately has no Lincoln cohorts on slow days — this is
        # the "success-with-zero-studies" path the orchestrator tolerates.
        print(f"[celerion-lincoln] no /medical-study/ links on {LINCOLN_INDEX_URL}")
        return []
    print(f"[celerion-lincoln] location page yielded {len(study_urls)} URL(s)")

    studies: list[dict] = []
    for url in study_urls:
        if not robots_allows(BASE, url):
            print(f"[celerion-lincoln] robots.txt disallows {url} — skipping")
            continue
        _polite_sleep()
        html = fetch(url)
        study = _parse_study(html, url)
        if study is None:
            continue
        print(
            f"[celerion-lincoln]   {study['title']!r} comp=${study['compensation']} "
            f"sex={study['sex']} ages={study['age_min']}-{study['age_max']} "
            f"nights={study['nights']} visits={study['visits']}"
        )
        studies.append(study)
    return studies


def _polite_sleep() -> None:
    """Honor the 10s Crawl-delay set in helpresearch.com/robots.txt. The shared
    fetch() helper still enforces its own 1s gap, so this is purely additive."""
    time.sleep(EXTRA_DELAY_SECONDS)


def _discover_study_urls(index_html: str) -> list[str]:
    soup = BeautifulSoup(index_html, "html.parser")
    found: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        h = a["href"].strip()
        path = h
        if h.startswith(BASE):
            path = h[len(BASE):]
        if not _STUDY_PATH_RE.match(path):
            continue
        full = BASE + path
        if full not in seen:
            seen.add(full)
            found.append(full)
    return found


# ---------- per-study parsing ----------

_FIELD_PATTERNS = {
    "Stipend":      re.compile(
        r"Stipend\s*:\s*(.+?)(?=\s+Study\s|\s+Age\s*:|\s+BMI\s*:|$)",
        re.IGNORECASE,
    ),
    "Age":          re.compile(r"\bAge\s*:\s*([0-9\-\s]{3,15})", re.IGNORECASE),
    "Length":       re.compile(
        r"Study\s+Length\s*:\s*(.+?)(?=\s+(?:Screening|Doctor|Study|Schedule)\s+(?:Dates?|Type|Information)|$)",
        re.IGNORECASE,
    ),
    "Requirement":  re.compile(
        r"Study\s+Requirement\s*:\s*(.+?)(?=\s+Stipend)",
        re.IGNORECASE,
    ),
    "Study Number": re.compile(r"Study\s+Number\s*:\s*([A-Z0-9\-]+)", re.IGNORECASE),
    "Group Number": re.compile(r"Group\s+Number\s*:\s*(\d+)", re.IGNORECASE),
    "Start Date":   re.compile(
        r"Start\s+Date\s*:\s*(.+?)(?=\s+End\s+Date\b)",
        re.IGNORECASE,
    ),
    "End Date":     re.compile(
        r"End\s+Date\s*:\s*(.+?)(?=\s+Study\s+Details\b)",
        re.IGNORECASE,
    ),
    "Indication":   re.compile(r"Indication\s*:\s*([^.\n]+\.)", re.IGNORECASE),
}

# Match "20 - Night Stay" / "8 Night Stay" / "20-Night Stay" — the hyphen is
# inconsistent across studies (was the original bug spotted in §2).
_NIGHTS_RE = re.compile(r"(\d+)\s*-?\s*Night\s+Stay", re.IGNORECASE)
_RETURNS_RE = re.compile(r"&\s*(\d+)\s+Returns?", re.IGNORECASE)


def _parse_study(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())

    # Sanity: the page must look like a Celerion study page (has "Study Details").
    if "Study Details" not in text:
        raise ScraperError(f"'Study Details' marker missing on {url} — layout drift")

    fields: dict[str, str] = {}
    for name, pat in _FIELD_PATTERNS.items():
        m = pat.search(text)
        if m:
            fields[name] = m.group(1).strip()

    # Lincoln-only check via the Study Dates table column.
    if "Lincoln" not in text:
        return None

    # Compensation
    comp_raw = fields.get("Stipend")
    compensation = parse_money(comp_raw) if comp_raw else None

    # Title: prefer "Study Number-Group" prefix + Study Requirement descriptor
    # so the card shows something human-readable.
    requirement = fields.get("Requirement") or ""
    study_no = fields.get("Study Number") or ""
    group_no = fields.get("Group Number") or ""
    if study_no and group_no and requirement:
        title = f"{study_no}-{group_no}: {requirement}"
    elif requirement:
        title = requirement
    else:
        # Fall back to the page title minus the brand suffix.
        tt = soup.find("title")
        title = (tt.get_text(strip=True).split("|")[0].strip() if tt else "Celerion study")

    # Age
    age_raw = fields.get("Age")
    age_min, age_max = parse_age_range(age_raw) if age_raw else (None, None)

    # Nights / visits from "Study Length: 20 - Night Stay & 2 Returns"
    length_raw = fields.get("Length")
    nights = _maybe_int(_NIGHTS_RE, length_raw or "")
    visits = _maybe_int(_RETURNS_RE, length_raw or "")

    if nights and nights > 0 and visits and visits > 0:
        study_type = "mixed"
    elif nights and nights > 0:
        study_type = "inpatient"
    elif visits and visits > 0:
        study_type = "outpatient"
    else:
        study_type = "unknown"

    sex, healthy = _classify_requirement(requirement, text)

    # Dates: assemble Start/End if present.
    parts = []
    if fields.get("Start Date"):
        parts.append(f"Start: {fields['Start Date']}")
    if fields.get("End Date"):
        parts.append(f"End: {fields['End Date']}")
    dates_raw = "; ".join(parts) if parts else None

    flag_spinal, flag_childbearing = detect_flags(text + " " + title)

    slug = url.rstrip("/").rsplit("/", 1)[-1]
    study_id = f"{CLINIC_SLUG}-{slugify(slug)}"

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
        "url": url,
        "scraped_at": now_iso(),
    }


def _classify_requirement(requirement: str, body: str) -> tuple[str, bool]:
    """The 'Study Requirement' field is authoritative when present, e.g.
    'Healthy Normal Male' or 'Healthy Females Postmenopausal Surgically
    Sterile'. Fall back to body keywords."""
    target = requirement or body[:500]
    low = target.lower()
    healthy = "healthy" in low
    has_m = bool(re.search(r"\bmale[s]?\b|\bmen\b", low))
    has_f = bool(re.search(r"\bfemale[s]?\b|\bwomen\b", low))
    if has_m and has_f:
        sex = "ALL"
    elif has_f:
        sex = "FEMALE"
    elif has_m:
        sex = "MALE"
    else:
        sex = "ALL"
    return sex, healthy


def _maybe_int(pattern: re.Pattern, text: str) -> int | None:
    m = pattern.search(text)
    return int(m.group(1)) if m else None


# ---------- standalone test entrypoint ----------

if __name__ == "__main__":
    import json
    studies = scrape()
    print(json.dumps(studies, indent=2, ensure_ascii=False))
    print(f"\n{len(studies)} Lincoln trial(s).")
