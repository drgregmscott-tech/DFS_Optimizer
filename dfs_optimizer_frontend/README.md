# DFS Optimizer Frontend — Session 7.1

Single-file static site (`index.html` — HTML/CSS/JS, no framework, no build
step) that lets you upload a `lineup_single_{site}_{week}.csv` or
`lineups_multi_{site}_{week}.csv` (Session 3.1/3.2's output contract) and
view the lineup(s), with a DK/FD selector.

**Why a single static HTML file, not a framework:** this session's job is
"basic UI + hosting setup" — no backend, no live data yet (per the roadmap
card, `lineups_multi_{site}_{week}.csv`'s *format* is the input, not live
data). A zero-build static file is the fastest path to a stable Cloudflare
Pages deploy with nothing to configure. If Session 7.2 (UI-Optimizer
Integration) ends up needing real interactivity/state beyond what vanilla
JS comfortably handles, that's the point to reconsider a framework — not
before, since it'd be unused complexity today.

## What it does

- Two upload slots (DK / FD) — drag-and-drop or click to browse. Each site's
  data stays loaded independently once uploaded, so you can flip the
  DK/FD toggle without re-uploading.
- Auto-detects single-lineup vs. multi-lineup format (checks for a
  `lineup_id` column) — works with either of Session 3.1's or Session
  3.2's output files unchanged.
- Multi-lineup files get prev/next navigation ("Lineup 3 / 20").
- Salary cap meter (segmented bar) and total projected points, computed
  client-side from the file's own `salary`/`projection` columns — not
  trusted from any external total, so a corrupted file would visibly show
  the wrong cap usage rather than silently displaying a stale number.
- Integrity strip under each lineup: roster slot count (9 expected),
  over/under cap, and a count of zero-projection players in the lineup —
  same "flag, don't silently assume" pattern the backend already uses.
  A zero-projection player shouldn't normally appear (the optimizer's own
  decision #4 in `optimizer.py` makes that mathematically near-impossible
  unless there's no legal alternative), so this is a real correctness
  check, not decoration.
- Everything runs in your browser — the CSV is parsed client-side and
  never leaves your machine. No backend in this session, per the roadmap.

## Known limitation (intentional, matches the roadmap card's scope)

This session (7.1) is upload/view only. It does **not** talk to the
GitHub repo, GitHub Actions, or Cloudflare Worker live data — that wiring
is explicitly Session 7.2 ("UI-Optimizer Integration"). For now, viewing
a real generated lineup means downloading the CSV from `/output` in the
repo (or GitHub Actions' committed output) and uploading it here by hand.

## Deploying to Cloudflare Pages

Recommended: **subfolder in the existing `DFS_Optimizer` repo**, not a
separate repo — keeps this on the same GitHub/Cloudflare accounts already
wired up in Session 5.2, and Cloudflare Pages' "root directory" build
setting handles a subfolder cleanly (same pattern already used for
`cloudflare_worker/` in Session 5.2). If you'd rather keep it in a fully
separate repo, that's a roadmap-permitted option too — say so and the
deploy steps below change only in "which repo to connect."

1. Commit this folder to the repo at `/dfs_optimizer_frontend/` (path
   below).
2. Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** →
   **Connect to Git** → select the `DFS_Optimizer` repo.
3. Build settings:
   - **Framework preset:** None
   - **Build command:** *(leave empty — no build step)*
   - **Build output directory:** `dfs_optimizer_frontend`
   - **Root directory:** `/` (the output directory setting above already
     points at the subfolder — leave root as the repo root, same as how
     the Worker's build used `cloudflare_worker` as its directory setting
     while root stayed at `/`, per Session 5.2's log)
4. Deploy. Cloudflare gives you a `*.pages.dev` URL immediately.
5. Custom domain: **Pages project → Custom domains → Set up a custom
   domain**, point it at your purchased domain's DNS (Cloudflare will
   walk you through the CNAME/records if the domain's already on
   Cloudflare DNS, which it should be if it was bought/managed there).

I can't click through your Cloudflare dashboard without you present (same
credential-handling rule as Session 5.2 — I'll drive the browser and fill
in non-secret fields, but you'd paste/confirm anything account-specific),
but I'm glad to walk through it live with you via Claude in Chrome the
same way we did the Worker deploy.

## File location in the repo

```
/DFS_Optimizer
  /dfs_optimizer_frontend
    index.html      <- this is the whole site
    README.md        <- this file
```

`test_fixtures/` (below) is **not** meant to be committed — it's just
what I used to validate the parser against real repo data this session.
Feel free to keep or discard it.

## Validation performed this session (before handing off)

- Extracted the page's CSV-parsing/grouping logic and ran it standalone
  in Node against **real files pulled from the repo** (not synthetic
  data): `lineup_single_dk_10.csv` in full, and representative real rows
  from `lineups_multi_dk_10.csv` / `lineups_multi_fd_10.csv` (including
  lineup 11/DK and lineup 15/FD, both of which contain the real
  zero-projection Dallas DST/DEF bye-week case already logged in
  SESSION_LOG.md's Session 3.1 entry).
- Confirmed for both sites: correct row count parsed, correct 9-slot
  roster detected, correct salary totals (verified by hand against the
  real per-row salaries), correct roster-slot ordering (QB → RB1/RB2 →
  WR1-3 → TE → FLEX → DST/DEF), and the zero-projection Dallas
  DST/DEF row correctly flagged rather than silently included as a
  normal contributor.
- Confirmed DK's `DST` vs. FD's `DEF` roster-slot label difference
  (real data, not assumed) is handled by each site's own `slotOrder`
  config rather than a single hardcoded label.
- Confirmed the trailing space present in real defense player names
  (e.g. `"Browns "`, `"Cowboys "` in the real committed CSVs) doesn't
  leak into the display — the parser trims every field.
- **Not yet done (needs you or a live browser session):** confirming
  the deployed page actually renders correctly in a real browser --
  everything above validates the *logic*, not the *rendered pixels*.
  See "Remaining actions" below.
