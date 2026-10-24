"""
cheat_sheet.py
==============

Weekly "top plays" cheat sheet -- a ranked, fixed-size list per position
(QB 5 / RB 10 / WR 15 / TE 5 / DST 5) for the main classic slate, each row
carrying a 1-10 confidence score, salary/projection/ownership for reference,
and a short plain-English rationale. This is a new artifact, not a rework
of anything existing -- see pivot_finder.py for the project's established
"same input file, different purpose" sibling script.

Ranking is NOT raw projection order. For each position group, every player
is z-scored (within that position's own pool, not across positions) on the
DFS game-theory factors that apply to it, then combined into one weighted
composite score:

  - value       final_projection / (salary/1000)
  - ceiling     statline_p90 (Monte Carlo 90th-percentile outcome)
  - floor       statline_p10 (Monte Carlo 10th-percentile outcome)
  - matchup     matchup_factor (already directionally correct per position
                -- see build_projections_statline.py's load_matchup_factors())
  - game_env    own team's implied_total for QB/RB/WR/TE; for DST, the
                OPPONENT's implied_total, inverted (a low-scoring spot for
                the opponent is the good environment for a defense) --
                looked up via a team -> implied_total map built from the
                full pool, since implied_total is constant per team
  - usage       QB: proj_pass_att. RB: proj_rush_att + proj_targets.
                WR/TE: proj_targets. DST: not applicable (omitted from
                DST's composite, weights renormalized accordingly).
  - leverage    zscore(final_projection) - zscore(estimated_ownership_pct)
                within the position pool -- a generalized version of
                pivot_finder.py's leverage_score (decision #6 there), but
                without that script's "candidate vs one specific cash
                player" framing: this just rewards being underowned
                relative to how good the projection is, full stop.

Weights are named constants below (FACTOR_WEIGHTS) so they're easy to see
and retune later -- not fitted to anything, just a reasonable starting
split where ceiling/floor get a little less weight than value/matchup/
game_env/usage/leverage since they're already correlated with value.

Confidence (1-10): the composite score is re-standardized (z-scored a
second time) against the FULL eligible pool for that position -- not just
the players who made the top-N cut -- so a "best available" player on a
genuinely flat/weak slate lands in the middle of the 1-10 scale instead of
being inflated to a 9-10 purely for being #1 that week. This is the
mechanism that makes a weak slate actually read as weak in the output,
without any separate slate-strength heuristic:

    confidence = clip(round(5 + composite_z * 1.5), 1, 10)

Rationale text is built deterministically from the same per-factor
z-scores -- no model call, just templated sentences picking the
2-3 highest-magnitude contributing factors for that player and filling in
the real numbers.

Only players with final_projection > 0 are eligible (status_check.py's
`apply` step zeroes OUT players in final_projections before this script
runs -- a zeroed/bye player is never a usable top play regardless of any
other signal, same filter pivot_finder.py already uses).

Usage:
    python3 scripts/cheat_sheet.py --site dk --slate-id dk_classic_wk7_main_25Oct2026
    python3 scripts/cheat_sheet.py --site fd --slate-id fd_classic_wk7_main_25Oct2026

Output:
    output/cheat_sheet_{site}_{slate_id}.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

DEFENSE_POSITION_LABELS = {"DST", "D", "DEF"}

# Fixed per-position list sizes -- user-specified, held constant regardless
# of slate strength (a weak slate shows up as low confidence numbers
# throughout the list, not a shorter list).
TOP_N_BY_POSITION = {"QB": 5, "RB": 10, "WR": 15, "TE": 5, "DST": 5}

# Starting weights -- see module docstring. ceiling/floor intentionally
# lighter since they're correlated with value; DST has no usage factor so
# its weights are renormalized (see composite_score()) rather than listed
# separately here.
FACTOR_WEIGHTS = {
    "value": 1.0,
    "ceiling": 0.75,
    "floor": 0.75,
    "matchup": 1.0,
    "game_env": 1.0,
    "usage": 1.0,
    "leverage": 1.0,
}

CONFIDENCE_CENTER = 5.0
CONFIDENCE_SCALE = 1.5


def canonical_position(pos: str) -> str:
    p = str(pos).strip().upper()
    return "DST" if p in DEFENSE_POSITION_LABELS else p


def load_final_projections(site: str, slate_id: str) -> pd.DataFrame:
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
        "statline_p90", "matchup_factor", "implied_total",
        "proj_pass_att", "proj_rush_att", "proj_targets",
    }
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path} is missing expected columns: {sorted(missing)}. "
            f"build_projections_statline.py's output schema may have "
            f"changed -- update this script's load_final_projections()."
        )
    df["position"] = df["position"].apply(canonical_position)
    return df[df["final_projection"] > 0].copy()


def zscore(series: pd.Series) -> pd.Series:
    """Mean-0/std-1 within whatever subset is passed in. A zero-variance
    pool (e.g. only one eligible player at a position) maps to all zeros
    rather than NaN/inf -- "no information to rank on" is a real, valid
    state, not a crash."""
    std = series.std(ddof=0)
    if not std or np.isnan(std):
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def usage_value(row: pd.Series) -> float:
    pos = row["position"]
    if pos == "QB":
        return row["proj_pass_att"]
    if pos == "RB":
        return row["proj_rush_att"] + row["proj_targets"]
    if pos in ("WR", "TE"):
        return row["proj_targets"]
    return np.nan  # DST -- no usage factor, see module docstring


def score_position_group(group: pd.DataFrame, team_implied_total: dict) -> pd.DataFrame:
    g = group.copy()
    pos = g["position"].iloc[0]

    g["_value_raw"] = g["final_projection"] / (g["salary"] / 1000.0)
    g["_ceiling_raw"] = g["statline_p90"]
    g["_floor_raw"] = g["statline_p10"]
    g["_matchup_raw"] = g["matchup_factor"]
    if pos == "DST":
        # Lower opponent implied total = better defensive environment --
        # negate so "higher z = better" holds the same direction as every
        # other factor.
        g["_game_env_raw"] = -g["opponent"].map(team_implied_total)
    else:
        g["_game_env_raw"] = g["implied_total"]
    g["_usage_raw"] = g.apply(usage_value, axis=1)
    g["_leverage_raw"] = zscore(g["final_projection"]) - zscore(g["estimated_ownership_pct"])

    factor_cols = {
        "value": "_value_raw", "ceiling": "_ceiling_raw", "floor": "_floor_raw",
        "matchup": "_matchup_raw", "game_env": "_game_env_raw", "usage": "_usage_raw",
    }
    weight_sum = pd.Series(0.0, index=g.index)
    composite = pd.Series(0.0, index=g.index)
    for factor, col in factor_cols.items():
        if g[col].isna().all():
            continue  # e.g. usage for DST -- excluded, not zero-filled
        z = zscore(g[col])
        w = FACTOR_WEIGHTS[factor]
        composite += w * z
        weight_sum += w
        g[f"_z_{factor}"] = z
    # leverage already an own-vs-ownership z-score, always applicable
    composite += FACTOR_WEIGHTS["leverage"] * g["_leverage_raw"]
    weight_sum += FACTOR_WEIGHTS["leverage"]
    g["_z_leverage"] = g["_leverage_raw"]

    g["composite_score"] = composite / weight_sum
    g["composite_z"] = zscore(g["composite_score"])
    g["confidence"] = (
        (CONFIDENCE_CENTER + g["composite_z"] * CONFIDENCE_SCALE)
        .round().clip(1, 10).astype(int)
    )
    return g


FACTOR_LABELS = {
    "value": "value",
    "ceiling": "ceiling",
    "floor": "floor",
    "matchup": "matchup",
    "game_env": "game environment",
    "usage": "usage",
    "leverage": "ownership leverage",
}


def factor_phrase(factor: str, row: pd.Series) -> str:
    pos = row["position"]
    if factor == "value":
        return f"strong value at {row['_value_raw']:.2f} pts per $1K"
    if factor == "ceiling":
        return f"real ceiling upside ({row['statline_p90']:.1f}-pt 90th-percentile outcome)"
    if factor == "floor":
        return f"a stable floor ({row['statline_p10']:.1f}-pt 10th-percentile outcome)"
    if factor == "matchup":
        return f"a favorable matchup ({row['matchup_factor']:.2f}x matchup factor)"
    if factor == "game_env":
        if pos == "DST":
            return f"a weak-scoring opposing offense ({row['opponent']}, {-row['_game_env_raw']:.1f}-pt implied total)"
        return f"a strong game environment ({row['implied_total']:.1f}-pt implied team total)"
    if factor == "usage":
        if pos == "QB":
            return f"heavy passing volume ({row['proj_pass_att']:.1f} projected attempts)"
        if pos == "RB":
            return f"a heavy workload ({row['_usage_raw']:.1f} projected touches)"
        return f"a strong target share ({row['proj_targets']:.1f} projected targets)"
    if factor == "leverage":
        direction = "underowned relative to projection" if row["_leverage_raw"] > 0 else "efficiently owned for the projection"
        return f"{direction} ({row['estimated_ownership_pct']:.1f}% projected ownership)"
    return factor


def build_rationale(row: pd.Series) -> tuple:
    z_cols = [c for c in row.index if str(c).startswith("_z_")]
    contributions = sorted(
        ((c[len("_z_"):], row[c] * FACTOR_WEIGHTS[c[len("_z_"):]]) for c in z_cols),
        key=lambda t: -t[1],
    )
    top = contributions[:3]
    phrases = [factor_phrase(factor, row) for factor, _ in top]
    rationale = ("; ".join(phrases) + ".")
    rationale = rationale[0].upper() + rationale[1:]
    top_factors = ", ".join(FACTOR_LABELS[f] for f, _ in top)
    return top_factors, rationale


OUTPUT_COLUMNS = [
    "position", "rank", "player_id", "player_name", "team", "opponent",
    "salary", "final_projection", "estimated_ownership_pct", "confidence",
    "composite_score", "top_factors", "rationale",
]


def build_cheat_sheet(site: str, slate_id: str) -> pd.DataFrame:
    df = load_final_projections(site, slate_id)
    team_implied_total = df.drop_duplicates("team").set_index("team")["implied_total"].to_dict()

    scored = []
    for pos, group in df.groupby("position"):
        if pos not in TOP_N_BY_POSITION:
            continue  # ignore anything outside the five tracked positions
        scored.append(score_position_group(group, team_implied_total))
    if not scored:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    scored_df = pd.concat(scored, ignore_index=True)

    rows = []
    for pos, top_n in TOP_N_BY_POSITION.items():
        pool = scored_df[scored_df["position"] == pos]
        if pool.empty:
            print(f"WARNING: no eligible {pos} players found for {site}/{slate_id} "
                  f"-- skipping (thin/empty slate for this position).", file=sys.stderr)
            continue
        if len(pool) < top_n:
            print(f"NOTE: only {len(pool)}/{top_n} eligible {pos} players found "
                  f"for {site}/{slate_id}.", file=sys.stderr)
        top = pool.sort_values("composite_score", ascending=False).head(top_n).reset_index(drop=True)
        for rank, (_, row) in enumerate(top.iterrows(), start=1):
            top_factors, rationale = build_rationale(row)
            rows.append({
                "position": pos,
                "rank": rank,
                "player_id": row["player_id"],
                "player_name": row["player_name"],
                "team": row["team"],
                "opponent": row["opponent"],
                "salary": row["salary"],
                "final_projection": row["final_projection"],
                "estimated_ownership_pct": row["estimated_ownership_pct"],
                "confidence": row["confidence"],
                "composite_score": row["composite_score"],
                "top_factors": top_factors,
                "rationale": rationale,
            })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--slate-id", type=str, required=True)
    args = parser.parse_args()

    sheet = build_cheat_sheet(args.site, args.slate_id)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"cheat_sheet_{args.site}_{args.slate_id}.csv"
    sheet.to_csv(out_path, index=False)

    print(f"Wrote {len(sheet)} cheat sheet row(s) to {out_path}")
    if not sheet.empty:
        for pos in TOP_N_BY_POSITION:
            pos_rows = sheet[sheet["position"] == pos]
            if not pos_rows.empty:
                print(f"  {pos}: {len(pos_rows)} rows, confidence range "
                      f"{pos_rows['confidence'].min()}-{pos_rows['confidence'].max()}")
