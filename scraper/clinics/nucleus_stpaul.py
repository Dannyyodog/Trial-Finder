"""Nucleus Network (St. Paul, MN) — nucleusnetwork.com.

Nucleus runs three Phase 1 units worldwide (Brisbane AU, Melbourne AU, and the
US site that's published as "Minneapolis, United States" but the physical
clinic is in St. Paul, MN — we follow the Phase 3 spec's location naming).
This module keeps only the US (St. Paul) trials.

Discovery source: the WordPress trials sitemap at /post-trial-sitemap.xml,
which lists every published trial page regardless of the site's region-routed
landing page. For each /trial/<slug>/ URL we fetch the page and use:

  - the top-of-page label/value cards (Phase, Remuneration, Location) to
    decide whether to keep the trial (Recruiting + US-flavored Location), AND
  - the "Are you a match?" eligibility card (Age, Remuneration, Gender,
    Commitment, …) to extract age_min/max, sex, nights, visits, and a more
    detailed compensation string.

Per Phase 3 §1a: any structural surprise raises an exception; the orchestrator
turns that into a FAIL row.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

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


BASE = "https://www.nucleusnetwork.com"
SITEMAP_URL = BASE + "/post-trial-sitemap.xml"
CLINIC_NAME = "Nucleus Network"
LOCATION = "St. Paul, MN"
STATE = "MN"
CLINIC_SLUG = "nucleus-stpaul"

_TRIAL_PATH_RE = re.compile(r"^https?://www\.nucleusnetwork\.com/trial/[^/]+/?$")
_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# Phrases on the Location card that mark a US (St. Paul) trial. The site
# labels its US clinic as "Minneapolis" so check both.
_US_LOCATION_HINT_RE = re.compile(
    r"(united states|usa|minneapolis|st\.?\s*paul|minnesota|\bmn\b)",
    flags=re.IGNORECASE,
)
# Status text that means "open to new participants right now".
_RECRUITING_RE = re.compile(r"recruit", re.IGNORECASE)


def scrape() -> list[dict]:
    if not robots_allows(BASE, BASE + "/"):
        raise ScraperError(f"robots.txt disallows {BASE}/")
    if not robots_allows(BASE, SITEMAP_URL):
        raise ScraperError(f"robots.txt disallows {SITEMAP_URL}")

    trial_urls = _discover_trial_urls()
    if not trial_urls:
        raise ScraperError(
            "No /trial/ URLs in Nucleus sitemap — site structure likely changed."
        )
    print(f"[nucleus-stpaul] sitemap yielded {len(trial_urls)} candidate URL(s)")

    studies: list[dict] = []
    skipped_non_us = 0
    skipped_not_recruiting = 0
    for url in trial_urls:
        if not robots_allows(BASE, url):
            print(f"[nucleus-stpaul] robots.txt disallows {url} — skipping")
            continue
        html = fetch(url)
        outcome, study = _parse_study(html, url)
        if outcome == "non_us":
            skipped_non_us += 1
            continue
        if outcome == "not_recruiting":
            skipped_not_recruiting += 1
            continue
        if study is None:
            continue
        print(
            f"[nucleus-stpaul]   {study['title']!r} comp=${study['compensation']} "
            f"sex={study['sex']} ages={study['age_min']}-{study['age_max']} "
            f"nights={study['nights']} visits={study['visits']}"
        )
        studies.append(study)
    print(
        f"[nucleus-stpaul] kept {len(studies)} US trial(s); "
        f"skipped {skipped_non_us} non-US, {skipped_not_recruiting} not recruiting"
    )
    return studies


# ---------- sitemap discovery ----------

def _discover_trial_urls() -> list[str]:
    xml_text = fetch(SITEMAP_URL)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ScraperError(f"post-trial-sitemap.xml is not valid XML: {e}")
    out: list[str] = []
    seen: set[str] = set()
    for loc in root.findall("sm:url/sm:loc", _NS):
        u = (loc.text or "").strip()
        if _TRIAL_PATH_RE.match(u):
            if not u.endswith("/"):
                u += "/"
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


# ---------- per-trial parsing ----------

def _parse_study(html: str, url: str) -> tuple[str, dict | None]:
    """Returns one of:
      ("non_us", None)         — Location doesn't look like the US clinic.
      ("not_recruiting", None) — Status is closed/completed/etc.
      ("ok", dict)             — fully-built study dict.
    Raises ScraperError on unrecoverable structural surprise.
    """
    soup = BeautifulSoup(html, "html.parser")
    header_pairs = _header_label_value_pairs(soup)
    if not header_pairs:
        raise ScraperError(
            f"No top-of-page label/value cards on {url} — layout likely changed."
        )

    location_text = header_pairs.get("Location") or ""
    if not _US_LOCATION_HINT_RE.search(location_text):
        return "non_us", None

    status = header_pairs.get("Phase") or header_pairs.get("Status") or ""
    if status and not _RECRUITING_RE.search(status):
        return "not_recruiting", None

    title = _study_title(soup, url)
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    study_id = f"{CLINIC_SLUG}-{slugify(slug)}"

    eligibility = _eligibility_pairs(soup)

    # Compensation comes from the header card's Remuneration value (the
    # eligibility-card Remuneration is unreachable by text-scan without a
    # crisp terminator and isn't materially different anyway).
    comp_raw = header_pairs.get("Remuneration")
    compensation = parse_money(comp_raw) if comp_raw else None

    age_raw = eligibility.get("Age")
    age_min, age_max = parse_age_range(age_raw)

    sex_raw = eligibility.get("Gender") or eligibility.get("Sex") or ""
    sex = _classify_sex(sex_raw)

    nights, visits = _parse_commitment(
        eligibility.get("Commitment") or "",
        eligibility.get("Study Duration") or "",
        url,
    )

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

    return "ok", {
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
        "dates_raw": eligibility.get("Study Duration"),
        "sex": sex,
        "sex_notes": None,
        "age_min": age_min,
        "age_max": age_max,
        "age_raw": age_raw,
        "healthy": _is_healthy(title, body_text),
        "flag_spinal": flag_spinal,
        "flag_childbearing": flag_childbearing,
        "url": url,
        "scraped_at": now_iso(),
    }


def _header_label_value_pairs(soup: BeautifulSoup) -> dict[str, str]:
    """The Phase / Remuneration / Location card at the top of the page.

    Each entry is a <label>HEADING</label><p>VALUE</p> pair inside
    `.page-grid-content`.
    """
    container = soup.select_one(".page-grid-content")
    out: dict[str, str] = {}
    if not container:
        # Fall back to scanning the whole document for label+p pairs near the title.
        labels = soup.find_all("label")
    else:
        labels = container.find_all("label")
    for lab in labels:
        k = " ".join(lab.get_text(" ", strip=True).split())
        sib = lab.find_next_sibling(["p", "div", "span"])
        if not sib:
            continue
        v = " ".join(sib.get_text(" ", strip=True).split())
        if k and v and k not in out:
            out[k] = v
    return out


def _eligibility_pairs(soup: BeautifulSoup) -> dict[str, str]:
    """The 'Are you a match?' eligibility card.

    The page renders this as repeated paragraphs/headings; we collect
    HEADING -> VALUE by walking the page text for known labels.
    """
    text = " ".join(soup.get_text(" ", strip=True).split())
    out: dict[str, str] = {}
    # Known labels (Remuneration is intentionally NOT scanned here — the
    # header card already exposes it cleanly; scanning the text-flow lets the
    # eligibility-card Remuneration bleed past its terminator into Location).
    labels = [
        "Study Duration", "Medical condition", "Commitment",
        "Gender", "Age", "BMI", "Population",
    ]
    # Find label positions; value runs to the next known label.
    spans: list[tuple[int, str]] = []
    for L in labels:
        for m in re.finditer(rf"\b{re.escape(L)}\b", text):
            spans.append((m.start(), L))
    if not spans:
        return out
    spans.sort()
    for i, (pos, label) in enumerate(spans):
        end = spans[i + 1][0] if i + 1 < len(spans) else pos + 200
        chunk = text[pos + len(label):end].strip(" :")
        if chunk and label not in out:
            out[label] = chunk[:300]
    return out


def _classify_sex(text: str) -> str:
    low = text.lower()
    if ("male" in low and "female" in low) or ("men" in low and "women" in low):
        return "ALL"
    if "female" in low or "women" in low:
        return "FEMALE"
    if "male" in low or "men" in low:
        return "MALE"
    return "ALL"


_COMMIT_NIGHTS_RE = re.compile(r"(\d+)\s*nights?", re.IGNORECASE)
_COMMIT_VISITS_RE = re.compile(
    r"(\d+)\s*(?:clinic|outpatient|follow[- ]?up)?\s*visits?",
    re.IGNORECASE,
)


def _parse_commitment(commitment: str, duration: str, url: str) -> tuple[int | None, int | None]:
    """Extract (nights, visits). Look at the Commitment field first; fall back
    to the Study Duration field. Phone calls and texts don't count as visits."""
    combined = " ".join(s for s in (commitment, duration) if s)
    if not combined:
        return None, None
    nights = None
    visits = None
    m = _COMMIT_NIGHTS_RE.search(combined)
    if m:
        nights = int(m.group(1))
    m = _COMMIT_VISITS_RE.search(combined)
    if m:
        visits = int(m.group(1))
    # Sanity: clinic visit numbers under 50 only — bigger means we're matching
    # something else entirely.
    if visits is not None and visits > 50:
        visits = None
    if nights is not None and nights > 365:
        nights = None
    return nights, visits


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


def _is_healthy(title: str, body: str) -> bool:
    # Nucleus runs both healthy-volunteer and patient-population trials. The
    # spec defaults healthy=True for paid sources, but here we look for clear
    # patient-population language and flip to False.
    patient_markers = (
        "diagnosed with", "patients with", "diabetic kidney", "type 2 diabetes",
        "kidney disease", "moderate to severe", "for adults living with",
        "people with", "diagnosed", "psoriasis", "asthma",
    )
    low = (title + " " + body[:1500]).lower()
    if any(m in low for m in patient_markers):
        return False
    return True


def _main_text(soup: BeautifulSoup) -> str:
    main = soup.find("main") or soup
    from copy import copy
    mc = copy(main)
    for t in mc(["script", "style", "noscript", "form"]):
        t.decompose()
    return " ".join(mc.get_text(" ", strip=True).split())


# ---------- standalone test entrypoint ----------

if __name__ == "__main__":
    import json
    studies = scrape()
    print(json.dumps(studies, indent=2, ensure_ascii=False))
    print(f"\n{len(studies)} US trial(s).")
