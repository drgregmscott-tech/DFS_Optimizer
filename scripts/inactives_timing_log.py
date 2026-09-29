"""Inactives timing logger (OBSERVE-ONLY, not wired into production).

Answers: how soon before kickoff do ESPN and Sleeper actually show game-day inactives?
Run it in a terminal Sunday morning and leave it going through the early window:

    python scripts/inactives_timing_log.py --season 2026 --week 4 --until-hours-before-last-kickoff -0

Each poll (default every 5 min for ESPN, every 15 min for Sleeper, which asks for very light use):
  * ESPN: for every scheduled game/team, records whether the per-game roster exists yet and the didNotPlay count
    -> first time it appears is the ESPN inactives time. (Uses inactives_pull.game_inactives.)
  * Sleeper: snapshots injury_status/status for skill players; logs every CHANGE with the poll timestamp
    (plus Sleeper's own news_updated) -> shows when Out/Inactive marks show up and how many are new.
Outputs (append-only): logs/inactives_timing_{season}_wk{week}.csv (one row per event) and a summary line on exit
with minutes-before-kickoff for the first ESPN roster per game and the first Sleeper newly-Out flag per team.
Never writes to output/ or any production file.
"""
import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inactives_pull as ip  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
SK = {"QB", "RB", "WR", "TE"}


def now():
    return datetime.now(timezone.utc)


def sleeper_snapshot():
    r = requests.get("https://api.sleeper.app/v1/players/nfl", timeout=90)
    r.raise_for_status()
    out = {}
    for pid, p in r.json().items():
        if p.get("position") in SK and p.get("team"):
            out[pid] = (p.get("full_name"), p.get("team"), p.get("injury_status"), p.get("status"),
                        p.get("news_updated"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--espn-every-min", type=float, default=5)
    ap.add_argument("--sleeper-every-min", type=float, default=15)
    ap.add_argument("--stop-after-hours", type=float, default=6,
                    help="hard stop so it can't run forever")
    a = ap.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"inactives_timing_{a.season}_wk{a.week}.csv"
    new = not path.exists()
    f = open(path, "a", newline="", encoding="utf-8")
    w = csv.writer(f)
    if new:
        w.writerow(["ts_utc", "source", "event", "team", "detail", "minutes_to_kickoff"])
    games = {g["event_id"]: g for g in ip.week_games(a.season, a.week)}
    kick = {eid: datetime.fromisoformat(g["kickoff"].replace("Z", "+00:00")) for eid, g in games.items()}
    espn_seen = {}       # (eid, tid) -> first ts posted
    prev_sl = None
    t_end = time.time() + a.stop_after_hours * 3600
    next_sl = 0.0
    first_sl_new_out = {}
    print(f"logging to {path}; {len(games)} games; Ctrl+C to stop")
    try:
        while time.time() < t_end:
            t = now()
            for eid, g in games.items():
                if g["state"] != "STATUS_SCHEDULED" and (eid, g["team_ids"][0]) in espn_seen:
                    continue
                for tid in g["team_ids"]:
                    if (eid, tid) in espn_seen:
                        continue
                    try:
                        status, rows = ip.game_inactives(eid, tid, resolve_names=False)
                    except Exception as e:  # noqa: BLE001
                        print("espn err", e, file=sys.stderr)
                        continue
                    if status != "not_posted":
                        mtk = (kick[eid] - t).total_seconds() / 60
                        abbr = ip.ID_TO_ESPN_ABBR.get(str(tid), tid)
                        espn_seen[(eid, tid)] = t
                        w.writerow([t.isoformat(), "espn_roster", eid, abbr,
                                    f"{status};skill_dnp={len(rows)}", round(mtk, 1)])
                        f.flush()
                        print(f"ESPN roster live: {abbr} game {eid} {round(mtk)} min before kickoff ({status}, {len(rows)} skill DNP)")
            if time.time() >= next_sl:
                next_sl = time.time() + a.sleeper_every_min * 60
                try:
                    snap = sleeper_snapshot()
                    if prev_sl is not None:
                        for pid, cur in snap.items():
                            old = prev_sl.get(pid)
                            if old and (old[2], old[3]) != (cur[2], cur[3]):
                                w.writerow([t.isoformat(), "sleeper_change", "", cur[1],
                                            f"{cur[0]}: {old[2]}/{old[3]} -> {cur[2]}/{cur[3]} (news_updated={cur[4]})", ""])
                                if str(cur[2]).lower() == "out" or str(cur[3]).lower() == "inactive":
                                    first_sl_new_out.setdefault(cur[1], t)
                        f.flush()
                    prev_sl = snap
                except Exception as e:  # noqa: BLE001
                    print("sleeper err", e, file=sys.stderr)
            time.sleep(a.espn_every_min * 60)
    except KeyboardInterrupt:
        pass
    finally:
        f.close()
    print(f"done. ESPN rosters seen for {len(espn_seen)} team-games. Raw log: {path}")


if __name__ == "__main__":
    main()
