# Claude Code Patch Spec — Trial Finder, Phase 3.1

## How to use this file
Place at **`specs/PHASE3.1_trial_finder_derived_fields.md`**. Phase 3 must be committed. Follow
the `CLAUDE.md` protocol (read `progress.md` and `docs/phase_current.md` first; update both at
the end). This is a small targeted patch — one focused change to the Fortrea module, plus a
re-verification pass on the other five clinics to see whether the same fix applies.

---

## Background — what we learned by spot-checking the deployed site

Manually inspecting Fortrea's per-study pages revealed that **nights, visits, and study_type
are not labeled fields on Fortrea's pages**. The structured header strip only exposes Dates,
Group, Location, Age, Gender, Smokers Allowed, Compensation, and Referral. The Phase 3 scraper
correctly pulled all of those.

But the same numbers we want for `nights` and `visits` **do exist on the page**, just embedded
in the prose "Additional Details" section in this shape:

```
Check-in: June 16
Check-out: June 18

Follow up Visits:
- June 21, 24,
- July 1, 8, 15, 29
- Aug 12, 26
```

So:
- **Nights** = (check-out date) − (check-in date), in days. June 16 → June 18 = 2 nights.
- **Visits** = count of dates listed under "Follow up Visits". The example above = 10 visits.
- **study_type** = `inpatient` whenever a check-in/check-out pair is present (regardless of how
  many follow-up visits also exist); `outpatient` if there are visits but no check-in/check-out;
  `unknown` otherwise. (Yes, this technically overrides the existing study_type derivation —
  that's intentional, the Phase 3 logic was too literal.)

This is exactly the situation Phase 3 §4 anticipated: "if a field is not confidently found,
null." It was correct to mark these null while reading only labeled fields. The patch is to add
a second derivation pass that reads the prose for these three derived fields.

---

## Goal

Extract `nights`, `visits`, and (when applicable) `study_type` from the prose body of Fortrea
study pages, in addition to the labeled-field parsing already in place. Then check whether the
same pattern applies to any of the other five clinics where these fields are currently null.

---

## 1. The Fortrea fix (`scraper/clinics/fortrea_madison.py`)

After the existing field parsing in `_parse_study()` (or wherever the per-study assembly
happens), add a second pass that scans the body text for the check-in/check-out and follow-up-
visits patterns. Implementation guidance:

### 1a. Find the "Additional Details" section, then scan it

The relevant prose lives under an `<h2>Additional Details</h2>` (or similar) heading. Locate
that section and extract its text, **not the whole page body** — restricting the scan reduces
false matches from sidebar or footer content.

### 1b. Parse check-in / check-out into nights

Match patterns like:
```
Check-in: <date>
Check-out: <date>
```
Both labels can appear with or without bold tags, with one or two spaces, and the dates can be
"June 16", "June 16, 2026", or "06/16/2026". Use a tolerant regex that captures the date string,
then parse with `dateutil.parser.parse` (add `python-dateutil` to `requirements.txt`).

Compute `nights = (checkout_date - checkin_date).days`. If the difference is ≤ 0 or > 60, treat
the parse as untrustworthy and leave `nights = null` rather than emit a junk value. Log a
warning when this happens.

If exactly one of check-in/check-out is found but not the other, `nights = null`.

### 1c. Count follow-up visits

Find the "Follow up Visits:" heading (case-insensitive, with or without colon). Read the
subsequent bullet list (`<ul><li>...</li></ul>` or equivalent). Within each bullet, count the
comma-separated date tokens. A bullet like `June 21, 24,` is **two** dates (the trailing comma
doesn't add a date). A bullet like `July 1, 8, 15, 29` is **four** dates.

Use a comma-split + filter approach: split on commas, strip whitespace, drop empty strings, and
count what remains. Cross-check that each remaining token actually looks like a date fragment
(starts with a month name, or is a 1–2 digit number that follows an earlier month on the same
bullet). Add a Potential Follow-ups section (e.g., "Sep 19 & 30, Oct 14") to the same count —
ampersands also separate dates.

`visits = sum across all bullets`. If the heading isn't found, `visits = null`.

### 1d. Override study_type when appropriate

After both extractions:
- If `nights ≥ 1`: `study_type = "inpatient"` (even if there are also follow-up visits — that's
  a mixed schedule, but the participant is *resident* for the main period, which is what matters
  for her).

  *Correction*: per the schema, `study_type = "mixed"` if there are both confinement nights and
  outpatient visits. Use "mixed" when `nights ≥ 1` and `visits ≥ 1`; "inpatient" when nights ≥ 1
  and visits is null or 0; "outpatient" when nights is null/0 and visits ≥ 1; "unknown"
  otherwise.

### 1e. Don't break working studies

The Phase 3 scrape produced 6 Fortrea studies. After this patch, re-run and confirm:
- All 6 still parse (count unchanged).
- `nights` populated on the ones with Check-in/Check-out in the body (likely all 6).
- `visits` populated where Follow up Visits appears.
- No regressions on `compensation`, `dates_raw`, `age_raw`, or any field this patch doesn't touch.

---

## 2. The cross-clinic spot check

Spend ~10 minutes manually inspecting one live study page from each of the other 5 clinics to
see whether the same kind of fix is needed. Specifically, for each clinic, look at the deployed
site cards where `nights` or `visits` is `—`, click through to the source page, and answer:
**Does the page show this information somewhere the scraper didn't look?**

For each clinic, document the finding in `progress.md`:

- **Spaulding**: are the studies with `—` for dates actually missing dates on Spaulding's own
  page (legitimately TBD, no fix possible), or did the scraper miss a section? (Penny was
  legitimately "Group 3: Dates TBD" — confirm that's still the case. Quill specifically — was
  there a dates section we missed?)
- **Nucleus**: spot-check 2 of the 13 to confirm they're St. Paul-conducted, not Australia.
  Look at the trial page for a location field. If any are Melbourne/Brisbane studies, fix the
  scraper's country filter and remove them from the data.
- **ICON Lenexa**: any obvious nights/visits info in body text we missed?
- **Celerion Lincoln**: same question. (Many fields are walled behind login — those should
  remain null, that's correct.)
- **AbbVie Grayslake**: same.

If any of these reveal the same kind of "data is on the page in prose" gap, fix that clinic
module in the same patch. If they don't, document the finding and move on — don't invent fixes
for nonexistent problems.

---

## 3. Files changed

```
trial-finder/
├─ scraper/
│  ├─ requirements.txt                   ← ADD python-dateutil
│  └─ clinics/
│     ├─ fortrea_madison.py              ← MODIFY (prose-derived nights/visits/study_type)
│     └─ <others as findings dictate>    ← MODIFY only if §2 reveals real issues
└─ specs/PHASE3.1_trial_finder_derived_fields.md   ← this file
```

---

## 4. Commit cadence

One commit per real change, descriptive messages:

- `clinics: fortrea-madison derive nights/visits from check-in/check-out and follow-up list`
- `clinics: <other> <what>` if §2 turns up additional fixes
- `phase 3.1: progress + phase_current`

Do not commit the spec file alone — commit it with the first patch commit, or in its own
`phase 3.1: spec` commit before the work starts. Your call.

---

## 5. `docs/phase_current.md` update

Add a Phase 3.1 section at the top, leave Phase 3 marked done:

```markdown
## Phase 3.1 — Derived-field extraction (Fortrea + cross-clinic check) — IN PROGRESS
- [ ] Fortrea: nights / visits / study_type derived from prose body
- [ ] Fortrea: all 6 studies still parse, no regressions
- [ ] Cross-clinic spot check documented in progress.md (per-clinic finding)
- [ ] Any additional clinic fixes that fall out of the spot check
- [ ] (Owner) verify on deployed site that the affected Fortrea cards now show populated fields
```

---

## Verification checklist

0. `CLAUDE.md`, `progress.md`, and active spec read at session start.
1. `python -m scraper.clinics.fortrea_madison` returns 6 studies; **at least 5 of them** have
   non-null `nights`, and at least the studies with a "Follow up Visits" section have non-null
   `visits`. (One outlier with missing prose is acceptable; mass null is not.)
2. Manual sanity check: pick one Fortrea study you can see on Fortrea's website, manually count
   nights from check-in/check-out and count visits from the bullet list, and confirm the
   scraper's numbers match. If they don't, fix the parser, don't fudge the test.
3. Combined `python scraper/scrape.py` finishes with all 6 clinics OK and 32+ studies (count
   could shift if §2 removes any Nucleus non-US studies).
4. `studies.json` validates against the schema.
5. Per-clinic findings from §2 are documented in `progress.md`, even when the finding is "no
   change needed."
6. Frontend on the deployed site (after push) shows populated Nights/Visits on Fortrea cards.
7. `docs/phase_current.md` and `progress.md` updated per convention.
