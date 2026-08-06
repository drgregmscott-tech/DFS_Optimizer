"""
probe_player_props.py
======================

Session 14.1 -- Player Props Scoping. THROWAWAY PROBE, not a permanent
pipeline script (matches this project's existing probe_*.py convention,
e.g. probe_reconcile_gap.py from Session 14.0b). Not wired into
refresh_data.yml or any other workflow.

Purpose: measure REAL market coverage and REAL credit cost from The Odds
API's player-props endpoint against a real upcoming NFL slate, before any
data-source or market-list decision is finalized. Per this project's
"pre-test before build" discipline -- the roadmap's cost/coverage numbers
(Session 14.1 scoping) are estimates from the provider's docs, not a real
pull. This script produces the real numbers.

Two-endpoint pull, matching The Odds API's own structure (Session 14.1
scoping note): game-level lines use the whole-sport /v4/sports/{sport}/odds
endpoint (see vegas_odds.py); player props require the PER-EVENT
/v4/sports/{sport}/events/{eventId}/odds endpoint instead, one call per
game. This script:
  1. Lists current events (free -- the /events endpoint does not consume
     quota per the provider's docs; confirmed live by this script's own
     credit-header logging, not assumed).
  2. Pulls player-props markets for each event (or a --max-events subset,
     to cap real credit burn during probing), tracking actual cost via the
     x-requests-used/x-requests-remaining/x-requests-last response headers
     (same pattern as vegas_odds.py's fetch_nfl_odds()).
  3. Reports, per market: how many events returned that market at all, and
     how many unique players had a line in it. A market can be "requested"
     but come back empty for an event with thin bookmaker coverage
     (expected to matter most for preseason -- see roadmap's flagged
     concern about early-season coverage being thinner).
  4. If --salary-csv is given, does a best-effort name-match against a
     site salary export (DK/FD format, same columns ingest_salaries.py
     already reads) to report coverage split by salary tier -- specifically
     whether low-salary/likely-cold-start players have ANY prop coverage,
     since that's the concrete open question from this session's design
     discussion (props are most useful exactly where they're least likely
     to be liquid).

Decision: SportsGameOdds is NOT probed by this script. Per "pre-test
before build," testing the source we already have an account for first
is cheaper than building two probes on spec. If this script's real
numbers show The Odds API's cost or coverage is unacceptable, build the
SportsGameOdds equivalent next -- don't build it preemptively.

Market list probed matches the roadmap's "Core" + "Worth adding" lists
from the Session 14.1 scoping card, decided so far:
  player_pass_yds, player_pass_tds, player_pass_interceptions,
  player_rush_yds, player_rush_tds,
  player_receptions, player_reception_yds, player_reception_tds,
  player_anytime_td,
  player_field_goals, player_kicking_points
"Secondary" markets (player_pass_attempts, player_rush_attempts) are
DELIBERATELY excluded from this probe -- the roadmap flagged these as
"worth testing... not worth the credit cost to include from day one."
Add them to MARKETS below if we later decide otherwise.

Usage:
  python3 probe_player_props.py --max-events 3
  python3 probe_player_props.py --max-events 3 --salary-csv data/dk_salaries.csv

Code-correctness sanity check (independent of NFL preseason coverage --
run against a sport with real live props right now, e.g. MLB):
  python3 probe_player_props.py --sport-key baseball_mlb --markets player_home_runs,player_hits,player_total_bases --max-events 3

--max-events caps REAL credit spend during probing. Cost is
[markets returned] x [regions] per event (provider's own formula, see
roadmap) -- with 11 markets x 1 region, that's up to 11 credits/event if
every market returns something, so --max-events 3 caps this single run
at <=33 credits against the 500/month free-tier budget. Omit --max-events
(or pass 0) to pull every currently-listed event -- don't do this without
checking the free-tier balance first.
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import requests

# Reuse the existing key-loading logic rather than duplicating it --
# same file, same config/api_keys.env, same ODDS_API_KEY entry vegas_odds.py
# already uses. No new setup step required.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vegas_odds import load_api_key  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

API_HOST = "https://api.the-odds-api.com"
REGIONS = "us"
ODDS_FORMAT = "american"

DEFAULT_SPORT_KEY = "americanfootball_nfl"
DEFAULT_MARKETS = [
    "player_pass_yds",
    "player_pass_tds",
    "player_pass_interceptions",
    "player_rush_yds",
    "player_rush_tds",
    "player_receptions",
    "player_reception_yds",
    "player_reception_tds",
    "player_anytime_td",
    "player_field_goals",
    "player_kicking_points",
]

# 2026-08-06 finding: probing real NFL preseason events returned zero
# coverage across every market, at zero credit cost -- traced to
# the-odds-api.com's own documented limitation ("Additional markets ...
# are not covered for NFL preseason since bookmakers usually have very
# limited coverage") rather than a plan/billing gate (that gate exists on
# a DIFFERENT, similarly-named competitor product, theoddsapi.com --
# confirmed NOT the vendor this project uses). --sport-key/--markets exist
# so the exact same probe logic can be pointed at a sport with real live
# props (e.g. MLB) as an independent code-correctness check, decoupled
# from the "is NFL preseason just thin" question.


# ---------------------------------------------------------------------------
# Step 1: list current events (expected free -- confirmed via headers below,
# not assumed from docs)
# ---------------------------------------------------------------------------

def fetch_events(api_key: str, sport_key: str) -> list[dict]:
    url = f"{API_HOST}/v4/sports/{sport_key}/events"
    params = {"apiKey": api_key}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()

    remaining = resp.headers.get("x-requests-remaining", "?")
    used = resp.headers.get("x-requests-used", "?")
    last_cost = resp.headers.get("x-requests-last", "?")
    print(f"[events list] quota -- used: {used}, remaining: {remaining}, "
          f"this call cost: {last_cost}")

    return resp.json()


# ---------------------------------------------------------------------------
# Step 2: pull player-props markets for one event
# ---------------------------------------------------------------------------

def fetch_event_props(api_key: str, sport_key: str, event_id: str, markets: list[str]) -> dict:
    url = f"{API_HOST}/v4/sports/{sport_key}/events/{event_id}/odds"
    params = {
        "apiKey": api_key,
        "regions": REGIONS,
        "markets": ",".join(markets),
        "oddsFormat": ODDS_FORMAT,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()

    remaining = resp.headers.get("x-requests-remaining", "?")
    used = resp.headers.get("x-requests-used", "?")
    last_cost = resp.headers.get("x-requests-last", "?")
    print(f"[event props] quota -- used: {used}, remaining: {remaining}, "
          f"this call cost: {last_cost}")

    return resp.json()


# ---------------------------------------------------------------------------
# Step 3: aggregate coverage across events
# ---------------------------------------------------------------------------

def summarize_coverage(events_props: list[dict]) -> dict:
    """Per market: how many events returned it at all, and the set of
    unique player names that had a line in it (across all events, all
    books)."""
    market_event_count = defaultdict(int)
    market_players = defaultdict(set)

    for event in events_props:
        markets_seen_this_event = set()
        for book in event.get("bookmakers", []):
            for market in book.get("markets", []):
                mkey = market["key"]
                markets_seen_this_event.add(mkey)
                for outcome in market.get("outcomes", []):
                    # Player-prop outcomes carry the player's name in
                    # "description" (Over/Under lines) -- "name" is
                    # Over/Under/Yes/No, not the player. Confirmed against
                    # this project's existing pattern of reading real API
                    # responses rather than assuming a schema (same
                    # discipline as vegas_odds.py's TEAM_NAME_MAP).
                    player = outcome.get("description")
                    if player:
                        market_players[mkey].add(player)
        for mkey in markets_seen_this_event:
            market_event_count[mkey] += 1

    return {
        "market_event_count": dict(market_event_count),
        "market_players": {k: sorted(v) for k, v in market_players.items()},
    }


# ---------------------------------------------------------------------------
# Step 4 (optional): salary-tier coverage cross-check
# ---------------------------------------------------------------------------

def load_salary_names(salary_csv: Path) -> list[tuple[str, float]]:
    """Best-effort read of a DK/FD salary export -- (name, salary) pairs.
    NOT using SITE_CONFIGS/ingest_salaries.py's full column-mapping logic
    here on purpose: this is a throwaway probe, not production ingest, and
    pulling in the full site-detection machinery is more coupling than a
    one-off coverage check needs. If this script gets promoted past
    probe status, switch to the real ingest_salaries.py functions instead
    of this simplified reader.
    """
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


def salary_tier_coverage(salary_rows: list[tuple[str, float]],
                          covered_players: set[str]) -> None:
    if not salary_rows:
        print("No salary rows loaded -- skipping tier breakdown.")
        return

    salaries = sorted(s for _, s in salary_rows)
    n = len(salaries)
    low_cutoff = salaries[n // 3]
    high_cutoff = salaries[(2 * n) // 3]

    tiers = {"low": [0, 0], "mid": [0, 0], "high": [0, 0]}  # [total, covered]
    covered_lower = {p.lower() for p in covered_players}

    for name, salary in salary_rows:
        tier = "low" if salary <= low_cutoff else ("mid" if salary <= high_cutoff else "high")
        tiers[tier][0] += 1
        if name.lower() in covered_lower:
            tiers[tier][1] += 1

    print("\nSalary-tier coverage (ANY probed market, exact-name match only "
          "-- no fuzzy matching in this throwaway probe):")
    for tier in ("low", "mid", "high"):
        total, covered = tiers[tier]
        pct = (covered / total * 100) if total else 0.0
        print(f"  {tier:>4} tier: {covered}/{total} players ({pct:.0f}%) "
              f"have a line in at least one probed market")
    print("  NOTE: exact-name matching will undercount real coverage "
          "(suffixes, nicknames, etc.) -- read this as a rough signal, not "
          "a precise number. If the low-tier percentage looks meaningfully "
          "low, that's real signal worth trusting; don't over-trust a "
          "small gap between tiers given the matching caveat.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-events", type=int, default=3,
                         help="Cap the number of events probed, to control "
                              "real credit spend. 0 = no cap (pulls every "
                              "currently-listed event -- check your "
                              "free-tier balance first). Default: 3.")
    parser.add_argument("--salary-csv", type=Path, default=None,
                         help="Optional path to a DK/FD salary export CSV. "
                              "If given, reports coverage broken out by "
                              "salary tier (low/mid/high thirds).")
    parser.add_argument("--sport-key", default=DEFAULT_SPORT_KEY,
                         help="The Odds API sport_key to probe. Default: "
                              f"{DEFAULT_SPORT_KEY}. Pass e.g. baseball_mlb "
                              "as an independent code-correctness check "
                              "against a sport with real live props right "
                              "now, decoupled from NFL-preseason coverage.")
    parser.add_argument("--markets", default=None,
                         help="Comma-separated market key override. If "
                              "omitted, uses the NFL default list baked "
                              "into this script. Required if --sport-key "
                              "is not NFL, since the default markets are "
                              "NFL-specific (e.g. for baseball_mlb try "
                              "player_home_runs,player_hits,player_total_bases).")
    args = parser.parse_args()

    markets = args.markets.split(",") if args.markets else DEFAULT_MARKETS
    if args.sport_key != DEFAULT_SPORT_KEY and not args.markets:
        print(f"ERROR: --sport-key {args.sport_key} needs an explicit "
              f"--markets list -- the built-in defaults are NFL-specific.",
              file=sys.stderr)
        sys.exit(1)

    try:
        api_key = load_api_key()
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    events = fetch_events(api_key, args.sport_key)
    if not events:
        print("No events currently listed (off-season, or no games in the "
              "current window). Nothing to probe.")
        sys.exit(0)

    if args.max_events:
        events = events[: args.max_events]

    print(f"\nProbing player props for {len(events)} event(s): "
          + ", ".join(f"{e['away_team']} @ {e['home_team']}" for e in events))

    events_props = []
    for event in events:
        print(f"\n-- {event['away_team']} @ {event['home_team']} "
              f"(event_id={event['id']}) --")
        try:
            props = fetch_event_props(api_key, args.sport_key, event["id"], markets)
        except requests.HTTPError as e:
            print(f"  ERROR fetching props for this event: {e}")
            continue
        events_props.append(props)

    summary = summarize_coverage(events_props)

    print("\n=== Market coverage summary ===")
    print(f"{'market':<28} {'events w/ market':<18} {'unique players'}")
    for mkey in markets:
        ev_count = summary["market_event_count"].get(mkey, 0)
        players = summary["market_players"].get(mkey, [])
        print(f"{mkey:<28} {ev_count:<18} {len(players)}")

    all_covered_players = set()
    for players in summary["market_players"].values():
        all_covered_players.update(players)
    print(f"\nTotal unique players with AT LEAST ONE probed market: "
          f"{len(all_covered_players)}")

    if args.salary_csv:
        try:
            salary_rows = load_salary_names(args.salary_csv)
            salary_tier_coverage(salary_rows, all_covered_players)
        except (FileNotFoundError, ValueError) as e:
            print(f"\nWARNING: skipping salary-tier breakdown -- {e}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "probe_player_props_summary.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["market", "events_with_market", "unique_players"])
        for mkey in markets:
            writer.writerow([
                mkey,
                summary["market_event_count"].get(mkey, 0),
                len(summary["market_players"].get(mkey, [])),
            ])
    print(f"\nWrote market summary to {out_path}")
