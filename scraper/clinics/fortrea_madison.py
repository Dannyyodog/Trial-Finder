"""Fortrea (Madison, WI) — fortreaclinicaltrials.com.

Fortrea runs three US Phase 1 units (Madison WI, Dallas TX, Daytona Beach FL);
this module keeps only the Madison ones. Source of truth for currently-recruiting
studies is the `/en-us/clinical-research/browse-studies` landing page.

Each per-study URL renders a fixed set of `<p class="heading">` label widgets
with sibling values, grouped as info "cells":

    Dates       : Jun 04 2026-Jun 17 2026
    Group       : C1
    Location    : Madison, Wisconsin   <-- the location filter
    Age         : 18-60
    Gender      : Male and Female
    Smokers Allowed : No
    Compensation: $4,277
    Referral    : $300                  <-- referral bonus, NOT participant pay

There's also an "Additional Details" section with Check-in: / Check-out: /
Call: lines that we include in dates_raw when present.

Per Phase 3 §1a: any unrecoverable structural surprise raises an exception; the
orchestrator turns that into a FAIL row in the run-summary table.
"""

from __future__ import annotations

import re

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


BASE = "https://www.fortreaclinicaltrials.com"
INDEX_URL = BASE + "/en-us/clinical-research/browse-studies"
CLINIC_NAME = "Fortrea"
LOCATION = "Madison, WI"
STATE = "WI"
CLINIC_SLUG = "fortrea-madison"

# Slugs on the index that are NOT studies (other pages under /clinical-research/).
_NON_STUDY_SLUGS = frozenset({
    "browse-studies", "phase-i-studies", "ame-studies", "participants-guide",
    "frequently-asked-questions-about-clinical-trials", "refer-friend",
    "clinical-trial-visit-checklist", "getting-paid-clinical-trials",
    "upcoming-volunteers-needed-upcoming-trials",
})

_STUDY_PATH_RE = re.compile(r"^/en-us/clinical-research/([^/?#]+)/?$")


def scrape() -> list[dict]:
    if not robots_allows(BASE, BASE + "/"):
        raise ScraperError(f"robots.txt disallows {BASE}/")
    if not robots_allows(BASE, INDEX_URL):
        raise ScraperError(f"robots.txt disallows {INDEX_URL}")

    index_html = fetch(INDEX_URL)
    study_urls = _discover_study_urls(index_html)
    if not study_urls:
        raise ScraperError(
            f"No study URLs discovered on {INDEX_URL} — page layout likely changed."
        )
    print(f"[fortrea-madison] browse page yielded {len(study_urls)} candidate URL(s)")

    studies: list[dict] = []
    skipped = 0
    for url in study_urls:
        if not robots_allows(BASE, url):
            print(f"[fortrea-madison] robots.txt disallows {url} — skipping")
            continue
        html = fetch(url)
        study = _parse_study(html, url)
        if study is None:
            skipped += 1
            continue
        print(
            f"[fortrea-madison]   {study['title']!r} "
            f"comp=${study['compensation']} sex={study['sex']} "
            f"ages={study['age_min']}-{study['age_max']}"
        )
        studies.append(study)
    print(f"[fortrea-madison] kept {len(studies)} Madison cohort(s); "
          f"skipped {skipped} non-Madison")
    return studies


# ---------- discovery ----------

def _discover_study_urls(index_html: str) -> list[str]:
    soup = BeautifulSoup(index_html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        h = a["href"].strip()
        m = _STUDY_PATH_RE.match(h)
        if not m:
            continue
        if m.group(1) in _NON_STUDY_SLUGS:
            continue
        full = BASE + h
        if not full.endswith("/"):
            pass  # paths without trailing slash are fine on Fortrea
        if full not in seen:
            seen.add(full)
            urls.append(full)
    return urls


# ---------- per-study parsing ----------

# slug patterns that nail down nights/visits without ambiguity
_SLUG_NIGHTS_RE = re.compile(r"(\d+)[- ]nights?\b", re.IGNORECASE)
_SLUG_OPVS_RE = re.compile(r"(\d+)[- ]opvs?\b", re.IGNORECASE)


def _parse_study(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    info_pairs = _collect_info_pairs(soup)
    if not info_pairs:
        raise ScraperError(
            f"No <p class=\"heading\">…</p> info blocks on {url} — page layout "
            "likely changed."
        )

    # Filter to Madison only.
    location_value = info_pairs.get("Location") or info_pairs.get("location")
    if not location_value:
        # Not a study page, skip silently.
        return None
    if "madison" not in location_value.lower():
        return None

    title = _study_title(soup, url)
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    study_id = f"{CLINIC_SLUG}-{slugify(slug)}"

    comp_raw = info_pairs.get("Compensation")
    compensation = parse_money(comp_raw) if comp_raw else None

    sex_raw = info_pairs.get("Gender") or ""
    sex = _classify_sex(sex_raw)

    age_raw = info_pairs.get("Age")
    age_min, age_max = parse_age_range(age_raw)

    dates_struct = info_pairs.get("Dates")
    dates_extra = _extract_additional_details(soup)
    dates_parts = [p for p in (dates_struct, dates_extra) if p]
    dates_raw = "; ".join(dates_parts) if dates_parts else None

    # Phase 3.1: derive nights/visits/study_type from the prose "Additional
    # Details" block on top of any URL-slug-based hints. The slug values were
    # only ever set when the slug happened to contain "<N>-nights" / "<N>-opvs"
    # phrasings (rare); the prose pass is the reliable signal.
    nights_slug = _maybe_int(_SLUG_NIGHTS_RE, slug)
    visits_slug = _maybe_int(_SLUG_OPVS_RE, slug)
    nights_prose, visits_prose = _derive_from_additional_details(soup, url)

    # Prefer prose-derived values when present; only fall back to slug when prose
    # didn't expose anything (the slug parse is opportunistic and rarely fires).
    nights = nights_prose if nights_prose is not None else nights_slug
    visits = visits_prose if visits_prose is not None else visits_slug

    if (nights or 0) >= 1 and (visits or 0) >= 1:
        study_type = "mixed"
    elif (nights or 0) >= 1:
        study_type = "inpatient"
    elif (visits or 0) >= 1:
        study_type = "outpatient"
    else:
        study_type = "unknown"

    body_text = _main_text(soup)
    flag_spinal, flag_childbearing = detect_flags(body_text + " " + title)

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
        "healthy": True,
        "flag_spinal": flag_spinal,
        "flag_childbearing": flag_childbearing,
        "url": url,
        "scraped_at": now_iso(),
    }


def _collect_info_pairs(soup: BeautifulSoup) -> dict[str, str]:
    """Walk every `.info` block on the page and build {heading_text: value_text}.

    Multiple .info blocks with the same heading: take the first occurrence (the
    page's prominent area). This is fine because Fortrea publishes one cohort
    per URL — multi-cohort listings would each have their own dedicated URL.
    """
    pairs: dict[str, str] = {}
    for info in soup.select(".info"):
        heading = info.select_one(".heading")
        if not heading:
            continue
        key = " ".join(heading.get_text(" ", strip=True).split())
        if not key:
            continue
        # The value is the next sibling that isn't another .heading
        sib = heading.find_next_sibling(["p", "div", "span"])
        if not sib:
            continue
        val = " ".join(sib.get_text(" ", strip=True).split())
        if not val or key in pairs:
            continue
        pairs[key] = val
    return pairs


def _study_title(soup: BeautifulSoup, url: str) -> str:
    h1 = soup.find("h1")
    if h1:
        t = " ".join(h1.get_text(" ", strip=True).split())
        if t:
            return t
    tt = soup.find("title")
    if tt:
        t = tt.get_text(" ", strip=True).split("|")[0].strip()
        if t:
            return t
    raise ScraperError(f"Could not determine title for {url}")


def _classify_sex(text: str) -> str:
    low = text.lower()
    if ("male" in low and "female" in low) or ("men" in low and "women" in low):
        return "ALL"
    if "female" in low or "women" in low:
        return "FEMALE"
    if "male" in low or "men" in low:
        return "MALE"
    return "ALL"  # default for ambiguous text


def _extract_additional_details(soup: BeautifulSoup) -> str | None:
    """Find the 'Additional Details' h2 and return concatenated lines below it.

    Includes Check-in / Check-out / Call / OPV-style lines but stops at the
    next h2 to avoid pulling in BMI calculator / footer noise.
    """
    h = next(
        (h for h in soup.find_all(["h2", "h3"])
         if "additional details" in h.get_text(strip=True).lower()),
        None,
    )
    if not h:
        return None
    lines: list[str] = []
    for sib in h.find_all_next():
        if sib.name in ("h1", "h2") and sib is not h:
            break
        if sib.name == "p":
            t = " ".join(sib.get_text(" ", strip=True).split())
            if t:
                lines.append(t)
    return " | ".join(lines) if lines else None


# --- Phase 3.1: prose-derived nights / visits ------------------------------

# Headings that introduce a *visit* list. "Phone Calls" is intentionally NOT
# here — phone calls aren't visits per the schema.
_VISITS_HEADING_RE = re.compile(
    r"\bfollow[- ]?up\s+visits?\b",
    re.IGNORECASE,
)
_POTENTIAL_HEADING_RE = re.compile(
    r"\bpotential\s+follow[- ]?ups?\b",
    re.IGNORECASE,
)
# Headings that end the visits section if we encounter them.
_STOP_HEADING_RE = re.compile(
    r"\bphone\s+calls?\b|\bdesigns?\s+are\s+selected\b",
    re.IGNORECASE,
)

# Check-in/Check-out lines (handle both "Check-in:" and "Check in:" forms).
_CHECKIN_RE = re.compile(
    r"check[\s\-]?in\s*:\s*([A-Za-z]+\.?\s+\d{1,2}(?:[a-z]{2})?(?:,\s*\d{4})?|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)
_CHECKOUT_RE = re.compile(
    r"check[\s\-]?out\s*:\s*([A-Za-z]+\.?\s+\d{1,2}(?:[a-z]{2})?(?:,\s*\d{4})?|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)

# A date fragment inside a bullet ("June 21", "21", "Jun 5", "Sep 19th").
_DATE_TOKEN_RE = re.compile(
    r"^(?:(?P<m>[A-Za-z]+\.?)\s+)?(?P<d>\d{1,2})(?:st|nd|rd|th)?$",
)


def _derive_from_additional_details(
    soup: BeautifulSoup,
    url: str,
) -> tuple[int | None, int | None]:
    """Phase 3.1 patch: read nights and visits from the prose body.

    Returns (nights, visits). Either may be None when not confidently found —
    that's the same null-when-unknown rule the schema uses everywhere else.
    """
    section_siblings = _find_additional_details_siblings(soup)
    if not section_siblings:
        return None, None

    # Joined text of the whole section — used for nights parsing only.
    section_text = " ".join(
        " ".join(s.get_text(" ", strip=True).split())
        for s in section_siblings
        if hasattr(s, "get_text")
    )

    nights = _parse_nights_from_section(section_text, url)
    visits = _parse_visits_from_section(section_siblings, url)
    return nights, visits


def _find_additional_details_siblings(soup: BeautifulSoup) -> list:
    """Return the list of sibling Tags between the Additional Details h2 and
    the next h1/h2 (BMI Calculator, etc.). Strictly siblings — no descendants."""
    h = next(
        (h for h in soup.find_all(["h2", "h3"])
         if "additional details" in h.get_text(strip=True).lower()),
        None,
    )
    if not h:
        return []
    sibs = []
    for sib in h.next_siblings:
        if getattr(sib, "name", None) is None:
            # NavigableString between tags — skip whitespace-only text.
            if str(sib).strip():
                # rare; keep for completeness but unlikely to matter
                continue
            continue
        if sib.name in ("h1", "h2"):
            break
        sibs.append(sib)
    return sibs


def _parse_nights_from_section(section_text: str, url: str) -> int | None:
    """Compute nights from check-in / check-out dates. Returns None if either
    is missing or the diff is implausible (<=0 or >60 days)."""
    try:
        from dateutil import parser as _dt
    except ImportError:
        # No dateutil → fall back to None silently; orchestrator still gets a
        # valid record, just without nights derived from prose.
        return None

    cm = _CHECKIN_RE.search(section_text)
    om = _CHECKOUT_RE.search(section_text)
    if not cm or not om:
        return None
    try:
        ci = _dt.parse(cm.group(1), fuzzy=True)
        co = _dt.parse(om.group(1), fuzzy=True)
    except (ValueError, OverflowError):
        print(f"[fortrea-madison] could not parse check-in/out on {url}: "
              f"{cm.group(1)!r} / {om.group(1)!r}")
        return None
    delta = (co.date() - ci.date()).days
    # If check-out parsed to a year-earlier (rare year-rollover heuristic),
    # add 365 days. Then validate.
    if delta < 0:
        delta += 365
    if delta < 1 or delta > 60:
        print(f"[fortrea-madison] implausible nights delta {delta} on {url} "
              f"({cm.group(1)} -> {om.group(1)}); treating as null")
        return None
    return delta


def _parse_visits_from_section(section_siblings: list, url: str) -> int | None:
    """Count date tokens under the "Follow up Visits:" heading (and any
    "Potential Follow-ups:" subsection), explicitly excluding "Phone Calls:".

    The section's structure is a sequence of Tag siblings (mostly <p> and
    <ul>). The "Follow up Visits:" label sits inline inside a <p>; the
    bulleted dates are the NEXT <ul> sibling. "Potential Follow-ups:" can be
    inline in a <p> (label + dates on the same line). "Phone Calls:" if seen
    ends the count.
    """
    if not section_siblings:
        return None

    # Did the section even mention Follow up Visits?
    joined = " ".join(
        " ".join(s.get_text(" ", strip=True).split()) for s in section_siblings
    )
    if not _VISITS_HEADING_RE.search(joined):
        return None

    visits_total = 0
    in_visits = False
    in_potential = False

    for sib in section_siblings:
        txt = " ".join(sib.get_text(" ", strip=True).split())
        if not txt and sib.name != "ul":
            continue

        # Section terminators — "Phone Calls:" or the designs footnote.
        if (in_visits or in_potential) and _STOP_HEADING_RE.search(txt):
            break

        if sib.name in ("p", "h3", "h4"):
            # Headings inside <p>: detect label transitions, then if the same
            # paragraph also carries inline dates (the Potential Follow-ups
            # case), count those tokens.
            if _VISITS_HEADING_RE.search(txt):
                in_visits, in_potential = True, False
                continue
            if _POTENTIAL_HEADING_RE.search(txt):
                in_visits, in_potential = False, True
                # Strip the label itself before counting inline dates.
                tail = _POTENTIAL_HEADING_RE.split(txt, maxsplit=1)[-1]
                visits_total += _count_dates_in_bullet(tail)
                continue
            # A non-label paragraph in the potential section may carry the
            # inline date list (rare layout).
            if in_potential:
                visits_total += _count_dates_in_bullet(txt)
            continue

        if sib.name == "ul" and in_visits:
            for li in sib.find_all("li", recursive=False) or sib.find_all("li"):
                bullet = " ".join(li.get_text(" ", strip=True).split())
                visits_total += _count_dates_in_bullet(bullet)
            continue

    return visits_total


def _count_dates_in_bullet(bullet: str) -> int:
    """Count comma/ampersand-separated date fragments inside one bullet line.

    Rules:
      * Strip leading punctuation that survived label splitting (": ", "- ", etc.).
      * Split on commas AND ampersands.
      * Trim whitespace; drop empty tokens.
      * Each token must be a date fragment: starts with a month name OR is a
        1–2 digit day number (which inherits the most recent month).
    """
    if not bullet:
        return 0
    bullet = bullet.lstrip(":-•– \t")
    raw_tokens = re.split(r"[,&]", bullet)
    count = 0
    current_month = None
    for tok in raw_tokens:
        tok = tok.strip(" .;:-")
        if not tok:
            continue
        m = _DATE_TOKEN_RE.match(tok)
        if not m:
            continue
        if m.group("m"):
            current_month = m.group("m")
            count += 1
        elif current_month:
            # day-only token like "24" or "29" following a month-prefixed one
            count += 1
        # else: bare day with no preceding month — skip, can't trust it
    return count


def _main_text(soup: BeautifulSoup) -> str:
    main = soup.find("main") or soup
    from copy import copy
    mc = copy(main)
    for t in mc(["script", "style", "noscript", "form"]):
        t.decompose()
    return " ".join(mc.get_text(" ", strip=True).split())


def _maybe_int(pattern: re.Pattern, text: str) -> int | None:
    m = pattern.search(text)
    return int(m.group(1)) if m else None


# ---------- standalone test entrypoint (§4 of Phase 3 spec) ----------

if __name__ == "__main__":
    import json
    studies = scrape()
    print(json.dumps(studies, indent=2, ensure_ascii=False))
    print(f"\n{len(studies)} Madison cohort(s).")
