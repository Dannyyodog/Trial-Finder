"""ICON Early Phase (Lenexa, KS) — iconstudies.com.

ICON runs three US Phase 1 units (Lenexa KS, Salt Lake City UT, San Antonio TX);
this module keeps only the Lenexa trials. The companion brand prastudies.com is
gone (HTTP 403 for plain GET), so iconstudies.com is the only live source.

Discovery: parse the homepage and the /All-Clinical-Research-Studies/ index
for hrefs matching `/Lenexa/Clinical-Research-Study/<id>/`. The other two
locations use the same URL shape with `/SLC/` or `/sanantonio/`.

ICON's study pages aren't structured with labeled fields the way Spaulding /
Fortrea / Nucleus are. The "STUDY DETAILS" block does have stable phrasing
though — we parse the visible text with anchored regexes:

  Title:       the line after "STUDY DETAILS"
  Comp:        "Up to $17000"  or  "$17,000 - $20,500"
  Nights:      "1 stay of 18 nights"  or  "X nights"
  Visits:      "Y outpatient visit"  or  "Y follow-up visit"
  Age:         "Age 18 - 65"
  Sex:         "Male/Female", "Male", "Female"
  Childbearing:will catch "non-childbearing potential" via detect_flags.
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


BASE = "https://iconstudies.com"
INDEX_URLS = (
    BASE + "/",
    BASE + "/All-Clinical-Research-Studies/",
)
CLINIC_NAME = "ICON Early Phase"
LOCATION = "Lenexa, KS"
STATE = "KS"
CLINIC_SLUG = "icon-lenexa"

_LENEXA_PATH_RE = re.compile(
    r"^/Lenexa/Clinical-Research-Study/(\d+)/?$",
    re.IGNORECASE,
)


def scrape() -> list[dict]:
    if not robots_allows(BASE, BASE + "/"):
        raise ScraperError(f"robots.txt disallows {BASE}/")

    study_urls = _discover_study_urls()
    if not study_urls:
        raise ScraperError(
            "No /Lenexa/Clinical-Research-Study/<id>/ links discovered on "
            f"{INDEX_URLS} — site structure likely changed."
        )
    print(f"[icon-lenexa] discovery yielded {len(study_urls)} Lenexa URL(s)")

    studies: list[dict] = []
    for url in study_urls:
        if not robots_allows(BASE, url):
            print(f"[icon-lenexa] robots.txt disallows {url} — skipping")
            continue
        html = fetch(url)
        study = _parse_study(html, url)
        if study is None:
            continue
        print(
            f"[icon-lenexa]   {study['title']!r} comp=${study['compensation']} "
            f"sex={study['sex']} ages={study['age_min']}-{study['age_max']} "
            f"nights={study['nights']} visits={study['visits']}"
        )
        studies.append(study)
    return studies


# ---------- discovery ----------

def _discover_study_urls() -> list[str]:
    found: dict[str, str] = {}  # study_id -> URL
    for index_url in INDEX_URLS:
        try:
            html = fetch(index_url)
        except ScraperError as e:
            print(f"[icon-lenexa] could not fetch {index_url}: {e}")
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            h = a["href"]
            # Accept either absolute or relative paths.
            path = h
            if h.startswith(BASE):
                path = h[len(BASE):]
            m = _LENEXA_PATH_RE.match(path)
            if m:
                sid = m.group(1)
                full = BASE + path
                if not full.endswith("/"):
                    full += "/"
                found.setdefault(sid, full)
    # Return in stable order (by numeric ID).
    return [u for _sid, u in sorted(found.items(), key=lambda kv: int(kv[0]))]


# ---------- per-study parsing ----------

_STUDY_DETAILS_RE = re.compile(r"STUDY\s+DETAILS\s+(.+)", re.IGNORECASE)
_AGE_RE = re.compile(r"\bAge\s+(\d{1,3})\s*-\s*(\d{1,3})\b", re.IGNORECASE)
_NIGHTS_RE = re.compile(r"(\d+)\s*nights?\b", re.IGNORECASE)
_VISITS_RE = re.compile(
    r"(\d+)\s+(?:outpatient|follow[- ]?up)\s+visits?",
    re.IGNORECASE,
)


def _parse_study(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    main = soup.select_one("main") or soup.select_one("article") or soup
    text = " ".join(main.get_text(" ", strip=True).split())

    # Title: ICON pages put the canonical study title right after "STUDY DETAILS".
    title = _extract_title(text, soup, url)
    if not title:
        raise ScraperError(f"Could not find STUDY DETAILS title on {url}")

    # Compensation: nearest dollar amount AFTER the title, before the body prose.
    # Common phrasings: "Up to $17000", "Up to $17,000", "$17,000 - $20,500".
    comp_raw = _extract_comp_raw(text, title)
    compensation = parse_money(comp_raw)

    # Nights / visits: scan everything after the title.
    nights = _maybe_int(_NIGHTS_RE, text)
    visits_val = _maybe_int(_VISITS_RE, text)

    age_match = _AGE_RE.search(text)
    if age_match:
        age_raw = f"{age_match.group(1)}-{age_match.group(2)}"
        age_min, age_max = parse_age_range(age_raw)
    else:
        age_raw, age_min, age_max = None, None, None

    sex_raw, sex = _classify_sex(text)

    healthy = True  # ICON's posted studies are explicitly healthy-volunteer.
    flag_spinal, flag_childbearing = detect_flags(text + " " + title)

    if nights and nights > 0 and visits_val and visits_val > 0:
        study_type = "mixed"
    elif nights and nights > 0:
        study_type = "inpatient"
    elif visits_val and visits_val > 0:
        study_type = "outpatient"
    else:
        study_type = "unknown"

    slug = url.rstrip("/").rsplit("/", 1)[-1]  # numeric study id
    study_id = f"{CLINIC_SLUG}-{slug}"

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
        "visits": visits_val,
        "screening_date_raw": None,
        "dates_raw": _extract_involvement(text),
        "sex": sex,
        # sex_notes is reserved for genuinely additional qualifiers (e.g.
        # "Postmenopausal women only"). ICON's "Male/Female" is just a verbose
        # restatement of sex=ALL, so leave it null.
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


def _extract_title(text: str, soup: BeautifulSoup, url: str) -> str | None:
    # Take the substring right after "STUDY DETAILS" and chop at the first
    # obvious next field marker (the Location string "<City>, <ST>").
    m = _STUDY_DETAILS_RE.search(text)
    if m:
        tail = m.group(1)
        # Stop the title at "Lenexa, KS" / "Up to $" / "Participation in this".
        for marker in ("Lenexa, KS", "Up to $", "Participation in", "$"):
            idx = tail.find(marker)
            if idx > 0:
                return tail[:idx].strip(" -—:")
        return tail[:120].strip()
    # Fallback: the page's <title>.
    if soup.title:
        return soup.title.get_text(strip=True).split("|")[0].strip()
    return None


def _extract_comp_raw(text: str, title: str | None) -> str | None:
    """Find the compensation phrasing nearest the study title.

    ICON consistently prints "Up to $X" or a "$A - $B" range right after the
    location line ("Lenexa, KS") that follows the title.
    """
    # Search the slice after the title.
    start = 0
    if title:
        i = text.find(title)
        if i >= 0:
            start = i + len(title)
    slice_ = text[start:start + 600]
    # Up to $X (with or without commas)
    m = re.search(r"Up\s+to\s+\$\s*[\d,]+(?:\s*-\s*\$\s*[\d,]+)?", slice_, re.IGNORECASE)
    if m:
        return " ".join(m.group(0).split())
    # $A - $B  (range)
    m = re.search(r"\$\s*[\d,]+\s*-\s*\$\s*[\d,]+", slice_)
    if m:
        return " ".join(m.group(0).split())
    # Plain $X
    m = re.search(r"\$\s*[\d,]{3,}", slice_)
    if m:
        return " ".join(m.group(0).split())
    return None


def _extract_involvement(text: str) -> str | None:
    """Try to capture the 'Participation in this study includes …' sentence."""
    m = re.search(
        r"Participation in this study includes [^.]{1,300}\.",
        text,
        re.IGNORECASE,
    )
    return m.group(0).strip() if m else None


def _classify_sex(text: str) -> tuple[str | None, str]:
    """Return (raw_phrase, sex_token)."""
    # Common ICON phrasings appearing right after the involvement sentence.
    for pat in (r"Male\s*/\s*Female", r"Females\s+only", r"Males\s+only",
                r"\bMale\s+only\b", r"\bFemale\s+only\b"):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = " ".join(m.group(0).split())
            low = raw.lower()
            if "male" in low and "female" in low:
                return raw, "ALL"
            if "female" in low:
                return raw, "FEMALE"
            if "male" in low:
                return raw, "MALE"
    # Fallback by direct word search
    has_m = bool(re.search(r"\bmen\b|\bmales?\b", text, re.IGNORECASE))
    has_f = bool(re.search(r"\bwomen\b|\bfemales?\b", text, re.IGNORECASE))
    if has_m and has_f:
        return "Male/Female", "ALL"
    if has_f:
        return "Female", "FEMALE"
    if has_m:
        return "Male", "MALE"
    return None, "ALL"


def _maybe_int(pattern: re.Pattern, text: str) -> int | None:
    m = pattern.search(text)
    return int(m.group(1)) if m else None


# ---------- standalone test entrypoint ----------

if __name__ == "__main__":
    import json
    studies = scrape()
    print(json.dumps(studies, indent=2, ensure_ascii=False))
    print(f"\n{len(studies)} Lenexa trial(s).")
