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

    nights = _maybe_int(_SLUG_NIGHTS_RE, slug)
    visits = _maybe_int(_SLUG_OPVS_RE, slug)

    if nights and nights > 0 and visits and visits > 0:
        study_type = "mixed"
    elif nights and nights > 0:
        study_type = "inpatient"
    elif visits and visits > 0:
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
