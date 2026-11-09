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

v2 (2026-11-09, user feedback on the v1 build): three real changes from
the first cut, plus the three real differences from the classic sheet
that motivated this script in the first place.

v3 (2026-11-09, same day, user follow-up): asked for the real DK
Showdown cash line instead of a guess, then "not just value, but also
... fpts range and risk for busting, not just bad value = bust play."
See analysis/showdown_cash_line_2026-11-09/ for the research (16 real DK
Showdown contests -> empirical cash line ~102 pts / 2.04x pts-per-$1K,
confirming VALUE_BUST/BAD/FIRE's breakpoints; also checked whether the
model's own projections are plausible at all against that real number --
they are, see RESULTS.md's alignment section) and BUST_Z_HIGH/LOW's own
comment for why range_bullet() stays pool-relative rather than measured
directly against the cash line (tried that first; it's statistically
unsound -- a team TOTAL's bad-outcome percentile and an individual
player's bad-outcome percentile aren't the same kind of number, so the
comparison flagged nearly everyone regardless of real relative risk,
recreating the exact v1 problem this whole recalibration started from).

FRONTEND INTEGRATION (new in v2): the user expected this on the live
cheat-sheet panel the same way the classic sheet already is -- that panel
(dfs_optimizer_frontend/index.html's renderCheatSheet()) reads
output/cheat_sheet_{site}_{slate_id}.csv through a generic worker
endpoint keyed only on site+slate_id, with NO awareness of classic vs
showdown; it was never gated to classic, it just never had a showdown
file to find (classic's own automation step explicitly excludes
showdown slates -- "see .github/workflows/refresh_data.yml's own
"Rebuild cheat sheet" step comment). So v2 writes to that SAME filename
(no "_showdown" infix) and matches that renderer's exact expected column
set (rank, position, player_id, player_name, team, opponent, salary,
final_projection, estimated_ownership_pct, confidence, badge, is_bonus,
rationale) instead of inventing a showdown-specific schema -- this is
what makes the existing frontend render it with zero frontend changes.
The refresh_data.yml workflow gets a parallel "Rebuild showdown cheat
sheet" step (mirroring the classic one, gated the opposite way) so this
actually runs automatically each refresh, same as classic.

ONE ROW PER PLAYER, NOT PER ROSTER-SLOT (v2, user feedback: "I don't
necessarily need a captain vs flex difference"). A showdown final_
projections file has two rows per physical player (roster_role=CPT at
1.5x salary/scoring, roster_role=FLEX at 1x) -- v1 ranked these as two
separate lists. Real-data check: CPT's final_projection is EXACTLY 1.5x
FLEX's for every player (verified on the Wk9 BUF/MIN slate), so ranking
by either produces the identical order -- there was never a case where
CPT vs FLEX disagreed on priority, just two copies of the same ranking
with different-looking numbers. v2 builds the list once off each
player's FLEX row (the "base" per-player numbers this sheet's salary/
projection/ownership columns show), and folds the player's CPT-specific
numbers (own salary, own projection, own ownership -- captain ownership
in particular is NOT just 1.5x FLEX ownership; it's a separate rate
real-DFS-players choose independently, e.g. Josh Allen reads 24.4% CPT
owned vs 52.7% FLEX owned on the Wk9 slate) into a dedicated rationale
bullet instead of a second ranked list.

RECALIBRATED BUST-RISK (v2, user feedback: "literally every player is
marked high bust risk"). v1's range_bullet() reused the ABSOLUTE floor/
bust bars classic cheat_sheet.py calibrated against its OWN 300-player
classic pool (ABS_FLOOR_HIGH_RISK=3.0, bust ratio >= 1.0 reads "high").
Checked against the real Wk9 BUF/MIN showdown pool: EVERY eligible
player's bust ratio ((p90-p10)/final_projection) was >= 0.88, median
1.93 -- nearly double classic's "high risk" cutoff, for literally the
average play on the slate, not just the risky ones. This isn't a scoring
bug -- showdown's Monte Carlo model genuinely produces much wider
relative spread for every player (one game's variance concentrated onto
6 roster spots instead of spread across a 9-player classic lineup pulling
from the whole slate), so an absolute bar tuned to classic's shape
necessarily reads "high risk" for the entire showdown pool and
discriminates nothing. The fix is the same one classic ALREADY uses for
its own bust_z (see that script's compute_confidence()) -- z-score the
bust ratio and the floor WITHIN the showdown slate's own eligible pool
instead of against a borrowed absolute number, so "normal" and "low
risk" become reachable tiers again, judged against what showdown
actually looks like rather than classic. See BUST_Z_HIGH/LOW below.

Three real differences from the classic cheat sheet carried over from v1
(these were never the issue; see that version's design for the full
reasoning, condensed here):

1. THRESHOLD, NOT FIXED TOP-N PER POSITION (final_projection > 2.0) --
   one unified priority list (both an "overall_rank" column across the
   whole slate and a per-position "rank" column the frontend already
   knows how to group/sort on, same name as classic's own column).
2. A REAL recent-usage bullet off data/weekly_stats_{season}.parquet --
   NOT final_projections' circular recent_form/season_avg.
3. Depth-tier DVP detail for WR/TE (WR1 vs WR2_3, TE1 vs TE2_3, assigned
   by THIS slate's own proj_targets rank among teammates) and a rushing-
   vs-receiving split for RB, off projections_matchup_showdown.py.
   QB/DST/K fall back to the aggregate matchup_factors file / DST's own
   column; K gets no DVP bullet at all (no concept in this pipeline).

Usage:
    python3 scripts/cheat_sheet_showdown.py --site dk --season 2026 --week 9 --slate-id dk_showdown_wk9_BUF_MIN_09Nov2026

Output:
    output/cheat_sheet_{site}_{slate_id}.csv  (same filename classic uses --
    slate_id already encodes showdown vs classic, so there's no collision)
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
PROJECTION_THRESHOLD = 2.0
RECENT_USAGE_LOOKBACK = 3

GAME_ENV_MARGIN = 2.0
MATCHUP_FAVORABLE = 1.10
MATCHUP_TOUGH = 0.90

# Value-per-dollar tiers -- v4 (2026-11-09, same day, user follow-up:
# "if everyone's labeled as a bust then what's the point"). v3 applied
# the flat 1.5/1.75/2.25 breakpoints (confirmed against real field-
# percentile data -- see analysis/showdown_cash_line_2026-11-09/
# RESULTS.md) PER PLAYER. Checked the real BUF/MIN output: 10 of 18
# players read "bust," zero read "fire." That's not a scoring bug either
# -- it's the SAME root mistake range_bullet() already hit once this
# session, just in a different bullet: the 2.0x/2.25x breakpoints were
# validated as the ROSTER-AVERAGE ratio across all 6 spots that clears a
# real cash line, not a bar each individual player should independently
# clear. A $50K budget is deliberately uneven -- studs are priced at a
# premium (a BELOW-average ratio is the normal, correct cost of rostering
# a stud), and cheap complementary pieces have to run an ABOVE-average
# ratio to balance the budget back up to that ~2.0x roster average. An
# absolute per-player bar mislabels a well-priced, appropriately
# expensive stud as a "bust" just for being expensive -- exactly the
# "bad value != bust" distinction the user keeps raising, just showing
# up here instead of in the range bullet this time.
#
# Fix: value_bullet() is now POOL-RELATIVE (z-scored against tonight's
# own eligible pool, same pattern as BUST_Z_HIGH/LOW below), and the
# word "bust" is retired from this bullet entirely -- it's a price-vs-
# tonight's-market read ("cheap/fair/pricey for this slate"), not a risk
# judgment. "Bust risk" is now exclusively range_bullet()'s own High/
# Medium/Low label (see BUST_Z_HIGH/LOW) -- the two concepts no longer
# share a word. The real $50K-cap/2.0x-average context from the cash-
# line research is still real and still printed in __main__ as a slate-
# level reference, just never applied as a per-player absolute bar again.
VALUE_Z_HIGH = 0.75
VALUE_Z_LOW = -0.75

# Real empirical cash line, NOT a guess -- mean score at the top-25% cut
# across 16 real 2026 DK Showdown contests (field sizes 2,378-47,562; see
# analysis/showdown_cash_line_2026-11-09/compute_cash_line.py). Checked
# whether the slate's own game total or field size predicts this before
# accepting one flat number -- neither does (correlation ~0.05-0.09 with
# game total, ~-0.25 with field size), so a flat historical average is
# the right anchor. Surfaced in the __main__ summary print as a slate-
# level reference point, NOT used per-player -- see BUST_Z_HIGH/LOW's
# comment for why a per-player floor-vs-cash-line comparison doesn't
# actually work (team-total percentiles and individual percentiles
# aren't comparable).
CASH_LINE_PTS = 102.0

# Bust-risk (ceiling/floor spread), z-scored WITHIN this slate's own
# eligible pool -- same numeric cutoffs classic's own CONF_* machinery
# uses for the identical "high/low relative to cohort" judgment. Used
# for compute_confidence() AND range_bullet() below. As of v4, this is
# the ONLY place the words "bust"/"risk" appear -- range_bullet() now
# reports an explicit High/Medium/Low bust-risk label (the user's own
# wording) off these thresholds; value_bullet() dropped the word
# entirely (see VALUE_Z_HIGH/LOW above).
#
# v3 note (2026-11-09, user feedback: "not just value, but also ...
# fpts range and risk for busting, not just bad value = bust play"):
# tried comparing each player's own floor (statline_p10, his bad-10th-
# percentile outcome) against his salary-implied pro-rata share of the
# real $102 empirical cash line (CASH_LINE_PTS -- see that constant and
# analysis/showdown_cash_line_2026-11-09/). That recreated the EXACT
# problem this whole recalibration started from: it flagged nearly every
# player as "risky," for a structural statistical reason, not a scoring
# bug -- a 6-player TEAM TOTAL's 10th percentile sits much closer to its
# own median than any ONE player's individual 10th percentile does
# (summing several roughly-independent variables compresses the relative
# spread of the total, basic variance-of-a-sum behavior), so comparing
# one player's bad-tail outcome against a team-level MEDIAN-ish target
# was never a fair comparison -- it would flag almost everyone regardless
# of their real relative risk. Kept the pool-relative z-score instead
# (BUST_Z_HIGH/LOW below) -- a genuinely different signal from value
# (variance/swing shape, not cost-per-point), and the one that actually
# discriminates between players rather than flagging the whole pool.
BUST_Z_HIGH = 0.75
BUST_Z_LOW = -0.75

# Confidence weights -- same shape as classic's CONF_WITHIN_WEIGHT/
# CONF_BUST_WEIGHT (see that script's module docstring), no slate-
# strength term here (there's only one slate to compare against, so a
# cross-slate shift term has nothing to anchor to).
CONF_CENTER = 5.5
CONF_WITHIN_WEIGHT = 1.5
CONF_BUST_WEIGHT = 0.8

DEPTH_TIER_POSITIONS = {"WR", "TE"}
RB_SPLIT_POSITION = "RB"

OUTPUT_COLUMNS = [
    "position", "rank", "overall_rank", "player_id", "player_name", "team",
    "opponent", "salary", "final_projection", "estimated_ownership_pct",
    "confidence", "composite_score", "top_factors", "rationale", "badge",
    "is_bonus",
]


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
    return df


def load_display_matchup_factors(site: str, season: int, week: int) -> dict:
    path = OUTPUT_DIR / f"matchup_factors_{site}_{season}_{week}.csv"
    if not path.exists():
        print(f"NOTE: {path} not found -- QB matchup bullets will read "
              f"neutral (1.0).", file=sys.stderr)
        return {}
    mf = pd.read_csv(path)
    return {(r["team"], r["position"]): r["matchup_factor"] for _, r in mf.iterrows()}


def load_depth_tier_matchup_factors(site: str, season: int, week: int) -> dict:
    path = OUTPUT_DIR / f"matchup_factors_showdown_{site}_{season}_{week}.csv"
    if not path.exists():
        print(f"NOTE: {path} not found -- run projections_matchup_showdown.py "
              f"--site {site} --season {season} --week {week} first. WR/TE/RB "
              f"matchup bullets will read neutral (1.0).", file=sys.stderr)
        return {}
    mf = pd.read_csv(path)
    return {(r["team"], r["tier"]): r["matchup_factor"] for _, r in mf.iterrows()}


def load_recent_usage(season: int, week: int) -> dict:
    """See module docstring point 2 / v1's identical function for the full
    reasoning (unchanged in v2)."""
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


def recent_usage_bullet(row: pd.Series, usage_lookup: dict):
    entry = usage_lookup.get(row["player_id"])
    pos = row["position"]
    if pos not in ("QB", "RB", "WR", "TE"):
        return None
    if entry is None:
        return "Recent usage: no games logged yet this season"
    avg, n = entry
    game_word = "game" if n == 1 else "games"
    return f"Recent usage: {avg:.1f} {usage_word(pos)}, last {n} {game_word} (actual box score)"


def _tier_label(row: pd.Series, team_pos_rank: dict):
    pos = row["position"]
    if pos not in DEPTH_TIER_POSITIONS:
        return None
    rank = team_pos_rank.get(row["player_id"])
    return f"{pos}1" if rank == 1 else f"{pos}2_3"


def _tier_word(mf: float) -> str:
    return "favorable" if mf >= MATCHUP_FAVORABLE else "tough" if mf <= MATCHUP_TOUGH else "average"


def matchup_bullet(row: pd.Series, display_matchup: dict, depth_matchup: dict, team_pos_rank: dict):
    pos = row["position"]
    if pos == "DST":
        mf = row["matchup_factor"]
        return f"Matchup: {mf:.2f}x matchup factor ({_tier_word(mf)})"
    if pos == "K":
        return None
    if pos == "QB":
        mf = display_matchup.get((row["opponent"], "QB"), 1.0)
        return f"Matchup: {row['opponent']} allows {mf:.2f}x league-avg to QBs ({_tier_word(mf)})"
    if pos in DEPTH_TIER_POSITIONS:
        depth_tier = _tier_label(row, team_pos_rank)
        mf = depth_matchup.get((row["opponent"], depth_tier), 1.0)
        tier_display = depth_tier.replace("2_3", "2/3")
        return f"Matchup ({tier_display}): {row['opponent']} allows {mf:.2f}x league-avg ({_tier_word(mf)})"
    if pos == RB_SPLIT_POSITION:
        mf_rush = depth_matchup.get((row["opponent"], "RB_rush"), 1.0)
        mf_rec = depth_matchup.get((row["opponent"], "RB_rec"), 1.0)
        return (f"Matchup: {row['opponent']} allows {mf_rush:.2f}x league-avg rushing pts "
                f"({_tier_word(mf_rush)}), {mf_rec:.2f}x receiving pts ({_tier_word(mf_rec)}) to RBs")
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


def bust_risk_tier(bust_z: float) -> str:
    """The user's own words -- High/Medium/Low, not a vague "swing"
    adjective. See BUST_Z_HIGH/LOW above."""
    if bust_z >= BUST_Z_HIGH:
        return "High"
    if bust_z <= BUST_Z_LOW:
        return "Low"
    return "Medium"


def range_bullet(row: pd.Series) -> str:
    """v4 (2026-11-09) -- explicit High/Medium/Low bust-risk label (the
    user's own wording), off the pool-relative z-score (see
    BUST_Z_HIGH/LOW's comment for why this stays pool-relative rather
    than measured against the real empirical cash line directly). Also
    reports the floor's real point/percent shortfall off this player's
    own projection (concrete numbers, not a bare z-score). A genuinely
    different question from value_bullet()'s price tier -- "how much
    does his own bad outcome cost him specifically," not "is he priced
    fairly for tonight."""
    p10, p90, proj = row["statline_p10"], row["statline_p90"], row["final_projection"]
    if row["position"] in ("DST", "K") and p10 == 0 and p90 == 0:
        return "Range: not modeled for this position"
    floor_shortfall_pct = (proj - p10) / proj if proj else 0.0
    return (f"Range: {p10:.1f}–{p90:.1f} pts — floor is "
            f"{floor_shortfall_pct:.0%} below his own projection "
            f"(Bust risk: {bust_risk_tier(row['_bust_z'])})")


def value_tier(value_z: float) -> str:
    """v4 (2026-11-09, user feedback: "if everyone's labeled as a bust
    then what's the point") -- pool-relative, NOT the flat absolute
    1.5/1.75/2.25 bars v3 used. See VALUE_Z_HIGH/LOW's comment above for
    why an absolute per-player bar was wrong (it mislabels a well-priced,
    appropriately expensive stud as a "bust" just for being expensive --
    those breakpoints were validated as a ROSTER-AVERAGE target, not a
    per-player one). Deliberately drops the word "bust" -- that word now
    belongs only to bust_risk_tier() above, a different question."""
    if value_z >= VALUE_Z_HIGH:
        return "cheap for this slate"
    if value_z <= VALUE_Z_LOW:
        return "pricey for this slate"
    return "fair for this slate"


def value_bullet(row: pd.Series) -> str:
    """Pts-per-$1000-salary, tiered against tonight's own pool (see
    value_tier())."""
    ratio = row["final_projection"] / (row["salary"] / 1000.0)
    return f"Value: {ratio:.2f} pts/$1K ({value_tier(row['_value_z'])})"


def captain_bullet(row, cpt_row) -> str:
    """See module docstring 'ONE ROW PER PLAYER' -- captain-specific
    numbers folded in here instead of a second ranked list. cpt_row is
    None when a player has no matching CPT row (shouldn't normally
    happen, but degrades to a plain statement rather than a crash). Uses
    row["_value_z"] (the FLEX row's own pool-relative tier), not a
    separately computed one for the CPT row -- CPT's pts/$1K ratio is
    exactly 1.5x/1.5x = the same ratio as FLEX's (verified on real data),
    so there's nothing new to tier; only the displayed dollar numbers
    differ."""
    if cpt_row is None:
        return "Captain: no captain-slot data found for this player"
    cpt_ratio = cpt_row["final_projection"] / (cpt_row["salary"] / 1000.0)
    return (f"Captain: ${cpt_row['salary']:.0f} salary, "
            f"{cpt_row['final_projection']:.1f} pts, "
            f"{cpt_row['estimated_ownership_pct']:.1f}% owned as CPT "
            f"({cpt_ratio:.2f} pts/$1K, {value_tier(row['_value_z'])})")


def build_rationale(row, cpt_row, avg_implied_total, display_matchup, depth_matchup,
                     team_pos_rank, usage_lookup) -> str:
    bullets = []
    mu = matchup_bullet(row, display_matchup, depth_matchup, team_pos_rank)
    if mu:
        bullets.append(mu)
    bullets.append(env_bullet(row, avg_implied_total))
    usage = recent_usage_bullet(row, usage_lookup)
    if usage:
        bullets.append(usage)
    bullets.append(value_bullet(row))
    bullets.append(range_bullet(row))
    bullets.append(captain_bullet(row, cpt_row))
    return "\n".join(f"• {b}" for b in bullets)


def zscore(series: pd.Series) -> pd.Series:
    std = series.std(ddof=0)
    if not std or np.isnan(std):
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def compute_confidence(pool: pd.DataFrame) -> pd.Series:
    """Re-standardized within the slate's own eligible pool -- same
    within-cohort spirit as classic's compute_confidence(), no cross-
    slate shift term (see module docstring)."""
    within_z = zscore(pool["final_projection"])
    bust_z = pool["_bust_z"]
    combined = within_z * CONF_WITHIN_WEIGHT - bust_z * CONF_BUST_WEIGHT
    return (CONF_CENTER + combined).round().clip(1, 10).astype(int)


def build_cheat_sheet_showdown(site: str, slate_id: str, season: int, week: int) -> pd.DataFrame:
    df = load_final_projections_showdown(site, slate_id)
    flex = df[(df["roster_role"] == "FLEX") & (df["final_projection"] > PROJECTION_THRESHOLD)].copy()
    cpt_by_pid = {r["player_id"]: r for _, r in df[df["roster_role"] == "CPT"].iterrows()}
    if flex.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    team_implied_total = flex.drop_duplicates("team").set_index("team")["implied_total"].to_dict()
    avg_implied_total = float(np.mean(list(team_implied_total.values())))

    display_matchup = load_display_matchup_factors(site, season, week)
    depth_matchup = load_depth_tier_matchup_factors(site, season, week)
    usage_lookup = load_recent_usage(season, week)

    depth_pool = flex[flex["position"].isin(DEPTH_TIER_POSITIONS)]
    ranks = depth_pool.groupby(["team", "position"])["proj_targets"].rank(ascending=False, method="first")
    team_pos_rank = dict(zip(depth_pool["player_id"], ranks))

    # Pool-relative bust z-score (ceiling/floor spread, for confidence +
    # range_bullet's High/Medium/Low label) computed once across the
    # whole eligible pool (DST excluded -- its p10/p90 are a flat 0/0,
    # not a real spread to z-score). See BUST_Z_HIGH/LOW's comment for
    # why this stays pool-relative instead of measured against the real
    # cash line.
    scorable = flex[~((flex["position"] == "DST") & (flex["statline_p10"] == 0) & (flex["statline_p90"] == 0))].copy()
    scorable["_bust_raw"] = (scorable["statline_p90"] - scorable["statline_p10"]) / scorable["final_projection"]
    scorable["_bust_z"] = zscore(scorable["_bust_raw"])
    flex = flex.merge(scorable[["player_id", "_bust_raw", "_bust_z"]], on="player_id", how="left")
    flex["_bust_z"] = flex["_bust_z"].fillna(0.0)

    # Pool-relative value z-score (pts/$1K vs tonight's own pool, for
    # value_bullet()/captain_bullet()'s price tier) -- see VALUE_Z_HIGH/
    # LOW's comment for why this replaced the flat absolute bars.
    flex["_value_raw"] = flex["final_projection"] / (flex["salary"] / 1000.0)
    flex["_value_z"] = zscore(flex["_value_raw"])

    flex = flex.sort_values("final_projection", ascending=False).reset_index(drop=True)
    flex["overall_rank"] = range(1, len(flex) + 1)
    flex["rank"] = flex.groupby("position")["final_projection"].rank(ascending=False, method="first").astype(int)
    conf = compute_confidence(flex)

    rows = []
    for idx, row in flex.iterrows():
        cpt_row = cpt_by_pid.get(row["player_id"])
        rationale = build_rationale(row, cpt_row, avg_implied_total, display_matchup,
                                     depth_matchup, team_pos_rank, usage_lookup)
        rows.append({
            "position": row["position"],
            "rank": int(row["rank"]),
            "overall_rank": int(row["overall_rank"]),
            "player_id": row["player_id"],
            "player_name": row["player_name"],
            "team": row["team"],
            "opponent": row["opponent"],
            "salary": row["salary"],
            "final_projection": row["final_projection"],
            "estimated_ownership_pct": row["estimated_ownership_pct"],
            "confidence": int(conf.loc[idx]),
            "composite_score": row["final_projection"],
            "top_factors": "matchup, game environment, recent usage, value, bust potential",
            "rationale": rationale,
            "badge": "",
            "is_bonus": False,
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
    out_path = OUTPUT_DIR / f"cheat_sheet_{args.site}_{args.slate_id}.csv"
    sheet.to_csv(out_path, index=False)

    print(f"Wrote {len(sheet)} cheat sheet row(s) to {out_path}")
    print(f"Reference: real empirical DK Showdown cash line (top 25%) averages "
          f"{CASH_LINE_PTS:.0f} total roster pts across 16 real 2026 contests -- "
          f"see analysis/showdown_cash_line_2026-11-09/RESULTS.md")
    if not sheet.empty:
        for pos in sheet["position"].unique():
            pos_rows = sheet[sheet["position"] == pos]
            print(f"  {pos}: {len(pos_rows)} rows, confidence range "
                  f"{pos_rows['confidence'].min()}-{pos_rows['confidence'].max()}")
