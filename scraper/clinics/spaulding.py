"""Spaulding Clinical (West Bend, WI) — spauldingpays.com.

Selectors here come from the live site as it actually exists (2026-05). The pages
are built with Elementor on top of WordPress; every study page renders the same
sequence of `.elementor-heading-title` widgets:

    Study Name: <Name>
    Compensation
    $<amount>           <-- compensation
    <sex line>          <-- e.g. "Male & Female", "Healthy male"
    Ages: <range>
    BMI ...
    Dates
    ...

The canonical index of currently-recruiting studies is the WordPress sitemap
(`/sitemap.xml`); the homepage no longer lists studies directly.

Hard guarantee: if the page layout doesn't match (no Compensation heading, no
$ amount, etc.), this module raises ScraperError. The orchestrator turns that
into a non-zero exit and refuses to overwrite docs/studies.json.
"""

from __future__ import annotations

import re
from lxml import etree

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


BASE = "https://www.spauldingpays.com"
SITEMAP_URL = BASE + "/sitemap.xml"
CLINIC_NAME = "Spaulding Clinical"
LOCATION = "West Bend, WI"
STATE = "WI"
CLINIC_SLUG = "spaulding"

STUDY_URL_RE = re.compile(r"^https?://www\.spauldingpays\.com/study/[^/]+/?$")
_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def scrape() -> list[dict]:
    """Return a list of study dicts (full schema). Raises ScraperError on failure."""
    if not robots_allows(BASE, BASE + "/"):
        raise ScraperError(f"robots.txt disallows scraping {BASE}/")

    study_urls = _discover_study_urls()
    if not study_urls:
        raise ScraperError(
            "No study URLs discovered in Spaulding sitemap — site structure likely "
            f"changed. Source: {SITEMAP_URL}"
        )

    print(f"[spaulding] sitemap yielded {len(study_urls)} study URL(s)")

    studies: list[dict] = []
    for url in study_urls:
        if not robots_allows(BASE, url):
            print(f"[spaulding] robots.txt disallows {url} — skipping")
            continue
        html = fetch(url)
        study = _parse_study(html, url)
        print(
            f"[spaulding]   {study['title']!r} "
            f"comp=${study['compensation']} nights={study['nights']} "
            f"visits={study['visits']} sex={study['sex']} "
            f"ages={study['age_min']}-{study['age_max']}"
        )
        studies.append(study)

    if not studies:
        raise ScraperError(
            "Spaulding scrape produced zero studies after fetching the sitemap. "
            "Refusing to return empty result."
        )
    return studies


# ---------- sitemap discovery ----------

def _discover_study_urls() -> list[str]:
    """Read the WordPress sitemap and return every URL under /study/<slug>/."""
    xml_text = fetch(SITEMAP_URL)
    # Use lxml.etree (not stdlib xml.etree) because Spaulding's sitemap.xml
    # starts with an <?xml-stylesheet?> processing instruction right after the
    # XML declaration. That's legal XML, but stdlib ET refuses it. lxml is
    # already an installed dependency. Encode to bytes — lxml prefers bytes
    # and that avoids subtle behavior changes around the XML declaration.
    try:
        root = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as e:
        raise ScraperError(f"sitemap.xml is not valid XML: {e}")

    urls: list[str] = []
    for loc in root.findall("sm:url/sm:loc", _NS):
        u = (loc.text or "").strip()
        if STUDY_URL_RE.match(u):
            if not u.endswith("/"):
                u += "/"
            urls.append(u)
    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ---------- per-study parsing ----------

def _parse_study(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # --- title ---
    title = _study_title(soup, url)
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    study_id = f"{CLINIC_SLUG}-{slugify(slug)}"

    # --- ordered list of Elementor heading-title texts ---
    headings: list[str] = []
    for h in soup.select(".elementor-heading-title"):
        t = " ".join(h.get_text(" ", strip=True).split())
        if t:
            headings.append(t)
    if not headings:
        raise ScraperError(
            f"No .elementor-heading-title widgets found on {url} — page layout "
            "likely changed."
        )

    try:
        i_comp = next(
            i for i, t in enumerate(headings) if t.strip().lower() == "compensation"
        )
    except StopIteration:
        raise ScraperError(
            f'Expected a "Compensation" heading widget on {url} but found none.'
        )

    if i_comp + 4 >= len(headings):
        raise ScraperError(
            f'Expected $amount/sex/ages/BMI headings after "Compensation" on {url}; '
            f"only {len(headings) - i_comp - 1} more headings present."
        )

    comp_raw = headings[i_comp + 1]
    sex_raw = headings[i_comp + 2]
    age_raw_full = headings[i_comp + 3]
    # headings[i_comp + 4] is BMI — captured but not in schema.

    compensation = parse_money(comp_raw)
    if compensation is None:
        raise ScraperError(
            f'Could not parse a $ amount from "{comp_raw}" on {url}.'
        )

    sex, sex_notes = _classify_sex(sex_raw)
    age_clean = re.sub(r"^\s*ages?\s*:?\s*", "", age_raw_full, flags=re.IGNORECASE).strip()
    age_min, age_max = parse_age_range(age_clean)

    # --- body text for nights/visits/flag detection ---
    body_text = _main_text(soup)

    nights = _parse_nights(body_text)
    visits = _parse_visits(body_text)

    if nights and nights > 0 and visits and visits > 0:
        study_type = "mixed"
    elif nights and nights > 0:
        study_type = "inpatient"
    elif visits and visits > 0:
        study_type = "outpatient"
    else:
        study_type = "unknown"

    dates_raw = _extract_dates_block(soup)
    screening_date_raw = None  # No per-study screening date strings on these pages.

    flag_spinal, flag_childbearing = detect_flags(body_text)

    # Spaulding studies are explicitly "healthy volunteer" unless a page
    # signals otherwise. We see "healthy male" / "healthy male and female" all
    # over the bodies; default to True. If a future patient-population study
    # ever appears, this is the field to revisit.
    healthy = True

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
        "screening_date_raw": screening_date_raw,
        "dates_raw": dates_raw,
        "sex": sex,
        "sex_notes": sex_notes,
        "age_min": age_min,
        "age_max": age_max,
        "age_raw": age_clean or None,
        "healthy": healthy,
        "flag_spinal": flag_spinal,
        "flag_childbearing": flag_childbearing,
        "url": url,
        "scraped_at": now_iso(),
    }


def _study_title(soup: BeautifulSoup, url: str) -> str:
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        t = og["content"].split("|")[0].strip()
        if t:
            return t
    # Fallback: "Study Name: X" heading widget.
    for h in soup.select(".elementor-heading-title"):
        m = re.match(
            r"^\s*study\s+name\s*:\s*(.+)$",
            " ".join(h.get_text(" ", strip=True).split()),
            flags=re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
    raise ScraperError(f"Could not determine study title for {url}")


def _classify_sex(text: str) -> tuple[str, str | None]:
    """Map the free-text sex line to ('ALL'|'FEMALE'|'MALE', notes-or-None)."""
    cleaned = re.sub(r"(?i)\bhealthy\b", "", text).strip(" -–—:")
    low = cleaned.lower()
    if "male" in low and "female" in low:
        sex = "ALL"
    elif low.startswith("female") or low == "female" or "female" in low.split():
        sex = "FEMALE"
    elif "male" in low.split() or low.startswith("male"):
        sex = "MALE"
    else:
        sex = "ALL"
    notes: str | None = None
    # Capture any extra qualifier text (e.g. "Postmenopausal or surgically sterile women").
    extras = re.sub(r"(?i)\bhealthy\b", "", text)
    extras = re.sub(r"(?i)(male\s*&\s*female|male\s+and\s+female|female|male)", "", extras)
    extras = extras.strip(" -–—:,.")
    if extras and len(extras) > 2:
        notes = extras
    return sex, notes


def _main_text(soup: BeautifulSoup) -> str:
    main = soup.find("main") or soup
    # Work on a copy so we don't mutate the tree the caller still needs.
    from copy import copy
    main_copy = copy(main)
    for t in main_copy(["script", "style", "noscript", "form"]):
        t.decompose()
    return " ".join(main_copy.get_text(" ", strip=True).split())


# --- nights & visits ---

_DAYS_NIGHTS_RE = re.compile(
    r"(\d+)\s*days?\s*/\s*(\d+)\s*nights?",
    flags=re.IGNORECASE,
)
_MULTI_STAY_RE = re.compile(
    r"(\d+)\s+(?:separate\s+)?in[- ]?house\s+stays?\s*,?\s+each\s+lasting",
    flags=re.IGNORECASE,
)
_VISITS_RE = re.compile(
    r"(\d+)\s+(?:outpatient|follow[- ]?up)\s+visit",
    flags=re.IGNORECASE,
)


def _parse_nights(text: str) -> int | None:
    """Total overnight nights across the whole study, or None if not stated.

    Handles 'N separate in-house stays, each lasting X days/Y nights' (multiplies),
    and otherwise sums the night counts of every *distinct* 'X days/Y nights' pair.
    De-dup is important: the volunteer description paragraph often repeats the same
    'X days/Y nights' phrase that also appears in the Dates block.
    """
    pairs_all = _DAYS_NIGHTS_RE.findall(text)
    if not pairs_all:
        return None
    # Deduplicate while preserving first-seen order.
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []
    for p in pairs_all:
        if p not in seen:
            seen.add(p)
            pairs.append(p)
    m = _MULTI_STAY_RE.search(text)
    if m and len(pairs) == 1:
        return int(m.group(1)) * int(pairs[0][1])
    return sum(int(p[1]) for p in pairs)


def _parse_visits(text: str) -> int | None:
    """Outpatient/follow-up *visit* counts. Phone calls and texts do NOT count
    as visits. Returns None when the page doesn't mention any visit term."""
    total = 0
    found = False
    for m in _VISITS_RE.finditer(text):
        total += int(m.group(1))
        found = True
    return total if found else None


# --- dates block ---

_DATE_HINT_RE = re.compile(
    r"check\s*in\s*:|check\s*out\s*:|length of stay|"
    r"(?:cohort|group|part)\s+\d+\b|\bdates?\s+tbd\b|\bopv\b",
    flags=re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(
    r"empty placeholder|i am item content|lorem ipsum|^placeholder\b",
    flags=re.IGNORECASE,
)
# The volunteer description paragraph contains "X days/Y nights" too — we have
# to exclude it explicitly so the dates_raw field doesn't pick it up.
_VOLUNTEER_DESC_RE = re.compile(
    r"needs research volunteers|currently looking for|"
    r"may be eligible to receive payment|study related time and travel",
    flags=re.IGNORECASE,
)


def _extract_dates_block(soup: BeautifulSoup) -> str | None:
    """Find a block on the page that clearly shows study dates.

    Looks for date-shaped signals (Check in:/Check out:, Length of stay, Cohort N,
    Part N, Group N, Dates TBD, OPV:). Scans both text-editor widgets and
    Elementor accordion items (Spaulding's cohort schedules live in accordions).
    Ignores placeholders and the volunteer-description paragraph.
    """
    # 1) Accordion items first — these are the structured cohort/part schedules.
    for item in soup.select(".elementor-accordion-item"):
        title_el = item.select_one(".elementor-accordion-title")
        body_el = item.select_one(".elementor-tab-content")
        title = " ".join(title_el.get_text(" ", strip=True).split()) if title_el else ""
        body = " ".join(body_el.get_text(" ", strip=True).split()) if body_el else ""
        combined = f"{title}: {body}".strip(": ").strip()
        if not combined or not body:
            continue
        if _PLACEHOLDER_RE.search(combined):
            continue
        if _VOLUNTEER_DESC_RE.search(combined):
            continue
        if _DATE_HINT_RE.search(combined):
            return combined

    # 2) Otherwise look for a text-editor block (e.g. Quill's "Length of stay…").
    for w in soup.select("[data-widget_type]"):
        wt = w.get("data-widget_type", "")
        if "text-editor" not in wt:
            continue
        txt = " ".join(w.get_text(" ", strip=True).split())
        if not txt:
            continue
        if _PLACEHOLDER_RE.search(txt):
            continue
        if _VOLUNTEER_DESC_RE.search(txt):
            continue
        if _DATE_HINT_RE.search(txt):
            return txt
    return None
