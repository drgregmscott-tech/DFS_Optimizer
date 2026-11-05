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
  - matchup     matchup_factor. NOTE (2026-11-03): build_projections_statline.py
                neutralizes this to a flat 1.0 for QB/RB/WR/TE project-wide
                (neutral_skill_matchup=True, since 2026-09-24 -- it measurably
                hurt projection accuracy; see that file's own comment). DST's
                factor is real and untouched. So for skill positions this
                composite factor currently contributes nothing to ranking --
                left in rather than removed because the decision is RESOLVED,
                not pending: re-checked 2026-10-26 and again 2026-11-03 with
                full 2021-25 history + 8 weeks of 2026 (analysis/
                proj_b1_revisit/RESULTS.md, local-only), verdict is still
                "keep neutralised" (full strength still hurts, best partial
                weight isn't worth the complexity, RB is still wrong-way).
                Nothing here needs to change unless a future re-check flips
                that call. Rationale text's matchup clause is DELIBERATELY a
                different, separate signal from this one -- see
                matchup_env_sentence() and load_display_matchup_factors()
                below.
  - game_env    own team's implied_total for QB/RB/WR/TE; for DST, the
                OPPONENT's implied_total, inverted (a low-scoring spot for
                the opponent is the good environment for a defense) --
                looked up via a team -> implied_total map built from the
                full pool, since implied_total is constant per team
  - usage       QB: proj_pass_att. RB: proj_rush_att + proj_targets.
                WR/TE: proj_targets. DST: not applicable (omitted from
                DST's composite, weights renormalized accordingly).

Ownership leverage (zscore(final_projection) - zscore(estimated_ownership_pct)
within the position pool) is deliberately EXCLUDED from the composite/
ranking -- see score_position_group()'s comment for the real-data finding
(Jordan Love, 2026-10-24) that drove this: leverage answers "is this
underowned?", not "is this good?", and blending the two penalizes a player
for being correctly popular, which buried an obviously-elite, deservedly-
chalky QB at rank 20/63. It's still computed and surfaced as its own
"Leverage Pick" badge in build_cheat_sheet() (the single best true
leverage play per position gets guaranteed visibility, same treatment as
Value Pick below) -- just never as a penalty on the main ranking.

Weights are named constants below (FACTOR_WEIGHTS) so they're easy to see
and retune later -- not fitted to anything, just a reasonable starting
split where ceiling/floor get a little less weight than value/matchup/
game_env/usage since they're already correlated with value.

Confidence (1-10): v1 re-standardized the composite score against the FULL
eligible position pool. That correctly keeps a weak slate's best player out
of the 9-10 band, but it also meant every row actually shown (already the
composite top-N by definition) clustered at 8-9 regardless of position --
real-data check on the Wk8 classic slate: mean 7.85, 90% of rows at 6-10,
nothing below 5. A confidence score that reads the same for almost every
play isn't telling the user anything, and -- the specific complaint that
drove this rework -- it reads as equally confident in a min-salary, no-floor
punt as it does in a $8K stud.

v2 re-standardizes within the cohort actually displayed for that position
(the composite top-N plus any Value/Leverage bonus rows), so the 1-10 scale
spreads across what the user is actually looking at instead of a nearly-flat
upper band. It also folds in a bust-risk penalty -- a player's own
(statline_p90 - statline_p10) / final_projection, z-scored the same way --
so a boom-or-bust cheap play no longer carries the same number as an
equally-ranked high-floor play; that's the direct fix for "false confidence"
on scrubby Value Pick rows (see the Value Pick comment in build_cheat_sheet()
below). A small slate-strength term (the #1 player's full-pool composite_z)
is kept so a stacked slate's best play can still outrank a thin slate's best
play, without letting that collapse the within-cohort spread back down:

    within_z = zscore(composite_z within displayed cohort)
    bust_z   = zscore(bust_raw within displayed cohort)
    combined = within_z * 1.5 - bust_z * 0.8 + slate_shift * 0.3
    confidence = clip(round(5.5 + combined), 1, 10)

See compute_confidence() for the real code; CONF_* constants below for the
weights (validated against the Wk8 classic slate -- see commit history, not
fitted to anything, same "reasonable starting split, easy to retune" spirit
as FACTOR_WEIGHTS).

Rationale text is built deterministically -- no model call. v2 (2026-11-03)
tried a fixed multi-sentence prose template; the user's reaction (2026-11-04)
was that it still read as "robotic... only minor differences in numbers"
even after a rewrite that varied sentence structure and wording per player
(see commit history for that attempt). Rather than keep tuning prose, v3
switched to the user's other offered option: plain bullet points of the raw
data, newline-separated (the frontend's .cheat-rationale CSS uses
white-space:pre-line so each bullet renders on its own line; the CSV field
itself just contains literal \n characters inside a quoted field, which both
pandas' writer and the frontend's parseCSV() handle correctly -- verified
before shipping). Every row gets exactly 4 bullets, same honest signals as
before: (1) matchup -- the real, un-neutralized defense-vs-position number
(see below), (2) game environment -- the team's (or for DST, the opponent's)
implied total, (3) history from dk_avg_ppg/games_played -- NOT season_avg/
recent_form, which build_projections_statline.py documents as the
projection with the market factor divided back out, i.e. circular with
final_projection, not an honest history signal, and (4) range -- the real
floor/ceiling spread, judged with an ABSOLUTE floor bar so a thin floor
never reads as "low risk" just because peers are worse (see ABS_FLOOR_*).
Value is still deliberately left out of the bullets (user feedback,
2026-11-03: the Value Pick badge already says "this is the cheap play").
See build_rationale() below.

Matchup clause, display-only (user decision, 2026-11-03): matchup_factor is
neutralized for QB/RB/WR/TE in the ranking composite (see above), but the
user still wants the rationale to state the real defense-vs-position signal
("does this defense actually give up a lot of points to this position") even
though it isn't currently trusted enough to rank on. load_display_matchup_
factors() reads the SAME output/matchup_factors_{site}_{season}_{week}.csv
build_projections.py's load_matchup_factors() reads -- the raw, un-
neutralized per-team/position ratio -- for text only. This is why cheat_
sheet.py now also takes --season/--week (previously derived nothing from
them): the file is keyed by season+week, not slate_id. DST is excluded from
this lookup (that file only covers QB/RB/WR/TE -- DST's own matchup_factor
column was never neutralized, so DST rows keep reading straight from
final_projections like before 2026-11-03).

Value Pick eligibility (user decision, 2026-11-03): previously "cheap half
of the position's salary pool + a nonzero projected role." Real-world
complaint: Corey Kiner (RB3 on his own team, 4.6 of his team's RB carries
vs. the actual lead back's 9.6) cleared that bar most weeks purely because
SOME volume was projected, not because he's a play anyone would realistically
trust. Now requires the single TOP usage-earner at this position on their
OWN team (by projected touches/targets among teammates who are actually
active this week) -- Gunnar Helm (clear TE1 on a thin-depth team) clears
this; Corey Kiner (clearly behind his own team's lead back) does not. See
the Value Pick block in build_cheat_sheet() for the real code and the
Carson Wentz/Amon-Ra lessons this replaces, not removes.

Only players with final_projection > 0 are eligible (status_check.py's
`apply` step zeroes OUT players in final_projections before this script
runs -- a zeroed/bye player is never a usable top play regardless of any
other signal, same filter pivot_finder.py already uses).

Usage:
    python3 scripts/cheat_sheet.py --site dk --season 2026 --week 8 --slate-id dk_classic_wk7_main_25Oct2026
    python3 scripts/cheat_sheet.py --site fd --season 2026 --week 8 --slate-id fd_classic_wk7_main_25Oct2026

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

# Confidence weights -- see module docstring "Confidence" section for the
# real-data reasoning (Wk8 classic slate clustering at 8-9 under v1).
CONF_CENTER = 5.5
CONF_WITHIN_WEIGHT = 1.5   # spread relative to the cohort actually shown
CONF_BUST_WEIGHT = 0.8     # penalty for a wide floor/ceiling spread
CONF_SLATE_WEIGHT = 0.3    # muted "weak slate reads weak" signal


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


def load_display_matchup_factors(site: str, season: int, week: int) -> dict:
    """The REAL (un-neutralized) per-team/position defense-vs-position ratio,
    for the rationale text only -- see module docstring "Matchup clause,
    display-only." Missing file degrades to "no real signal, show neutral"
    (same spirit as build_projections.py's own fillna(1.0)) rather than
    crashing the whole cheat sheet build over a display-only lookup."""
    path = OUTPUT_DIR / f"matchup_factors_{site}_{season}_{week}.csv"
    if not path.exists():
        print(f"NOTE: {path} not found -- rationale matchup clause will read "
              f"neutral (1.0) for every skill-position player.", file=sys.stderr)
        return {}
    mf = pd.read_csv(path)
    return {(r["team"], r["position"]): r["matchup_factor"] for _, r in mf.iterrows()}


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
    # Bust-risk proxy for confidence/rationale (not part of the ranking
    # composite): floor-to-ceiling spread relative to the player's own
    # projection, so a boom-or-bust cheap punt and a steady stud are
    # compared on the same relative scale rather than raw point spread.
    g["_bust_raw"] = (g["_ceiling_raw"] - g["_floor_raw"]) / g["final_projection"]
    g["_bust_z_full"] = zscore(g["_bust_raw"])
    # Rank 1 = the single leading usage-earner at this position on their OWN
    # team (among teammates active this week, since final_projection>0 is
    # already the whole pool here) -- used by the Value Pick selection below
    # to mean "a real role," not just "some nonzero projected touches." NaN
    # for DST (no usage_raw) is harmless -- DST's Value Pick logic doesn't
    # use this column.
    g["_team_pos_rank"] = g.groupby("team")["_usage_raw"].rank(ascending=False, method="first")

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
    # Leverage is deliberately EXCLUDED from the composite/ranking itself
    # (real-data finding, 2026-10-24): it answers "is this underowned?",
    # not "is this good?" -- those are different questions, and blending
    # them penalizes a player for being correctly popular. Confirmed on
    # real data: Jordan Love (top-3 or better on value/ceiling/floor/usage,
    # a 20.0-pt QB at 17.4% ownership -- the highest-owned QB on the slate,
    # i.e. deservedly chalky) had a _leverage_raw z of -4.1, the most
    # extreme value in the whole QB pool, which alone dragged him from a
    # clear top play down to rank 20/63 when leverage was still weighted
    # into the composite. Still computed and reported (_z_leverage,
    # rationale text) for its ONE real purpose -- surfacing the single
    # best true leverage play per position as a separate badge in
    # build_cheat_sheet(), never as a penalty on an otherwise-great play.
    g["_z_leverage"] = zscore(g["_leverage_raw"])

    g["composite_score"] = composite / weight_sum
    g["composite_z"] = zscore(g["composite_score"])
    # Confidence itself is computed later in build_cheat_sheet(), once the
    # displayed cohort (top-N + bonus rows) for this position is known --
    # see module docstring "Confidence" section for why.
    return g


def compute_confidence(displayed: pd.DataFrame, slate_shift: float) -> pd.Series:
    """1-10 confidence, re-standardized within the cohort actually shown
    for this position (not the full eligible pool -- see module docstring),
    with a bust-risk penalty and a muted slate-strength shift."""
    within_z = zscore(displayed["composite_z"])
    bust_z = zscore(displayed["_bust_raw"])
    combined = (
        within_z * CONF_WITHIN_WEIGHT
        - bust_z * CONF_BUST_WEIGHT
        + slate_shift * CONF_SLATE_WEIGHT
    )
    return (CONF_CENTER + combined).round().clip(1, 10).astype(int)


# Game-environment framing is relative to the slate's own average implied
# team total (passed in as avg_implied_total), not a fixed league-wide
# number -- a 24-pt implied total reads differently on a low-scoring slate
# than a shootout-heavy one.
GAME_ENV_MARGIN = 2.0
# Calibrated against the REAL (un-neutralized) matchup_factors_{site}_
# {season}_{week}.csv distribution, not the ranking composite's neutralized
# column -- that file's QB/RB/WR/TE spread is roughly std 0.10-0.20 (checked
# on the Wk8 file), wide enough that the 25th/75th percentile lands close to
# 0.90/1.10 across positions. The original 0.95/1.05 thresholds were
# calibrated against the composite column's much tighter pre-neutralization
# shape and flagged near-average performers (e.g. 0.95x) as "tough."
MATCHUP_FAVORABLE = 1.10
MATCHUP_TOUGH = 0.90
HISTORY_DIFF_MARGIN = 3.0
BUST_Z_HIGH = 0.75
BUST_Z_LOW = -0.75
# Absolute (not relative-to-pool) floor bars -- see bust_sentence() for why
# relative-only framing was wrong. A sub-3-pt floor is a real lineup killer
# for any offensive skill position regardless of how it compares to peers;
# "low risk" requires clearing a real double-digit cushion, not just being
# less bad than other scrubs.
ABS_FLOOR_HIGH_RISK = 3.0
ABS_FLOOR_LOW_RISK = 10.0


def _matchup_tier(mf: float) -> str:
    if mf >= MATCHUP_FAVORABLE:
        return "favorable"
    if mf <= MATCHUP_TOUGH:
        return "tough"
    return "average"


def matchup_bullet(row: pd.Series) -> str:
    # _display_matchup is the REAL defense-vs-position signal (how many
    # fantasy points the opponent has actually allowed to this position this
    # season, vs. league average) -- NOT the same column the ranking
    # composite uses, which is neutralized to 1.0 for QB/RB/WR/TE. See
    # module docstring "Matchup clause, display-only."
    mf = row["_display_matchup"]
    tier = _matchup_tier(mf)
    if row["position"] == "DST":
        return f"Matchup: {mf:.2f}x matchup factor ({tier})"
    return f"Matchup: {row['opponent']} allows {mf:.2f}x league-avg to {row['position']}s ({tier})"


def env_bullet(row: pd.Series, avg_implied_total: float) -> str:
    if row["position"] == "DST":
        opp_total = -row["_game_env_raw"]  # negated back to a real implied total
        if opp_total <= avg_implied_total - GAME_ENV_MARGIN:
            tier = "plus"
        elif opp_total >= avg_implied_total + GAME_ENV_MARGIN:
            tier = "tough"
        else:
            tier = "middling"
        return f"Game environment: opponent implied {opp_total:.1f} ({tier})"
    team_total = row["implied_total"]
    if team_total >= avg_implied_total + GAME_ENV_MARGIN:
        tier = "plus"
    elif team_total <= avg_implied_total - GAME_ENV_MARGIN:
        tier = "low-scoring"
    else:
        tier = "middling"
    return f"Game environment: {row['team']} implied {team_total:.1f} ({tier})"


def history_bullet(row: pd.Series):
    """Returns (bullet_text, has_history). Real season-to-date history
    (DK's/FD's own displayed avg pts/game) -- NOT season_avg/recent_form,
    which build_projections_statline.py documents as circular with
    final_projection, see module docstring. games_played isn't tracked for
    DST (offense-only stat upstream), so a DST with a valid dk_avg_ppg still
    gets a history bullet, just without a game count attached."""
    pos = row["position"]
    avg_ppg = row.get("dk_avg_ppg")
    games_played = row.get("games_played")
    games_played = 0 if pd.isna(games_played) else int(games_played)
    if pos != "DST" and games_played <= 0:
        return "History: no games logged yet this season", False
    if pos == "DST" and pd.isna(avg_ppg):
        return "History: no games logged yet this season", False
    diff = row["final_projection"] - avg_ppg
    if diff >= HISTORY_DIFF_MARGIN:
        trend = "projection running above average"
    elif diff <= -HISTORY_DIFF_MARGIN:
        trend = "projection running below average"
    else:
        trend = "in line with average"
    if pos == "DST":
        return f"History: {avg_ppg:.1f} pts/game season avg ({trend})", True
    game_word = "game" if games_played == 1 else "games"
    return f"History: {avg_ppg:.1f} pts/game season avg, {games_played} {game_word} ({trend})", True


def range_bullet(row: pd.Series) -> str:
    """Floor/ceiling spread, judged with an ABSOLUTE floor bar, not just
    relative-to-pool -- the direct fix for a cheap, boom-or-bust play
    reading as a safe one (user feedback, 2026-11-03: a 2.0-pt floor got
    called "low risk" purely because other scrubs were even worse). See
    ABS_FLOOR_* above."""
    p10, p90 = row["statline_p10"], row["statline_p90"]
    if row["position"] == "DST" and p10 == 0 and p90 == 0:
        # DST has no Monte Carlo floor/ceiling model upstream (statline_p10/
        # p90 are both a flat 0.0) -- printing "0.0 to 0.0 pts" would read as
        # "no variance," the opposite of the truth, so say so honestly
        # instead of a fabricated range.
        return "Range: not modeled for defense (a pick-six/safety can swing it well outside the base projection)"
    bust_z = row["_bust_z_full"]
    if p10 < ABS_FLOOR_HIGH_RISK or bust_z >= BUST_Z_HIGH:
        tier = "high bust risk"
    elif p10 >= ABS_FLOOR_LOW_RISK and bust_z <= BUST_Z_LOW:
        tier = "low bust risk"
    else:
        tier = "normal swing"
    return f"Range: {p10:.1f}–{p90:.1f} pts ({tier})"


def build_rationale(row: pd.Series, avg_implied_total: float) -> tuple:
    history_line, has_history = history_bullet(row)
    bullets = [
        matchup_bullet(row),
        env_bullet(row, avg_implied_total),
        history_line,
        range_bullet(row),
    ]
    rationale = "\n".join(f"• {b}" for b in bullets)
    top_factors = "matchup, game environment"
    if has_history:
        top_factors += ", history"
    top_factors += ", bust potential"
    return top_factors, rationale


OUTPUT_COLUMNS = [
    "position", "rank", "player_id", "player_name", "team", "opponent",
    "salary", "final_projection", "estimated_ownership_pct", "confidence",
    "composite_score", "top_factors", "rationale", "badge", "is_bonus",
]


def _build_row(pos: str, row: pd.Series, rank, is_bonus: bool, badge: str,
                confidence: int, avg_implied_total: float) -> dict:
    top_factors, rationale = build_rationale(row, avg_implied_total)
    return {
        "position": pos,
        "rank": rank,
        "player_id": row["player_id"],
        "player_name": row["player_name"],
        "team": row["team"],
        "opponent": row["opponent"],
        "salary": row["salary"],
        "final_projection": row["final_projection"],
        "estimated_ownership_pct": row["estimated_ownership_pct"],
        "confidence": confidence,
        "composite_score": row["composite_score"],
        "top_factors": top_factors,
        "rationale": rationale,
        "badge": badge,
        "is_bonus": is_bonus,
    }


def build_cheat_sheet(site: str, slate_id: str, season: int, week: int) -> pd.DataFrame:
    df = load_final_projections(site, slate_id)
    team_implied_total = df.drop_duplicates("team").set_index("team")["implied_total"].to_dict()
    avg_implied_total = float(np.mean(list(team_implied_total.values())))

    scored = []
    for pos, group in df.groupby("position"):
        if pos not in TOP_N_BY_POSITION:
            continue  # ignore anything outside the five tracked positions
        scored.append(score_position_group(group, team_implied_total))
    if not scored:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    scored_df = pd.concat(scored, ignore_index=True)

    # Display-only real DVP signal for the rationale text (see module
    # docstring) -- DST keeps reading its own (already real) matchup_factor
    # column since that file only covers QB/RB/WR/TE.
    display_matchup = load_display_matchup_factors(site, season, week)
    scored_df["_display_matchup"] = scored_df.apply(
        lambda r: r["matchup_factor"] if r["position"] == "DST"
        else display_matchup.get((r["opponent"], r["position"]), 1.0),
        axis=1,
    )

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
        top_ids = set(top["player_id"])

        # Guaranteed Value/Leverage slots (user decision, 2026-10-24): a
        # single global composite blend structurally favors players who
        # are strong across every factor at once -- a min-priced "best
        # bang-for-buck" play can almost never out-rank a $7-8K stud on
        # raw ceiling/floor/usage (absolute point totals, not per-dollar),
        # even when its pts-per-$1K value is the best on the slate. Rather
        # than reweighting the whole composite (which the user explicitly
        # didn't want -- it would distort every other pick too), the
        # single best Value play and single best Leverage play per
        # position are identified directly and guaranteed visibility: if
        # either already made the composite top-N, that row is just
        # badged; if not, it's appended as an extra "bonus" row (is_bonus
        # =True) past the normal top_n count, same pattern for both so a
        # thin/non-existent leverage standout doesn't silently mean a
        # thin/non-existent value standout either.
        # "Value Pick" means cheap-and-efficient in normal DFS usage, not
        # literally the single best pts-per-$1K in the pool -- an expensive
        # stud can win that ratio outright in a top-heavy week (confirmed
        # on real data: Amon-Ra St. Brown, $7800, had the single best WR
        # value ratio this slate), which isn't what anyone means by "value
        # play."
        #
        # v1 restricted to the cheaper half of the position's salary pool
        # with a nonzero projected role (_usage_raw > 0). That bar is too
        # low -- real-data complaint (user, 2026-11-03): Corey Kiner
        # ($4000 RB) cleared it most weeks purely because the model gave
        # him SOME volume, even though he was clearly his own team's RB3
        # (4.6 of the team's rush attempts vs. the actual lead back's 9.6)
        # -- "nobody is playing him," not a real value play no matter how
        # cheap. v1's bust-risk confidence penalty (compute_confidence())
        # correctly flagged the RISK, but didn't fix WHO got picked.
        #
        # v2 (first cut): Value Pick required being the single TOP
        # usage-earner at this position on their OWN team (_team_pos_rank
        # == 1, among teammates active this week) -- a real lead role, not
        # merely some projected touches -- with NO salary cap, on the
        # (wrong) assumption that the best-$/$1K team-lead would naturally
        # skew cheap. Real-data complaint (user, 2026-11-03): Zay Flowers
        # ($7200 WR) won that way -- he genuinely has the single best WR
        # $/$1K ratio among team-leads this slate (2.55, beating $4200
        # Wan'Dale Robinson's 2.39), but $7200 is a spend-up price, not a
        # value price. A stud with elite volume can out-value a cheap lead
        # on pure ratio in a top-heavy week -- same root pattern as the
        # original Amon-Ra lesson above, just one level deeper (restricting
        # to team-leads doesn't by itself restrict to cheap team-leads).
        #
        # v2 (fixed): adds a salary cap back, but against the team-leads'
        # OWN median salary, not the whole position pool's (checked: the
        # whole-pool median is usually below every real lead's salary,
        # since backups/committee pieces drag it down -- that's what made
        # v1's cheap-half-of-the-whole-pool rule zero out real finds like
        # Gunnar Helm's position). "Value" among leads means cheaper than a
        # TYPICAL lead, not cheaper than a typical player including bench
        # pieces. DST keeps the old cheap-half-of-the-position-pool rule
        # (depth chart/usage-rank has no DST equivalent). If NO team-lead
        # at this position is also cheap relative to other leads, there
        # just isn't a legitimate value play here this week -- no bonus row
        # is forced (same "an empty result is real information" philosophy
        # pivot_finder.py already uses for thin pivot pools).
        if pos == "DST":
            value_pool = pool[pool["salary"] <= pool["salary"].median()]
        else:
            leads = pool[(pool["_team_pos_rank"] == 1) & (pool["_usage_raw"] > 0)]
            value_pool = leads[leads["salary"] <= leads["salary"].median()] if not leads.empty else leads
        best_value_row = (
            value_pool.loc[value_pool["_z_value"].idxmax()] if not value_pool.empty else None
        )
        best_leverage_row = pool.loc[pool["_z_leverage"].idxmax()]
        badges_by_id = {}
        if best_value_row is not None:
            badges_by_id.setdefault(best_value_row["player_id"], []).append("Value Pick")
        badges_by_id.setdefault(best_leverage_row["player_id"], []).append("Leverage Pick")

        # Confidence is re-standardized within the cohort actually displayed
        # for this position (top-N + any bonus rows below), not the full
        # eligible pool -- see module docstring "Confidence" section.
        displayed_ids = set(top_ids)
        if best_value_row is not None:
            displayed_ids.add(best_value_row["player_id"])
        displayed_ids.add(best_leverage_row["player_id"])
        displayed = pool[pool["player_id"].isin(displayed_ids)].copy()
        slate_shift = float(top["composite_z"].iloc[0]) if not top.empty else 0.0
        conf_by_id = dict(zip(displayed["player_id"], compute_confidence(displayed, slate_shift)))

        for rank, (_, row) in enumerate(top.iterrows(), start=1):
            badge = ", ".join(badges_by_id.get(row["player_id"], []))
            rows.append(_build_row(pos, row, rank, False, badge,
                                    conf_by_id[row["player_id"]], avg_implied_total))

        bonus_rank = top_n + 1
        if best_value_row is None:
            print(f"NOTE: no eligible cheap/real-role value play found for {pos} "
                  f"on {site}/{slate_id} -- no Value Pick bonus row added.", file=sys.stderr)
        elif best_value_row["player_id"] not in top_ids:
            rows.append(_build_row(pos, best_value_row, bonus_rank, True, "Value Pick",
                                    conf_by_id[best_value_row["player_id"]], avg_implied_total))
            bonus_rank += 1
        best_value_id = best_value_row["player_id"] if best_value_row is not None else None
        if (best_leverage_row["player_id"] not in top_ids
                and best_leverage_row["player_id"] != best_value_id):
            rows.append(_build_row(pos, best_leverage_row, bonus_rank, True, "Leverage Pick",
                                    conf_by_id[best_leverage_row["player_id"]], avg_implied_total))

    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate-id", type=str, required=True)
    args = parser.parse_args()

    sheet = build_cheat_sheet(args.site, args.slate_id, args.season, args.week)

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
