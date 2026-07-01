# Claude Code Patch Spec — Trial Finder, Phase 3.3

## How to use this file
Place at **`specs/PHASE3.3_spaulding_sitemap_recovery.md`**. Phase 3.2 must be committed and
the Node 24 workflow bump must be in place. Follow the `CLAUDE.md` protocol (read `progress.md`
and `docs/phase_current.md` first; update both at the end).

Small, targeted patch. One-line code change plus verification.

---

## Context — the recurring bug

The Phase 3.2 findings surfaced a recurring intermittent Spaulding sitemap failure. Diagnosis
from prior investigation:

- Same failure signature on runs 6/23, 6/25, 6/29, 7/1:
  `ScraperError: sitemap.xml is not valid XML: EntityRef: expecting ';', line 1, column 124`
- Column 124 sits at the `<?xml-stylesheet ... ?>` processing instruction's `href` attribute.
- Root cause: Spaulding's sitemap intermittently emits an unescaped `&` in that PI, almost
  certainly a WordPress cache-buster query string like `?ver=1.2&t=1234567890` where the `&`
  should be `&amp;`.
- Some days the sitemap is clean (no `&` present) and parses fine. This matches the alternating
  pass/fail pattern in the run history.
- Per-clinic isolation held on every failing day: 5 of 6 clinics still deployed 14–22 studies.
  Phase 3.2's workflow fix worked as designed. But Spaulding data disappears from the site on
  roughly half of scrape days, which is the visible symptom for the end user.

The fix is to switch lxml's XML parser to **recovery mode** so it tolerates the bare `&` (and
any similar minor malformation) while still parsing everything valid.

---

## 1. The fix

In `scraper/clinics/spaulding.py`, change the sitemap parsing call from strict to recovery mode.

Currently something like:

```python
from lxml import etree
# ...
root = etree.fromstring(xml_text.encode("utf-8"))
```

Change to:

```python
from lxml import etree
# ...
parser = etree.XMLParser(recover=True)
root = etree.fromstring(xml_text.encode("utf-8"), parser=parser)

# Log a warning if recovery mode had to recover from anything — makes it visible
# in future runs whether the Spaulding workaround is still engaging.
if parser.error_log:
    print(f"[spaulding] sitemap parsed with recovery ({len(parser.error_log)} "
          f"issue(s) tolerated): {parser.error_log[0]}")
```

### Why the logging matters

Recovery mode silently smooths over malformations. That's what we want operationally, but it
also means we lose visibility into whether Spaulding's bug persists, gets worse, or gets fixed
over time. Logging when recovery engages (and what it recovered from) gives us that signal
without noise on clean-sitemap days.

### What NOT to do

- Don't add a regex fallback to pre-escape bare `&` — brittle to shape changes.
- Don't strip the `<?xml-stylesheet?>` PI selectively — targeted at the specific known problem
  but assumes malformation only ever appears in that PI. Recovery mode is broader and less
  fragile.
- Don't switch discovery methods (e.g., fall back to scanning the homepage). Homepage was
  verified empty of `/study/` links back in Phase 1; recovery mode addresses the actual bug.

---

## 2. Files changed

```
trial-finder/
├─ scraper/clinics/spaulding.py                          ← MODIFY (recover=True + log)
└─ specs/PHASE3.3_spaulding_sitemap_recovery.md          ← this file
```

---

## 3. Commit cadence

Two commits:

- `scrape: spaulding sitemap uses lxml recovery mode`
- `phase 3.3: progress + phase_current`

---

## 4. `docs/phase_current.md` — add Phase 3.3 section at the top

```markdown
## Phase 3.3 — Spaulding sitemap recovery mode — IN PROGRESS
- [ ] scraper/clinics/spaulding.py uses etree.XMLParser(recover=True)
- [ ] Log emitted when recovery engages (so intermittent bug remains visible)
- [ ] Verified against synthesized bad-entity sitemap: URLs still extract, exit 0
- [ ] Verified against live (good-day) sitemap: 4 studies parse, no regressions
- [ ] (Owner) watch the next 1–2 weeks of scheduled runs; confirm Spaulding
      no longer intermittently disappears from the deployed site
```

---

## Verification checklist

0. `CLAUDE.md`, `progress.md`, and `docs/phase_current.md` read at session start.

1. **Reproduce the bug locally before fixing** (proves the fix is doing real work, not just
   happening to run on a good day):
   - Fetch the current live sitemap.
   - Synthesize a bad version by injecting an unescaped `&` into the `<?xml-stylesheet?>` PI's
     href attribute (e.g., change `?ver=1` to `?a=1&b=2`).
   - Confirm the pre-fix parser fails with the same `EntityRef: expecting ';'` error the
     production logs showed. If it doesn't fail, the reproduction isn't valid and the test
     doesn't prove anything — investigate why before proceeding.

2. **Apply the fix**, then re-run against the synthesized bad sitemap:
   - Parser succeeds.
   - All `<loc>` URLs extract correctly (count matches the good version).
   - Recovery log line prints, mentioning the tolerated issue.

3. **Run against the live sitemap:**
   - `python -m scraper.clinics.spaulding` returns 4 studies (current live value).
   - If today's live sitemap is clean, no recovery log prints — recovery mode is a no-op on
     valid XML, that's correct.

4. **Full orchestrator:** `python scraper/scrape.py` shows all 6 clinics OK with 6/6 succeeded
   and exits 0. `studies.json` validates against the schema.

5. **`docs/phase_current.md`** has the Phase 3.3 section at the top with the recovery-mode
   checkboxes. Owner watch-item is called out and NOT marked done (only the next 1–2 weeks of
   live runs can prove that).

6. **End-of-session bookkeeping:** new dated entry at the top of `progress.md` summarizing what
   was built, what the reproduction showed, and what remains for the owner to observe.
