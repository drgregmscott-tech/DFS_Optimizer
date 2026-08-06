"""
probe_player_props_sgo.py
==========================

Session 14.1 -- Player Props Scoping. THROWAWAY PROBE, not a permanent
pipeline script (same convention as probe_player_props.py and
probe_reconcile_gap.py). Not wired into refresh_data.yml.

Purpose: real coverage, real per-event cost, and the real statID taxonomy
from SportsGameOdds -- the second candidate data source raised in this
session, after The Odds API's per-market-per-event credit cost was found
(via probe_player_props.py's own real numbers) to plausibly exceed the
free-tier budget under weekly full-coverage polling.

Deliberately does NOT hardcode a guessed statID list the way
probe_player_props.py's first MLB run did (player_home_runs vs. the
real batter_home_runs -- a real 422 caught by that probe, not this one).
SportsGameOdds' own docs only confirm one statID for certain
(rushing_yards); the rest (passing yards/TDs, receiving, anytime-TD,
kicking) are inferred from marketing copy, not confirmed live. So this
script pulls odds UNFILTERED (no oddIDs param) for a small number of
events and reports every real statID it finds, grouped and counted --
letting the real data define the taxonomy instead of assuming it. This
also naturally answers the low-salary/cold-start coverage question the
same way probe_player_props.py's --salary-csv does.

Billing model differs fundamentally from The Odds API: SportsGameOdds
bills 1 object per EVENT regardless of how many markets/players/books
are returned (confirmed via their own pricing page and blog -- "1 object
= 1 event, not 1 event-market"). This is the whole reason it's worth
testing: a full, unfiltered pull of every market for a whole NFL week
should cost ~14-16 objects total, not ~150+ credits the way The Odds
API's per-market billing would. This script's own printed object count
(from the response, not assumed) is the real number to trust.

Setup required before this script will run:
  1. Sign up for a free key at https://sportsgameodds.com/pricing
     (Amateur tier, no card required) -- manual step, account creation
     is not something this script or Claude can do.
  2. Add `SGO_API_KEY=your_key_here` to config/api_keys.env (gitignored),
     same file vegas_odds.py's ODDS_API_KEY already lives in.

Auth note: SportsGameOdds' own docs show two different auth styles across
different pages (apiKey as a query param in their guide pages, x-api-key
as a header in their more recent DFS-use-case page). This script sends
BOTH, so it works regardless of which one this account/endpoint actually
expects -- if you see a 401, that's real signal one of the two styles
isn't valid and worth reporting back, not this script's fault.

Response-shape note: the exact top-level wrapper key for /v2/events
(e.g. "data" vs a bare list) isn't confirmed from docs alone either. This
script handles both shapes defensively and prints the raw top-level keys
if neither matches, so a real mismatch is visible and fixable rather than
silently swallowed.

Usage:
  python3 probe_player_props_sgo.py --max-events 3
  python3 probe_player_props_sgo.py --max-events 3 --salary-csv data/dk_salaries.csv

--max-events caps the real object spend (and response size/time) during
probing. Default: 3. Given the per-event billing model, even a generous
--max-events 16 (a full NFL week) should stay well inside the 2,500/month
free tier -- but let the script's own reported object usage confirm that,
don't assume it.
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
OUTPUT_DIR = REPO_ROOT / "output"

API_HOST = "https://api.sportsgameodds.com"
LEAGUE_ID = "NFL"

# Keyword buckets to flag against whatever real statIDs come back --
# NOT a hardcoded market list to request (see module docstring for why).
# Substring-matched, case-insensitive, against each real statID found.
KEYWORD_BUCKETS = {
    "passing": ["passing", "pass_"],
    "rushing": ["rushing", "rush_"],
    "receiving": ["receiving", "reception"],
    "touchdown": ["touchdown"],
    "interception": ["interception"],
    "field_goal": ["field_goal", "fieldgoal"],
    "kicking": ["kicking", "extra_point", "pat"],
}


# ---------------------------------------------------------------------------
# Step 0: API key
# ---------------------------------------------------------------------------

def load_sgo_api_key() -> str:
    """Read SGO_API_KEY from config/api_keys.env. Same file, same
    utf-8-sig-safe read pattern as vegas_odds.py's load_api_key() (Windows
    BOM issue applies equally here) -- duplicated rather than imported
    since the key NAME differs (SGO_API_KEY vs ODDS_API_KEY) and this is
    a throwaway probe, not worth adding a shared-utils module for.
    """
    env_path = CONFIG_DIR / "api_keys.env"
    if not env_path.exists():
        raise FileNotFoundError(
            f"{env_path} not found. Sign up for a free key at "
            f"https://sportsgameodds.com/pricing, then add a line "
            f"'SGO_API_KEY=your_key_here' to {env_path}."
        )
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "SGO_API_KEY":
            value = value.strip().strip('"').strip("'")
            if value:
                return value
    raise ValueError(
        f"SGO_API_KEY not found in {env_path}. Add a line: "
        f"SGO_API_KEY=your_key_here"
    )


# ---------------------------------------------------------------------------
# Step 1: fetch events, odds unfiltered
# ---------------------------------------------------------------------------

def fetch_events(api_key: str, max_events: int) -> list[dict]:
    url = f"{API_HOST}/v2/events"
    params = {
        "apiKey": api_key,
        "leagueID": LEAGUE_ID,
        "oddsAvailable": "true",
        "limit": max_events,
    }
    headers = {"x-api-key": api_key}
    resp = requests.get(url, params=params, headers=headers, timeout=30)

    print(f"HTTP {resp.status_code}. Response headers of note:")
    for h in resp.headers:
        if "rate" in h.lower() or "limit" in h.lower() or "usage" in h.lower() or "credit" in h.lower() or "object" in h.lower():
            print(f"  {h}: {resp.headers[h]}")

    resp.raise_for_status()
    payload = resp.json()

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]

    print("WARNING: unrecognized response shape. Top-level keys/type:")
    if isinstance(payload, dict):
        print(f"  dict with keys: {list(payload.keys())}")
    else:
        print(f"  type: {type(payload)}")
    return []


# ---------------------------------------------------------------------------
# Step 2: discover real statIDs from real odds objects
# ---------------------------------------------------------------------------

def iter_odds(event: dict):
    """Yield individual odd dicts from an event's `odds` field, handling
    it as either a dict-of-dicts (keyed by oddID, per the DFS-use-case
    doc's example) or a list -- shape not independently confirmed, so
    both are handled rather than assumed."""
    odds = event.get("odds")
    if isinstance(odds, dict):
        for odd_id, odd in odds.items():
            odd = dict(odd) if isinstance(odd, dict) else {"value": odd}
            odd.setdefault("oddID", odd_id)
            yield odd
    elif isinstance(odds, list):
        yield from odds


def discover_stat_coverage(events: list[dict]) -> dict:
    stat_event_count = defaultdict(int)
    stat_players = defaultdict(set)

    for event in events:
        stats_seen_this_event = set()
        for odd in iter_odds(event):
            stat_id = odd.get("statID")
            player_id = odd.get("playerID") or odd.get("statEntityID")
            if not stat_id:
                continue
            stats_seen_this_event.add(stat_id)
            if player_id:
                stat_players[stat_id].add(player_id)
        for s in stats_seen_this_event:
            stat_event_count[s] += 1

    return {
        "stat_event_count": dict(stat_event_count),
        "stat_players": {k: v for k, v in stat_players.items()},
    }


def keyword_matches(stat_id: str) -> list[str]:
    s = stat_id.lower()
    return [bucket for bucket, needles in KEYWORD_BUCKETS.items()
            if any(n in s for n in needles)]


# ---------------------------------------------------------------------------
# Step 3 (optional): salary-tier coverage cross-check -- same approach as
# probe_player_props.py, duplicated rather than imported (throwaway,
# different player-id join key: SGO playerIDs are NOT DK/FD names, so
# this does a best-effort match against a `players` lookup if the API
# response includes one; falls back to skipping the tier breakdown with
# a clear message if it doesn't, rather than guessing a broken match).
# ---------------------------------------------------------------------------

def load_salary_names(salary_csv: Path) -> list[tuple[str, float]]:
    rows = []
    with salary_csv.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        name_col = next((c for c in reader.fieldnames or []
                          if c.strip().lower() in ("name", "player", "nickname")), None)
        salary_col = next((c for c in reader.fieldnames or []
                            if "salary" in c.strip().lower()), None)
        if not name_col or not salary_col:
            raise ValueError(
                f"Couldn't find a name/salary column pair in {salary_csv}. "
                f"Columns found: {reader.fieldnames}"
            )
        for row in reader:
            try:
                rows.append((row[name_col].strip(), float(row[salary_col])))
            except (ValueError, KeyError):
                continue
    return rows


def build_player_name_lookup(events: list[dict]) -> dict:
    """SportsGameOdds' DFS doc shows a top-level `players` object resolving
    playerID -> real name/team. Not confirmed whether it's per-event or
    top-level-only in this response shape, so check both."""
    lookup = {}
    for event in events:
        players_obj = event.get("players")
        if isinstance(players_obj, dict):
            for pid, pdata in players_obj.items():
                name = pdata.get("name") if isinstance(pdata, dict) else None
                if name:
                    lookup[pid] = name
    return lookup


def salary_tier_coverage(salary_rows: list[tuple[str, float]],
                          covered_names_lower: set[str]) -> None:
    if not salary_rows:
        print("No salary rows loaded -- skipping tier breakdown.")
        return

    salaries = sorted(s for _, s in salary_rows)
    n = len(salaries)
    low_cutoff = salaries[n // 3]
    high_cutoff = salaries[(2 * n) // 3]

    tiers = {"low": [0, 0], "mid": [0, 0], "high": [0, 0]}
    for name, salary in salary_rows:
        tier = "low" if salary <= low_cutoff else ("mid" if salary <= high_cutoff else "high")
        tiers[tier][0] += 1
        if name.lower() in covered_names_lower:
            tiers[tier][1] += 1

    print("\nSalary-tier coverage (ANY discovered stat, exact-name match "
          "only -- no fuzzy matching in this throwaway probe):")
    for tier in ("low", "mid", "high"):
        total, covered = tiers[tier]
        pct = (covered / total * 100) if total else 0.0
        print(f"  {tier:>4} tier: {covered}/{total} players ({pct:.0f}%) "
              f"have at least one discovered stat")
    print("  NOTE: relies on the response including a resolvable "
          "players/name lookup -- if 'players resolved: 0' printed above, "
          "this breakdown is not meaningful and needs a different join "
          "strategy (e.g. matching on playerID against a roster file) "
          "before it can be trusted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-events", type=int, default=3,
                         help="Cap the number of events pulled -- also "
                              "caps real object spend under SGO's "
                              "per-event billing. Default: 3.")
    parser.add_argument("--salary-csv", type=Path, default=None,
                         help="Optional path to a DK/FD salary export CSV "
                              "for the salary-tier coverage breakdown.")
    args = parser.parse_args()

    try:
        api_key = load_sgo_api_key()
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    events = fetch_events(api_key, args.max_events)
    if not events:
        print("No events returned -- see the response-shape warning above "
              "if this is unexpected (e.g. off-season, no NFL events "
              "currently listed, or a response-shape mismatch this script "
              "didn't handle).")
        sys.exit(0)

    print(f"\nPulled {len(events)} event(s) -- {len(events)} object(s) "
          f"under SGO's per-event billing (confirm against the real "
          f"usage headers printed above, not just this count).")

    coverage = discover_stat_coverage(events)
    name_lookup = build_player_name_lookup(events)

    print(f"\n=== Real statID taxonomy discovered ({len(coverage['stat_event_count'])} unique statIDs) ===")
    print(f"{'statID':<32} {'events':<8} {'players':<9} {'keyword match'}")
    for stat_id in sorted(coverage["stat_event_count"]):
        ev_count = coverage["stat_event_count"][stat_id]
        players = coverage["stat_players"].get(stat_id, set())
        matches = keyword_matches(stat_id)
        print(f"{stat_id:<32} {ev_count:<8} {len(players):<9} {', '.join(matches) if matches else '-'}")

    print(f"\nPlayers resolved via response's own `players` lookup: {len(name_lookup)}")

    if args.salary_csv:
        try:
            salary_rows = load_salary_names(args.salary_csv)
            covered_names_lower = {n.lower() for n in name_lookup.values()}
            salary_tier_coverage(salary_rows, covered_names_lower)
        except (FileNotFoundError, ValueError) as e:
            print(f"\nWARNING: skipping salary-tier breakdown -- {e}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "probe_player_props_sgo_summary.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["statID", "events_with_stat", "unique_players", "keyword_match"])
        for stat_id in sorted(coverage["stat_event_count"]):
            writer.writerow([
                stat_id,
                coverage["stat_event_count"][stat_id],
                len(coverage["stat_players"].get(stat_id, set())),
                "|".join(keyword_matches(stat_id)),
            ])
    print(f"\nWrote statID summary to {out_path}")
