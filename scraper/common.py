"""Shared helpers for every clinic module.

The schema, validator, HTTP fetcher, robots check, and parsing utilities live here so
that each clinic module only has to do the source-specific scraping.
"""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timezone

import requests


USER_AGENT = (
    "trial-finder-bot/1.0 (personal study finder; "
    "+https://github.com/local/trial-finder)"
)
REQUEST_TIMEOUT = 30  # seconds
POLITE_DELAY = 1.0    # seconds between fetches
MAX_RETRIES = 2       # additional attempts after the first


# Every clinic module emits study dicts with exactly these keys.
SCHEMA_KEYS: tuple[str, ...] = (
    "id",
    "clinic",
    "location",
    "title",
    "compensation",
    "compensation_raw",
    "study_type",
    "nights",
    "visits",
    "screening_date_raw",
    "dates_raw",
    "sex",
    "sex_notes",
    "age_min",
    "age_max",
    "age_raw",
    "healthy",
    "flag_spinal",
    "flag_childbearing",
    "url",
    "scraped_at",
)

ALLOWED_STUDY_TYPES = ("inpatient", "outpatient", "mixed", "unknown")
ALLOWED_SEX = ("ALL", "FEMALE", "MALE")


class ScraperError(RuntimeError):
    """Raised when a scrape cannot complete safely. Bubbles up to the orchestrator
    so we exit non-zero rather than overwriting good data with empty/bad output."""


# ---------- time helpers ----------

def now_iso() -> str:
    """ISO 8601 UTC, second precision (e.g. 2026-05-28T12:00:00Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- HTTP ----------

_last_fetch_at: float = 0.0


def fetch(url: str) -> str:
    """GET a URL with a descriptive User-Agent, polite delay, and a small retry budget.

    Returns the response text on 2xx, raises ScraperError on persistent failure.
    """
    global _last_fetch_at
    elapsed = time.monotonic() - _last_fetch_at
    if elapsed < POLITE_DELAY:
        time.sleep(POLITE_DELAY - elapsed)

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            _last_fetch_at = time.monotonic()
            if 200 <= resp.status_code < 300:
                return resp.text
            # 4xx is not retried — caller decides what to do.
            if 400 <= resp.status_code < 500:
                raise ScraperError(f"HTTP {resp.status_code} for {url}")
            last_err = ScraperError(f"HTTP {resp.status_code} for {url}")
        except requests.RequestException as e:
            last_err = e
        # backoff before retry
        if attempt < MAX_RETRIES:
            time.sleep(1.5 * (attempt + 1))

    raise ScraperError(f"fetch failed for {url}: {last_err}")


# ---------- robots.txt ----------

_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}


def check_robots(base_url: str) -> urllib.robotparser.RobotFileParser:
    """Fetch and parse the site's robots.txt. Returns a parser that can be queried
    with .can_fetch(USER_AGENT, url). Cached per origin.

    If robots.txt is unreachable, fail closed: assume everything is disallowed
    (we'd rather skip than misbehave)."""
    origin = _origin(base_url)
    if origin in _robots_cache:
        return _robots_cache[origin]
    rp = urllib.robotparser.RobotFileParser()
    robots_url = origin + "/robots.txt"
    try:
        body = fetch(robots_url)
        rp.parse(body.splitlines())
    except ScraperError as e:
        print(f"[warn] robots.txt unreachable ({e}); failing closed for {origin}")
        # An empty parser disallows nothing by default; flip it to deny-all by
        # parsing a synthetic policy.
        rp.parse(["User-agent: *", "Disallow: /"])
    _robots_cache[origin] = rp
    return rp


def robots_allows(base_url: str, url: str) -> bool:
    rp = check_robots(base_url)
    return rp.can_fetch(USER_AGENT, url)


def _origin(url: str) -> str:
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"


# ---------- parsing helpers ----------

_MONEY_RE = re.compile(r"\$\s*([\d][\d,]*(?:\.\d+)?)")


def parse_money(text: str | None) -> int | None:
    """Return the largest dollar amount found in ``text`` (as int), or None.

    Examples: '$15,250' -> 15250 ; 'Up to $15,250' -> 15250 ;
    '$2,280–$5,000' -> 5000 ; 'no payout listed' -> None.
    """
    if not text:
        return None
    amounts: list[int] = []
    for m in _MONEY_RE.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            amounts.append(int(float(raw)))
        except ValueError:
            continue
    return max(amounts) if amounts else None


_AGE_RANGE_RE = re.compile(
    r"(\d{1,3})\s*(?:-|–|—|to|and)\s*(\d{1,3})",
    flags=re.IGNORECASE,
)


def parse_age_range(text: str | None) -> tuple[int | None, int | None]:
    """Return (age_min, age_max) parsed from a free-text age range. None for unknown.

    Examples: '18-55' -> (18,55) ; '18 to 55 years' -> (18,55) ; '75-85' -> (75,85).
    """
    if not text:
        return (None, None)
    m = _AGE_RANGE_RE.search(text)
    if not m:
        return (None, None)
    lo, hi = int(m.group(1)), int(m.group(2))
    if lo > hi:
        lo, hi = hi, lo
    # Sanity check: ages should be plausible (5..99).
    if not (5 <= lo <= 99 and 5 <= hi <= 99):
        return (None, None)
    return (lo, hi)


# Identical to the original frontend regexes, applied case-insensitively.
_SPINAL_RE = re.compile(
    r"lumbar punctur|spinal tap|intrathecal|cerebrospinal|\bcsf\b",
    flags=re.IGNORECASE,
)
_CHILDBEARING_RE = re.compile(
    r"contracept|childbearing|child-bearing|wocbp|surgically steril|"
    r"postmenopausal|negative pregnancy|highly effective method|"
    r"must not be pregnant|intrauterine device|"
    r"agree to use (a )?(birth|contracep)",
    flags=re.IGNORECASE,
)


def detect_flags(text: str | None) -> tuple[bool, bool]:
    """Return (flag_spinal, flag_childbearing) by scanning ``text``."""
    if not text:
        return (False, False)
    return (bool(_SPINAL_RE.search(text)), bool(_CHILDBEARING_RE.search(text)))


def slugify(s: str) -> str:
    """Lowercase ASCII slug suitable for the 'id' field."""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


# ---------- schema validation ----------

def validate_study(d: dict) -> list[str]:
    """Return a list of human-readable problems. Empty list means the study is valid.

    The orchestrator refuses to write the output file if ANY study is invalid, so
    this catches schema drift before it can clobber good data.
    """
    problems: list[str] = []

    missing = [k for k in SCHEMA_KEYS if k not in d]
    if missing:
        problems.append(f"missing keys: {missing}")
        return problems  # bail early — other checks would just produce noise

    extra = [k for k in d.keys() if k not in SCHEMA_KEYS]
    if extra:
        problems.append(f"unexpected keys: {extra}")

    # Type checks. None is allowed everywhere except a few mandatory fields.
    def _must_str(k: str) -> None:
        if not isinstance(d[k], str) or not d[k]:
            problems.append(f"{k} must be a non-empty string, got {d[k]!r}")

    def _opt_str(k: str) -> None:
        v = d[k]
        if v is not None and not isinstance(v, str):
            problems.append(f"{k} must be string or null, got {type(v).__name__}")

    def _opt_int(k: str) -> None:
        v = d[k]
        if v is not None and (isinstance(v, bool) or not isinstance(v, int)):
            problems.append(f"{k} must be int or null, got {type(v).__name__}")
        if isinstance(v, int) and not isinstance(v, bool) and v < 0:
            problems.append(f"{k} must be non-negative, got {v}")

    def _must_bool(k: str) -> None:
        if not isinstance(d[k], bool):
            problems.append(f"{k} must be bool, got {type(d[k]).__name__}")

    for k in ("id", "clinic", "location", "title", "url", "scraped_at"):
        _must_str(k)
    for k in ("compensation_raw", "screening_date_raw", "dates_raw", "sex_notes", "age_raw"):
        _opt_str(k)
    for k in ("compensation", "nights", "visits", "age_min", "age_max"):
        _opt_int(k)
    for k in ("healthy", "flag_spinal", "flag_childbearing"):
        _must_bool(k)

    if d.get("study_type") not in ALLOWED_STUDY_TYPES:
        problems.append(
            f"study_type must be one of {ALLOWED_STUDY_TYPES}, got {d.get('study_type')!r}"
        )
    if d.get("sex") not in ALLOWED_SEX:
        problems.append(f"sex must be one of {ALLOWED_SEX}, got {d.get('sex')!r}")

    # id is "<clinic-slug>-<study-slug>", so a hyphen must be present.
    if isinstance(d.get("id"), str) and "-" not in d["id"]:
        problems.append(f"id must be '<clinic>-<study>' form, got {d['id']!r}")

    return problems
