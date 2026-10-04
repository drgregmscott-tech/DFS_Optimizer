# Multi-session concurrency gap (flagged 2026-10-04, action item for after today)

## What happened
During the Wk4 noon-lock window, this interactive session and the newly-created
`x-injury-monitor-sunday-midday` scheduled task both fired within minutes of each
other. Both run on this same machine against the same working directory and the
same git checkout. Both independently:

- Edited `config/manual_status_overrides.csv` (harmlessly -- different rows,
  Tyjae Spears vs. Colby Parkinson -- merged fine as plain file edits since
  they happened to land as sequential writes, not simultaneous ones).
- Pulled fresh status, re-applied it, rebuilt pivots, and tried to commit +
  push to origin. The scheduled task's automated GH Actions-triggered refreshes
  (light_vegas_refresh / full_refresh_dispatch, also firing on their own cadence
  during the real near-lock window) landed on origin first; this session's push
  was rejected as non-fast-forward and needed a manual merge, resolved by taking
  origin's fresher generated files and re-running the fix on top.

This time it resolved safely because the conflicts were all in machine-generated
CSV output (safe to regenerate rather than hand-merge) and nothing silently
overwrote a real fix. But the only reason it was caught is that a human was
watching in real time. **There is currently no coordination between:**
1. This interactive session's own /loop,
2. The 5 new recurring local scheduled tasks (Thu/Sun x3/Mon),
3. The existing GH Actions automated refresh cadence (near-lock, vegas, full,
   injury_only) pushing from a separate CI environment entirely,
4. Any other interactive session the user might have open.

All of them read and write the same handful of files
(`config/manual_status_overrides.csv`, `output/final_projections_*.csv`,
`output/pivot_suggestions_*.csv`, `data/x_injury_feed_state.json`) with no
locking, no "is someone else already on this" check, and no merge strategy
beyond "last push wins, hope for a clean auto-merge."

## Why it matters
- A silent bad outcome is possible: two processes applying DIFFERENT manual
  overrides for the SAME player (e.g. one says OUT, another says ACTIVE) could
  resolve via git's text merge in either direction with no one noticing, since
  CSV conflict markers inside a generated file are easy to miss if nobody is
  watching the push fail.
- `data/x_injury_feed_state.json` gets written by every tick of every one of
  these processes. Two near-simultaneous writes could stomp each other's
  `last_seen_status_id` and cause a real re-notification or a missed one.
- The GH Actions pipeline and the local scheduled tasks can both legitimately
  decide to "fix" the same stale status at the same time, each unaware of the
  other, each burning a push.

## What to actually do about it (NOT today -- pick this up after Wk4's games)
Options to evaluate, roughly cheapest to most robust:
1. **Stagger, don't coordinate.** Offset the 5 local scheduled tasks' cron
   minutes from the GH Actions near-lock cadence's known firing times, so they
   almost never land in the same few minutes. Cheap, doesn't eliminate the
   race, just makes it rarer.
2. **A simple lock file.** Before any of these processes runs pull/apply/pivot/
   commit, check for (and write) a `*.lock` file with a short TTL; skip the run
   (log and exit) if one is already held. Low effort, handles the common case.
3. **Serialize through a single entry point.** Instead of N independent
   processes each running the full pull->apply->pivot->commit->push sequence,
   have everything funnel through one queue/dispatcher that actually runs them
   one at a time. More correct, more work to build.
4. **Rebase-and-retry push loop.** Make every one of these processes retry
   `git pull --rebase && git push` a few times on rejection instead of just
   failing or (worse) force-pushing. Doesn't prevent the race, makes losing it
   non-fatal.
5. **Narrow what each process is allowed to touch.** The X monitor really only
   ever needs to add a row to `manual_status_overrides.csv` and ask the
   *existing* pipeline to re-run -- it doesn't need its own independent
   pull/apply/commit/push sequence duplicating what GH Actions already does on
   its own cadence. Shrinking its footprint shrinks the collision surface.

Recommendation to start the conversation from: some combination of #2 (lock
file, cheap and catches the actual failure mode seen today) and #5 (shrink the
X monitor's footprint so it has less to collide over) is probably the right
first pass, without building a full dispatcher (#3) unless #2+#5 turn out not
to be enough in practice.

## Status
Flagged by the user during the Wk4 noon-lock window (2026-10-04) as something
we didn't design for ahead of time. Not addressed today -- today's actual
conflict was resolved manually and safely. Pick this up as its own session,
likely starting 2026-10-05.
