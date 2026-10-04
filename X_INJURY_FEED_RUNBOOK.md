# X/Twitter injury-news monitor (built 2026-10-03)

## Why this exists
ESPN's own status feed (what `status_check.py pull` reads) lags real injury news by
minutes to hours. X/beat-reporter accounts break news faster. The automated GH Actions
cadence (full/vegas/injury_only dispatches, see `refresh_data.yml`) is the reliable
backstop that eventually picks up any real status change within a few hours at most.
This monitor's job is narrower: catch news **faster** than that backstop, specifically
in the hour or two before a lock, where a Q->O flip or a backup promotion actually
changes a lineup decision in time to matter.

## Accounts (5, confirmed working 2026-10-03)
- `RotoWireNFL` -- fast aggregator, DFS-focused
- `UnderdogNFL` -- fast aggregator, DFS-focused
- `AdamSchefter` -- ESPN insider, often fastest on trades/IR moves
- `RapSheet` (Ian Rapoport) -- NFL Network insider
- `MySportsUpdate` (Ari Meirov) -- fast aggregator

## How reading works
Runs through **Claude in Chrome** (rides the user's own logged-in X session --
confirmed no login wall this way). Method: `navigate` to `https://x.com/<handle>`,
then `read_page` (accessibility tree) on the timeline region -- NOT `get_page_text`,
which grabs sidebar/Spaces content instead of actual tweets on X's dynamic feed.
Each tweet article exposes: post text, a relative timestamp ("51m", "14h"), and a
`/status/<id>` link whose numeric id is the dedup key.

**Hard boundary: read-only.** Only `navigate`, `read_page`, `get_page_text`,
`computer{action:"wait"}` are used. Never `left_click`/`type`/form interactions on
x.com -- no follow, like, reply, repost, ever. This is what makes it safe to run
unattended: there is no write action in the code path to misfire.

## State file
`data/x_injury_feed_state.json` -- one `last_seen_status_id` per account. Each poll
tick: read current posts, compare ids against stored last_seen, treat anything newer
as new, update the stored id to the newest one seen, update `last_checked_utc`.

## Cadence (revised 2026-10-04 -- now data-driven, not hand-typed per week)
Windows are derived automatically from whatever's in `data/current_slate.json` --
**never hand-type a week's lock times into a monitor prompt again.** Run:

    python scripts/x_monitor_windows.py

It groups every still-future `lock_time_utc` across the whole `slates` list (deduped,
since DK/FD main/early share a lock) into one window per distinct lock time -- default
90 minutes before lock through lock -- and reports whether "now" falls inside one, how
long until the next one starts, or "done" once every slate has locked. This is day-of-
week agnostic: a Thursday TNF showdown, a Sunday wave of classic slates, and a Monday
MNF showdown each just show up as their own window the moment that slate's entry is
added to `current_slate.json` (same step the user already does every week to let
`refresh_data.yml` track it) -- no code or runbook change needed week to week.

Within an active window, poll every ~10-15 min (same grain `x_monitor_windows.py`'s
default lead and the near-lock refresh cadence already use). Outside any window,
there's nothing to do -- re-check `x_monitor_windows.py`'s `seconds_until_next_event`
and wait. Saturday / weekday gaps between windows get no checks: real teams mostly
hold roster news for the 90-minutes-before-kickoff inactive report, which is exactly
what the window around each lock already covers.

The live `/loop` driving this should call `x_monitor_windows.py` each tick rather than
carry a fixed set of times -- that's what makes the same /loop invocation work
unmodified week after week, slate mix after slate mix.

## Per-tick procedure
1. For each of the 5 accounts: navigate, read_page the timeline, pull new posts
   (status id > stored last_seen_status_id).
2. For each new post, scan for a player name + an injury/status signal (OUT,
   DOUBTFUL, Questionable, ruled out, IR, game-time decision, inactive, etc.).
3. Cross-check the mentioned player against the latest `output/player_status_*.csv`
   -- if the X post's implied status doesn't match what's already on file, that's a
   real find: surface it to the user immediately, don't wait for the next scheduled
   GH Actions run.
4. If confirmed as a genuine new status change close to a lock, the fix is a targeted
   re-run: `python scripts/status_check.py pull --season 2026 --week 4` then
   `apply` against the affected slate(s) -- same as the manual fix done earlier this
   session for Jefferson/Nacua/Collins -- rather than waiting for the next cron slot.
5. Update `data/x_injury_feed_state.json` with the new last_seen ids.

## Known constraints
- Only works while a Claude Code session with Claude in Chrome is open -- this is a
  session-based loop (`/loop`), not a 24/7 unattended service like the GH Actions cron.
- X occasionally shows a transient login/rate-limit wall even when logged in; if a
  profile page doesn't render real tweets, wait and retry once before reporting a
  failure.
