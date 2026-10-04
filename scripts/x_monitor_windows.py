"""
x_monitor_windows.py
=====================

Derives this week's X/Twitter injury-monitor lock windows from
data/current_slate.json, so the X injury monitor (see
X_INJURY_FEED_RUNBOOK.md) never has a week's dates/lock-times hand-typed
into a /loop prompt. Every week, the user adds that week's slates to
current_slate.json as part of the normal weekly process (same file
props_auto.py and refresh_data.yml already read) -- this script is the
single place that turns "slates with lock times" into "when should the
X monitor be actively polling."

A "window" is [lock_time_utc - lead_minutes, lock_time_utc] for each
DISTINCT lock_time_utc still in the future across every slate in the
list (already-locked slates, filtered the same way refresh_data.yml's
`prepare` job does, are dropped). Slates sharing a lock time (e.g. DK
main + FD main + DK early, all noon ET) collapse into one window --
the point is "is real injury news about to matter for ANY still-open
slate," not one window per slate.

    python scripts/x_monitor_windows.py                  # real run, uses now()
    python scripts/x_monitor_windows.py --now 2026-10-04T16:45:00Z   # testing
    python scripts/x_monitor_windows.py --lead-minutes 90

Prints one JSON object to stdout:
  {
    "now_utc": "...",
    "status": "in_window" | "waiting" | "done",
    "active_window": {"lock_time_utc": "...", "slate_ids": [...], "minutes_to_lock": N} or null,
    "next_window_starts_utc": "..." or null,
    "seconds_until_next_event": N or null,   # either window start or, if in_window, the lock itself
    "remaining_windows_today": N
  }

`status`:
  - "in_window"  -- now is inside [lock - lead, lock] for some still-open
                    lock time. `active_window` names it and every slate_id
                    sharing it (cross-check those slates' final_projections
                    when scanning new posts).
  - "waiting"     -- not in a window yet, but at least one future window
                    remains today. `next_window_starts_utc` /
                    `seconds_until_next_event` say how long to wait.
  - "done"        -- every slate in current_slate.json has either locked
                    or its window closed. The caller (the /loop monitor)
                    should stop rather than keep polling.

Exit code is always 0; a malformed current_slate.json or empty slate list
is reported as status "done" (nothing to watch) rather than crashing --
same fail-open philosophy as the rest of the refresh pipeline.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_LEAD_MIN = 90


def parse_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead-minutes", type=int, default=DEFAULT_LEAD_MIN,
                     help="how long before a lock the monitor should start polling (default 90)")
    ap.add_argument("--now", default=None, help="override the clock (ISO UTC, for testing)")
    args = ap.parse_args()

    now = parse_utc(args.now) if args.now else datetime.now(timezone.utc)
    lead = timedelta(minutes=args.lead_minutes)

    out = {
        "now_utc": now.isoformat(),
        "status": "done",
        "active_window": None,
        "next_window_starts_utc": None,
        "seconds_until_next_event": None,
        "remaining_windows_today": 0,
    }

    try:
        cfg = json.load(open(DATA_DIR / "current_slate.json", encoding="utf-8"))
        slates = cfg.get("slates", [])
    except (OSError, json.JSONDecodeError):
        slates = []

    # Group still-future slates by distinct lock_time_utc.
    by_lock = {}
    for s in slates:
        try:
            lock = parse_utc(s["lock_time_utc"])
        except (KeyError, ValueError, AttributeError):
            continue
        if lock <= now:
            continue  # already locked -- same philosophy as refresh_data.yml's `prepare` job
        by_lock.setdefault(lock, []).append(s["slate_id"])

    if not by_lock:
        print(json.dumps(out, indent=2))
        return

    locks_sorted = sorted(by_lock)
    # Only windows that start "today" in the sense of being the remaining
    # locks reachable without an overnight gap matter for `remaining_windows_today`;
    # since the caller only cares about "is there anything left to watch right
    # now or soon," count every future lock still in by_lock.
    out["remaining_windows_today"] = len(locks_sorted)

    active = None
    for lock in locks_sorted:
        if now >= lock - lead:
            active = lock
            break  # locks_sorted is ascending; the first whose window has opened is the one we're in

    if active is not None:
        out["status"] = "in_window"
        out["active_window"] = {
            "lock_time_utc": active.isoformat(),
            "slate_ids": by_lock[active],
            "minutes_to_lock": round((active - now).total_seconds() / 60.0, 1),
        }
        out["seconds_until_next_event"] = max(0, int((active - now).total_seconds()))
    else:
        nxt = locks_sorted[0]
        out["status"] = "waiting"
        out["next_window_starts_utc"] = (nxt - lead).isoformat()
        out["seconds_until_next_event"] = int((nxt - lead - now).total_seconds())

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
