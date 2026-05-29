# Claude Code Patch Spec — Trial Finder, Phase 3.2

## How to use this file
Place at `specs/PHASE3.2_workflow_and_spaulding_fixes.md`. Phase 3.1 must be committed. Follow the
`CLAUDE.md` protocol (read `progress.md` and `docs/phase_current.md` first; update both at the
end). This is a small, focused patch — two specific bugs.

## Context — what we learned from the first live partial-failure run

The Phase 3 daily workflow ran on the live runner and produced this outcome:

* Scraper: 5 of 6 clinics succeeded (Spaulding failed); 22 valid studies were written to
  `docs/studies.json`; scraper exited 1 to signal partial failure.
* "Detect a real change" step: SKIPPED.
* "Commit and push" step: SKIPPED.
* Run summary step: ran (because it has `if: always()`).

So the data updated locally on the runner — Fortrea's newly-derived nights/visits, Nucleus's
filtered list — but never got committed back, and the deployed site continues to show the older
data. The whole point of per-clinic isolation was "good clinics still publish on partial-failure
days." That promise is currently broken at the workflow layer.

Spaulding's failure itself was diagnosed by hand: its sitemap.xml is valid XML (HTTP 200, correct
content type, well-formed) but starts with `<?xml-stylesheet ... ?>` immediately after the XML
declaration. Python's stdlib `xml.etree.ElementTree` rejects that legal processing instruction;
`lxml.etree` (already an installed dependency) handles it correctly.

Two surgical fixes, both small.

## 1. Workflow fix — `.github/workflows/daily-scrape.yml`

Add `if: always()` to the two steps that currently get skipped on scraper non-zero exit. Do not
change anything else in the workflow.

### 1a. Steps to modify

The "Detect a real change" step and the "Commit and push" step. Both need:

```yaml
      - name: Detect a real change
        if: always()
        # ... existing body unchanged ...
```

```yaml
      - name: Commit and push
        if: always() && steps.diff.outputs.changed == 'true'
        # ... existing body unchanged ...
```

Note the `&&` on the commit step: it should run when the previous step finished (success or
failure) and the diff said something actually changed. Without the `&&`, the commit step would
try to run on every job, including jobs where the scraper crashed before writing the file (in
which case there'd be nothing to commit).

### 1b. Why this is the right shape

* `always()` makes the step ignore the previous step's exit status, but it doesn't bypass the
  step's own logic. The diff step still correctly returns `changed=false` if the file wasn't
  modified (e.g., scraper crashed early). The commit step still skips itself if `changed=false`.
* The overall job exit code is still driven by the scraper step. A partial failure means: the
  scraper exits 1 → job ends red in the Actions tab → owner sees the red X → opens the run →
  sees the per-clinic table → knows which clinic to fix. Visibility preserved.
* We don't want to suppress the scraper's non-zero exit. Going green on partial failure would
  hide the very signal we built isolation to surface.

### 1c. Improve the commit message

Today's message format is `data: daily refresh (N studies)`. Make it slightly more informative
on partial-failure days by including the clinic count from `docs/studies.json`'s top-level
`clinic_count` field:

```
data: daily refresh (22 studies, 5 clinics)
```

Pull `clinic_count` and `study_count` from the JSON with `jq` in the commit step. If `jq` isn't
available on the runner (it is by default on `ubuntu-latest`, but verify), fall back to a tiny
Python one-liner. Either is fine.

## 2. Spaulding parser fix — `scraper/clinics/spaulding.py`

Switch the XML parser from `xml.etree.ElementTree` to `lxml.etree`. `lxml` is already in
`scraper/requirements.txt`.

### 2a. The change

Replace the `import xml.etree.ElementTree as ET` and the corresponding `ET.fromstring(xml_text)`
call with `from lxml import etree` and `etree.fromstring(xml_text.encode("utf-8"))`. (lxml's
`fromstring` prefers bytes; encoding explicitly avoids subtle behavior changes around the XML
declaration.)

Update the namespace handling if needed — both libraries use the same `{namespace}element`
syntax for find/findall, but spot-check that the existing code's `findall(".//ns:url/ns:loc", ns)`
style still works under lxml. (It should — both libraries accept the same XPath subset for this
case.)

### 2b. Don't add a fallback discovery path yet

It would be tempting to add "if sitemap fails, scan the homepage for `/study/` links." Resist.
The homepage's listing structure was already verified empty back in Phase 1. Adding speculative
fallbacks now adds complexity for a failure mode we haven't seen. If a different Spaulding
discovery break ever happens, we add the fallback then with knowledge of what to fall back to.

## 3. Files changed

```
trial-finder/
├─ .github/workflows/daily-scrape.yml      ← MODIFY (if: always() on diff + commit, improved msg)
├─ scraper/clinics/spaulding.py            ← MODIFY (lxml parser)
└─ specs/PHASE3.2_workflow_and_spaulding_fixes.md   ← this file
```

## 4. Commit cadence

Two real fixes, one bookkeeping commit:

* `scrape: spaulding parser switched to lxml`
* `workflow: run diff and commit on partial failure; richer commit message`
* `phase 3.2: progress + phase_current`

## 5. `docs/phase_current.md` — add Phase 3.2 at the top

```markdown
## Phase 3.2 — Workflow + Spaulding hotfix — IN PROGRESS
- [ ] scraper/clinics/spaulding.py uses lxml parser; 4 Spaulding studies parse locally
- [ ] daily-scrape.yml diff and commit steps run `if: always()` (commit also gated by `changed`)
- [ ] commit message includes clinic_count from studies.json
- [ ] (Owner) trigger daily-scrape manually after push; confirm green with 6 clinics OK and one
      commit from trial-finder-bot with the new message format
- [ ] (Owner) inject a temporary fault into one clinic, trigger the workflow, confirm: job goes
      RED, the other 5 clinics' data deploys, a partial-refresh commit lands, then revert
```

## Verification checklist

1. `CLAUDE.md`, `progress.md`, and `docs/phase_current.md` read at session start.
2. Spaulding standalone: `python -m scraper.clinics.spaulding` returns ≥ 1 study (current live
   value: 4) and no exceptions.
3. Combined run: `python scraper/scrape.py` finishes with 6 of 6 clinics OK and exits 0.
   `studies.json` validates against the schema.
4. Workflow file has `if: always()` on the "Detect a real change" step and
   `if: always() && steps.diff.outputs.changed == 'true'` on the "Commit and push" step.
   `permissions: contents: write` is still the only entry under top-level `permissions:` —
   no widening.
5. Workflow file commit-message construction reads `clinic_count` and `study_count` from
   `docs/studies.json` (via jq or a Python one-liner) and produces a message like
   `data: daily refresh (26 studies, 6 clinics)`.
6. Local simulation of partial-failure path: with a temporary `raise` injected into one clinic,
   `python scraper/scrape.py` writes a smaller `studies.json` and exits non-zero, and the diff
   fingerprint correctly detects a change. (Remove the injection before commit.)
7. `docs/phase_current.md` updated with the Phase 3.2 section at the top.
8. End-of-session bookkeeping: new dated entry at the top of `progress.md`. Owner action items
   (manual trigger + injected-fault test on the live workflow) called out explicitly and not
   marked done.
