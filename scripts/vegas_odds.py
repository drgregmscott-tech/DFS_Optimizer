"""
vegas_odds.py
=============

Session 2.3 -- Vegas Integration.

Pulls current NFL spread + total (over/under) lines from The Odds API and
converts them into per-team implied point totals, one row per team per
game.

Site-agnostic: implied team totals don't depend on DK vs FD, so this
script's output is shared by both sites' blend pipelines (Session 2.4).

Implied total formula:
  A team's own `point` value in the `spreads` market is already signed the
  standard way (negative = favorite, positive = underdog). Given that and
  the game's total (`totals` market, same number for both teams):

    team_implied_total = (total / 2) - (team_spread / 2)

  Example: total=48, home team spread=-6.5 (favored by 6.5):
    home_implied = 48/2 - (-6.5/2) = 24 + 3.25 = 27.25
    away_implied = 48/2 - ( 6.5/2) = 24 - 3.25 = 20.75
  27.25 + 20.75 = 48.0 -- implied totals always sum back to the game total,
  which is a cheap built-in sanity check used in validation below.

Consensus across books: the Odds API returns one spread/total per
bookmaker. Rather than pin the output to a single book (which could be an
outlier), this script averages the spread and total across every US-region
bookmaker returned for a game, then computes implied totals from the
averaged numbers. This is a design decision, not specified on the roadmap
card -- flagged here and in SESSION_LOG so it doesn't get silently
relitigated later.

IMPORTANT -- the API returns EVERY currently-listed upcoming game, not just
one slate's games. `--slate-id` only labels the output filename; it does not
filter which games are pulled. This means a single team can appear in
multiple rows (one per upcoming game it's part of) in the same output file.
The `opponent` and `commence_time` columns exist specifically so a
downstream consumer (e.g. Session 2.4's blend pipeline) can disambiguate
which row corresponds to the game it actually cares about, rather than
assuming one row per team.

Session 13.5-pause Bug Fix Session (decision #1, this file): was `--week`,
not `--slate-id`, through Session 13.5. That was a real, recurring problem
-- `--week` was never anything more than a filename label here (this
script always pulls "every currently live game" regardless of its value),
but downstream code borrowed the SAME week number used for historical
stats lookback (a legitimate, deliberate carryover -- see build_projections
.py decision #4/#19) to also key vegas lookups (not legitimate -- a
preseason/Madden-Sim/Thanksgiving/playoff slate has no real relationship
between "which past week's stats to borrow" and "which vegas file has this
slate's actual lines"). Concretely this caused an output/vegas_implied_
totals_23.csv left over from an unrelated earlier pull to get silently
reused for a real preseason Week 1 Showdown slate, because both happened
to reuse week=23 for stats-lookback purposes. Renamed to --slate-id to
match the salaries/projections files (Session 2.4's `final_projections_
{site}_{slate_id}.csv` fix, same reasoning), removing the NFL-week concept
from vegas entirely -- every slate now gets its own explicitly-named vegas
snapshot with no collision risk across different logical periods that
happen to share a week number.

Credit cost: 2 per call (spreads + totals markets, us region only). See
SESSION_LOG for the weekly polling cadence this was budgeted against.

Setup required before this script will run:
  1. Sign up for a free Odds API key at https://the-odds-api.com (Starter
     plan, 500 credits/month) -- this is a manual step, not automatable
     from here (account creation).
  2. Add `ODDS_API_KEY=your_key_here` to config/api_keys.env (gitignored,
     see Session 2.3's SESSION_LOG entry / README's Config section).

Usage:
  python3 vegas_odds.py --slate-id showdown_preseason_wk1_ari_car
"""

import argparse
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
OUTPUT_DIR = REPO_ROOT / "output"

API_HOST = "https://api.the-odds-api.com"
SPORT_KEY = "americanfootball_nfl"
REGIONS = "us"
MARKETS = "spreads,totals"
ODDS_FORMAT = "american"

# Full team name (as returned by The Odds API) -> nflverse team abbreviation
# (as used in weekly_stats_{season}.parquet's `team`/`opponent_team` columns,
# confirmed in Session 2.2's output -- notably `LA` not `LAR` for the Rams,
# and `WAS` not `WSH`).
TEAM_NAME_MAP = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}


# ---------------------------------------------------------------------------
# Step 0: API key
# ---------------------------------------------------------------------------

def load_api_key() -> str:
    """Read ODDS_API_KEY from config/api_keys.env.

    Deliberately not using python-dotenv (not in requirements.txt, and this
    is a one-line parse) -- consistent with the project's preference for
    small dependency-light utilities over adding a package for something
    this simple (same reasoning as nflverse_fetch.py replacing nfl_data_py).

    Reads with encoding="utf-8-sig" (Session 13.5-pause Bug Fix): a bare
    read on Windows silently glues a UTF-8 BOM onto the first line if the
    file was ever saved by an editor that adds one (Notepad does, by
    default) -- "\ufeffODDS_API_KEY" != "ODDS_API_KEY" fails the key-name
    match with no visible sign anything's wrong, since the key really is
    sitting right there in the file. utf-8-sig strips a BOM if present and
    is a no-op if not, so this is safe either way.
    """
    env_path = CONFIG_DIR / "api_keys.env"
    if not env_path.exists():
        raise FileNotFoundError(
            f"{env_path} not found. Sign up for a free key at "
            f"https://the-odds-api.com (Starter plan), then add a line "
            f"'ODDS_API_KEY=your_key_here' to {env_path}. "
            f"See SESSION_LOG.md, Session 2.3, for the full setup steps."
        )
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "ODDS_API_KEY":
            value = value.strip().strip('"').strip("'")
            if value:
                return value
    raise ValueError(
        f"ODDS_API_KEY not found in {env_path}. Add a line: "
        f"ODDS_API_KEY=your_key_here"
    )


# ---------------------------------------------------------------------------
# Step 1: Fetch odds
# ---------------------------------------------------------------------------

def fetch_nfl_odds(api_key: str) -> list[dict]:
    """Pull current NFL spreads + totals, US region, all books.

    Costs 2 usage credits per call (2 markets x 1 region). Prints the
    x-requests-remaining / x-requests-used response headers so actual
    quota burn is visible every run, not just estimated.
    """
    url = f"{API_HOST}/v4/sports/{SPORT_KEY}/odds"
    params = {
        "apiKey": api_key,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": ODDS_FORMAT,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()

    remaining = resp.headers.get("x-requests-remaining", "?")
    used = resp.headers.get("x-requests-used", "?")
    last_cost = resp.headers.get("x-requests-last", "?")
    print(f"Odds API quota -- used this cycle: {used}, remaining: {remaining}, "
          f"this call cost: {last_cost}")

    return resp.json()


# ---------------------------------------------------------------------------
# Step 2: Consensus spread/total per game, across all US books
# ---------------------------------------------------------------------------

def consensus_lines(game: dict) -> dict | None:
    """Average spread (per team) and total across all bookmakers in the
    response for one game. Returns None if a game has no usable spreads/
    totals data yet (common for games far out, before books post lines).
    """
    home_team = game["home_team"]
    away_team = game["away_team"]

    home_spreads, away_spreads, totals = [], [], []

    for book in game.get("bookmakers", []):
        for market in book.get("markets", []):
            if market["key"] == "spreads":
                for outcome in market["outcomes"]:
                    if outcome["name"] == home_team:
                        home_spreads.append(outcome["point"])
                    elif outcome["name"] == away_team:
                        away_spreads.append(outcome["point"])
            elif market["key"] == "totals":
                # totals outcomes are Over/Under, both carry the same point
                if market["outcomes"]:
                    totals.append(market["outcomes"][0]["point"])

    if not home_spreads or not away_spreads or not totals:
        return None

    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_spread": sum(home_spreads) / len(home_spreads),
        "away_spread": sum(away_spreads) / len(away_spreads),
        "total": sum(totals) / len(totals),
        "n_books": len(totals),
    }


# ---------------------------------------------------------------------------
# Step 3: Implied totals (now validates inline, per game, and tags each
# row with opponent + commence_time so duplicate team rows across multiple
# upcoming games are disambiguated downstream)
# ---------------------------------------------------------------------------

def build_implied_totals(games_json: list[dict]) -> list[dict]:
    rows = []
    skipped = []
    mismatches = []

    for game in games_json:
        lines = consensus_lines(game)
        if lines is None:
            skipped.append(f"{game['away_team']} @ {game['home_team']}")
            continue

        commence_time = game.get("commence_time", "")
        game_rows = []
        for team_key, spread_key, opp_key in (
            ("home_team", "home_spread", "away_team"),
            ("away_team", "away_spread", "home_team"),
        ):
            full_name = lines[team_key]
            abbrev = TEAM_NAME_MAP.get(full_name)
            if abbrev is None:
                raise KeyError(
                    f"Unmapped team name from Odds API: '{full_name}'. "
                    f"Add it to TEAM_NAME_MAP in this file."
                )
            opp_abbrev = TEAM_NAME_MAP.get(lines[opp_key])
            team_spread = lines[spread_key]
            implied = (lines["total"] / 2) - (team_spread / 2)
            game_rows.append({
                "team": abbrev,
                "opponent": opp_abbrev,
                "commence_time": commence_time,
                "spread": round(team_spread, 2),
                "over_under": round(lines["total"], 2),
                "implied_total": round(implied, 2),
            })

        # Validate THIS game's pair right here, while we still know for
        # certain which two rows belong together. Doing this later by
        # re-looking-up rows by team name breaks if a team appears in
        # more than one upcoming game (it did -- that was the bug).
        pair_sum = game_rows[0]["implied_total"] + game_rows[1]["implied_total"]
        expected = lines["total"]
        if abs(pair_sum - expected) > 0.02:
            mismatches.append(
                f"{game['away_team']} @ {game['home_team']}: sum={pair_sum}, expected={expected}"
            )

        rows.extend(game_rows)

    if skipped:
        print(f"Skipped {len(skipped)} game(s) with no posted spread/total yet: "
              f"{', '.join(skipped)}")

    if mismatches:
        print(f"WARNING: {len(mismatches)} game(s) failed the implied-total sum check "
              f"(this now indicates a REAL math problem, not a stale-lookup false positive):")
        for m in mismatches:
            print(f"  {m}")
    else:
        print("Sum-to-total check passed for all games.")

    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slate-id", required=True,
                         help="Slate identifier, used only in the output filename -- "
                              "same string passed to ingest_salaries.py/build_projections.py "
                              "for the slate this pull is for. Does not filter which games "
                              "are pulled (see module docstring); just names the file so "
                              "downstream code loads the right snapshot.")
    args = parser.parse_args()

    try:
        api_key = load_api_key()
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    games = fetch_nfl_odds(api_key)
    if not games:
        print("No games returned (off-season, or no games in the current window). "
              "Nothing to write.")
        sys.exit(0)

    rows = build_implied_totals(games)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"vegas_implied_totals_{args.slate_id}.csv"

    import csv
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["team", "opponent", "commence_time", "spread", "over_under", "implied_total"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} team rows ({len(rows)//2} games) to {out_path}")
