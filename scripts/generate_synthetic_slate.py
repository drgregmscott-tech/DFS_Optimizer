"""
generate_synthetic_slate.py
============================

Session 4.3 addendum -- Synthetic slate generator.

Produces a RAW site-export-shaped salary CSV (the same shape as what you'd
get from DK/FD's own "Export to CSV" button) for testing when no real slate
export is available -- e.g. FD, which (per the user, this session) doesn't
run Madden Sim contests the way DK does, so DK's "download a real Madden
Sim export" path has no FD equivalent.

IMPORTANT SCOPE NOTE: this produces a RAW export-shaped file, meant to be
fed into the EXISTING, REAL ingest_salaries.py exactly like a real download
would be -- it does NOT bypass ingestion or hand-fabricate the post-ingest
salaries_{site}_{slate_id}.csv schema itself. Reasoning: ingest_salaries.py
already owns all of the real matching/normalization logic (player_id
lookup, defense handling, name normalization) -- duplicating that logic
here would create a second, separately-drifting copy of it. This script's
only job is to fabricate a plausible RAW input; the real pipeline does
everything downstream exactly as it would for real data.

Design decisions (same "flag, don't silently assume" pattern as every
other script in this project):

1. Player pool: real player names/teams/positions, pulled from the SAME
   build_player_reference() this project's own ingest_salaries.py uses
   (imported directly, not reimplemented) -- so every synthetic slate
   automatically matches a real player_id during ingestion, exactly like
   a real slate would. Only game info, salaries, and Vegas-adjacent
   numbers (implied totals/spreads consumed downstream) are fabricated.

2. Salaries: FLAGGED ARBITRARY. Assigned by position tier + uniform
   random noise within that tier, NOT fit to any real site pricing model
   or to real recent performance (this script deliberately does not read
   weekly_stats' fantasy-points columns for salary tiering, to avoid
   assuming a specific column name/shape that hasn't been verified against
   this repo's actual parquet schema -- see module docstring). Good enough
   to exercise the full pipeline (ingestion -> projections -> lineup ->
   pivot suggestions) end-to-end; NOT a substitute for real site pricing
   when actually evaluating pivot-suggestion quality.

3. Fake matchups: --num-games teams are randomly paired into synthetic
   "games" with a fabricated kickoff time (today + 1 day, staggered by
   game) and an explicit, clearly-fake game label so nothing here is
   mistakable for a real slate if the CSV is opened by hand.

4. Defenses: one synthetic DST/D row per team included in the slate,
   matching that site's own roster_slots requirement exactly (the
   intersection of roster_slots and defense_position_values -- NOT just
   any label present in defense_position_values, since that set exists to
   match multiple raw-export variants during ingestion, not to declare
   the canonical output label). FIX (found via a real Infeasible-solver
   run): an earlier version of this script guessed "D" for FD, but FD's
   roster_slots actually requires "DEF" -- a mismatched label meant FD's
   DEF roster slot had zero eligible players, making the optimizer
   structurally infeasible regardless of anything else in the pool.

5. Reproducibility: --seed (default 42, FLAGGED ARBITRARY) makes a given
   run reproducible for debugging; omit or vary it for a fresh random
   slate.

Usage:
python3 generate_synthetic_slate.py --site fd --season 2025 --num-games 4 --out DKSalaries_synthetic.csv
# then, exactly like a real download:
python3 ingest_salaries.py --site fd --raw DKSalaries_synthetic.csv --season 2025 --slate-id synthetic_08022026
"""

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import SITE_CONFIGS, build_player_reference

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

POSITIONS = ["QB", "RB", "WR", "TE"]

# FLAGGED ARBITRARY (decision #2) -- (min, max) salary band per position,
# roughly shaped like real DK/FD ranges but not fit to either site's real
# distribution. A future session with real slate data should replace this
# with an actual fit, same as every other "starting heuristic" in this repo.
SALARY_BANDS = {
    "QB": (5000, 8500),
    "RB": (3000, 9500),
    "WR": (3000, 9000),
    "TE": (2500, 7000),
    "DEF": (2500, 5000),
}

# How many of each position to include PER TEAM in the synthetic pool --
# enough for a full slate's worth of roster construction (2 RB/3 WR/1 FLEX
# starters per site need real depth, not just starters). FLAGGED ARBITRARY.
PLAYERS_PER_TEAM = {"QB": 2, "RB": 4, "WR": 5, "TE": 3}


def build_synthetic_slate(site: str, season: int, num_games: int, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    cfg = SITE_CONFIGS[site]

    weekly_stats_path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not weekly_stats_path.exists():
        raise FileNotFoundError(
            f"{weekly_stats_path} not found. Run nflverse_fetch.py --season "
            f"{season} first -- this script needs it for real player "
            f"names/teams/positions (decision #1), even though everything "
            f"else about the slate is fabricated."
        )
    reference = build_player_reference(weekly_stats_path)
    reference = reference[reference["position"].isin(POSITIONS)]

    teams = reference["team"].dropna().unique().tolist()
    if len(teams) < num_games * 2:
        raise SystemExit(
            f"Only {len(teams)} distinct teams found in {weekly_stats_path}, "
            f"need at least {num_games * 2} for {num_games} synthetic games. "
            f"Lower --num-games or check the parquet has full-season team "
            f"coverage."
        )
    rng.shuffle(teams)
    game_teams = teams[:num_games * 2]
    games = list(zip(game_teams[::2], game_teams[1::2]))

    kickoff_base = datetime.now() + timedelta(days=1)
    rows = []
    for gi, (team_a, team_b) in enumerate(games):
        kickoff = kickoff_base + timedelta(hours=gi)
        game_label = f"SYNTHETIC {team_a}@{team_b} {kickoff.strftime('%m/%d/%Y %I:%M%p')} ET"
        for team in (team_a, team_b):
            opp = team_b if team == team_a else team_a
            pool = reference[reference["team"] == team]
            for pos in POSITIONS:
                pos_pool = pool[pool["position"] == pos]
                n = min(PLAYERS_PER_TEAM[pos], len(pos_pool))
                if n == 0:
                    continue
                picks = pos_pool.sample(n=n, random_state=rng.randint(0, 2**31))
                for _, p in picks.iterrows():
                    lo, hi = SALARY_BANDS[pos]
                    salary = int(round(rng.uniform(lo, hi), -2))  # nearest $100
                    rows.append({
                        "_player_id": p["player_id"],
                        "_name": p["player_display_name"],
                        "_team": team,
                        "_opponent": opp,
                        "_position": pos,
                        "_salary": salary,
                        "_game_label": game_label,
                    })
            # One synthetic defense per team (decision #4). FIX (found this
            # session): def_pos must match the label optimizer.py's
            # roster_slots actually requires -- NOT just any label present
            # in defense_position_values (that set exists to MATCH multiple
            # raw-export variants during ingestion, e.g. FD's raw exports
            # sometimes say "D" and sometimes "DEF"; it was never meant as
            # the canonical output label). Deriving it as the intersection
            # of roster_slots and defense_position_values guarantees this
            # generator always writes whichever label the roster actually
            # asks for, instead of guessing -- the original "DST" if...else
            # "D" fallback happened to be right for DK (roster_slots really
            # does say "DST") but wrong for FD (roster_slots says "DEF",
            # not "D"), leaving FD's DEF slot with zero eligible players and
            # making the ILP structurally infeasible regardless of anything
            # else in the pool.
            def_candidates = [s for s in cfg["roster_slots"] if s in cfg["defense_position_values"]]
            if not def_candidates:
                raise SystemExit(
                    f"SITE_CONFIGS[{site!r}]['roster_slots'] has no entry "
                    f"matching SITE_CONFIGS[{site!r}]['defense_position_values'] "
                    f"{cfg['defense_position_values']} -- can't determine the "
                    f"correct synthetic defense position label. Check "
                    f"ingest_salaries.py's SITE_CONFIGS for a mismatch."
                )
            def_pos = def_candidates[0]
            lo, hi = SALARY_BANDS["DEF"]
            rows.append({
                "_player_id": None,
                "_name": f"{team} Defense",
                "_team": team,
                "_opponent": opp,
                "_position": def_pos,
                "_salary": int(round(rng.uniform(lo, hi), -2)),
                "_game_label": game_label,
            })

    return pd.DataFrame(rows)


def to_dk_raw(df: pd.DataFrame) -> pd.DataFrame:
    # Matches DK's real export shape (Position, Name + ID, Name, ID, Roster
    # Position, Salary, Game Info, TeamAbbrev, AvgPointsPerGame) -- fake IDs
    # are synthesized (real DK IDs aren't ours to invent) but everything
    # ingest_salaries.py's _load_dk_raw() actually requires is present.
    out = pd.DataFrame()
    out["Position"] = df["_position"]
    fake_ids = [100000 + i for i in range(len(df))]
    out["Name"] = df["_name"]
    out["Name + ID"] = out["Name"] + " (" + pd.Series(fake_ids).astype(str) + ")"
    out["ID"] = fake_ids
    out["Roster Position"] = df["_position"] + "/FLEX"
    out["Salary"] = df["_salary"]
    out["Game Info"] = df["_game_label"]
    out["TeamAbbrev"] = df["_team"]
    out["AvgPointsPerGame"] = 0.0  # FLAGGED ARBITRARY -- not used by ingest_salaries.py's required columns
    return out


def to_fd_raw(df: pd.DataFrame) -> pd.DataFrame:
    # Matches FD's documented (unverified, per ingest_salaries.py's own
    # caveat) export shape: Id, Position, First Name, Nickname, Last Name,
    # FPPG, Played, Salary, Game, Team, Opponent, Injury Indicator/Details.
    out = pd.DataFrame()
    fake_ids = [200000 + i for i in range(len(df))]
    out["Id"] = fake_ids
    out["Position"] = df["_position"]
    name_parts = df["_name"].str.split(" ", n=1, expand=True)
    out["First Name"] = name_parts[0]
    out["Last Name"] = name_parts[1].fillna("")
    out["Nickname"] = df["_name"]
    out["FPPG"] = 0.0  # FLAGGED ARBITRARY -- not used by ingest_salaries.py's required columns
    out["Played"] = ""
    out["Salary"] = df["_salary"]
    out["Game"] = df["_game_label"]
    out["Team"] = df["_team"]
    out["Opponent"] = df["_opponent"]
    out["Injury Indicator"] = ""
    out["Injury Details"] = ""
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True,
        help="nflverse season year to pull real player names/teams from (decision #1).")
    parser.add_argument("--num-games", type=int, default=4,
        help="Number of synthetic games (default 4, FLAGGED ARBITRARY).")
    parser.add_argument("--seed", type=int, default=42,
        help="Random seed for reproducibility (default 42, FLAGGED ARBITRARY).")
    parser.add_argument("--out", required=True,
        help="Output path for the RAW export-shaped CSV -- feed this into "
             "ingest_salaries.py --raw exactly like a real download.")
    args = parser.parse_args()

    slate = build_synthetic_slate(args.site, args.season, args.num_games, args.seed)
    raw = to_dk_raw(slate) if args.site == "dk" else to_fd_raw(slate)

    out_path = Path(args.out)
    raw.to_csv(out_path, index=False)
    print(f"Wrote {len(raw)} synthetic {SITE_CONFIGS[args.site]['label']} salary rows to {out_path}")
    print(f"NOTE: this is FABRICATED data (real players, fake salaries/games) -- "
          f"see module docstring decision #2 before using it for anything beyond "
          f"pipeline/UI testing.")
    print(f"Next: python3 ingest_salaries.py --site {args.site} --raw {out_path} "
          f"--season {args.season} --slate-id <your-slate-id>")
