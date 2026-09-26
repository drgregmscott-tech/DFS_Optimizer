"""Game-day inactives overlay (OPT-IN, fail-safe). Not run by anything unless invoked.

Source (verified 2026-09-26 against past games, see analysis/proj_inactives/):
  1. site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={season}&seasontype=2&week={week}
     -> event ids + competitor team ids (same public host status_check.py already uses)
  2. sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{eid}/competitions/{eid}/competitors/{tid}/roster
     -> per-game roster; each entry carries `didNotPlay` (true = game-day inactive in past games)
     (same core host status_check.py's docstring already references)
  The per-game roster returns HTTP 404 before the game ("No roster found for team X and competition Y").
  WHEN it first appears (at the ~90-min inactives release, or only at/after kickoff) is NOT verified --
  past data cannot show it. So on lock day this step may simply find nothing; that is a no-op by design.

Behaviour:
  * Reads the newest output/player_status_{week}_*.csv (written by `status_check.py pull`) as the base.
    No base, or base older than --max-base-age-hours -> no-op (never re-stamps a stale file, which would
    defeat status_check's filename-based staleness check).
  * Only marks OUT players whose game roster says didNotPlay=true, and only for teams whose roster passes
    sanity checks (>= 40 entries, 1..15 didNotPlay). Never downgrades, never invents any other status.
  * Writes a NEW output/player_status_{week}_{ts}.csv (same schema, so apply/build pick it up as latest)
    ONLY if at least one player changed; logs every flagged player to logs/inactives_{week}_{ts}.csv.
  * Any exception anywhere -> message to stderr, previous files untouched, exit 0.

Usage:  python scripts/inactives_pull.py --season 2026 --week 3 [--teams BUF,LAC] [--dry-run]
"""
import argparse
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from status_check import ESPN_TEAM_IDS, OUTPUT_DIR, LOG_DIR, DATA_DIR, match_to_player_id  # noqa: E402
from ingest_salaries import normalize_team  # noqa: E402

SCOREBOARD = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
              "?dates={season}&seasontype=2&week={week}")
GAME_ROSTER = ("https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{eid}"
               "/competitions/{eid}/competitors/{tid}/roster")
FANTASY_POS = {"QB", "RB", "WR", "TE", "FB", "PK", "K"}
ID_TO_ESPN_ABBR = {v: k for k, v in ESPN_TEAM_IDS.items()}
_pos_cache: dict = {}
TIMEOUT = 15


def _get(url):
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _ref_json(ref):
    return _get(ref.replace("http://", "https://"))


def position_abbr(entry):
    ref = (entry.get("position") or {}).get("$ref")
    if not ref:
        return ""
    key = ref.split("?")[0]
    if key not in _pos_cache:
        j = _ref_json(ref) or {}
        _pos_cache[key] = j.get("abbreviation", "")
    return _pos_cache[key]


def week_games(season, week):
    sb = _get(SCOREBOARD.format(season=season, week=week)) or {}
    out = []
    for e in sb.get("events", []):
        comp = e["competitions"][0]
        out.append({"event_id": e["id"], "kickoff": e.get("date"),
                    "state": e["status"]["type"]["name"],
                    "team_ids": [c["team"]["id"] for c in comp["competitors"]]})
    return out


def game_inactives(event_id, team_id, resolve_names=True):
    """Returns (status, rows). status in {'not_posted','insane','ok'}; rows = didNotPlay fantasy players."""
    j = _get(GAME_ROSTER.format(eid=event_id, tid=team_id))
    if not j or not j.get("entries"):
        return "not_posted", []
    ents = j["entries"]
    dnp = [x for x in ents if x.get("didNotPlay") is True]
    if len(ents) < 40 or not (1 <= len(dnp) <= 15):
        return f"insane(entries={len(ents)},dnp={len(dnp)})", []
    rows = []
    for x in dnp:
        pos = position_abbr(x)
        if pos not in FANTASY_POS:
            continue
        name = x.get("displayName", "")
        if resolve_names and x.get("athlete", {}).get("$ref"):
            a = _ref_json(x["athlete"]["$ref"]) or {}
            name = a.get("fullName", name)
        rows.append({"espn_id": str(x.get("playerId")), "player_name": name, "espn_position": pos,
                     "team": normalize_team(ID_TO_ESPN_ABBR.get(str(team_id), ""), "dk"),
                     "event_id": event_id})
    return "ok", rows


def map_to_player_id(flag, season):
    """espn_id -> gsis via nflverse weekly_rosters first; name/team matching (status_check's) as fallback."""
    flag = flag.copy()
    flag["player_id"] = None
    flag["match_method"] = None
    rp = DATA_DIR / f"weekly_rosters_{season}.parquet"
    if rp.exists() and len(flag):
        r = pd.read_parquet(rp, columns=["espn_id", "gsis_id"]).dropna()
        r["espn_id"] = r["espn_id"].astype(str).str.replace(r"\.0$", "", regex=True)
        m = r.drop_duplicates("espn_id").set_index("espn_id")["gsis_id"]
        flag["player_id"] = flag["espn_id"].map(m)
        flag.loc[flag.player_id.notna(), "match_method"] = "espn_id"
    rest = flag[flag.player_id.isna()]
    if len(rest):
        from ingest_salaries import build_player_reference
        ref = build_player_reference(DATA_DIR / f"weekly_stats_{season}.parquet",
                                     DATA_DIR / f"weekly_rosters_{season}.parquet")
        mm = match_to_player_id(rest.drop(columns=["player_id", "match_method"]), ref)
        flag.loc[rest.index, "player_id"] = mm["player_id"].values
        flag.loc[rest.index, "match_method"] = mm["match_method"].values
    return flag


def collect(season, week, teams=None, resolve_names=True, include_started=False):
    want = None
    if teams:
        want = {ESPN_TEAM_IDS[{"LA": "LAR", "WAS": "WSH"}.get(t, t)] for t in teams}
    rows, audit = [], []
    for g in week_games(season, week):
        if not include_started and g["state"] != "STATUS_SCHEDULED":
            # didNotPlay on a started/final game means "no snap yet/at all" (post-game semantics:
            # it flags dressed-but-unused backup QBs too) -- never use it once a game is underway.
            audit.append((g["event_id"], "-", f"skipped_{g['state']}", 0))
            continue
        for tid in g["team_ids"]:
            if want and tid not in want:
                continue
            try:
                st, rr = game_inactives(g["event_id"], tid, resolve_names)
            except requests.RequestException as e:
                st, rr = f"error:{e.__class__.__name__}", []
            audit.append((g["event_id"], ID_TO_ESPN_ABBR.get(tid, tid), st, len(rr)))
            rows += rr
    return pd.DataFrame(rows), audit


def run(args):
    now = datetime.now(timezone.utc)
    bases = sorted(OUTPUT_DIR.glob(f"player_status_{args.week}_*.csv"))
    if not bases:
        print(f"inactives: no output/player_status_{args.week}_*.csv base -- no-op.")
        return
    base_path = bases[-1]
    ts = datetime.strptime("_".join(base_path.stem.split("_")[-2:]), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    age_h = (now - ts).total_seconds() / 3600
    if age_h > args.max_base_age_hours:
        print(f"inactives: base {base_path.name} is {age_h:.1f}h old (> {args.max_base_age_hours}) -- no-op.")
        return
    teams = [t.strip().upper() for t in args.teams.split(",")] if args.teams else None
    flag, audit = collect(args.season, args.week, teams)
    for a in audit:
        print("inactives: event %s %s -> %s (%d fantasy inactives)" % a)
    if flag.empty:
        print("inactives: no posted game-day inactives found -- no-op.")
        return
    flag = map_to_player_id(flag, args.season)
    base = pd.read_csv(base_path, dtype={"player_id": str})
    stamp = now.strftime("%Y%m%d_%H%M%S")
    log = []
    new = base.copy()
    for f in flag.itertuples():
        if not isinstance(f.player_id, str):
            log.append({**f._asdict(), "action": "unmatched_skipped", "prev_status": None})
            continue
        hit = new.player_id == f.player_id
        if hit.any():
            prev = new.loc[hit, "status"].iloc[0]
            if prev == "OUT":
                log.append({**f._asdict(), "action": "already_out", "prev_status": prev})
                continue
            new.loc[hit, ["status", "raw_status", "last_updated"]] = ["OUT", "Inactive (gameday)", now.isoformat()]
            log.append({**f._asdict(), "action": "set_out", "prev_status": prev})
        else:
            new = pd.concat([new, pd.DataFrame([{"player_id": f.player_id, "player_name": f.player_name,
                             "team": f.team, "position": f.espn_position, "status": "OUT",
                             "raw_status": "Inactive (gameday)", "last_updated": now.isoformat(),
                             "match_method": f.match_method}])], ignore_index=True)
            log.append({**f._asdict(), "action": "added_out", "prev_status": None})
    lg = pd.DataFrame(log)
    n_changed = int(lg.action.isin(["set_out", "added_out"]).sum()) if len(lg) else 0
    print(f"inactives: {len(flag)} fantasy inactives, {n_changed} status change(s) vs {base_path.name}")
    if args.dry_run:
        print(lg.to_string())
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    lg.assign(base_file=base_path.name).to_csv(LOG_DIR / f"inactives_{args.week}_{stamp}.csv", index=False)
    if n_changed:
        out = OUTPUT_DIR / f"player_status_{args.week}_{stamp}.csv"
        new[base.columns].to_csv(out, index=False)
        print(f"inactives: wrote {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--week", type=int, required=True)
    p.add_argument("--teams", default=None)
    p.add_argument("--max-base-age-hours", type=float, default=6.0)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    try:
        run(args)
    except Exception:  # fail-safe: never break the refresh, never touch prior files
        print("inactives: FAILED (previous status file left untouched):\n" + traceback.format_exc(), file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
