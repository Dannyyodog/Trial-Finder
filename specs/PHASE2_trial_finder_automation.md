# Claude Code Build Spec — Trial Finder, Phase 2

## How to use this file
Place this file at **`specs/PHASE2_trial_finder_automation.md`** in the repo. Phase 1 must already
be merged and Pages must be live. Follow the operating protocol in `CLAUDE.md` (read `progress.md`
and `docs/phase_current.md` first; update both at the end).

---

## Goal — what Phase 2 ships

A daily **GitHub Action** that:
1. Runs `scraper/scrape.py` against the live Spaulding site.
2. Diffs the freshly-scraped output against the `docs/studies.json` already in the repo.
3. **Commits and pushes** the new `studies.json` **only if it actually changed.**
4. **Fails loudly** (and visibly in the repo's Actions tab) if the scrape errors, so a quietly
   broken scraper doesn't go unnoticed for weeks.

That's the whole job. No new clinics, no frontend changes — those are Phase 3.

---

## 1. Why this design (do not drift)

- **Commit-only-on-change** keeps Git history meaningful: every commit on `main` represents a real
  data update. Quiet days produce no commits and no Pages rebuild.
- **Pages auto-rebuilds** when `docs/` changes, so updating `studies.json` is the *whole* trigger
  for the site refreshing. No separate deploy step is needed.
- **Fail loud** matters because a silent-failing scraper is worse than no scraper — she'd think
  she's seeing current data when she isn't. Phase 1's `scrape.py` already exits non-zero on empty
  or invalid output; the Action surfaces that as a red ✗ on the repo and an email to the repo owner.
- **No third-party services.** No webhooks, no Slack, no separate runner — just GitHub Actions on
  the free tier, which has more than enough minutes for one daily Python run.

---

## 2. Files to create

```
trial-finder/
├─ .github/
│  └─ workflows/
│     └─ daily-scrape.yml       ← THE NEW FILE
└─ specs/
   └─ PHASE2_trial_finder_automation.md   ← this file
```

Nothing else changes. Do not touch `scraper/`, `docs/`, or `CLAUDE.md` content — the Phase 1
scraper is the contract and it stays as-is.

---

## 3. `.github/workflows/daily-scrape.yml` — full spec

### 3a. Triggers
- **Scheduled:** cron `0 5 * * *` — that's 05:00 UTC daily, ≈ midnight Central (drifts ±1 hour with
  US DST). GitHub-hosted schedules can lag by minutes to ~an hour under load; that's expected and
  fine.
- **Manual:** `workflow_dispatch` so the owner can trigger a run from the Actions tab at any time
  for testing or a forced refresh.

### 3b. Permissions
The job must be able to commit and push back to `main`. Set the workflow's top-level
`permissions:` to `contents: write` — nothing more. Do **not** grant `pull-requests`, `issues`, or
any other scope. Principle of least privilege.

### 3c. Runner and concurrency
- `runs-on: ubuntu-latest`.
- Set `concurrency: { group: daily-scrape, cancel-in-progress: false }` so two runs (e.g., a
  scheduled run plus a manual one) cannot race each other into a push conflict.
- Top-level `timeout-minutes: 10`. A healthy run takes well under a minute; ten minutes is a
  generous ceiling that still prevents a stuck job from burning Actions minutes.

### 3d. Job steps (in order)

1. **Checkout** — `actions/checkout@v4` with `fetch-depth: 1` and `persist-credentials: true` (the
   default). The default `GITHUB_TOKEN` is what authorizes the later push.
2. **Set up Python** — `actions/setup-python@v5` with `python-version: '3.12'` and
   `cache: 'pip'` keyed on `scraper/requirements.txt` so dependency installs are fast on repeat
   runs.
3. **Install dependencies** — `pip install -r scraper/requirements.txt`.
4. **Run the scraper** — `python scraper/scrape.py`. If this exits non-zero, the workflow fails
   here (which is the desired fail-loud behavior). Phase 1's scraper already refuses to overwrite
   `docs/studies.json` with empty/invalid data, so a failure here is genuinely meaningful.
5. **Detect a real change** — use `git status --porcelain docs/studies.json` to decide whether the
   file actually changed. Set a step output (`changed=true|false`) for the next step to read. Do
   **not** rely on byte-level diffs of the whole file; the `generated_at` and `scraped_at`
   timestamps change every run, so a naive "did the file change" check would commit every day even
   when no study data changed.

   **The correct check:** parse the new and the previously-committed `studies.json` with `jq` (or a
   tiny inline Python snippet) and compare the **`studies` array only**, ignoring the top-level
   `generated_at` / `scraped_at` fields. Concretely:

   - Get the old version: `git show HEAD:docs/studies.json > /tmp/old.json` (handle the case where
     the file didn't exist — treat that as "changed").
   - Compute a stable hash of the studies list with `generated_at`/`scraped_at` stripped from each
     entry. Example shape of the comparator:
     ```python
     import json, hashlib
     def fingerprint(path):
         data = json.load(open(path))
         studies = data.get("studies", [])
         # strip per-study timestamps so only real changes register
         stripped = [{k: v for k, v in s.items() if k != "scraped_at"} for s in studies]
         return hashlib.sha256(
             json.dumps(stripped, sort_keys=True).encode()
         ).hexdigest()
     ```
   - If the fingerprints differ (or the old file is missing), `changed=true`.

6. **Commit and push (conditional)** — only runs if `changed=true`. Configure the bot identity:
   ```
   git config user.name  "trial-finder-bot"
   git config user.email "trial-finder-bot@users.noreply.github.com"
   ```
   Stage `docs/studies.json`, commit with a message like
   `data: daily Spaulding refresh (<N> studies)` (compute N from the JSON), and `git push`.
7. **Run summary (always)** — write a short summary to `$GITHUB_STEP_SUMMARY` so the Actions tab
   shows at a glance what happened:
   - "No change — N studies, fingerprint unchanged" **or**
   - "Committed update — N studies, <list of changed study slugs>".
   This makes the Actions tab a real audit log without needing to crack open the JSON.

### 3e. What NOT to do
- Don't add a `pull_request` trigger. We're committing straight to `main`.
- Don't add caching of `docs/studies.json` — it's the artifact, not a cache.
- Don't push if `changed=false`. Empty commits are noise.
- Don't email/Slack/notify on failure beyond what GitHub already does — the owner already gets a
  failure email from GitHub for any failed Action on their repos by default. Don't reinvent that.
- Don't widen `permissions:` beyond `contents: write`.

---

## 4. Repo settings the owner has to do by hand (one time)

These are GitHub UI changes the workflow can't do for itself. Document them in the closing
`progress.md` entry as **owner action items** so they don't get forgotten:

1. **Settings → Actions → General → Workflow permissions** → set to **"Read and write
   permissions"** (this allows the default `GITHUB_TOKEN` to push). Save.
2. **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests** →
   leave unchecked. We don't use PRs.
3. After the first scheduled or manual run, **Settings → Pages** should still show "Your site is
   live at …". No change needed there — Pages will rebuild automatically whenever `docs/`
   changes on `main`.

These steps are not part of Claude Code's work; just include them in `progress.md` and
`docs/phase_current.md` as the human's checklist items.

---

## 5. `docs/phase_current.md` — replace the file's content

Phase 1 is done; this file should now track Phase 2.

```markdown
# Trial Finder — current phase

## Phase 2 — Daily automation (Spaulding only) — IN PROGRESS
Goal: a daily GitHub Action runs the scraper and commits studies.json only when the study data
actually changed, with loud failures.

- [ ] .github/workflows/daily-scrape.yml created per spec
- [ ] Workflow runs cleanly on manual dispatch (Actions tab → Run workflow)
- [ ] Fingerprint diff verified: a no-op run produces NO commit
- [ ] Change-detection verified: a forced data change produces ONE commit with the right message
- [ ] Fail-loud verified: a deliberately broken scraper makes the Action go red
- [ ] (Owner) Settings → Actions → General → Workflow permissions = Read and write
- [ ] (Owner) Confirm scheduled 05:00 UTC run fires the next day

## Phase 1 — Prove the pipeline (Spaulding, manual run) — DONE
All checkboxes complete; Pages live at https://dannyyodog.github.io/Trial-Finder/.

## Next phases
- Phase 3: add more clinic scrapers (Fortrea Madison, Nucleus St. Paul, AbbVie Grayslake, then
  ICON Lenexa / Celerion Lincoln); replace clinic dropdown with a STATE filter; fix dates_raw
  rendering (collapsed schedule block, expand on tap).
```

---

## Verification checklist (work through before declaring done)

0. `CLAUDE.md` and `progress.md` were read at the start of this session; you understand the
   project state.
1. `.github/workflows/daily-scrape.yml` exists and matches §3 (triggers, permissions, concurrency,
   timeout, six step blocks).
2. **Manual run (no-op):** trigger the workflow via `gh workflow run daily-scrape.yml`
   (or instruct the owner to use the Actions tab → Run workflow). It completes green. The
   `$GITHUB_STEP_SUMMARY` reads "No change — N studies, fingerprint unchanged." **No new commit
   appears on `main`.**
3. **Manual run (with change):** temporarily edit `docs/studies.json` locally to flip one study's
   `nights` value to a clearly different number, commit and push that change, then trigger the
   workflow. Confirm:
   - The workflow runs the scraper (which restores the correct value).
   - It detects the difference and commits `data: daily Spaulding refresh (N studies)`.
   - The commit author is `trial-finder-bot`.
   - Pages rebuilds automatically and shows the corrected value within ~1–2 minutes.
4. **Fail-loud:** temporarily break the scraper (e.g., point `SITEMAP_URL` at a bogus path), commit
   and push, trigger the workflow, confirm it goes **red** in the Actions tab and **does not** push
   a commit. Revert the breakage before closing the session.
5. **No widened permissions:** open the workflow file and confirm `permissions: contents: write` is
   the only entry under top-level `permissions:`.
6. **`docs/phase_current.md`** updated per §5, with the owner action items clearly marked.
7. **End-of-session bookkeeping:** new dated entry at the TOP of `progress.md` summarizing what
   was built, what was verified, and the two **owner action items** (workflow permissions toggle
   + waiting one calendar day to confirm the scheduled run fires). Do not mark the owner items as
   done — only the owner can verify them.
