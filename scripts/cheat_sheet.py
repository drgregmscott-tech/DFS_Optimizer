"""
cheat_sheet.py  (v3, 2026-11-16)
================================

Weekly "top plays" cheat sheet -- a ranked, fixed-size list per position
(QB 5 / RB 10 / WR 15 / TE 5 / DST 5) for the main classic slate, plus
Value / Leverage / Value Candidate bonus rows, each row carrying a 1-10
confidence score, salary/projection/ownership for reference, and a short
plain-English rationale (newline-separated bullets). It is a data-grounded
GUIDE, not a validation or a prediction: every word in a bullet is meant to
match the number behind it. Design: analysis/cheat_sheet_v3/SPEC.md.

Composite score (unchanged from v2). For each position group every player is
z-scored within that position's own pool on the DFS game-theory factors that
apply to it and combined with FACTOR_WEIGHTS:

  - value       final_projection / (salary/1000)
  - ceiling     statline_p90 (Monte Carlo 90th-percentile outcome)
  - floor       statline_p10 (Monte Carlo 10th-percentile outcome)
  - matchup     matchup_factor. NOTE (2026-11-03): build_projections_statline.py
                neutralizes this to a flat 1.0 for QB/RB/WR/TE project-wide
                (neutral_skill_matchup=True; it measurably hurt projection
                accuracy; re-checked 2026-10-26 and 2026-11-03, verdict "keep
                neutralised"). DST's factor is real. So for skill positions
                this contributes nothing to the composite. The rationale's
                matchup bullet is a DIFFERENT, display-only signal -- see
                load_display_matchup_factors().
  - game_env    own team's implied_total for QB/RB/WR/TE; for DST, the
                OPPONENT's implied_total, inverted
  - usage       QB: proj_pass_att. RB: proj_rush_att + proj_targets.
                WR/TE: proj_targets. DST: not applicable (weights renormalized)

Ownership leverage (zscore(projection) - zscore(ownership)) is deliberately
EXCLUDED from the composite (real-data finding 2026-10-24, Jordan Love: it
answers "is this underowned?", not "is this good?"). It still drives the
"Leverage Pick" badge.

v3 changes (owner request, 2026-11-16)
--------------------------------------
1. Matchup words: 5 tiers on fixed cutoffs (smash spot / favorable / neutral /
   below average / tough), separate cutoffs for DST's own matchup_factor.
2. Game environment: 5 tiers (elite / plus / middling / low-scoring /
   bottom-tier; DST on the opponent's total: elite / plus / middling / tough /
   brutal), with game total and spread printed next to the implied total.
3. Range / bust risk no longer comes from the simulated floor (which is a
   fixed fraction of the projection, so it just encodes price/projection
   level). Skill positions get a Role Security score (0-100) from projected
   volume, team share, recent snap %, and stability flags (games played,
   missed time, usage trend, injury step-up dependence, questionable tag),
   and a bust-risk tier from that plus how often the player has actually
   dudded this season (a game under half his own season average). No salary
   term anywhere. Two bullets: "Usage" and "Range".
4. DST gets an "Upside setup" bullet (game environment, spread, game total,
   opposing sack rate and QB INT rate, rookie/low-sample QB, opposing skill
   injuries, weather) and a basic range of projection +/- the DST model's
   held-out typical miss, with the pick-six/safety caveat kept.
5. The "Builds" bullet (share of the user's built lineups) was removed
   2026-11-16 at the owner's request. (Value Candidate rows from the Wk9 Item
   A redesign are kept: top-5 raw $/pt RB/WR/TE not already shown.)
6. Confidence is an absolute quality score Q (see compute_quality()):
   composite strength percentile within the startable pool, role security
   (or DST setup), game environment, matchup, history -- fixed anchors, not
   re-standardized per slate. The main list is ranked by Q and gated on role
   security so a fragile role cannot hold a "top play" slot, and bonus rows
   use the same Q, so confidence never rises as you read down the list.
7. New badges appended to the existing badge string: Solid Value, Boom/Bust
   Dart, Fragile Chalk.

Value Pick eligibility (user decision, 2026-11-03, unchanged): the single top
usage-earner at the position on their OWN team, cheaper than the median
team-lead salary (Corey Kiner / Zay Flowers lessons). DST keeps the
cheap-half-of-the-position-pool rule. Only players with final_projection > 0
are eligible (status_check.py zeroes OUT players).

Usage:
    python3 scripts/cheat_sheet.py --site dk --season 2026 --week 8 --slate-id dk_classic_wk7_main_25Oct2026
    python3 scripts/cheat_sheet.py --site fd --season 2026 --week 8 --slate-id fd_classic_wk7_main_25Oct2026

Output:
    output/cheat_sheet_{site}_{slate_id}.csv
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
DATA_DIR = REPO_ROOT / "data"

DEFENSE_POSITION_LABELS = {"DST", "D", "DEF"}

# Fixed per-position list sizes -- user-specified, held constant regardless
# of slate strength.
TOP_N_BY_POSITION = {"QB": 5, "RB": 10, "WR": 15, "TE": 5, "DST": 5}

FACTOR_WEIGHTS = {
    "value": 1.0,
    "ceiling": 0.75,
    "floor": 0.75,
    "matchup": 1.0,
    "game_env": 1.0,
    "usage": 1.0,
    "leverage": 1.0,
}

# Value Candidate rows (Wk9 Item A): RB/WR/TE only, top 5 by raw $/pt not
# already displayed.
VALUE_CANDIDATE_POSITIONS = {"RB", "WR", "TE"}
VALUE_CANDIDATE_TOP_N = 5

# ---- matchup tiers (SPEC A) -------------------------------------------------
MATCHUP_CUTS = [(1.15, "smash spot"), (1.05, "favorable"), (0.95, "neutral"), (0.85, "below average")]
DST_MATCHUP_CUTS = [(1.30, "smash spot"), (1.10, "favorable"), (0.90, "neutral"), (0.75, "below average")]

# ---- game environment tiers (SPEC B) ----------------------------------------
# Relative to the slate's own mean implied team total.
GAME_ENV_MARGIN = 2.0
GAME_ENV_STRONG = 5.0
ENV_NAMES_SKILL = ["elite", "plus", "middling", "low-scoring", "bottom-tier"]
ENV_NAMES_DST = ["elite", "plus", "middling", "tough", "brutal"]
SPREAD_PICKEM = 0.5

HISTORY_DIFF_MARGIN = 3.0

# ---- role security (SPEC C3) ------------------------------------------------
VOL_BARS = {"QB": (28.0, 36.0), "RB": (8.0, 18.0), "WR": (4.0, 8.5), "TE": (3.8, 7.8)}
SHARE_BARS = {"RB": (0.30, 0.75), "WR": (0.12, 0.26), "TE": (0.12, 0.24)}
SNAP_BARS = {"QB": (0.50, 0.95), "RB": (0.35, 0.75), "WR": (0.55, 0.85), "TE": (0.55, 0.85)}
W_VOL, W_SHARE, W_SNAP, W_STAB = 0.30, 0.20, 0.20, 0.30
RS_TIERS = [(85.0, "locked-in role"), (65.0, "solid role"), (45.0, "partial role")]  # else fragile
STEPUP_UNPROVEN_FRAC = 0.25
STEPUP_COUNT_FRAC = 0.10

# ---- bust-risk tier (SPEC C4) -----------------------------------------------
W_RS_IN_RISK, W_CONS_IN_RISK = 0.65, 0.35
DUD_FRAC = 0.5          # a "dud" is a game under half the player's own season average
DUD_SHRINK_K = 4
DUD_RATE_FLOOR_CAP = 0.5
RISK_TIERS = [(30.0, "low bust risk"), (42.0, "moderate bust risk"), (55.0, "elevated bust risk")]  # else high
DEFAULT_POS_DUD_RATE = {"QB": 0.066, "RB": 0.206, "WR": 0.225, "TE": 0.277}

# ---- confidence / membership (SPEC F, G) ------------------------------------
STARTABLE_MIN_PROJ = {"QB": 12.0, "RB": 5.0, "WR": 5.0, "TE": 4.0, "DST": 0.0}
CONF_W_STRENGTH = 0.45
CONF_W_ROLE = 0.35
CONF_W_ENV = 0.08
CONF_W_MATCHUP = 0.05    # display matchup is deliberately not trusted for ranking; 0 removes it
CONF_W_HISTORY = 0.07
CONF_Q_LO, CONF_Q_HI = 0.40, 1.00
RS_MAIN_LIST_MIN = 45.0  # 0 disables the role gate on the main list
ENV_SCORE = {"elite": 1.0, "plus": 0.75, "middling": 0.5, "low-scoring": 0.25, "tough": 0.25,
             "bottom-tier": 0.0, "brutal": 0.0}
MATCHUP_SCORE = {"smash spot": 1.0, "favorable": 0.75, "neutral": 0.5, "below average": 0.25, "tough": 0.0}

# ---- risk badges (SPEC G3) --------------------------------------------------
SOLID_VALUE_MIN_RS = 65.0
DART_MAX_RS = 45.0
FRAGILE_CHALK_OWN = 15.0
FRAGILE_CHALK_RS = 65.0

# ---- DST setup (SPEC D) -----------------------------------------------------
DST_TYPICAL_MISS = 4.3   # fallback; real value read from data/dst_recal_v2.json
DST_SETUP_TIERS = [(4, "strong"), (2, "good"), (0, "neutral")]  # else poor
SACK_HIGH_MULT, SACK_LOW_MULT = 1.12, 0.87
INT_HIGH_MULT, INT_LOW_MULT = 0.97, 0.77
DROPBACKS_HIGH = 38.4
LOW_TOTAL, HIGH_TOTAL = 41.0, 49.0
SPREAD_BIG = 6.0
OPP_OUT_MIN_PPG, OPP_OUT_MIN_GAMES = 10.0, 3


def canonical_position(pos: str) -> str:
    p = str(pos).strip().upper()
    return "DST" if p in DEFENSE_POSITION_LABELS else p


def _is_num(x) -> bool:
    try:
        return x is not None and not pd.isna(x)
    except (TypeError, ValueError):
        return False


def _num(row, col, default=np.nan):
    v = row.get(col, default) if hasattr(row, "get") else default
    return float(v) if _is_num(v) else default


def lin(x, lo, hi) -> float:
    if not _is_num(x):
        return 0.0
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))


# =============================================================================
# Loaders (each degrades to empty + a NOTE on stderr, never crashes)
# =============================================================================

def read_final_projections(site: str, slate_id: str) -> pd.DataFrame:
    """Unfiltered final_projections (includes zeroed/OUT rows)."""
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
            f"changed -- update this script's read_final_projections()."
        )
    df["position"] = df["position"].apply(canonical_position)
    return df


def load_final_projections(site: str, slate_id: str) -> pd.DataFrame:
    df = read_final_projections(site, slate_id)
    return df[df["final_projection"] > 0].copy()


def load_display_matchup_factors(site: str, season: int, week: int) -> dict:
    """The REAL (un-neutralized) per-team/position defense-vs-position ratio,
    for the rationale text only. Missing file degrades to neutral (1.0)."""
    path = OUTPUT_DIR / f"matchup_factors_{site}_{season}_{week}.csv"
    if not path.exists():
        print(f"NOTE: {path} not found -- rationale matchup clause will read "
              f"neutral (1.0) for every skill-position player.", file=sys.stderr)
        return {}
    mf = pd.read_csv(path)
    return {(r["team"], r["position"]): r["matchup_factor"] for _, r in mf.iterrows()}


def load_snap_recent(season: int, week: int) -> pd.DataFrame:
    """Offense snap rows from weeks BEFORE `week` with offense_snaps > 0, sorted
    by player/week. Empty frame (and a NOTE) if the file is missing."""
    path = DATA_DIR / f"snap_counts_{season}.parquet"
    cols = ["player_id", "week", "offense_snaps", "offense_pct"]
    try:
        s = pd.read_parquet(path)
        s = s[(s["week"] < week) & (s["offense_snaps"] > 0)]
        return s[cols].sort_values(["player_id", "week"]).reset_index(drop=True)
    except Exception as exc:  # noqa: BLE001 -- degrade, never crash
        print(f"NOTE: snap counts unavailable ({path.name}: {type(exc).__name__}) -- "
              f"usage bullets will read 'no snap data yet'.", file=sys.stderr)
        return pd.DataFrame(columns=cols)


def load_game_log(season: int, week: int, snaps: pd.DataFrame) -> dict:
    """{player_id: (n_games, n_duds)} for this season's weeks < `week`. A game
    counts when the player had offense snaps (falls back to any
    attempts/carries/targets when snap data is missing). A dud is a game under
    DUD_FRAC of the player's own season-average PPR points."""
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    try:
        ws = pd.read_parquet(path)
        if "season_type" in ws.columns:
            ws = ws[ws["season_type"] == "REG"]
        ws = ws[ws["week"] < week]
        if not snaps.empty:
            # Left-join from snaps: a snap-game with no stat line is a real
            # zero-point game (counts toward n and as a dud).
            ws = ws[["player_id", "week", "fantasy_points_ppr"]]
            ws = snaps[["player_id", "week"]].merge(ws, on=["player_id", "week"], how="left")
            ws["fantasy_points_ppr"] = ws["fantasy_points_ppr"].fillna(0.0)
        else:
            vol = ws[["attempts", "carries", "targets"]].fillna(0).sum(axis=1)
            ws = ws[vol > 0]
        ws = ws.copy()
        ws["_pts"] = ws["fantasy_points_ppr"].astype(float)
        mean = ws.groupby("player_id")["_pts"].transform("mean")
        ws["_dud"] = (ws["_pts"] < DUD_FRAC * mean).astype(int)
        agg = ws.groupby("player_id").agg(n=("_pts", "count"), duds=("_dud", "sum"))
        return {pid: (int(r.n), int(r.duds)) for pid, r in agg.iterrows()}
    except Exception as exc:  # noqa: BLE001
        print(f"NOTE: weekly game log unavailable ({path.name}: {type(exc).__name__}) -- "
              f"dud-rate falls back to the position rate.", file=sys.stderr)
        return {}


def load_rookie_ids(season: int) -> set:
    path = DATA_DIR / f"weekly_rosters_{season}.parquet"
    try:
        r = pd.read_parquet(path, columns=["gsis_id", "years_exp", "week"])
        last = r.sort_values("week").drop_duplicates("gsis_id", keep="last")
        return set(last.loc[last["years_exp"] == 0, "gsis_id"].dropna().astype(str))
    except Exception as exc:  # noqa: BLE001
        print(f"NOTE: rosters unavailable ({path.name}: {type(exc).__name__}) -- "
              f"rookie-QB clause skipped.", file=sys.stderr)
        return set()


def load_weather(season: int, week: int) -> dict:
    path = DATA_DIR / f"weather_{season}_wk{week}.csv"
    try:
        w = pd.read_csv(path)
        return {r["team"]: r for _, r in w.drop_duplicates("team").iterrows()}
    except Exception as exc:  # noqa: BLE001
        print(f"NOTE: weather unavailable ({path.name}: {type(exc).__name__}) -- "
              f"weather clause skipped.", file=sys.stderr)
        return {}


def load_dst_typical_miss() -> float:
    try:
        with open(DATA_DIR / "dst_recal_v2.json") as fh:
            d = json.load(fh)
        return float(d["heldout_loso_2021_25"]["v2"]["MAE"])
    except Exception:  # noqa: BLE001
        return DST_TYPICAL_MISS


def load_dst_features(season: int, week: int, dst_rows: pd.DataFrame, team_implied_total: dict,
                      team_ou: dict) -> dict:
    """Sack-rate / opposing-QB INT-rate / dropback features from dst_model, or
    {} if anything fails (the sack/INT/dropback clauses are then dropped)."""
    try:
        _here = str(Path(__file__).resolve().parent)
        if _here not in sys.path:
            sys.path.insert(0, _here)
        import dst_model
        veg = pd.DataFrame({
            "team": dst_rows["team"], "opponent": dst_rows["opponent"],
            "implied_total": dst_rows["team"].map(team_implied_total),
            "over_under": dst_rows["team"].map(team_ou),
        })
        model = dst_model.load_model()
        feat = dst_model.build_features(
            season, week, list(dst_rows["team"]), veg, model,
            games=pd.read_parquet(DATA_DIR / "games.parquet"),
            opponent_map=dict(zip(dst_rows["team"], dst_rows["opponent"])),
        ).set_index("team")
        return {
            "feat": feat,
            "lg_sack": model["league_means"]["sacks"] / model["league_means"]["dropbacks"],
            "lg_int": model["int_rate"]["league_int_rate"],
        }
    except Exception as exc:  # noqa: BLE001
        print(f"NOTE: dst_model features unavailable ({type(exc).__name__}: {exc}) -- "
              f"DST sack/INT/dropback clauses skipped.", file=sys.stderr)
        return {}


# =============================================================================
# Scoring (composite unchanged from v2)
# =============================================================================

def zscore(series: pd.Series) -> pd.Series:
    """Mean-0/std-1 within whatever subset is passed in. A zero-variance
    pool maps to all zeros rather than NaN/inf."""
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
    return np.nan  # DST -- no usage factor


def score_position_group(group: pd.DataFrame, team_implied_total: dict) -> pd.DataFrame:
    g = group.copy()
    pos = g["position"].iloc[0]

    g["_value_raw"] = g["final_projection"] / (g["salary"] / 1000.0)
    g["_ceiling_raw"] = g["statline_p90"]
    g["_floor_raw"] = g["statline_p10"]
    g["_matchup_raw"] = g["matchup_factor"]
    if pos == "DST":
        g["_game_env_raw"] = -g["opponent"].map(team_implied_total)
    else:
        g["_game_env_raw"] = g["implied_total"]
    g["_usage_raw"] = g.apply(usage_value, axis=1)
    g["_leverage_raw"] = zscore(g["final_projection"]) - zscore(g["estimated_ownership_pct"])
    # Rank 1 = the single leading usage-earner at this position on their OWN
    # team (among teammates active this week).
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
    # Leverage deliberately excluded from the composite (see module docstring).
    g["_z_leverage"] = zscore(g["_leverage_raw"])

    g["composite_score"] = composite / weight_sum
    g["composite_z"] = zscore(g["composite_score"])
    return g


# =============================================================================
# Tiers
# =============================================================================

def _tier_from_cuts(x: float, cuts: list, last: str) -> str:
    for cut, name in cuts:
        if x >= cut:
            return name
    return last


def _matchup_tier(mf: float, is_dst: bool = False) -> str:
    return _tier_from_cuts(mf, DST_MATCHUP_CUTS if is_dst else MATCHUP_CUTS, "tough")


def env_tier(row: pd.Series, avg_implied_total: float, team_implied_total: dict) -> str:
    """Slate-relative tier on the team's implied total (skill) or, inverted, the
    opponent's (DST)."""
    if row["position"] == "DST":
        opp = team_implied_total.get(row["opponent"])
        d = (avg_implied_total - opp) if _is_num(opp) else 0.0
        names = ENV_NAMES_DST
    else:
        d = row["implied_total"] - avg_implied_total
        names = ENV_NAMES_SKILL
    if d >= GAME_ENV_STRONG:
        return names[0]
    if d >= GAME_ENV_MARGIN:
        return names[1]
    if d > -GAME_ENV_MARGIN:
        return names[2]
    if d > -GAME_ENV_STRONG:
        return names[3]
    return names[4]


# =============================================================================
# Role security + bust risk (skill positions)
# =============================================================================

def compute_role_security(scored: pd.DataFrame, df_pool: pd.DataFrame, snaps: pd.DataFrame,
                          game_log: dict) -> pd.DataFrame:
    """Adds _rs, _role_tier, _risk, _risk_tier, _flags, _snap3, _snap_n, _share,
    _stepup_pts, _stepup_frac, _dud_n, _dud_games for QB/RB/WR/TE rows (NaN/''
    for DST). No salary term anywhere."""
    s = scored.copy()
    # snap % over the player's last <= 3 games (weeks already < target week)
    if not snaps.empty:
        last3 = snaps.groupby("player_id").tail(3).groupby("player_id")["offense_pct"].agg(["mean", "count"])
        s["_snap3"] = s["player_id"].map(last3["mean"])
        s["_snap_n"] = s["player_id"].map(last3["count"])
    else:
        s["_snap3"] = np.nan
        s["_snap_n"] = np.nan

    team_tgt = df_pool.groupby("team")["proj_targets"].sum()
    team_rb_rush = df_pool[df_pool["position"] == "RB"].groupby("team")["proj_rush_att"].sum()
    tgt_den = s["team"].map(team_tgt).replace(0, np.nan)
    rush_den = s["team"].map(team_rb_rush).replace(0, np.nan)
    tgt_share = s["proj_targets"] / tgt_den
    rush_share = s["proj_rush_att"] / rush_den
    s["_share"] = np.where(s["position"] == "RB", rush_share, tgt_share)  # QB: unused

    for col in ("wrw_delta_pts", "wrw_wr_delta_pts", "wrw_te_delta_pts"):
        if col not in s.columns:
            s[col] = np.nan
    s["_stepup_pts"] = s[["wrw_delta_pts", "wrw_wr_delta_pts", "wrw_te_delta_pts"]].fillna(0).clip(lower=0).sum(axis=1)
    s["_stepup_frac"] = s["_stepup_pts"] / s["final_projection"]

    s["_dud_n"] = s["player_id"].map(lambda p: game_log.get(p, (0, 0))[0])
    s["_dud_games"] = s["player_id"].map(lambda p: game_log.get(p, (0, 0))[1])

    # pooled position dud rate over the startable pool
    pos_dud = dict(DEFAULT_POS_DUD_RATE)
    for p in ("QB", "RB", "WR", "TE"):
        q = s[(s["position"] == p) & (s["final_projection"] >= STARTABLE_MIN_PROJ[p]) & (s["_dud_n"] > 0)]
        if q["_dud_n"].sum() > 0:
            pos_dud[p] = float(q["_dud_games"].sum() / q["_dud_n"].sum())

    out = {k: [] for k in ("_rs", "_risk", "_flags", "_dud_rate")}
    for _, r in s.iterrows():
        p = r["position"]
        if p == "DST":
            for k in out:
                out[k].append(np.nan if k != "_flags" else "")
            continue
        fp = r["final_projection"]
        stepup, frac = r["_stepup_pts"], r["_stepup_frac"]
        opp = r["_usage_raw"]
        opp_eff = opp * fp / max(fp - stepup, 1.0) if frac >= STEPUP_COUNT_FRAC else opp
        V = lin(opp_eff, *VOL_BARS[p])
        if p == "QB":
            S = 1.0 if r["_team_pos_rank"] == 1 else 0.0
        else:
            S = lin(r["_share"], *SHARE_BARS[p]) if _is_num(r["_share"]) else 0.0
        if p != "QB" and frac >= STEPUP_COUNT_FRAC:
            S = 0.5  # share is inflated by the injury step-up; use neutral
        N = lin(r["_snap3"], *SNAP_BARS[p]) if _is_num(r["_snap3"]) else np.nan

        T, flags = 1.0, []
        gp = _num(r, "games_played", 0.0)
        gp = int(gp)
        if gp <= 2:
            T -= 0.40
            flags.append("no games yet this season" if gp == 0
                         else f"only {gp} {'game' if gp == 1 else 'games'} this season")
        elif gp <= 4:
            T -= 0.20
            flags.append(f"only {gp} games this season")
        pe = _num(r, "participation_effective")
        if _is_num(pe) and pe < 1:
            T -= 0.5 * (1 - pe)
            flags.append("missed recent time")
        ut = _num(r, "usage_trend_ratio")
        if _is_num(ut):
            if ut <= 0.80:
                T -= 0.25
                flags.append("usage trending down")
            elif ut <= 0.90:
                T -= 0.10
                flags.append("usage dipping")
            elif ut >= 1.15:
                flags.append("usage trending up")
        if frac >= STEPUP_UNPROVEN_FRAC:
            T -= 0.35
        elif frac >= STEPUP_COUNT_FRAC:
            T -= 0.15
        if str(r.get("injury_status", "")).upper() == "QUESTIONABLE":
            T -= 0.30
            flags.append("questionable")
        avg = _num(r, "dk_avg_ppg")
        if _is_num(avg) and fp - avg >= 3.0:
            T -= 0.10
        T = float(np.clip(T, 0.0, 1.0))

        parts = [(W_VOL, V), (W_SHARE, S), (W_STAB, T)] + ([(W_SNAP, N)] if _is_num(N) else [])
        RS = 100.0 * sum(w * v for w, v in parts) / sum(w for w, _ in parts)

        n, duds = r["_dud_n"], r["_dud_games"]
        dud_rate = (duds + DUD_SHRINK_K * pos_dud[p]) / (n + DUD_SHRINK_K)
        consistency = 100.0 * (1.0 - float(np.clip(dud_rate / DUD_RATE_FLOOR_CAP, 0, 1)))
        risk = 100.0 - (W_RS_IN_RISK * RS + W_CONS_IN_RISK * consistency)
        out["_rs"].append(RS)
        out["_risk"].append(risk)
        out["_flags"].append("; ".join(flags))
        out["_dud_rate"].append(dud_rate)
    for k, v in out.items():
        s[k] = v

    def role_tier(r):
        if r["position"] == "DST" or pd.isna(r["_rs"]):
            return ""
        if r["_rs"] < RS_TIERS[-1][0] and r["_stepup_frac"] >= STEPUP_UNPROVEN_FRAC:
            return "unproven new role"
        return _tier_from_cuts(r["_rs"], RS_TIERS, "fragile role")

    def risk_tier(r):
        if r["position"] == "DST" or pd.isna(r["_risk"]):
            return ""
        for cut, name in RISK_TIERS:
            if r["_risk"] < cut:
                return name
        return "high bust risk"

    s["_role_tier"] = s.apply(role_tier, axis=1)
    s["_risk_tier"] = s.apply(risk_tier, axis=1)
    return s


# =============================================================================
# DST upside setup
# =============================================================================

def compute_dst_setup(scored: pd.DataFrame, df_pool: pd.DataFrame, df_full: pd.DataFrame,
                      team_implied_total: dict, avg_implied_total: float, team_ou: dict,
                      dst_feat: dict, rookie_ids: set, weather: dict,
                      snaps: pd.DataFrame = None, week: int = 0) -> pd.DataFrame:
    """Adds _setup_score, _setup_tier, _setup_rank, _setup_facts for DST rows.
    Every clause below traces to a source listed in SPEC D1; clauses whose data
    is unavailable are skipped (never guessed)."""
    s = scored.copy()
    for c in ("_setup_score", "_setup_rank"):
        s[c] = np.nan
    s["_setup_tier"] = ""
    s["_setup_facts"] = ""
    dst = s[s["position"] == "DST"]
    if dst.empty:
        return s

    feat = dst_feat.get("feat")
    lg_sack, lg_int = dst_feat.get("lg_sack"), dst_feat.get("lg_int")
    qbs = (df_pool[df_pool["position"] == "QB"].sort_values("proj_pass_att", ascending=False)
           .drop_duplicates("team").set_index("team"))
    outs = df_full[(df_full.get("injury_status") == "OUT") & df_full["position"].isin(["RB", "WR", "TE"])] \
        if "injury_status" in df_full.columns else df_full.iloc[0:0]

    last_snap_wk = (snaps.groupby("player_id")["week"].max().to_dict()
                    if snaps is not None and not snaps.empty else {})
    scores, facts_out = {}, {}
    for idx, r in dst.iterrows():
        team, opp = r["team"], r["opponent"]
        pos_f, neg_f, sc = [], [], 0
        opp_it = team_implied_total.get(opp)
        own_it = team_implied_total.get(team)
        if _is_num(opp_it):
            d = round(opp_it, 1) - round(avg_implied_total, 1)
            d = round(d, 1)
            if d <= -GAME_ENV_STRONG:
                sc += 2
                pos_f.append(f"{opp} implied only {opp_it:.1f}, {-d:.1f} below the slate average")
            elif d <= -GAME_ENV_MARGIN:
                sc += 1
                pos_f.append(f"{opp} implied only {opp_it:.1f}, {-d:.1f} below the slate average")
            elif d >= GAME_ENV_STRONG:
                sc -= 2
                neg_f.append(f"{opp} implied {opp_it:.1f}, {d:.1f} above the slate average, works against")
            elif d >= GAME_ENV_MARGIN:
                sc -= 1
                neg_f.append(f"{opp} implied {opp_it:.1f}, {d:.1f} above the slate average, works against")
        if _is_num(opp_it) and _is_num(own_it):
            fav = own_it - opp_it
            if fav >= SPREAD_BIG:
                sc += 1
                pos_f.append(f"favored by {fav:.1f}")
            elif fav <= -SPREAD_BIG:
                sc -= 1
                neg_f.append(f"underdog by {-fav:.1f}, works against")
        tot = team_ou.get(team)
        if _is_num(tot):
            if tot <= LOW_TOTAL:
                sc += 1
                pos_f.append(f"low game total {tot:.1f}")
            elif tot >= HIGH_TOTAL:
                sc -= 1
                neg_f.append(f"shootout-level game total {tot:.1f}, works against")
        if feat is not None and team in feat.index and lg_sack:
            f = feat.loc[team]
            sk = f.get("opp_sack_allowed_rate")
            if _is_num(sk):
                if sk >= SACK_HIGH_MULT * lg_sack:
                    sc += 1
                    pos_f.append(f"{opp} allows sacks on {sk:.1%} of dropbacks")
                elif sk <= SACK_LOW_MULT * lg_sack:
                    sc -= 1
                    neg_f.append(f"{opp} rarely sacked ({sk:.1%} of dropbacks, works against)")
            qi = f.get("qb_int_rate")
            if _is_num(qi) and lg_int and not str(f.get("qb_source", "")).startswith("league_mean"):
                if qi >= INT_HIGH_MULT * lg_int:
                    sc += 1
                    pos_f.append(f"{opp} QB throws interceptions on {qi:.1%} of attempts")
                elif qi <= INT_LOW_MULT * lg_int:
                    sc -= 1
                    neg_f.append(f"{opp} QB protects the ball ({qi:.1%} INT rate, works against)")
            db = f.get("opp_dropbacks")
            if _is_num(db) and db >= DROPBACKS_HIGH:
                pos_f.append(f"high dropback volume for {opp} ({db:.1f} per game)")
        if opp in qbs.index:
            q = qbs.loc[opp]
            gp = _num(q, "games_played", 0.0)
            gp = int(gp)
            gtxt = f"{gp} {'game' if gp == 1 else 'games'} this season"
            if str(q["player_id"]) in rookie_ids:
                sc += 1
                pos_f.append(f"rookie QB {q['player_name']} ({'no games yet this season' if gp == 0 else gtxt})")
                if gp <= 3:
                    sc += 1
            elif gp <= 3:
                sc += 1
                pos_f.append(f"{opp} QB {q['player_name']} has " +
                             ("no games yet this season" if gp == 0 else f"only {gtxt}"))
        if "dk_avg_ppg" in outs.columns and "games_played" in outs.columns:
            ko = outs[(outs["team"] == opp) & (outs["dk_avg_ppg"] >= OPP_OUT_MIN_PPG)
                      & (outs["games_played"] >= OPP_OUT_MIN_GAMES)]
            if len(ko):
                ko = ko.sort_values("dk_avg_ppg", ascending=False)
                recent, stale = [], []
                for _, k in ko.iterrows():
                    lw = last_snap_wk.get(k["player_id"])
                    if lw is not None and lw >= week - 2:
                        recent.append(k["player_name"])
                    elif lw is not None:
                        stale.append((k["player_name"], int(lw)))
                if recent:
                    sc += 1
                    pos_f.append(f"{opp} missing {', '.join(recent[:2])}")
                elif stale:
                    nm, lw = stale[0]
                    pos_f.append(f"{opp} without {nm} since wk {lw}")
        w = weather.get(team)
        if w is not None and not bool(w.get("indoor", False)):
            wind, gust, rain, temp = (_num(w, "wind_mph"), _num(w, "gust_mph"),
                                      _num(w, "precip_mm_hr"), _num(w, "temp_f"))
            bits = []
            if _is_num(wind) and wind >= 15:
                bits.append(f"wind {wind:.0f} mph")
            if _is_num(gust) and gust >= 30:
                bits.append(f"gusts {gust:.0f} mph")
            if _is_num(rain) and rain >= 0.5:
                bits.append(f"rain {rain:.1f} mm/hr")
            if _is_num(temp) and temp <= 25:
                bits.append(f"{temp:.0f}F")
            if bits:
                sc += 1
                pos_f.append("weather: " + ", ".join(bits))
        scores[idx] = sc
        facts_out[idx] = "; ".join(pos_f + neg_f)

    sc_series = pd.Series(scores)
    for idx, sc in scores.items():
        s.at[idx, "_setup_score"] = sc
        s.at[idx, "_setup_rank"] = int((sc_series > sc).sum()) + 1
        s.at[idx, "_setup_tier"] = _tier_from_cuts(sc, DST_SETUP_TIERS, "poor")
        s.at[idx, "_setup_facts"] = facts_out[idx]
    s["_setup_n"] = len(scores)
    return s


# =============================================================================
# Quality / confidence
# =============================================================================

def _history_score(r: pd.Series) -> float:
    gp = _num(r, "games_played", 0.0)
    avg = _num(r, "dk_avg_ppg")
    if r["position"] != "DST" and gp <= 0:
        return 0.3
    if not _is_num(avg):
        return 0.3
    d = r["final_projection"] - avg
    if d >= HISTORY_DIFF_MARGIN:
        return 0.5
    if d <= -HISTORY_DIFF_MARGIN:
        return 0.7
    return 1.0


def compute_quality(scored: pd.DataFrame) -> pd.DataFrame:
    """Adds _startable, _strength, _q (absolute quality, 0-1) and confidence
    (1-10, fixed anchors CONF_Q_LO / CONF_Q_HI)."""
    s = scored.copy()
    s["_startable"] = s.apply(lambda r: r["final_projection"] >= STARTABLE_MIN_PROJ[r["position"]], axis=1)
    s["_strength"] = 0.0
    for _, g in s[s["_startable"]].groupby("position"):
        s.loc[g.index, "_strength"] = (g["composite_score"].rank(method="average") - 0.5) / len(g)
    hist = s.apply(_history_score, axis=1)
    env = s["_env_tier"].map(ENV_SCORE).fillna(0.5)
    mat = s["_m_tier"].map(MATCHUP_SCORE).fillna(0.5)
    role = np.where(
        s["position"] == "DST",
        np.clip((s["_setup_score"].fillna(0) + 2) / 8, 0, 1),
        s["_rs"].fillna(0) / 100.0,
    )
    s["_q"] = (CONF_W_STRENGTH * s["_strength"] + CONF_W_ROLE * role + CONF_W_ENV * env
               + CONF_W_MATCHUP * mat + CONF_W_HISTORY * hist)
    conf = 1 + 9 * ((s["_q"] - CONF_Q_LO) / (CONF_Q_HI - CONF_Q_LO)).clip(0, 1)
    s["confidence"] = conf.round().astype(int)
    return s


# =============================================================================
# Bullets
# =============================================================================

def matchup_bullet(row: pd.Series) -> str:
    # _display_matchup is the REAL defense-vs-position signal, NOT the
    # neutralized ranking column -- see module docstring.
    mf = row["_display_matchup"]
    tier = row["_m_tier"]
    if row["position"] == "DST":
        return f"Matchup: {mf:.2f}x matchup factor ({tier})"
    return f"Matchup: {row['opponent']} allows {mf:.2f}x league-avg to {row['position']}s ({tier})"


def env_bullet(row: pd.Series, avg_implied_total: float, team_implied_total: dict) -> str:
    tier = row["_env_tier"]
    ou = _num(row, "over_under")
    total_txt = f" of a {ou:.1f} total" if _is_num(ou) else ""
    if row["position"] == "DST":
        opp_total = team_implied_total.get(row["opponent"])
        if not _is_num(opp_total):
            return f"Game environment: opponent {row['opponent']} implied total unavailable ({tier})"
        return f"Game environment: opponent {row['opponent']} implied {opp_total:.1f}{total_txt} ({tier})"
    team_total = row["implied_total"]
    spread_txt = ""
    opp_total = team_implied_total.get(row["opponent"])
    if _is_num(opp_total):
        diff = team_total - opp_total
        if diff >= SPREAD_PICKEM:
            spread_txt = f", favored by {diff:.1f}"
        elif diff <= -SPREAD_PICKEM:
            spread_txt = f", underdog by {-diff:.1f}"
        else:
            spread_txt = ", pick'em"
    return f"Game environment: {row['team']} implied {team_total:.1f}{total_txt}{spread_txt} ({tier})"


def history_bullet(row: pd.Series):
    """Returns (bullet_text, has_history). Real season-to-date history (DK's/FD's
    own displayed avg pts/game) -- NOT season_avg/recent_form, which are circular
    with final_projection. games_played isn't tracked for DST."""
    pos = row["position"]
    avg_ppg = row.get("dk_avg_ppg")
    games_played = row.get("games_played")
    games_played = 0 if pd.isna(games_played) else int(games_played)
    if pos != "DST" and games_played <= 0:
        return "History: no games logged yet this season", False
    if pd.isna(avg_ppg):
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


def usage_bullet(row: pd.Series) -> str:
    pos = row["position"]
    if pos == "QB":
        text = f"{row['proj_pass_att']:.1f} pass att + {row['proj_rush_att']:.1f} rush att projected"
    elif pos == "RB":
        touches = row["proj_rush_att"] + row["proj_targets"]
        share = (f", {row['_share']:.0%} of RB carries"
                 if _is_num(row["_share"]) and not row["_stepup_frac"] >= STEPUP_COUNT_FRAC else "")
        text = (f"{touches:.1f} touches projected ({row['proj_rush_att']:.1f} carries + "
                f"{row['proj_targets']:.1f} targets{share})")
    else:
        share = (f" ({row['_share']:.0%} of team targets)"
                 if _is_num(row["_share"]) and not row["_stepup_frac"] >= STEPUP_COUNT_FRAC else "")
        text = f"{row['proj_targets']:.1f} targets projected{share}"
    if row["_stepup_frac"] >= STEPUP_COUNT_FRAC:
        text += f" + injury step-up worth {row['_stepup_pts']:.1f} pts"
    if _is_num(row["_snap3"]):
        n = int(row["_snap_n"])
        span = "last game" if n == 1 else f"last {n} games"
        snap = f"{row['_snap3']:.0%} of snaps {span}"
    else:
        snap = "no snap data yet"
    flags = f"; {row['_flags']}" if row["_flags"] else ""
    return f"Usage: {text}, {snap} ({row['_role_tier']}{flags})"


def range_bullet(row: pd.Series, dst_miss: float) -> str:
    if row["position"] == "DST":
        lo = max(0.0, row["final_projection"] - dst_miss)
        hi = row["final_projection"] + dst_miss
        return (f"Range: about {lo:.0f}–{hi:.0f} pts in a typical game (DST projections miss by "
                f"{dst_miss:.1f} pts on average, 2021-25); a defensive or return TD or a safety is "
                f"what pushes it higher, and those aren't modeled")
    n, d = int(row["_dud_n"]), int(row["_dud_games"])
    if n > 0:
        dud = f"under half his average in {d} of {n} games"
    else:
        dud = "no games logged yet" if row.get("_log_ok", True) else "game log unavailable"
    return f"Range: {row['statline_p10']:.1f}–{row['statline_p90']:.1f} pts ({row['_risk_tier']}; {dud})"


def setup_bullet(row: pd.Series) -> str:
    rank = int(row["_setup_rank"])
    n = int(row["_setup_n"])
    facts = row["_setup_facts"] or "no standout factors either way"
    return f"Upside setup: {row['_setup_tier']}, #{rank} of {n} on the slate: {facts}"


def build_rationale(row: pd.Series, avg_implied_total: float, team_implied_total: dict,
                    dst_miss: float) -> tuple:
    history_line, has_history = history_bullet(row)
    is_dst = row["position"] == "DST"
    bullets = [
        matchup_bullet(row),
        env_bullet(row, avg_implied_total, team_implied_total),
        history_line,
        setup_bullet(row) if is_dst else usage_bullet(row),
        range_bullet(row, dst_miss),
    ]
    rationale = "\n".join(f"• {b}" for b in bullets)
    top_factors = "matchup, game environment"
    if has_history:
        top_factors += ", history"
    top_factors += ", upside setup" if is_dst else ", usage"
    top_factors += ", range"
    return top_factors, rationale


OUTPUT_COLUMNS = [
    "position", "rank", "player_id", "player_name", "team", "opponent",
    "salary", "final_projection", "estimated_ownership_pct", "confidence",
    "composite_score", "top_factors", "rationale", "badge", "is_bonus",
    "role_security", "role_tier", "risk_tier", "setup_score", "conf_basis",
]


def _risk_badges(row: pd.Series, base_badges: list) -> list:
    """Solid Value / Boom/Bust Dart / Fragile Chalk (skill positions only)."""
    if row["position"] == "DST":
        return []
    tags = []
    is_val = any(b in ("Value Pick", "Value Candidate") for b in base_badges)
    rs, tier = row["_rs"], row["_risk_tier"]
    if is_val and rs >= SOLID_VALUE_MIN_RS and tier in ("low bust risk", "moderate bust risk"):
        tags.append("Solid Value")
    if is_val and (rs < DART_MAX_RS or tier == "high bust risk"):
        tags.append("Boom/Bust Dart")
    if row["estimated_ownership_pct"] >= FRAGILE_CHALK_OWN and (
            rs < FRAGILE_CHALK_RS or tier in ("elevated bust risk", "high bust risk")):
        tags.append("Fragile Chalk")
    return tags


def _build_row(pos: str, row: pd.Series, rank, is_bonus: bool, base_badges: list,
               avg_implied_total: float, team_implied_total: dict, dst_miss: float,
               conf_cap: int = None) -> dict:
    top_factors, rationale = build_rationale(row, avg_implied_total, team_implied_total, dst_miss)
    badge = ", ".join(list(base_badges) + _risk_badges(row, base_badges))
    is_dst = pos == "DST"
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
        "confidence": int(row["confidence"]) if conf_cap is None else int(min(row["confidence"], conf_cap)),
        "composite_score": row["composite_score"],
        "top_factors": top_factors,
        "rationale": rationale,
        "badge": badge,
        "is_bonus": is_bonus,
        "role_security": np.nan if is_dst else round(float(row["_rs"]), 1),
        "role_tier": "" if is_dst else row["_role_tier"],
        "risk_tier": "" if is_dst else row["_risk_tier"],
        "setup_score": row["_setup_score"] if is_dst else np.nan,
        "conf_basis": round(float(row["_q"]), 3),
    }


def build_cheat_sheet(site: str, slate_id: str, season: int, week: int) -> pd.DataFrame:
    df_full = read_final_projections(site, slate_id)
    df = df_full[df_full["final_projection"] > 0].copy()
    team_implied_total = df.drop_duplicates("team").set_index("team")["implied_total"].to_dict()
    avg_implied_total = float(np.mean(list(team_implied_total.values()))) if team_implied_total else 0.0
    team_ou = (df.drop_duplicates("team").set_index("team")["over_under"].to_dict()
               if "over_under" in df.columns else {})

    scored = []
    for pos, group in df.groupby("position"):
        if pos not in TOP_N_BY_POSITION:
            continue  # ignore anything outside the five tracked positions
        scored.append(score_position_group(group, team_implied_total))
    if not scored:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    scored_df = pd.concat(scored, ignore_index=True)

    # Display-only real DVP signal for the matchup bullet (see docstring).
    display_matchup = load_display_matchup_factors(site, season, week)
    scored_df["_display_matchup"] = scored_df.apply(
        lambda r: r["matchup_factor"] if r["position"] == "DST"
        else display_matchup.get((r["opponent"], r["position"]), 1.0),
        axis=1,
    )
    scored_df["_m_tier"] = scored_df.apply(
        lambda r: _matchup_tier(round(float(r["_display_matchup"]), 2), r["position"] == "DST"), axis=1)
    scored_df["_env_tier"] = scored_df.apply(
        lambda r: env_tier(r, avg_implied_total, team_implied_total), axis=1)

    # Role security / bust risk (skill) and upside setup (DST)
    snaps = load_snap_recent(season, week)
    game_log = load_game_log(season, week, snaps)
    scored_df = compute_role_security(scored_df, df, snaps, game_log)
    scored_df["_log_ok"] = bool(game_log)

    dst_rows = scored_df[scored_df["position"] == "DST"]
    dst_feat = load_dst_features(season, week, dst_rows, team_implied_total, team_ou) if not dst_rows.empty else {}
    rookie_ids = load_rookie_ids(season) if not dst_rows.empty else set()
    weather = load_weather(season, week) if not dst_rows.empty else {}
    scored_df = compute_dst_setup(scored_df, df, df_full, team_implied_total, avg_implied_total,
                                  team_ou, dst_feat, rookie_ids, weather, snaps, week)
    scored_df = compute_quality(scored_df)
    dst_miss = load_dst_typical_miss()

    rows = []
    for pos, top_n in TOP_N_BY_POSITION.items():
        pool = scored_df[scored_df["position"] == pos]
        if pool.empty:
            print(f"WARNING: no eligible {pos} players found for {site}/{slate_id} "
                  f"-- skipping (thin/empty slate for this position).", file=sys.stderr)
            continue

        # Main list: startable players (and, for skill positions, a real
        # enough role) ranked by absolute quality Q.
        elig = pool[pool["_startable"]]
        if pos != "DST":
            elig = elig[elig["_rs"] >= RS_MAIN_LIST_MIN]
        if len(elig) < top_n:
            print(f"NOTE: only {len(elig)}/{top_n} eligible {pos} players found "
                  f"for {site}/{slate_id}.", file=sys.stderr)
        top = elig.sort_values(["_q", "composite_score"], ascending=False).head(top_n).reset_index(drop=True)
        top_ids = set(top["player_id"])
        floor_conf = int(top["confidence"].min()) if len(top) else None

        # Guaranteed Value/Leverage slots (user decision, 2026-10-24) and the
        # Value Pick eligibility rule (user decision, 2026-11-03) are
        # unchanged from v2, drawn from the full position pool: Value Pick =
        # best $/pt among the team-lead players cheaper than the median lead
        # salary (DST: cheap half of the pool); Leverage Pick = best
        # projection-minus-ownership z.
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

        displayed_ids = set(top_ids)
        if best_value_row is not None:
            displayed_ids.add(best_value_row["player_id"])
        displayed_ids.add(best_leverage_row["player_id"])

        # Value Candidate rows (Wk9 Item A): RB/WR/TE, top 5 by raw $/pt not
        # already displayed.
        value_candidate_rows = []
        if pos in VALUE_CANDIDATE_POSITIONS:
            candidates = pool[~pool["player_id"].isin(displayed_ids)].sort_values(
                "_value_raw", ascending=False).head(VALUE_CANDIDATE_TOP_N)
            value_candidate_rows = [row for _, row in candidates.iterrows()]
            for row in value_candidate_rows:
                displayed_ids.add(row["player_id"])
                badges_by_id.setdefault(row["player_id"], []).append("Value Candidate")

        def mk(row, rank, is_bonus):
            return _build_row(pos, row, rank, is_bonus, badges_by_id.get(row["player_id"], []),
                              avg_implied_total, team_implied_total, dst_miss,
                              conf_cap=floor_conf if is_bonus else None)

        for rank, (_, row) in enumerate(top.iterrows(), start=1):
            rows.append(mk(row, rank, False))

        bonus_rank = top_n + 1
        if best_value_row is None:
            print(f"NOTE: no eligible cheap/real-role value play found for {pos} "
                  f"on {site}/{slate_id} -- no Value Pick bonus row added.", file=sys.stderr)
        elif best_value_row["player_id"] not in top_ids:
            rows.append(mk(best_value_row, bonus_rank, True))
            bonus_rank += 1
        best_value_id = best_value_row["player_id"] if best_value_row is not None else None
        if (best_leverage_row["player_id"] not in top_ids
                and best_leverage_row["player_id"] != best_value_id):
            rows.append(mk(best_leverage_row, bonus_rank, True))
            bonus_rank += 1
        for row in value_candidate_rows:
            rows.append(mk(row, bonus_rank, True))
            bonus_rank += 1

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
