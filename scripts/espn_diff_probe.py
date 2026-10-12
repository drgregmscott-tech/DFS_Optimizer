"""
espn_diff_probe.py
===================

WK4 postmortem item 4 (2026-10-05) built this as a cheap, unattended,
browser-free probe to catch ESPN status changes faster than the coarse
refresh_data.yml cadence, without the attended X/Twitter monitor's "nobody
at the keyboard" failure mode. WK5 postmortem item 5 (2026-10-12) made it
the PERMANENT primary mechanism (not a one-week workaround) after a
real-case review found the attended X monitor gave no consistent speed
edge over this probe once it existed (across 6 real Wk3-5 cases, X was
ahead twice by 4-8 minutes, ESPN-first three times, and wrong once --
see X_INJURY_FEED_RUNBOOK.md). The X monitor is now optional best-effort
when a session happens to be open; this script is what Sunday actually
depends on.

That same review found two real problems with the original version of
this script, both fixed here:
  1. It diffed EVERY player in the active week's status file, including
     players whose own game had already kicked off -- in-game status
     flicker (OUT -> Questionable -> OUT as a broadcast corrects itself)
     on an already-locked game was triggering full refreshes for no
     reason. Fixed: `still_to_kick()` below drops any player whose team's
     game has already started from the diff entirely.
  2. Cron-job.org's own fixed clock-hour schedule ran this far wider than
     the "105 min before lock through lock" window it was meant to cover
     (e.g. 10:01-19:51 CT continuously on 2026-10-11), and every
     change-triggered dispatch escalated to `near_lock_refresh`, which
     re-pulls Vegas lines -- on a free 500-credit/month Odds API plan,
     one Sunday alone (2026-10-11) burned ~70 credits this way. Fixed:
     this script now decides its own active window in code (reusing
     x_monitor_windows.compute_window(), lead=105 min, same as the
     attended monitor used), so cron-job.org can be simplified to one
     "every 10 minutes, every day" job with no weekly editing -- this
     script no-ops (no ESPN pull at all) outside an active window. Two
     fixed anchors inside each window (~75 and ~60 minutes before lock --
     per the user, 2026-10-12: the official inactive report lands around
     90 min out, so these anchors sit just after that, not at an arbitrary
     round number) still get a full `near_lock_refresh` (Vegas lines +
     props) so that data doesn't go stale; every other in-window tick is a
     free injury-only check (`scheduled_injury_refresh`, no Vegas pull)
     that only escalates when a real, not-yet-kicked-off-game status
     change is found. Inside 60 minutes of lock, there is deliberately NO
     automatic Vegas-pulling refresh any more (that's the window that was
     burning Odds API credits) -- if a real change needs a fresh Vegas
     pull that close to lock, fire one on request:
         gh api repos/{owner}/{repo}/dispatches -f event_type=near_lock_refresh
     (same command X_INJURY_FEED_RUNBOOK.md's step 4 already documents for
     a manual override). The injury-only (Vegas-free) check keeps running
     every tick all the way to lock regardless.

Usage:
    python scripts/espn_diff_probe.py                 # pull + diff, print JSON, no dispatch
    python scripts/espn_diff_probe.py --dispatch-on-change   # also fire `gh api .../dispatches`
                                                        #   when this tick calls for one (see above)
    python scripts/espn_diff_probe.py --now 2026-10-05T16:00:00Z   # testing: override the clock

Exit code is always 0 -- same fail-open philosophy as the rest of this
pipeline (x_monitor_windows.py, refresh_data.yml's continue-on-error steps).
A pull failure or a missing baseline file is reported in the JSON output,
never crashes the caller.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from x_monitor_windows import compute_window  # noqa: E402

# Same buffer refresh_data.yml's `prepare` job uses to decide a slate is
# still active -- keep in sync if that value ever changes.
LOCK_BUFFER_MIN = 5
WINDOW_LEAD_MIN = 105  # same lead x_monitor_windows.py's attended monitor used

# Fixed in-window anchors (minutes-to-lock) that always get a full refresh
# (Vegas lines + props), regardless of whether a status change was found --
# every other in-window tick is injury-only (no Vegas pull). Each is a
# +/-5min band around the target so a ~10min cron-job.org cadence reliably
# lands one tick inside it without double-firing on a second tick. Chosen
# 2026-10-12 per the user: the official inactive report lands ~90 min
# before lock, so ~75 and ~60 catch it and its first confirmation without
# reaching into the <60min range, which is deliberately left to the
# Vegas-free injury-only check plus a manual on-request full refresh (see
# this module's docstring) rather than another automatic Vegas pull.
GUARANTEED_FULL_BANDS = [(70, 80), (55, 65)]


def parse_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def active_season_week_pairs(now: datetime) -> list[tuple[int, int]]:
    try:
        cfg = json.load(open(DATA_DIR / "current_slate.json", encoding="utf-8"))
        slates = cfg.get("slates", [])
    except (OSError, json.JSONDecodeError):
        return []
    buffer = timedelta(minutes=LOCK_BUFFER_MIN)
    pairs = set()
    for s in slates:
        try:
            lock = parse_utc(s["lock_time_utc"])
        except (KeyError, ValueError, AttributeError):
            continue
        if now >= lock + buffer:
            continue  # already locked, same philosophy as refresh_data.yml's `prepare` job
        pairs.add((s["season"], s["week"]))
    return sorted(pairs)


def latest_status_file(week: int, exclude: Path | None = None) -> Path | None:
    candidates = sorted(OUTPUT_DIR.glob(f"player_status_{week}_*.csv"))
    if exclude is not None:
        candidates = [c for c in candidates if c != exclude]
    return candidates[-1] if candidates else None


def status_map(path: Path) -> dict[str, str]:
    df = pd.read_csv(path, dtype=str).fillna("")
    return dict(zip(df["player_id"], df["status"]))


def team_map(path: Path) -> dict[str, str]:
    df = pd.read_csv(path, dtype=str).fillna("")
    return dict(zip(df["player_id"], df["team"]))


def not_yet_kicked_teams(season: int, week: int, now: datetime, notes: list[str]) -> set[str] | None:
    """DK-normalized team abbreviations whose game hasn't started yet this
    week, per ESPN's own scoreboard. Returns None (meaning "don't filter,
    include everyone") if the scoreboard pull fails -- fail-open, same as
    the rest of this script, rather than silently dropping every player
    because of a transient network error."""
    try:
        from inactives_pull import week_games, ID_TO_ESPN_ABBR  # noqa: PLC0415
        from ingest_salaries import normalize_team  # noqa: PLC0415

        games = week_games(season, week)
        teams = set()
        for g in games:
            try:
                kickoff = parse_utc(g["kickoff"])
            except (KeyError, ValueError, TypeError):
                continue
            if kickoff > now:
                for tid in g["team_ids"]:
                    abbr = ID_TO_ESPN_ABBR.get(str(tid), "")
                    if abbr:
                        teams.add(normalize_team(abbr, "dk"))
        return teams
    except Exception as e:  # noqa: BLE001
        notes.append(f"week {week}: could not pull scoreboard to filter in-game teams ({e}) -- not filtering")
        return None


def diff_statuses(before: dict[str, str], after: dict[str, str],
                   after_teams: dict[str, str], eligible_teams: set[str] | None) -> list[dict]:
    changed = []
    for player_id, new_status in after.items():
        if eligible_teams is not None and after_teams.get(player_id) not in eligible_teams:
            continue  # that player's game already kicked off -- in-game flicker, not a lineup-relevant change
        old_status = before.get(player_id)
        if old_status is not None and old_status != new_status:
            changed.append({"player_id": player_id, "from": old_status, "to": new_status})
    return changed


def dispatch_refresh(event_type: str) -> tuple[bool, str]:
    """Fire a repository_dispatch via the `gh` CLI the user already has
    authenticated for this repo (confirmed 2026-10-05: 'repo' + 'workflow'
    scopes, enough for this endpoint -- no new secret needed). Best-effort:
    if this fails for any reason, the change is already committed by the
    caller, so the regular cadence still picks it up on its own next tick --
    this call only shaves the latency further, it's never the only path to
    correctness."""
    try:
        result = subprocess.run(
            ["gh", "api", "repos/{owner}/{repo}/dispatches".format(
                owner=os.environ.get("GH_REPO_OWNER", "drgregmscott-tech"),
                repo=os.environ.get("GH_REPO_NAME", "DFS_Optimizer"),
            ), "-f", f"event_type={event_type}"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode == 0:
            return True, "dispatched"
        return False, (result.stderr or result.stdout or "unknown gh failure").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", default=None, help="override the clock (ISO UTC, for testing)")
    ap.add_argument("--dispatch-on-change", action="store_true",
                     help="fire the repository_dispatch this tick calls for (guaranteed full refresh "
                          "near an anchor, or injury-only refresh on a real detected change)")
    args = ap.parse_args()

    now = parse_utc(args.now) if args.now else datetime.now(timezone.utc)

    out = {
        "now_utc": now.isoformat(),
        "window": None,
        "season_week_pairs": [],
        "changed": False,
        "changed_count": 0,
        "changes": [],
        "notes": [],
        "dispatch_reason": None,  # None | "guaranteed_full" | "detected_change"
        "dispatched": None,
    }

    window = compute_window(now, WINDOW_LEAD_MIN)
    out["window"] = window
    if window["status"] != "in_window":
        out["notes"].append(f"status={window['status']} -- outside any pre-lock window, skipping ESPN pull entirely")
        print(json.dumps(out, indent=2))
        return

    pairs = active_season_week_pairs(now)
    out["season_week_pairs"] = [{"season": s, "week": w} for s, w in pairs]
    if not pairs:
        out["notes"].append("in_window per x_monitor_windows but no active slates in current_slate.json -- nothing to probe")
        print(json.dumps(out, indent=2))
        return

    minutes_to_lock = window["active_window"]["minutes_to_lock"]
    guaranteed_full = any(lo <= minutes_to_lock <= hi for lo, hi in GUARANTEED_FULL_BANDS)

    any_changed = False
    for season, week in pairs:
        baseline_path = latest_status_file(week)
        baseline = status_map(baseline_path) if baseline_path else {}

        # Import locally so this script can be unit-tested without network
        # access when a caller only wants diff_statuses()/active_season_week_pairs().
        from status_check import run_pull  # noqa: PLC0415

        try:
            run_pull(season, week, teams_arg=None, weekly_stats_override=None)
        except SystemExit as e:
            out["notes"].append(f"week {week}: pull failed or raised ({e}) -- using last-known-good, no diff computed")
            continue

        new_path = latest_status_file(week, exclude=baseline_path)
        if new_path is None:
            out["notes"].append(f"week {week}: pull produced no new file")
            continue

        if baseline_path is None:
            out["notes"].append(f"week {week}: no prior baseline -- first pull this week, establishing baseline, not flagging as change")
            continue

        after = status_map(new_path)
        after_teams = team_map(new_path)
        eligible_teams = not_yet_kicked_teams(season, week, now, out["notes"])
        changes = diff_statuses(baseline, after, after_teams, eligible_teams)
        if changes:
            any_changed = True
            out["changes"].extend({**c, "season": season, "week": week} for c in changes)

    out["changed"] = any_changed
    out["changed_count"] = len(out["changes"])

    if guaranteed_full:
        out["dispatch_reason"] = "guaranteed_full"
        event_type = "near_lock_refresh"
    elif any_changed:
        out["dispatch_reason"] = "detected_change"
        event_type = "scheduled_injury_refresh"
    else:
        event_type = None

    if event_type and args.dispatch_on_change:
        ok, detail = dispatch_refresh(event_type)
        out["dispatched"] = {"event_type": event_type, "ok": ok, "detail": detail}

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"changed={'true' if any_changed else 'false'}\n")
            f.write(f"dispatch_reason={out['dispatch_reason'] or 'none'}\n")

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
