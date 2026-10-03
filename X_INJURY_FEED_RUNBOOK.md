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

## Cadence (agreed with user 2026-10-03)
Self-paced, not a fixed interval -- tighter near a real lock:
- **Light touch (20-30 min)**: outside any pre-lock window.
- **Tight (5-10 min)**: within ~2 hours of a lock the user is actively building for.

Wk4 lock times (CT, from `data/current_slate.json`):
- Main/early classic: **11:00 AM** Sun 10/4
- Afternoon classic: **3:05 PM** Sun 10/4
- DET@CAR showdown (SNF): **7:20 PM** Sun 10/4
- ATL@NO showdown (MNF): locks Mon 10/5 evening

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
