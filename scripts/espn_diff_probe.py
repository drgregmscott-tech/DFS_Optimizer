"""
espn_diff_probe.py
===================

WK4 postmortem item 4 (2026-10-05) -- see WK4_POSTMORTEM_CHECKLIST.md and
X_INJURY_FEED_RUNBOOK.md for the full reasoning. Traced the real injury-
pipeline timeline end to end: the manual X-monitor rescue's own apply chain
(write override -> apply -> rebuild pivots) was never the bottleneck -- it
measured 2.5-5 minutes even across 4 slates. The real cost was (a) the
automated path's own near-lock CI pull cadence running up to ~55 minutes
apart on cron-job.org's existing schedule, and (b) the X monitor's one real
outage (an attended-browser session with nobody at the keyboard to approve
it) leaving a ~4.5 hour gap with no coverage at all.

This script is the "faster primary status source" half of that finding --
a CHEAP, unattended, browser-free probe that can run on a tight (~5 min)
cadence without paying the full refresh_data.yml pipeline's cost (projection
rebuild + pivot rebuild for every active slate) on every tick. It only
re-pulls ESPN's status feed and diffs it against the last committed
snapshot; the expensive build only runs when something actually changed,
via `python scripts/espn_diff_probe.py --dispatch-on-change` triggering a
near_lock_refresh the same way the existing cron-job.org cadence does.

Usage:
    python scripts/espn_diff_probe.py                 # pull + diff, print JSON, no dispatch
    python scripts/espn_diff_probe.py --dispatch-on-change   # also fire `gh api .../dispatches`
                                                        #   (event_type=near_lock_refresh) if changed
    python scripts/espn_diff_probe.py --now 2026-10-05T16:00:00Z   # testing: override the clock
                                                        #   used to decide which slates are still active

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

# Same buffer refresh_data.yml's `prepare` job uses to decide a slate is
# still active -- keep in sync if that value ever changes.
LOCK_BUFFER_MIN = 5


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


def diff_statuses(before: dict[str, str], after: dict[str, str]) -> list[dict]:
    changed = []
    for player_id, new_status in after.items():
        old_status = before.get(player_id)
        if old_status is not None and old_status != new_status:
            changed.append({"player_id": player_id, "from": old_status, "to": new_status})
    return changed


def dispatch_near_lock_refresh() -> tuple[bool, str]:
    """Fire the same repository_dispatch event cron-job.org's near-lock job
    fires, via the `gh` CLI the user already has authenticated for this repo
    (confirmed 2026-10-05: 'repo' + 'workflow' scopes, enough for this
    endpoint -- no new secret needed). Best-effort: if this fails for any
    reason, the change is already committed by the caller, so the regular
    cadence still picks it up on its own next tick -- this call only shaves
    the latency further, it's never the only path to correctness."""
    try:
        result = subprocess.run(
            ["gh", "api", "repos/{owner}/{repo}/dispatches".format(
                owner=os.environ.get("GH_REPO_OWNER", "drgregmscott-tech"),
                repo=os.environ.get("GH_REPO_NAME", "DFS_Optimizer"),
            ), "-f", "event_type=near_lock_refresh"],
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
                     help="fire a near_lock_refresh repository_dispatch via `gh` if any status changed")
    args = ap.parse_args()

    now = parse_utc(args.now) if args.now else datetime.now(timezone.utc)

    out = {
        "now_utc": now.isoformat(),
        "season_week_pairs": [],
        "changed": False,
        "changed_count": 0,
        "changes": [],
        "notes": [],
        "dispatched": None,
    }

    pairs = active_season_week_pairs(now)
    out["season_week_pairs"] = [{"season": s, "week": w} for s, w in pairs]
    if not pairs:
        out["notes"].append("no active slates -- nothing to probe")
        print(json.dumps(out, indent=2))
        return

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
        changes = diff_statuses(baseline, after)
        if changes:
            any_changed = True
            out["changes"].extend({**c, "season": season, "week": week} for c in changes)

    out["changed"] = any_changed
    out["changed_count"] = len(out["changes"])

    if any_changed and args.dispatch_on_change:
        ok, detail = dispatch_near_lock_refresh()
        out["dispatched"] = {"ok": ok, "detail": detail}

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"changed={'true' if any_changed else 'false'}\n")

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
