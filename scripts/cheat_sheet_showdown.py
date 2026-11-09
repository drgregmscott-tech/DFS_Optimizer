"""
cheat_sheet_showdown.py
========================

Showdown (single-game) sibling to cheat_sheet.py -- same goal (a ranked
"top plays" sheet with a short plain-English rationale per row), adapted
for how showdown actually gets decided. Separate module, not a mode flag
on cheat_sheet.py, following this project's established convention for
showdown-specific pipeline pieces (ownership_model_showdown.py vs
ownership_v2.py is the model for that -- a fully separate file, not a
branch inside the classic one).

Three real differences from the classic cheat sheet, each driven by how
showdown is actually played, not a stylistic choice:

1. THRESHOLD, NOT FIXED TOP-N PER POSITION.
   A showdown slate is ~12-16 skill players total across both teams, and
   CPT/FLEX decisions are inherently about ONE player's role, not "the WR
   position" as a bucket the way a 300-player classic slate supports a
   top-15-WRs cut. Position matters far less than it does in classic --
   this is really ONE unified priority list of every viable player on the
   slate (final_projection > PROJECTION_THRESHOLD, same "zeroed/bye player
   is never a usable play" filter classic's load_final_projections()
   uses), with both an overall priority rank and a per-position rank so
   it's still sortable/groupable by position for scanning.

   A showdown slate's final_projections file has TWO rows per physical
   player -- one `roster_role=CPT` (1.5x salary/scoring) and one
   `roster_role=FLEX` -- because they're genuinely different roster
   decisions with different salaries and point ceilings, not the same
   row twice. Ranking is done SEPARATELY within each roster_role (overall
   rank 1 among CPT candidates is a different question from overall rank 1
   among FLEX candidates), which is also why this script doesn't attempt
   the classic sheet's full value/leverage composite-score machinery --
   "priority rank" here is real `final_projection` (the number that
   already reflects CPT's 1.5x), the single most decision-relevant number
   for a captain/FLEX call, not a multi-factor z-scored blend the 1-2
   roster slots this covers don't need.

2. A REAL recent-usage bullet, not projection-derived.
   cheat_sheet.py's own docstring documents why `recent_form` (and by
   extension `season_avg`) in final_projections_*.csv is circular for this
   purpose -- build_projections_statline.py builds it FROM
   final_projection with the market factor divided back out, so quoting it
   back as "recent usage" is quoting the model's own output as if it were
   independent evidence. This script instead pulls ACTUAL last-N-game
   touches/targets straight from data/weekly_stats_{season}.parquet --
   the same raw source projections_matchup.py reads -- with the identical
   lookahead-bias guard (week N only uses weeks 1..N-1 of that season).

3. Depth-tier DVP detail for WR/TE, rush/rec split for RB.
   See projections_matchup_showdown.py (new sibling to
   projections_matchup.py) for how matchup_factors_showdown_{site}_
   {season}_{week}.csv is built -- WR1 vs WR2_3, TE1 vs TE2_3 (ranked by
   that GAME's own targets, not a season-long label), and RB rushing-
   points-allowed vs receiving-points-allowed (a stat-type split, not a
   depth split -- most teams only have one real every-down back most
   weeks, so RB1/RB2 would mostly be noise; rush-funnel vs pass-funnel-at-
   -the-RB is the real distinction a CPT/FLEX call on a receiving back
   needs). This slate's own CURRENT depth tier for each WR/TE is assigned
   by THIS WEEK's proj_targets rank among that player's active teammates
   at the same position (same "team_pos_rank" pattern cheat_sheet.py's
   Value Pick logic already uses) -- not last season's label, which can be
   stale the moment an injury or gameplan shift changes a team's target
   distribution. QB/DST/K fall back to the existing aggregate
   matchup_factors_{site}_{season}_{week}.csv / DST's own matchup_factor
   column, same as the classic sheet -- the depth-tier question doesn't
   apply to single-player-per-team positions, and showdown rosters commonly
   include a kicker, which has no DVP concept in this pipeline at all (that
   bullet is simply omitted for K).

Everything else carried over unchanged from the classic sheet's own
conventions: only final_projection > 0 (effectively > PROJECTION_THRESHOLD
here) players are eligible; floor/ceiling range bullet off statline_p10/
p90; game-environment bullet off implied_total relative to the slate's own
average.

Usage:
    python3 scripts/cheat_sheet_showdown.py --site dk --season 2026 --week 9 --slate-id dk_showdown_wk9_TB_CHI_08Nov2026

Output:
    output/cheat_sheet_showdown_{site}_{slate_id}.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"

DEFENSE_POSITION_LABELS = {"DST", "D", "DEF"}

# See module docstring point 1 -- threshold inclusion, not fixed top-N.
# A thin showdown slate shows up as a short list, which is real
# information, not padded out to a fixed size.
PROJECTION_THRESHOLD = 2.0

# Real recent-usage lookback -- last N games with box-score data strictly
# before the target week (same lookahead guard as projections_matchup.py).
RECENT_USAGE_LOOKBACK = 3

GAME_ENV_MARGIN = 2.0
MATCHUP_FAVORABLE = 1.10
MATCHUP_TOUGH = 0.90
ABS_FLOOR_HIGH_RISK = 3.0
ABS_FLOOR_LOW_RISK = 10.0

DEPTH_TIER_POSITIONS = {"WR", "TE"}
RB_SPLIT_POSITION = "RB"


def canonical_position(pos: str) -> str:
    p = str(pos).strip().upper()
    return "DST" if p in DEFENSE_POSITION_LABELS else p


def load_final_projections_showdown(site: str, slate_id: str) -> pd.DataFrame:
    path = OUTPUT_DIR / f"final_projections_{site}_{slate_id}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run build_projections_statline.py --site "
            f"{site} --slate-id {slate_id} first."
        )
    df = pd.read_csv(path, dtype={"player_id": str})
    required = {
        "player_id", "player_name", "position", "team", "opponent", "salary",
        "final_projection", "estimated_ownership_pct", "statline_p10",
        "statline_p90", "matchup_factor", "implied_total", "roster_role",
        "proj_pass_att", "proj_rush_att", "proj_targets",
    }
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path} is missing expected columns: {sorted(missing)}. This "
            f"script requires a showdown-format final_projections file "
            f"(roster_role column with CPT/FLEX rows)."
        )
    df["position"] = df["position"].apply(canonical_position)
    return df[df["final_projection"] > PROJECTION_THRESHOLD].copy()


def load_display_matchup_factors(site: str, season: int, week: int) -> dict:
    """Aggregate (not depth-tier) DVP, for QB only here -- see module
    docstring point 3. Same file/lookup classic cheat_sheet.py's
    load_display_matchup_factors() uses."""
    path = OUTPUT_DIR / f"matchup_factors_{site}_{season}_{week}.csv"
    if not path.exists():
        print(f"NOTE: {path} not found -- QB matchup bullets will read "
              f"neutral (1.0).", file=sys.stderr)
        return {}
    mf = pd.read_csv(path)
    return {(r["team"], r["position"]): r["matchup_factor"] for _, r in mf.iterrows()}


def load_depth_tier_matchup_factors(site: str, season: int, week: int) -> dict:
    """Depth-tier/split DVP for WR/TE/RB -- see projections_matchup_
    showdown.py. Keyed by (team, tier) where tier is one of WR1, WR2_3,
    TE1, TE2_3, RB_rush, RB_rec."""
    path = OUTPUT_DIR / f"matchup_factors_showdown_{site}_{season}_{week}.csv"
    if not path.exists():
        print(f"NOTE: {path} not found -- run projections_matchup_showdown.py "
              f"--site {site} --season {season} --week {week} first. WR/TE/RB "
              f"matchup bullets will read neutral (1.0).", file=sys.stderr)
        return {}
    mf = pd.read_csv(path)
    return {(r["team"], r["tier"]): r["matchup_factor"] for _, r in mf.iterrows()}


def load_recent_usage(season: int, week: int) -> dict:
    """Real last-N-game touches/targets straight off weekly_stats_
    {season}.parquet -- see module docstring point 2 for why this is NOT
    final_projections' own recent_form/season_avg. Same lookahead-bias
    guard as projections_matchup.py (week N uses weeks 1..N-1 of THIS
    season only -- no cross-season blending, matching that script's own
    scope). Returns {player_id: (avg_touches_per_game, n_games_used)};
    missing entirely (no games logged yet this season, or file absent)
    degrades to the caller's own "no usage history yet" bullet, same
    "flag, don't silently assume" pattern as the rest of this pipeline."""
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not path.exists():
        print(f"NOTE: {path} not found -- recent-usage bullets will read "
              f"'no usage history yet' for every player.", file=sys.stderr)
        return {}
    df = pd.read_parquet(path, engine="pyarrow")
    df = df[(df["season_type"] == "REG") & (df["week"] < week)]
    if df.empty:
        return {}
    df = df.sort_values(["player_id", "week"])

    def touches(row):
        pos = row["position"]
        if pos == "QB":
            return row["attempts"]
        if pos == "RB":
            return row["carries"] + row["targets"]
        if pos in ("WR", "TE"):
            return row["targets"]
        return np.nan

    df["_touches"] = df.apply(touches, axis=1)
    df = df.dropna(subset=["_touches"])
    result = {}
    for pid, g in df.groupby("player_id"):
        recent = g.tail(RECENT_USAGE_LOOKBACK)
        result[pid] = (float(recent["_touches"].mean()), len(recent))
    return result


def usage_word(pos: str) -> str:
    if pos == "QB":
        return "pass att/game"
    if pos == "RB":
        return "touches/game"
    return "targets/game"  # WR/TE


def recent_usage_bullet(row: pd.Series, usage_lookup: dict) -> str:
    entry = usage_lookup.get(row["player_id"])
    pos = row["position"]
    if pos not in ("QB", "RB", "WR", "TE"):
        return None
    if entry is None:
        return "Recent usage: no games logged yet this season"
    avg, n = entry
    game_word = "game" if n == 1 else "games"
    return f"Recent usage: {avg:.1f} {usage_word(pos)}, last {n} {game_word} (actual box score)"


def _tier_label(row: pd.Series, team_pos_rank: dict) -> str:
    """This SLATE's own depth tier for a WR/TE, by proj_targets rank among
    teammates at the same position -- see module docstring point 3."""
    pos = row["position"]
    if pos not in DEPTH_TIER_POSITIONS:
        return None
    rank = team_pos_rank.get(row["player_id"])
    return f"{pos}1" if rank == 1 else f"{pos}2_3"


def matchup_bullet(row: pd.Series, display_matchup: dict, depth_matchup: dict,
                    team_pos_rank: dict) -> str:
    pos = row["position"]
    if pos == "DST":
        mf = row["matchup_factor"]
        tier = "favorable" if mf >= MATCHUP_FAVORABLE else "tough" if mf <= MATCHUP_TOUGH else "average"
        return f"Matchup: {mf:.2f}x matchup factor ({tier})"
    if pos == "K":
        return None  # no DVP concept for kickers in this pipeline
    if pos == "QB":
        mf = display_matchup.get((row["opponent"], "QB"), 1.0)
        tier = "favorable" if mf >= MATCHUP_FAVORABLE else "tough" if mf <= MATCHUP_TOUGH else "average"
        return f"Matchup: {row['opponent']} allows {mf:.2f}x league-avg to QBs ({tier})"
    if pos in DEPTH_TIER_POSITIONS:
        depth_tier = _tier_label(row, team_pos_rank)
        mf = depth_matchup.get((row["opponent"], depth_tier), 1.0)
        tier = "favorable" if mf >= MATCHUP_FAVORABLE else "tough" if mf <= MATCHUP_TOUGH else "average"
        tier_display = depth_tier.replace("2_3", "2/3")
        return f"Matchup ({tier_display}): {row['opponent']} allows {mf:.2f}x league-avg ({tier})"
    if pos == RB_SPLIT_POSITION:
        mf_rush = depth_matchup.get((row["opponent"], "RB_rush"), 1.0)
        mf_rec = depth_matchup.get((row["opponent"], "RB_rec"), 1.0)
        rush_tier = "favorable" if mf_rush >= MATCHUP_FAVORABLE else "tough" if mf_rush <= MATCHUP_TOUGH else "average"
        rec_tier = "favorable" if mf_rec >= MATCHUP_FAVORABLE else "tough" if mf_rec <= MATCHUP_TOUGH else "average"
        return (f"Matchup: {row['opponent']} allows {mf_rush:.2f}x league-avg rushing pts "
                f"({rush_tier}), {mf_rec:.2f}x receiving pts ({rec_tier}) to RBs")
    return None


def env_bullet(row: pd.Series, avg_implied_total: float) -> str:
    team_total = row["implied_total"]
    if team_total >= avg_implied_total + GAME_ENV_MARGIN:
        tier = "plus"
    elif team_total <= avg_implied_total - GAME_ENV_MARGIN:
        tier = "low-scoring"
    else:
        tier = "middling"
    return f"Game environment: {row['team']} implied {team_total:.1f} ({tier})"


def range_bullet(row: pd.Series) -> str:
    p10, p90 = row["statline_p10"], row["statline_p90"]
    if row["position"] in ("DST", "K") and p10 == 0 and p90 == 0:
        return "Range: not modeled for this position"
    bust = (p90 - p10) / row["final_projection"] if row["final_projection"] else 0.0
    if p10 < ABS_FLOOR_HIGH_RISK or bust >= 1.0:
        tier = "high bust risk"
    elif p10 >= ABS_FLOOR_LOW_RISK and bust <= 0.4:
        tier = "low bust risk"
    else:
        tier = "normal swing"
    return f"Range: {p10:.1f}–{p90:.1f} pts ({tier})"


def build_rationale(row, avg_implied_total, display_matchup, depth_matchup,
                     team_pos_rank, usage_lookup) -> str:
    bullets = []
    mu = matchup_bullet(row, display_matchup, depth_matchup, team_pos_rank)
    if mu:
        bullets.append(mu)
    bullets.append(env_bullet(row, avg_implied_total))
    usage = recent_usage_bullet(row, usage_lookup)
    if usage:
        bullets.append(usage)
    bullets.append(range_bullet(row))
    return "\n".join(f"• {b}" for b in bullets)


OUTPUT_COLUMNS = [
    "roster_role", "position", "overall_rank", "position_rank",
    "player_id", "player_name", "team", "opponent", "salary",
    "final_projection", "estimated_ownership_pct", "rationale",
]


def build_cheat_sheet_showdown(site: str, slate_id: str, season: int, week: int) -> pd.DataFrame:
    df = load_final_projections_showdown(site, slate_id)
    if df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    team_implied_total = df.drop_duplicates("team").set_index("team")["implied_total"].to_dict()
    avg_implied_total = float(np.mean(list(team_implied_total.values())))

    display_matchup = load_display_matchup_factors(site, season, week)
    depth_matchup = load_depth_tier_matchup_factors(site, season, week)
    usage_lookup = load_recent_usage(season, week)

    # This slate's own current depth tier (WR1 vs WR2_3, TE1 vs TE2_3) by
    # proj_targets rank among teammates at the same position -- computed
    # once off the FLEX rows only (CPT rows are the same player at 1.5x,
    # which would double-count each player in the groupby otherwise).
    flex = df[df["roster_role"] == "FLEX"]
    depth_pool = flex[flex["position"].isin(DEPTH_TIER_POSITIONS)]
    team_pos_rank = (
        depth_pool.groupby(["team", "position"])["proj_targets"]
        .rank(ascending=False, method="first")
        .to_dict()
    )
    # .to_dict() above keys by the original index, not player_id -- rebuild
    # keyed by player_id instead.
    team_pos_rank = dict(zip(depth_pool["player_id"], team_pos_rank.values()))

    rows = []
    for role in ("CPT", "FLEX"):
        pool = df[df["roster_role"] == role].copy()
        if pool.empty:
            continue
        pool = pool.sort_values("final_projection", ascending=False).reset_index(drop=True)
        pool["overall_rank"] = range(1, len(pool) + 1)
        pool["position_rank"] = pool.groupby("position")["final_projection"] \
            .rank(ascending=False, method="first").astype(int)

        for _, row in pool.iterrows():
            rationale = build_rationale(row, avg_implied_total, display_matchup,
                                         depth_matchup, team_pos_rank, usage_lookup)
            rows.append({
                "roster_role": role,
                "position": row["position"],
                "overall_rank": int(row["overall_rank"]),
                "position_rank": int(row["position_rank"]),
                "player_id": row["player_id"],
                "player_name": row["player_name"],
                "team": row["team"],
                "opponent": row["opponent"],
                "salary": row["salary"],
                "final_projection": row["final_projection"],
                "estimated_ownership_pct": row["estimated_ownership_pct"],
                "rationale": rationale,
            })

    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate-id", type=str, required=True)
    args = parser.parse_args()

    sheet = build_cheat_sheet_showdown(args.site, args.slate_id, args.season, args.week)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"cheat_sheet_showdown_{args.site}_{args.slate_id}.csv"
    sheet.to_csv(out_path, index=False)

    print(f"Wrote {len(sheet)} cheat sheet row(s) to {out_path}")
    if not sheet.empty:
        for role in ("CPT", "FLEX"):
            role_rows = sheet[sheet["roster_role"] == role]
            if not role_rows.empty:
                print(f"  {role}: {len(role_rows)} rows across "
                      f"{role_rows['position'].nunique()} position(s)")
