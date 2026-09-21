"""
props_ingest.py
================

Pulls NFL player-prop lines from The Odds API for the games on ONE slate and
writes them where the projection build looks for them.

    python scripts/props_ingest.py --site dk --slate-id dk_showdown_wk2_NYG_LAR_21Sep2026
    python scripts/props_ingest.py --site dk --slate-id dk_classic_wk3_main_27Sep2026 --max-credits 120

Reads the slate's already-ingested salary file (data/salaries_{site}_{slate_id}.csv)
to learn which teams/games are on it, so only those events are pulled.

Outputs
  data/props/raw/{utc_timestamp}_{event_id}.json   one raw response per event (kept, timestamped)
  data/props/props_{slate_id}.csv                  normalized long table the build reads
  data/props/events_{slate_id}.csv                 event_id -> home/away abbreviations, start time

COST. The Odds API bills 1 credit per market per event per region. With the 6
markets below and 1 region a 16-game week is ~96 credits, one 2-team showdown
5-6 credits. The /events listing is free. `--max-credits` (default 120) aborts
BEFORE spending if the estimate is over budget, and the run refuses to start if
the account's remaining quota (read from a free call's headers) is below the
estimate plus RESERVE_CREDITS.

KEY. Uses ODDS_API_KEY_PROPS (env var or config/api_keys.env) so props can run
on their own account/quota; falls back to ODDS_API_KEY.

Failure policy: a failed pull leaves any existing props file untouched and
exits non-zero; the projection build treats "no props file" as "engine only".
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import normalize_team  # noqa: E402
from vegas_odds import TEAM_NAME_MAP  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
PROPS_DIR = DATA_DIR / "props"
RAW_DIR = PROPS_DIR / "raw"
API_HOST = "https://api.the-odds-api.com"
SPORT_KEY = "americanfootball_nfl"
REGIONS = "us"
ODDS_FORMAT = "american"
MARKETS = ["player_reception_yds", "player_receptions", "player_rush_yds",
           "player_pass_yds", "player_pass_tds", "player_anytime_td"]
RESERVE_CREDITS = 25


def load_key() -> str:
    for name in ("ODDS_API_KEY_PROPS", "ODDS_API_KEY"):
        if os.environ.get(name):
            return os.environ[name].strip()
    path = REPO_ROOT / "config" / "api_keys.env"
    found = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                found[k.strip().lstrip("﻿")] = v.strip().strip('"').strip("'")
    for name in ("ODDS_API_KEY_PROPS", "ODDS_API_KEY"):
        if found.get(name):
            return found[name]
    raise SystemExit("No ODDS_API_KEY_PROPS / ODDS_API_KEY found (env or config/api_keys.env).")


def slate_teams(site: str, slate_id: str) -> set:
    path = DATA_DIR / f"salaries_{site}_{slate_id}.csv"
    if not path.exists():
        raise SystemExit(f"{path} not found -- ingest the slate's salary file first (ingest_salaries.py).")
    df = pd.read_csv(path)
    col = "normalized_team" if "normalized_team" in df.columns else "TeamAbbrev"
    return {normalize_team(t, site) for t in df[col].dropna().unique()}


def abbr(full_name: str, site: str = "dk"):
    a = TEAM_NAME_MAP.get(full_name)
    return normalize_team(a, site) if a else None


def list_events(key: str):
    r = requests.get(f"{API_HOST}/v4/sports/{SPORT_KEY}/events", params={"apiKey": key}, timeout=20)
    r.raise_for_status()
    remaining = r.headers.get("x-requests-remaining")
    return r.json(), (float(remaining) if remaining not in (None, "?") else None)


def fetch_event(key: str, event_id: str) -> tuple:
    r = requests.get(f"{API_HOST}/v4/sports/{SPORT_KEY}/events/{event_id}/odds",
                     params={"apiKey": key, "regions": REGIONS, "markets": ",".join(MARKETS),
                             "oddsFormat": ODDS_FORMAT}, timeout=30)
    r.raise_for_status()
    return r.json(), r.headers.get("x-requests-remaining"), r.headers.get("x-requests-last")


def normalize(event_json: dict, pulled_at: str) -> pd.DataFrame:
    rows = []
    for b in event_json.get("bookmakers", []):
        for m in b.get("markets", []):
            for o in m.get("outcomes", []):
                rows.append({
                    "event_id": event_json["id"], "home": event_json["home_team"],
                    "away": event_json["away_team"], "commence_time": event_json["commence_time"],
                    "player": o.get("description"), "market": m["key"], "line": o.get("point"),
                    "side": o.get("name"), "price": o.get("price"), "book": b["key"],
                    "pulled_at": pulled_at})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="dk")
    ap.add_argument("--slate-id", required=True)
    ap.add_argument("--max-credits", type=int, default=120)
    args = ap.parse_args()

    key = load_key()
    teams = slate_teams(args.site, args.slate_id)
    events, remaining = list_events(key)
    chosen = []
    for e in events:
        h, a = abbr(e["home_team"], args.site), abbr(e["away_team"], args.site)
        if h in teams and a in teams:
            chosen.append({"event_id": e["id"], "home_abbr": h, "away_abbr": a,
                           "home": e["home_team"], "away": e["away_team"], "commence_time": e["commence_time"]})
    if not chosen:
        raise SystemExit(f"No listed Odds API events match the slate's teams {sorted(teams)}.")
    est = len(chosen) * len(MARKETS)
    print(f"Slate {args.slate_id}: {len(chosen)} event(s), est. cost {est} credits; account remaining: {remaining}")
    if est > args.max_credits:
        raise SystemExit(f"Estimated cost {est} exceeds --max-credits {args.max_credits}. Aborting before spending.")
    if remaining is not None and remaining < est + RESERVE_CREDITS:
        raise SystemExit(f"Account has {remaining} credits left; need {est} + {RESERVE_CREDITS} reserve. Aborting.")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    frames = []
    for ev in chosen:
        data, rem, last = fetch_event(key, ev["event_id"])
        (RAW_DIR / f"{stamp}_{ev['event_id']}.json").write_text(json.dumps(data), encoding="utf-8")
        frames.append(normalize(data, stamp))
        print(f"  {ev['away']} @ {ev['home']}: cost {last}, remaining {rem}")
    props = pd.concat(frames, ignore_index=True)
    if props.empty:
        raise SystemExit("Pull returned no props rows; leaving any existing props file untouched.")
    PROPS_DIR.mkdir(parents=True, exist_ok=True)
    props.to_csv(PROPS_DIR / f"props_{args.slate_id}.csv", index=False)
    pd.DataFrame(chosen).to_csv(PROPS_DIR / f"events_{args.slate_id}.csv", index=False)
    print(f"Wrote {len(props)} rows for {props['player'].nunique()} players "
          f"across {props['book'].nunique()} books -> data/props/props_{args.slate_id}.csv")


if __name__ == "__main__":
    main()
