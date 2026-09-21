"""
props_auto.py
==============

Automatic per-slate props pull, meant to run inside refresh_data.yml's
shared_pull job (and runnable by hand). For every slate in
data/current_slate.json whose lock is within --lead-minutes from now (and not
already locked), it makes sure a FRESH props snapshot exists:

  - a slate whose snapshot (data/props/props_{slate_id}.csv) was pulled less
    than --fresh-minutes ago is skipped (so two triggers close together do
    not buy the same lines twice);
  - all remaining due slates are handled in ONE pass: the union of their
    games is pulled once each, and every slate gets its own props/events
    files from that shared pull (classic main/early/afternoon slates share
    games, so this avoids paying for them two or three times).

Slates are independent in time: a Thursday-night showdown is due only near
its own lock, Sunday's classic slates only near theirs, and the Sunday-night
and Monday-night showdowns near theirs.

    python scripts/props_auto.py                 # real run, uses now()
    python scripts/props_auto.py --dry-run       # print what would be pulled
    python scripts/props_auto.py --now 2026-09-21T23:00:00Z --dry-run

Cost guard, key handling and file formats are props_ingest.py's (it reuses its
functions). Any failure exits 0 after printing a warning: props are an
enhancement, and a failed pull must never fail the refresh (the build simply
uses the last committed snapshot if it is <72h old, else engine only).
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import props_ingest as pi  # noqa: E402

DEFAULT_LEAD_MIN = 100
DEFAULT_FRESH_MIN = 120
DEFAULT_REUSE_HOURS = 8
LOCK_BUFFER = timedelta(minutes=5)


def parse_utc(s: str):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def snapshot_age_minutes(slate_id: str, now: datetime):
    path = pi.PROPS_DIR / f"props_{slate_id}.csv"
    if not path.exists():
        return None
    try:
        stamp = pd.read_csv(path, usecols=["pulled_at"], nrows=1)["pulled_at"].iloc[0]
        pulled = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return (now - pulled).total_seconds() / 60.0
    except Exception:  # noqa: BLE001
        return None


def reusable_snapshot(slate_id: str, event_ids: set, now: datetime, reuse_hours: float):
    """If ANOTHER slate's snapshot (pulled within `reuse_hours`) already contains
    every one of this slate's games, return (donor_slate_id, its props rows).
    Used so a later slate on the same day (Sunday afternoon) reuses the earlier
    pull that covered its games instead of buying the lines again."""
    best = None
    for path in pi.PROPS_DIR.glob("props_*.csv"):
        other = path.stem[len("props_"):]
        if other == slate_id:
            continue
        age = snapshot_age_minutes(other, now)
        if age is None or age > reuse_hours * 60:
            continue
        try:
            df = pd.read_csv(path)
        except Exception:  # noqa: BLE001
            continue
        if event_ids <= set(df["event_id"].unique()) and (best is None or age < best[0]):
            best = (age, other, df)
    return None if best is None else (best[1], best[2], best[0])


def due_slates(now: datetime, lead_min: int, fresh_min: int, slates: list):
    due = []
    for s in slates:
        try:
            lock = parse_utc(s["lock_time_utc"])
        except (KeyError, ValueError, AttributeError):
            continue
        if s.get("site") != "dk":
            continue                                   # no FD props model / salary pipeline for props yet
        mins_to_lock = (lock - now).total_seconds() / 60.0
        if now >= lock + LOCK_BUFFER or mins_to_lock > lead_min:
            continue
        age = snapshot_age_minutes(s["slate_id"], now)
        if age is not None and age < fresh_min:
            print(f"  {s['slate_id']}: lock in {mins_to_lock:.0f} min, snapshot is {age:.0f} min old -> skip (fresh)")
            continue
        print(f"  {s['slate_id']}: lock in {mins_to_lock:.0f} min, snapshot age "
              f"{'none' if age is None else f'{age:.0f} min'} -> DUE")
        due.append(s)
    return due


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead-minutes", type=int, default=DEFAULT_LEAD_MIN)
    ap.add_argument("--fresh-minutes", type=int, default=DEFAULT_FRESH_MIN)
    ap.add_argument("--max-credits", type=int, default=120)
    ap.add_argument("--reuse-hours", type=float, default=DEFAULT_REUSE_HOURS,
                    help="reuse another slate's snapshot pulled within this many hours if it already covers "
                         "all of this slate's games (default 8; 0 disables reuse)")
    ap.add_argument("--now", default=None, help="override the clock (ISO, for testing)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = parse_utc(args.now) if args.now else datetime.now(timezone.utc)
    cfg = json.load(open(pi.DATA_DIR / "current_slate.json", encoding="utf-8"))
    print(f"props_auto at {now.isoformat()} (lead {args.lead_minutes} min, fresh {args.fresh_minutes} min)")
    due = due_slates(now, args.lead_minutes, args.fresh_minutes, cfg.get("slates", []))
    if not due:
        print("No slates due for a props pull.")
        return

    try:
        key = pi.load_key()
        listed, remaining = pi.list_events(key)
        by_id = {}
        slate_events = {}
        reused = set()
        for s in due:
            teams = pi.slate_teams("dk", s["slate_id"])
            evs = []
            for e in listed:
                h, a = pi.abbr(e["home_team"], "dk"), pi.abbr(e["away_team"], "dk")
                if h in teams and a in teams:
                    ev = {"event_id": e["id"], "home_abbr": h, "away_abbr": a, "home": e["home_team"],
                          "away": e["away_team"], "commence_time": e["commence_time"]}
                    evs.append(ev)
                    by_id[e["id"]] = ev
            slate_events[s["slate_id"]] = evs
            print(f"  {s['slate_id']}: {len(evs)} game(s)")
        # Reuse: a due slate whose games are ALL already in a recent snapshot of
        # another slate (e.g. Sunday afternoon vs the main slate pulled ~3h
        # earlier) gets a copy instead of a new purchase.
        if args.reuse_hours > 0:
            for sid in list(slate_events):
                ids = {e["event_id"] for e in slate_events[sid]}
                hit = reusable_snapshot(sid, ids, now, args.reuse_hours) if ids else None
                if hit:
                    donor, df, age = hit
                    print(f"  {sid}: reusing {donor}'s snapshot ({age:.0f} min old) instead of a new pull")
                    if not args.dry_run:
                        pi.PROPS_DIR.mkdir(parents=True, exist_ok=True)
                        df[df["event_id"].isin(ids)].to_csv(pi.PROPS_DIR / f"props_{sid}.csv", index=False)
                        pd.DataFrame(slate_events[sid]).to_csv(pi.PROPS_DIR / f"events_{sid}.csv", index=False)
                    for e in slate_events[sid]:
                        if not any(e["event_id"] in {x["event_id"] for x in evs}
                                   for k2, evs in slate_events.items() if k2 != sid and k2 not in reused):
                            by_id.pop(e["event_id"], None)
                    reused.add(sid)
            slate_events = {k: v for k, v in slate_events.items() if k not in reused}
        est = len(by_id) * len(pi.MARKETS)
        print(f"Union of {len(by_id)} game(s) -> est. {est} credits; account remaining: {remaining}")
        if args.dry_run:
            print("Dry run: nothing pulled.")
            return
        if est == 0:
            print("No matching events listed by the Odds API; nothing to pull.")
            return
        if est > args.max_credits:
            print(f"::warning::props estimate {est} exceeds --max-credits {args.max_credits}; skipping props pull.")
            return
        if remaining is not None and remaining < est + pi.RESERVE_CREDITS:
            print(f"::warning::props account has {remaining} credits; need {est}+{pi.RESERVE_CREDITS}; skipping.")
            return

        pi.RAW_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        frames = {}
        for eid, ev in by_id.items():
            data, rem, last = pi.fetch_event(key, eid)
            (pi.RAW_DIR / f"{stamp}_{eid}.json").write_text(json.dumps(data), encoding="utf-8")
            frames[eid] = pi.normalize(data, stamp)
            print(f"  pulled {ev['away']} @ {ev['home']}: cost {last}, remaining {rem}")
        pi.PROPS_DIR.mkdir(parents=True, exist_ok=True)
        for sid, evs in slate_events.items():
            parts = [frames[e["event_id"]] for e in evs if e["event_id"] in frames and len(frames[e["event_id"]])]
            if not parts:
                print(f"  {sid}: no props rows returned; leaving any existing snapshot untouched")
                continue
            pd.concat(parts, ignore_index=True).to_csv(pi.PROPS_DIR / f"props_{sid}.csv", index=False)
            pd.DataFrame(evs).to_csv(pi.PROPS_DIR / f"events_{sid}.csv", index=False)
            print(f"  {sid}: wrote snapshot ({len(parts)} game(s))")
    except SystemExit as exc:
        print(f"::warning::props pull aborted: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::props pull failed ({type(exc).__name__}: {exc}); builds fall back to the last snapshot or engine only.")


if __name__ == "__main__":
    main()
