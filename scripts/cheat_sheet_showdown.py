"""
cheat_sheet_showdown.py
========================

v5 (2026-11-16, owner: "aligning the language with the data ... a guide, a
cheat sheet, not a crystal ball ... find the best plays on the slate ... the
right value plays ... the high risk bust value plays that others in the field
will slip up on"). Implements analysis/cheat_sheet_showdown_v3/SPEC.md. Nothing
here is an accuracy claim; every cutoff is a language cutoff.
  * Matchup words: classic's 5 tiers and cutoffs (smash spot / favorable /
    neutral / below average / tough); DST gets no tier word (its factor is
    normalized between the two defenses).
  * Game environment: tiers vs the league-average team total (22.3), not the
    slate mean; game-total word; kicker/DST bullets use the right team's total
    (team maps are max-positive per team, never drop_duplicates).
  * Role security + bust risk ported from classic (51a72f3c, incl. the RB
    step-up fix), with the showdown split of the low-role tier (part-time /
    punt-level / backup QB) and a fifth risk word. Replaces the pool-relative
    bust z-score.
  * History bullet (DK AvgPointsPerGame from the salary file), usage bullet with
    projected + real box-score + snaps, kicker usage + weather, DST upside setup.
  * Captain bullet rewritten to match SHOWDOWN_RULES.md.
  * Confidence = one absolute score Q (showdown anchors 0.20/0.95); the whole
    sheet is ranked by Q, so confidence never rises down the list.
  * Badges: Solid Value / Boom/Bust Dart / Fragile Chalk (skill positions).
  * Optional --out writes the CSV elsewhere (scratch review).
Everything below marked SUPERSEDED describes earlier versions' bust-risk
(pool-relative z-score), confidence and 3-tier matchup machinery, which v5 removed.

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

v3 [SUPERSEDED by v5 for bust/cash-line wording] (2026-11-09, same day, user follow-up): asked for the real DK
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

RECALIBRATED BUST-RISK [SUPERSEDED by v5: role security + bust-risk tiers] (v2, user feedback: "literally every player is
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
import json
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

# ---- matchup tiers (v5 SPEC A) ----------------------------------------------
# Same five words and cutoffs as classic cheat_sheet.py MATCHUP_CUTS (51a72f3c):
# the same number must read the same word on both sheets.
MATCHUP_CUTS = [(1.15, "smash spot"), (1.05, "favorable"), (0.95, "neutral"), (0.85, "below average")]
DST_EVEN_MARGIN = 0.05

# ---- game environment for a single game (v5 SPEC B) -------------------------
# League team implied total, data/games.parquet regular season 2021-2026 closing
# lines, n = 3,044 team-games (p10 17.2, p50 22.2, p90 27.2). Hard-coded on purpose.
LEAGUE_IMPLIED_BASE = 22.3
GAME_ENV_MARGIN = 2.0
GAME_ENV_STRONG = 5.0
ENV_NAMES_SKILL = ["elite", "plus", "middling", "low-scoring", "bottom-tier"]
ENV_NAMES_DST = ["elite", "plus", "middling", "tough", "brutal"]
SPREAD_PICKEM = 0.5
# Game total words: league p90 / p75 / p25 / p10 of the closing total.
TOTAL_CUTS = [(50.5, "shootout-level"), (47.5, "high"), (41.5, "average"), (39.0, "low")]  # else very low
HISTORY_DIFF_MARGIN = 3.0

# ---- role security (ported verbatim from classic, 51a72f3c) -----------------
VOL_BARS = {"QB": (28.0, 36.0), "RB": (8.0, 18.0), "WR": (4.0, 8.5), "TE": (3.8, 7.8)}
SHARE_BARS = {"RB": (0.30, 0.75), "WR": (0.12, 0.26), "TE": (0.12, 0.24)}
SNAP_BARS = {"QB": (0.50, 0.95), "RB": (0.35, 0.75), "WR": (0.55, 0.85), "TE": (0.55, 0.85)}
W_VOL, W_SHARE, W_SNAP, W_STAB = 0.30, 0.20, 0.20, 0.30
RS_TIERS = [(85.0, "locked-in role"), (65.0, "solid role"), (45.0, "partial role")]  # below: showdown split
STEPUP_UNPROVEN_FRAC = 0.25
STEPUP_COUNT_FRAC = 0.10
# Confirmed-vacancy inheritor (classic 51a72f3c, analysis/cheat_sheet_stepup/RESULTS.md): RB only.
STEPUP_USAGE_FROM_ENGINE = True
SOLE_TEAMMATE_MIN_PROJ = 5.0
STEPUP_UNPROVEN_T_SOLE = 0.15
# Showdown split of the RS < 45 group (part-time vs punt-level).
FILL_USAGE = {"QB": 20.0, "RB": 5.0, "WR": 3.0, "TE": 2.5}
FILL_SNAP = {"QB": 0.50, "RB": 0.25, "WR": 0.45, "TE": 0.45}

# ---- bust-risk tier (classic score, showdown adds a fifth word) -------------
W_RS_IN_RISK, W_CONS_IN_RISK = 0.65, 0.35
DUD_FRAC = 0.5
DUD_SHRINK_K = 4
DUD_RATE_FLOOR_CAP = 0.5
RISK_TIERS = [(30.0, "low bust risk"), (42.0, "moderate bust risk"), (55.0, "elevated bust risk"),
              (70.0, "high bust risk")]  # else very high
DEFAULT_POS_DUD_RATE = {"QB": 0.066, "RB": 0.206, "WR": 0.225, "TE": 0.277}
STARTABLE_MIN_PROJ = {"QB": 12.0, "RB": 5.0, "WR": 5.0, "TE": 4.0, "DST": 0.0}

# ---- confidence: one absolute score Q (v5 SPEC F) ---------------------------
STRENGTH_LO, STRENGTH_HI = 2.0, 22.0
K_ROLE = 0.60
CONF_W_STRENGTH = 0.45
CONF_W_ROLE = 0.35
CONF_W_ENV = 0.08
CONF_W_MATCHUP = 0.05
CONF_W_HISTORY = 0.07
CONF_Q_LO, CONF_Q_HI = 0.20, 0.95
ENV_SCORE = {"elite": 1.0, "plus": 0.75, "middling": 0.5, "low-scoring": 0.25, "tough": 0.25,
             "bottom-tier": 0.0, "brutal": 0.0}
MATCHUP_SCORE = {"smash spot": 1.0, "favorable": 0.75, "neutral": 0.5, "below average": 0.25, "tough": 0.0}

# ---- badges (v5 SPEC H) -----------------------------------------------------
SOLID_VALUE_MAX_SALARY = 6000
SOLID_VALUE_MAX_RISK = 55.0
DART_MIN_RISK = 70.0
FRAGILE_CHALK_OWN = 25.0
FRAGILE_CHALK_RS = 45.0
FRAGILE_CHALK_RISK = 55.0
GOOD_ROLE_TIERS = {"locked-in role", "solid role", "partial role", "part-time role"}
BAD_ROLE_TIERS = {"punt-level role", "unproven new role", "backup QB"}

# ---- DST setup (ported from classic, v5 SPEC D1) ----------------------------
DST_TYPICAL_MISS = 4.3   # fallback; real value read from data/dst_recal_v2.json
DST_SETUP_TIERS = [(4, "strong"), (2, "good"), (0, "neutral")]  # else poor
SACK_HIGH_MULT, SACK_LOW_MULT = 1.12, 0.87
INT_HIGH_MULT, INT_LOW_MULT = 0.97, 0.77
DROPBACKS_HIGH = 38.4
LOW_TOTAL, HIGH_TOTAL = 41.0, 49.0
SPREAD_BIG = 6.0
OPP_OUT_MIN_PPG, OPP_OUT_MIN_GAMES = 10.0, 3

# Value-per-dollar tiers: pool-relative (2026-11-09), a price read, not a risk read.
VALUE_Z_HIGH = 0.75
VALUE_Z_LOW = -0.75

# Real empirical cash line -- printed in __main__ as a slate-level reference only.
CASH_LINE_PTS = 102.0

SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
DEPTH_TIER_POSITIONS = {"WR", "TE"}
RB_SPLIT_POSITION = "RB"

OUTPUT_COLUMNS = [
    "position", "rank", "overall_rank", "player_id", "player_name", "team",
    "opponent", "salary", "final_projection", "estimated_ownership_pct",
    "confidence", "composite_score", "top_factors", "rationale", "badge",
    "is_bonus",
    "role_security", "role_tier", "risk_tier", "setup_score", "conf_basis",
    "cpt_salary", "cpt_projection", "cpt_ownership_pct", "value_per_k",
]
# v4 (2026-11-24): appended after the 25 original columns. Showdown gets the tag bar only (no price tiers).
V4_EXTRA_COLUMNS = ["matchup_tier", "env_tier", "history_trend", "setup_tier", "tag_bar"]


def canonical_position(pos: str) -> str:
    p = str(pos).strip().upper()
    return "DST" if p in DEFENSE_POSITION_LABELS else p


# Ported from cheat_sheet.py @ 51a72f3c (_is_num, _num, lin, _tier_from_cuts, zscore).
def _is_num(x) -> bool:
    try:
        return x is not None and not pd.isna(x)
    except (TypeError, ValueError):
        return False


def _num(row, col, default=np.nan):
    v = row.get(col, default) if hasattr(row, "get") else default
    try:
        return float(v) if _is_num(v) else default
    except (TypeError, ValueError):
        return default


def lin(x, lo, hi) -> float:
    if not _is_num(x):
        return 0.0
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))


def _tier_from_cuts(x: float, cuts: list, last: str) -> str:
    for cut, name in cuts:
        if x >= cut:
            return name
    return last


def zscore(series: pd.Series) -> pd.Series:
    std = series.std(ddof=0)
    if not std or np.isnan(std):
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def _truthy(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    try:
        return bool(v) and not pd.isna(v)
    except (TypeError, ValueError):
        return False


# =============================================================================
# Loaders (each degrades to empty + a NOTE on stderr, never crashes)
# =============================================================================

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
        "statline_p90", "matchup_factor", "implied_total", "over_under",
        "roster_role", "proj_pass_att", "proj_rush_att", "proj_targets",
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
    try:
        mf = pd.read_csv(path)
        return {(r["team"], r["position"]): r["matchup_factor"] for _, r in mf.iterrows()}
    except Exception as exc:  # noqa: BLE001
        print(f"NOTE: {path.name} unavailable ({type(exc).__name__}) -- QB matchup "
              f"bullets will read neutral (1.0).", file=sys.stderr)
        return {}


def load_depth_tier_matchup_factors(site: str, season: int, week: int) -> dict:
    path = OUTPUT_DIR / f"matchup_factors_showdown_{site}_{season}_{week}.csv"
    try:
        mf = pd.read_csv(path)
        return {(r["team"], r["tier"]): r["matchup_factor"] for _, r in mf.iterrows()}
    except Exception as exc:  # noqa: BLE001
        print(f"NOTE: {path.name} unavailable ({type(exc).__name__}) -- run "
              f"projections_matchup_showdown.py --site {site} --season {season} "
              f"--week {week} first. WR/TE/RB matchup bullets will read neutral (1.0).",
              file=sys.stderr)
        return {}


def load_dk_avg(site: str, slate_id: str) -> dict:
    """{player_id: season avg pts/game} from the slate's salary file (DK
    AvgPointsPerGame, FD FPPG), FLEX rows. Includes K and DST."""
    path = DATA_DIR / f"salaries_{site}_{slate_id}.csv"
    try:
        s = pd.read_csv(path, dtype={"player_id": str})
        if "roster_role" in s.columns:
            f = s[s["roster_role"] == "FLEX"]
            s = f if not f.empty else s
        col = "AvgPointsPerGame" if "AvgPointsPerGame" in s.columns else "FPPG"
        s = s.dropna(subset=["player_id"]).drop_duplicates("player_id")
        vals = pd.to_numeric(s[col], errors="coerce")
        return {pid: float(v) for pid, v in zip(s["player_id"], vals) if pd.notna(v)}
    except Exception as exc:  # noqa: BLE001
        print(f"NOTE: salary-file season averages unavailable ({path.name}: "
              f"{type(exc).__name__}) -- History bullets read 'no games logged yet'.",
              file=sys.stderr)
        return {}


def load_recent_usage(season: int, week: int) -> dict:
    """Real box-score usage, last RECENT_USAGE_LOOKBACK games before `week`
    (touches for RB, attempts for QB, targets for WR/TE)."""
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    try:
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
    except Exception as exc:  # noqa: BLE001
        print(f"NOTE: {path.name} unavailable ({type(exc).__name__}) -- recent-usage "
              f"text will read 'no games logged yet this season'.", file=sys.stderr)
        return {}


def load_kicker_usage(season: int, week: int) -> dict:
    """{player_id: (fg_att/game, pat_att/game, n)} over each kicker's last 3 games before `week`."""
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    try:
        df = pd.read_parquet(path, engine="pyarrow")
        df = df[(df["position"] == "K") & (df["season_type"] == "REG") & (df["week"] < week)]
        df = df.sort_values(["player_id", "week"])
        out = {}
        for pid, g in df.groupby("player_id"):
            r = g.tail(3)
            out[pid] = (float(r["fg_att"].fillna(0).mean()), float(r["pat_att"].fillna(0).mean()), len(r))
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"NOTE: kicker usage unavailable ({path.name}: {type(exc).__name__}) -- "
              f"kicker bullets read 'no kicks logged yet this season'.", file=sys.stderr)
        return {}


def load_snap_recent(season: int, week: int) -> pd.DataFrame:
    path = DATA_DIR / f"snap_counts_{season}.parquet"
    cols = ["player_id", "week", "offense_snaps", "offense_pct"]
    try:
        s = pd.read_parquet(path)
        s = s[(s["week"] < week) & (s["offense_snaps"] > 0)]
        return s[cols].sort_values(["player_id", "week"]).reset_index(drop=True)
    except Exception as exc:  # noqa: BLE001
        print(f"NOTE: snap counts unavailable ({path.name}: {type(exc).__name__}) -- "
              f"usage bullets will read 'no snap data yet'.", file=sys.stderr)
        return pd.DataFrame(columns=cols)


def load_game_log(season: int, week: int, snaps: pd.DataFrame) -> dict:
    """{player_id: (n_games, n_duds)} -- ported from classic @ 51a72f3c."""
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    try:
        ws = pd.read_parquet(path)
        if "season_type" in ws.columns:
            ws = ws[ws["season_type"] == "REG"]
        ws = ws[ws["week"] < week]
        if not snaps.empty:
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
              f"weather clauses skipped.", file=sys.stderr)
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
    """Ported from classic @ 51a72f3c."""
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
# Team maps, tiers
# =============================================================================

def build_team_maps(flex_all: pd.DataFrame) -> tuple:
    """Max positive implied total / over-under per team over ALL FLEX rows
    (K rows and some skill rows carry 0.0 -- never use drop_duplicates('team'))."""
    def pos_max(col):
        out = {}
        if col not in flex_all.columns:
            return out
        for t, g in flex_all.groupby("team"):
            v = pd.to_numeric(g[col], errors="coerce")
            v = v[v > 0]
            if len(v):
                out[t] = float(v.max())
        return out
    return pos_max("implied_total"), pos_max("over_under")


def _matchup_tier(mf: float) -> str:
    return _tier_from_cuts(round(float(mf), 2), MATCHUP_CUTS, "tough")


def env_tier(row: pd.Series, team_implied_total: dict) -> str:
    """Tier vs the league-average team total (not the slate mean). DST reads the
    opponent's total, inverted."""
    if row["position"] == "DST":
        opp = team_implied_total.get(row["opponent"])
        d = (LEAGUE_IMPLIED_BASE - opp) if _is_num(opp) else 0.0
        names = ENV_NAMES_DST
    else:
        own = team_implied_total.get(row["team"])
        d = (own - LEAGUE_IMPLIED_BASE) if _is_num(own) else 0.0
        names = ENV_NAMES_SKILL
    d = round(d, 1)
    if d >= GAME_ENV_STRONG:
        return names[0]
    if d >= GAME_ENV_MARGIN:
        return names[1]
    if d > -GAME_ENV_MARGIN:
        return names[2]
    if d > -GAME_ENV_STRONG:
        return names[3]
    return names[4]


def total_word(ou: float) -> str:
    return _tier_from_cuts(ou, TOTAL_CUTS, "very low")


# =============================================================================
# Role security + bust risk (skill positions)
# =============================================================================

def usage_value(row: pd.Series) -> float:
    pos = row["position"]
    if pos == "QB":
        return row["proj_pass_att"]
    if pos == "RB":
        return row["proj_rush_att"] + row["proj_targets"]
    return row["proj_targets"]  # WR/TE


def add_usage_columns(skill: pd.DataFrame) -> pd.DataFrame:
    """_usage_raw and _team_pos_rank, per position (the only two columns needed
    from classic's score_position_group; the composite is not ported)."""
    s = skill.copy()
    s["_usage_raw"] = s.apply(usage_value, axis=1)
    s["_team_pos_rank"] = s.groupby(["team", "position"])["_usage_raw"].rank(ascending=False, method="first")
    return s


# Ported from cheat_sheet.py compute_role_security() @ 51a72f3c (no salary term). Showdown
# differences: part-time / punt-level / backup-QB split of the bottom tier, and a fifth
# risk word.
def compute_role_security(scored: pd.DataFrame, df_pool: pd.DataFrame, snaps: pd.DataFrame,
                          game_log: dict) -> pd.DataFrame:
    s = scored.copy()
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
    s["_share"] = np.where(s["position"] == "RB", rush_share, tgt_share)

    for col in ("wrw_delta_pts", "wrw_wr_delta_pts", "wrw_te_delta_pts"):
        if col not in s.columns:
            s[col] = np.nan
    s["_stepup_pts"] = s[["wrw_delta_pts", "wrw_wr_delta_pts", "wrw_te_delta_pts"]].fillna(0).clip(lower=0).sum(axis=1)
    s["_stepup_frac"] = s["_stepup_pts"] / s["final_projection"]
    startable = s[s["final_projection"] >= SOLE_TEAMMATE_MIN_PROJ].groupby(["team", "position"]).size()
    s["_n_mates"] = [max(int(startable.get((t, p), 0)) - (1 if fp >= SOLE_TEAMMATE_MIN_PROJ else 0), 0)
                     for t, p, fp in zip(s["team"], s["position"], s["final_projection"])]
    s["_sole"] = (s["_n_mates"] == 0) & (s["position"] == "RB")
    if "engine_projection" not in s.columns:
        s["engine_projection"] = np.nan

    s["_dud_n"] = s["player_id"].map(lambda p: game_log.get(p, (0, 0))[0])
    s["_dud_games"] = s["player_id"].map(lambda p: game_log.get(p, (0, 0))[1])

    pos_dud = dict(DEFAULT_POS_DUD_RATE)
    for p in SKILL_POSITIONS:
        q = s[(s["position"] == p) & (s["final_projection"] >= STARTABLE_MIN_PROJ[p]) & (s["_dud_n"] > 0)]
        if q["_dud_n"].sum() > 0:
            pos_dud[p] = float(q["_dud_games"].sum() / q["_dud_n"].sum())

    out = {k: [] for k in ("_rs", "_risk", "_flags", "_dud_rate", "_usage_eff")}
    for _, r in s.iterrows():
        p = r["position"]
        fp = r["final_projection"]
        stepup, frac = r["_stepup_pts"], r["_stepup_frac"]
        opp = r["_usage_raw"]
        opp_eff = opp * fp / max(fp - stepup, 1.0) if frac >= STEPUP_COUNT_FRAC else opp
        eng = r["engine_projection"]
        if STEPUP_USAGE_FROM_ENGINE and p == "RB" and frac >= STEPUP_COUNT_FRAC and _is_num(eng) and eng > 1.0 and fp > eng:
            opp_eff = max(opp_eff, opp * fp / eng)
        out["_usage_eff"].append(opp_eff)
        V = lin(opp_eff, *VOL_BARS[p])
        if p == "QB":
            S = 1.0 if r["_team_pos_rank"] == 1 else 0.0
        else:
            S = lin(r["_share"], *SHARE_BARS[p]) if _is_num(r["_share"]) else 0.0
        if p != "QB" and frac >= STEPUP_COUNT_FRAC:
            S = 0.5
        N = lin(r["_snap3"], *SNAP_BARS[p]) if _is_num(r["_snap3"]) else np.nan

        T, flags = 1.0, []
        gp = int(_num(r, "games_played", 0.0))
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
            T -= STEPUP_UNPROVEN_T_SOLE if (STEPUP_USAGE_FROM_ENGINE and r["_sole"]) else 0.35
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
        rs = r["_rs"]
        for cut, name in RS_TIERS:
            if rs >= cut:
                return name
        p = r["position"]
        _ue = r["_usage_eff"]
        _sp = r["_stepup_pts"]
        _real_stepup = ((_is_num(_ue) and _ue >= FILL_USAGE[p]) or (_is_num(_sp) and _sp >= 2.0))
        if r["_stepup_frac"] >= STEPUP_UNPROVEN_FRAC and _real_stepup:
            return "unproven new role"
        if p == "QB" and r["_team_pos_rank"] != 1:
            return "backup QB"
        snap = r["_snap3"]
        snap_ok = (not _is_num(snap)) or snap >= FILL_SNAP[p]
        if r["_usage_eff"] >= FILL_USAGE[p] and snap_ok:
            return "part-time role"
        return "punt-level role"

    def risk_tier(r):
        for cut, name in RISK_TIERS:
            if r["_risk"] < cut:
                return name
        return "very high bust risk"

    s["_role_tier"] = s.apply(role_tier, axis=1)
    s["_risk_tier"] = s.apply(risk_tier, axis=1)
    return s


# =============================================================================
# DST upside setup (ported from classic compute_dst_setup() @ 51a72f3c; league-baseline
# environment, no slate rank, dk_avg_ppg from the salary-file map)
# =============================================================================

def compute_dst_setup(scored: pd.DataFrame, df_pool: pd.DataFrame, df_full: pd.DataFrame,
                      team_implied_total: dict, team_ou: dict, dst_feat: dict,
                      rookie_ids: set, weather: dict, snaps: pd.DataFrame = None,
                      week: int = 0) -> pd.DataFrame:
    s = scored.copy()
    s["_setup_score"] = np.nan
    s["_setup_tier"] = ""
    s["_setup_facts"] = ""
    dst = s[s["position"] == "DST"]
    if dst.empty:
        return s

    feat = dst_feat.get("feat")
    lg_sack, lg_int = dst_feat.get("lg_sack"), dst_feat.get("lg_int")
    qbs = (df_pool[df_pool["position"] == "QB"].sort_values("proj_pass_att", ascending=False)
           .drop_duplicates("team").set_index("team"))
    outs = (df_full[(df_full["injury_status"] == "OUT") & df_full["position"].isin(["RB", "WR", "TE"])]
            if "injury_status" in df_full.columns else df_full.iloc[0:0])

    last_snap_wk = (snaps.groupby("player_id")["week"].max().to_dict()
                    if snaps is not None and not snaps.empty else {})
    for idx, r in dst.iterrows():
        team, opp = r["team"], r["opponent"]
        pos_f, neg_f, sc = [], [], 0
        opp_it = team_implied_total.get(opp)
        own_it = team_implied_total.get(team)
        if _is_num(opp_it):
            d = round(round(opp_it, 1) - LEAGUE_IMPLIED_BASE, 1)
            if d <= -GAME_ENV_STRONG:
                sc += 2
                pos_f.append(f"{opp} implied only {opp_it:.1f}, {-d:.1f} below the league average")
            elif d <= -GAME_ENV_MARGIN:
                sc += 1
                pos_f.append(f"{opp} implied only {opp_it:.1f}, {-d:.1f} below the league average")
            elif d >= GAME_ENV_STRONG:
                sc -= 2
                neg_f.append(f"{opp} implied {opp_it:.1f}, {d:.1f} above the league average, works against")
            elif d >= GAME_ENV_MARGIN:
                sc -= 1
                neg_f.append(f"{opp} implied {opp_it:.1f}, {d:.1f} above the league average, works against")
        if _is_num(opp_it) and _is_num(own_it):
            fav = round(own_it, 1) - round(opp_it, 1)
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
            gp = int(_num(q, "games_played", 0.0))
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
            # a player missing from the salary file (NaN average) is skipped, never guessed
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
        if w is not None and not _truthy(w.get("indoor", False)):
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
        s.at[idx, "_setup_score"] = sc
        s.at[idx, "_setup_tier"] = _tier_from_cuts(sc, DST_SETUP_TIERS, "poor")
        s.at[idx, "_setup_facts"] = "; ".join(pos_f + neg_f)
    return s


# =============================================================================
# Quality / confidence (v5 SPEC F)
# =============================================================================

def _history_score(r: pd.Series) -> float:
    avg = _num(r, "dk_avg_ppg")
    if r["position"] in SKILL_POSITIONS and _num(r, "games_played", 0.0) <= 0:
        return 0.3
    if not _is_num(avg):
        return 0.3
    d = r["final_projection"] - avg
    if d >= HISTORY_DIFF_MARGIN:
        return 0.5
    if d <= -HISTORY_DIFF_MARGIN:
        return 0.7
    return 1.0


def compute_quality(s: pd.DataFrame) -> pd.DataFrame:
    """Adds _strength, _q (absolute quality 0-1) and confidence (1-10, fixed
    anchors CONF_Q_LO / CONF_Q_HI)."""
    s = s.copy()
    s["_strength"] = s["final_projection"].apply(lambda x: lin(x, STRENGTH_LO, STRENGTH_HI))
    hist = s.apply(_history_score, axis=1)
    env = s["_env_tier"].map(ENV_SCORE).fillna(0.5)
    mat = s["_m_tier_q"].map(MATCHUP_SCORE).fillna(0.5)

    def role_term(r):
        if r["position"] == "DST":
            sc = r["_setup_score"]
            return float(np.clip(((sc if _is_num(sc) else 0.0) + 2) / 8, 0, 1))
        if r["position"] == "K":
            return K_ROLE
        return float(r["_rs"]) / 100.0
    role = s.apply(role_term, axis=1)
    s["_q"] = (CONF_W_STRENGTH * s["_strength"] + CONF_W_ROLE * role + CONF_W_ENV * env
               + CONF_W_MATCHUP * mat + CONF_W_HISTORY * hist)
    conf = 1 + 9 * ((s["_q"] - CONF_Q_LO) / (CONF_Q_HI - CONF_Q_LO)).clip(0, 1)
    s["confidence"] = conf.round().astype(int)
    return s


# =============================================================================
# Bullets
# =============================================================================

def _tier_label(row: pd.Series):
    pos = row["position"]
    if pos not in DEPTH_TIER_POSITIONS:
        return None
    return f"{pos}1" if row["_team_pos_rank"] == 1 else f"{pos}2_3"


def matchup_info(row: pd.Series, display_matchup: dict, depth_matchup: dict, dst_other: dict):
    """Returns (bullet or None, tier word used for confidence)."""
    pos = row["position"]
    if pos == "K":
        return None, "neutral"
    if pos == "DST":
        own = _num(row, "matchup_factor", 1.0)
        other = dst_other.get(row["player_id"])
        if not _is_num(other):
            return f"Matchup: model factor {own:.2f}x (relative to tonight's other defense only)", "neutral"
        if abs(own - other) <= DST_EVEN_MARGIN:
            return (f"Matchup: about even with tonight's other defense ({own:.2f}x vs {other:.2f}x)"), "neutral"
        word = "better" if own > other else "weaker"
        return (f"Matchup: model rates this the {word} defensive spot of the two "
                f"({own:.2f}x vs {other:.2f}x; relative to tonight's other defense only)"), "neutral"
    opp = row["opponent"]
    if pos == "QB":
        mf = round(float(display_matchup.get((opp, "QB"), 1.0)), 2)
        tier = _matchup_tier(mf)
        return f"Matchup: {opp} allows {mf:.2f}x league-avg to QBs ({tier})", tier
    if pos in DEPTH_TIER_POSITIONS:
        depth_tier = _tier_label(row)
        mf = round(float(depth_matchup.get((opp, depth_tier), 1.0)), 2)
        tier = _matchup_tier(mf)
        tier_display = depth_tier.replace("2_3", "2/3")
        note = "; small numbers, swings a lot" if depth_tier == "TE2_3" else ""
        return f"Matchup ({tier_display}): {opp} allows {mf:.2f}x league-avg ({tier}{note})", tier
    # RB
    mf_rush = round(float(depth_matchup.get((opp, "RB_rush"), 1.0)), 2)
    mf_rec = round(float(depth_matchup.get((opp, "RB_rec"), 1.0)), 2)
    t_rush, t_rec = _matchup_tier(mf_rush), _matchup_tier(mf_rec)
    ra, tg = _num(row, "proj_rush_att", 0.0), _num(row, "proj_targets", 0.0)
    blended = (ra * mf_rush + tg * mf_rec) / (ra + tg) if (ra + tg) > 0 else 1.0
    return (f"Matchup: {opp} allows {mf_rush:.2f}x league-avg rushing pts ({t_rush}), "
            f"{mf_rec:.2f}x receiving pts ({t_rec}) to RBs"), _matchup_tier(blended)


def env_bullet(row: pd.Series, team_implied_total: dict, team_ou: dict) -> str:
    tier = row["_env_tier"]
    ou = team_ou.get(row["team"])
    total_txt = f", game total {ou:.1f} ({total_word(ou)})" if _is_num(ou) else ""
    if row["position"] == "DST":
        opp_it = team_implied_total.get(row["opponent"])
        if not _is_num(opp_it):
            return "Game environment: implied total unavailable"
        return (f"Game environment: opponent {row['opponent']} implied {opp_it:.1f} "
                f"({tier}; league average is {LEAGUE_IMPLIED_BASE}){total_txt}")
    own = team_implied_total.get(row["team"])
    if not _is_num(own):
        return "Game environment: implied total unavailable"
    spread_txt = ""
    opp_it = team_implied_total.get(row["opponent"])
    if _is_num(opp_it):
        diff = round(own, 1) - round(opp_it, 1)
        if diff >= SPREAD_PICKEM:
            spread_txt = f", favored by {diff:.1f}"
        elif diff <= -SPREAD_PICKEM:
            spread_txt = f", underdog by {-diff:.1f}"
        else:
            spread_txt = ", pick'em"
    return (f"Game environment: {row['team']} implied {own:.1f} "
            f"({tier}; league average is {LEAGUE_IMPLIED_BASE}){total_txt}{spread_txt}")


def history_bullet(row: pd.Series):
    """Ported from classic @ 51a72f3c. K and DST use the no-game-count form."""
    pos = row["position"]
    avg_ppg = row.get("dk_avg_ppg")
    gp = row.get("games_played")
    gp = 0 if pd.isna(gp) else int(gp)
    if pos in SKILL_POSITIONS and gp <= 0:
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
    if pos in ("DST", "K"):
        return f"History: {avg_ppg:.1f} pts/game season avg ({trend})", True
    game_word = "game" if gp == 1 else "games"
    return f"History: {avg_ppg:.1f} pts/game season avg, {gp} {game_word} ({trend})", True


def usage_word(pos: str) -> str:
    return {"QB": "pass att/game", "RB": "touches/game"}.get(pos, "targets/game")


def usage_bullet(row: pd.Series, usage_lookup: dict) -> str:
    pos = row["position"]
    stepup_on = _is_num(row["_stepup_frac"]) and row["_stepup_frac"] >= STEPUP_COUNT_FRAC
    if pos == "QB":
        text = f"{row['proj_pass_att']:.1f} pass att + {row['proj_rush_att']:.1f} rush att projected"
    elif pos == "RB":
        touches = row["proj_rush_att"] + row["proj_targets"]
        share = (f", {row['_share']:.0%} of RB carries" if _is_num(row["_share"]) and not stepup_on else "")
        text = (f"{touches:.1f} touches projected ({row['proj_rush_att']:.1f} carries + "
                f"{row['proj_targets']:.1f} targets{share})")
    else:
        share = (f" ({row['_share']:.0%} of team targets)" if _is_num(row["_share"]) and not stepup_on else "")
        text = f"{row['proj_targets']:.1f} targets projected{share}"
    if stepup_on:
        text += f" + injury step-up worth {row['_stepup_pts']:.1f} pts"
        _ue = row.get("_usage_eff")
        if (STEPUP_USAGE_FROM_ENGINE and pos == "RB" and _is_num(_ue)
                and (_ue >= FILL_USAGE["RB"] or row["_stepup_pts"] >= 2.0)):
            text += (f"; inheriting vacated work puts him near {_ue:.0f} "
                     f"{'touch' if round(_ue) == 1 else 'touches'}"
                     + (", with no other startable RB on the team" if row.get("_sole") else ""))
    entry = usage_lookup.get(row["player_id"])
    if entry is None:
        recent = "no games logged yet this season"
    else:
        avg, n = entry
        recent = f"{avg:.1f} {usage_word(pos)} last {n} (actual)"
    if _is_num(row["_snap3"]):
        n = int(row["_snap_n"])
        span = "last game" if n == 1 else f"last {n} games"
        snap = f"{row['_snap3']:.0%} of snaps {span}"
    else:
        snap = "no snap data yet"
    flags = f"; {row['_flags']}" if row["_flags"] else ""
    return f"Usage: {text}; {recent}, {snap} ({row['_role_tier']}{flags})"


def weather_clause(team: str, weather: dict) -> str:
    w = weather.get(team)
    if w is None:
        return ""
    if _truthy(w.get("indoor", False)):
        return "indoors"
    wind, gust, rain = _num(w, "wind_mph"), _num(w, "gust_mph"), _num(w, "precip_mm_hr")
    if not _is_num(wind):
        return ""
    txt = f"wind {wind:.0f} mph"
    if wind >= 15 or (_is_num(gust) and gust >= 30) or (_is_num(rain) and rain >= 0.5):
        txt += ", weather could cut into kicks"
    return txt


def kicker_usage_bullet(row: pd.Series, k_lookup: dict, weather: dict) -> str:
    entry = k_lookup.get(row["player_id"])
    if entry is None:
        base = "no kicks logged yet this season"
    else:
        fg, pat, n = entry
        base = (f"{fg:.1f} FG attempts + {pat:.1f} extra-point attempts per game, "
                f"last {n} {'game' if n == 1 else 'games'}")
    wx = weather_clause(row["team"], weather)
    return f"Kicker usage: {base}" + (f"; {wx}" if wx else "")


def range_bullet(row: pd.Series, dst_miss: float, log_ok: bool) -> str:
    pos = row["position"]
    if pos == "DST":
        lo = max(0.0, row["final_projection"] - dst_miss)
        hi = row["final_projection"] + dst_miss
        return (f"Range: about {lo:.0f}–{hi:.0f} pts in a typical game (DST projections miss by "
                f"about {dst_miss:.1f} pts on average); a defensive or return TD or a safety is "
                f"what pushes it higher, and those aren't modeled")
    p10, p90 = row["statline_p10"], row["statline_p90"]
    rng = f"{p10:.1f}–{p90:.1f} pts" if _is_num(p10) and _is_num(p90) else "range unavailable"
    if pos == "K":
        return (f"Range: {rng} (the model gives every kicker the same band; kicker scoring "
                f"follows game flow, not a player-specific role)")
    n, d = int(row["_dud_n"]), int(row["_dud_games"])
    if n > 0:
        dud = f"under half his average in {d} of {n} games"
    else:
        dud = "no games logged yet" if log_ok else "game log unavailable"
    return f"Range: {rng} ({row['_risk_tier']}; {dud})"


def setup_bullet(row: pd.Series) -> str:
    facts = row["_setup_facts"] or "no standout factors either way"
    return f"Upside setup: {row['_setup_tier']} — {facts}"


def value_tier(value_z: float) -> str:
    if value_z >= VALUE_Z_HIGH:
        return "cheap for this slate"
    if value_z <= VALUE_Z_LOW:
        return "pricey for this slate"
    return "fair for this slate"


def value_bullet(row: pd.Series) -> str:
    ratio = row["final_projection"] / (row["salary"] / 1000.0)
    extra = ""
    if 600 <= row["salary"] <= 1000:
        extra = "; in the $600–$1,000 band that has trailed true $500-or-less punts"
    return f"Value: {ratio:.2f} pts/$1K ({value_tier(row['_value_z'])}{extra})"


def captain_bullet(row, cpt_row, qb_by_team: dict, top_cpt_pid) -> str:
    """CPT facts first, then one rule clause per SHOWDOWN_RULES.md (v5 SPEC E)."""
    if cpt_row is None:
        return "Captain: no captain-slot data found for this player"
    own = _num(cpt_row, "estimated_ownership_pct", 0.0)
    tag = " — most-owned captain tonight" if row["player_id"] == top_cpt_pid else ""
    pos = row["position"]
    starter = qb_by_team.get(row["team"])
    if pos == "QB":
        if row.get("_role_tier") == "backup QB" and starter:
            clause = f"backup; only matters if {starter} leaves the game"
        else:
            clause = ("QB captain is a sound build; his RB or TE has been the better first "
                      "partner than his WR1")
    elif pos == "RB":
        clause = "RB captain is fine; the builds don't require a partner"
    elif pos in DEPTH_TIER_POSITIONS:
        who = starter if starter else "his QB"
        clause = f"fine as captain, but needs {who} in the FLEX (the builds enforce it)"
    elif pos == "K":
        clause = ("not a recommended captain (a kicker was the best captain in 1 of 49 games "
                  "studied; the builds penalize it)")
    else:  # DST
        clause = (f"not a captain option (best captain in 0 of 49 games; the builds exclude it). "
                  f"As a FLEX it only fits lineups with no {row['opponent']} skill players, "
                  f"so it rarely makes a build")
    return (f"Captain: ${cpt_row['salary']:,.0f}, {cpt_row['final_projection']:.1f} pts, "
            f"{own:.1f}% owned as CPT{tag}; {clause}")


def build_rationale(row, cpt_row, ctx: dict) -> tuple:
    pos = row["position"]
    history_line, _ = history_bullet(row)
    matchup, _tier = matchup_info(row, ctx["display_matchup"], ctx["depth_matchup"], ctx["dst_other"])
    env = env_bullet(row, ctx["tim"], ctx["tou"])
    value = value_bullet(row)
    rng = range_bullet(row, ctx["dst_miss"], ctx["log_ok"])
    cap = captain_bullet(row, cpt_row, ctx["qb_by_team"], ctx["top_cpt_pid"])
    if pos == "K":
        bullets = [env, history_line, kicker_usage_bullet(row, ctx["k_usage"], ctx["weather"]),
                   value, rng, cap]
        factors = "game environment, history, kicker usage, value, range, captain"
    elif pos == "DST":
        bullets = [matchup, env, history_line, setup_bullet(row), value, rng, cap]
        factors = "matchup, game environment, history, upside setup, value, range, captain"
    else:
        bullets = [matchup, env, history_line, usage_bullet(row, ctx["usage_lookup"]), value, rng, cap]
        factors = "matchup, game environment, history, usage, value, range, captain"
    return factors, "\n".join(f"• {b}" for b in bullets)


_TAG_ROLE_TONE = {"locked-in role": "pos", "solid role": "neu", "partial role": "warn",
                  "part-time role": "warn", "punt-level role": "neg", "unproven new role": "warn",
                  "backup QB": "neg"}
_TAG_RISK_TONE = {"low bust risk": "pos", "moderate bust risk": "neu", "elevated bust risk": "warn",
                  "high bust risk": "neg", "very high bust risk": "neg"}
_TAG_MATCHUP_TONE = {"smash spot": "pos", "favorable": "pos", "neutral": "neu",
                     "below average": "neg", "tough": "neg"}
_TAG_ENV_TONE = {"elite": "pos", "plus": "pos", "middling": "neu", "low-scoring": "neg",
                 "bottom-tier": "neg", "tough": "neg", "brutal": "neg"}
_TAG_SETUP_TONE = {"strong": "pos", "good": "pos", "neutral": "neu", "poor": "neg"}


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _history_trend(row: pd.Series) -> str:
    """'Proj above avg (+4.1)' / 'Proj below avg (-3.5)' only when the gap clears HISTORY_DIFF_MARGIN."""
    avg = row.get("dk_avg_ppg")
    gp = row.get("games_played")
    gp = 0 if not _is_num(gp) else int(gp)
    if (row["position"] not in ("DST", "K") and gp <= 0) or not _is_num(avg):
        return ""
    d = row["final_projection"] - avg
    if d >= HISTORY_DIFF_MARGIN:
        return f"Proj above avg (+{d:.1f})"
    if d <= -HISTORY_DIFF_MARGIN:
        return f"Proj below avg ({d:.1f})"
    return ""


def _tag_bar(row: pd.Series, tim: dict) -> str:
    """'tone:text' items joined by ';' (the frontend colors them). Numbers match the CSV columns."""
    pos = row["position"]
    items = []
    if pos not in ("K", "DST"):
        mt = row["_m_tier_q"]
        items.append((_TAG_MATCHUP_TONE.get(mt, "neu"), f"{_cap(mt)} matchup"))
    et = row["_env_tier"]
    tot = tim.get(row["opponent"]) if pos == "DST" else tim.get(row["team"])
    pre = "opp " if pos == "DST" else ""
    items.append((_TAG_ENV_TONE.get(et, "neu"),
                  f"{_cap(et)} env ({pre}{tot:.1f})" if _is_num(tot) else f"{_cap(et)} env"))
    if pos in SKILL_POSITIONS:
        rt = row["_role_tier"]
        items.append((_TAG_ROLE_TONE.get(rt, "neu"), f"{_cap(rt)} ({row['_rs']:.0f})"))
        if row["_stepup_frac"] >= STEPUP_COUNT_FRAC:
            items.append(("warn", "Step-up role"))
        k = row["_risk_tier"]
        items.append((_TAG_RISK_TONE.get(k, "neu"), _cap(k)))
    elif pos == "DST" and row["_setup_tier"]:
        st = row["_setup_tier"]
        items.append((_TAG_SETUP_TONE.get(st, "neu"), f"Setup {st}"))
    ptsk = row["final_projection"] / (row["salary"] / 1000.0)
    vt = value_tier(row["_value_z"])
    tone = "pos" if vt.startswith("cheap") else ("neg" if vt.startswith("pricey") else "neu")
    items.append((tone, f"{ptsk:.1f} pts/$1K ({vt})"))
    trend = _history_trend(row)
    if trend:
        items.append(("neu", trend))
    return ";".join(f"{t}:{x}" for t, x in items)


def _risk_badges(row: pd.Series) -> list:
    """Solid Value / Boom/Bust Dart / Fragile Chalk (skill positions only; v5 SPEC H).
    Open call 3 default: Fragile Chalk replaces Solid Value on the same row."""
    if row["position"] not in SKILL_POSITIONS:
        return []
    rs, risk, tier = row["_rs"], row["_risk"], row["_role_tier"]
    value_eligible = row["salary"] <= SOLID_VALUE_MAX_SALARY and row["_value_z"] >= 0
    sole_inheritor = (STEPUP_USAGE_FROM_ENGINE and bool(row.get("_sole"))
                      and row["_stepup_frac"] >= STEPUP_COUNT_FRAC)
    own = row["estimated_ownership_pct"] if _is_num(row["estimated_ownership_pct"]) else 0.0
    chalk = (not sole_inheritor) and own >= FRAGILE_CHALK_OWN and (
        rs < FRAGILE_CHALK_RS or risk >= FRAGILE_CHALK_RISK)
    tags = []
    if value_eligible and tier in GOOD_ROLE_TIERS and risk < SOLID_VALUE_MAX_RISK and not chalk:
        tags.append("Solid Value")
    if value_eligible and (tier in BAD_ROLE_TIERS or risk >= DART_MIN_RISK):
        tags.append("Boom/Bust Dart")
    if chalk:
        tags.append("Fragile Chalk")
    return tags


# =============================================================================
# Main build
# =============================================================================

def build_cheat_sheet_showdown(site: str, slate_id: str, season: int, week: int) -> pd.DataFrame:
    df = load_final_projections_showdown(site, slate_id)
    for c in ("proj_pass_att", "proj_rush_att", "proj_targets"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["estimated_ownership_pct"] = pd.to_numeric(df["estimated_ownership_pct"], errors="coerce").fillna(0.0)

    dk_avg = load_dk_avg(site, slate_id)
    if dk_avg:
        df["dk_avg_ppg"] = df["player_id"].map(dk_avg)
    elif "dk_avg_ppg" not in df.columns:
        df["dk_avg_ppg"] = np.nan

    flex_all = df[(df["roster_role"] == "FLEX") & (df["final_projection"] > 0)
                  & df["position"].isin(SKILL_POSITIONS + ("K", "DST"))].copy()
    cpt_by_pid = {r["player_id"]: r for _, r in df[df["roster_role"] == "CPT"].iterrows()}
    if flex_all.empty or (flex_all["final_projection"] > PROJECTION_THRESHOLD).sum() == 0:
        return pd.DataFrame(columns=OUTPUT_COLUMNS + V4_EXTRA_COLUMNS)

    tim, tou = build_team_maps(flex_all)
    display_matchup = load_display_matchup_factors(site, season, week)
    depth_matchup = load_depth_tier_matchup_factors(site, season, week)
    usage_lookup = load_recent_usage(season, week)
    k_usage = load_kicker_usage(season, week)
    snaps = load_snap_recent(season, week)
    game_log = load_game_log(season, week, snaps)

    # skill positions: role security + bust risk on the whole FLEX pool (shares need every teammate)
    skill = add_usage_columns(flex_all[flex_all["position"].isin(SKILL_POSITIONS)])
    skill = compute_role_security(skill, skill, snaps, game_log) if not skill.empty else skill
    other = flex_all[~flex_all["position"].isin(SKILL_POSITIONS)].copy()
    for c, v in (("_rs", np.nan), ("_risk", np.nan), ("_flags", ""), ("_role_tier", ""),
                 ("_risk_tier", ""), ("_dud_n", 0), ("_dud_games", 0), ("_snap3", np.nan),
                 ("_snap_n", np.nan), ("_share", np.nan), ("_stepup_frac", 0.0),
                 ("_stepup_pts", 0.0), ("_usage_eff", np.nan), ("_sole", False),
                 ("_team_pos_rank", np.nan)):
        other[c] = v
    other.loc[other["position"] == "K", "_role_tier"] = "kicker"
    allp = pd.concat([skill, other], ignore_index=True)

    allp["_env_tier"] = allp.apply(lambda r: env_tier(r, tim), axis=1)

    # DST: two defenses -- each one's factor vs the other's
    dst_rows = allp[allp["position"] == "DST"]
    dst_by_team = {r["team"]: r for _, r in dst_rows.iterrows()}
    dst_other = {}
    for _, r in dst_rows.iterrows():
        o = dst_by_team.get(r["opponent"])
        dst_other[r["player_id"]] = _num(o, "matchup_factor") if o is not None else np.nan

    allp["_m_tier_q"] = allp.apply(
        lambda r: matchup_info(r, display_matchup, depth_matchup, dst_other)[1], axis=1)

    weather = load_weather(season, week)
    if not dst_rows.empty:
        dst_feat = load_dst_features(season, week, dst_rows, tim, tou)
        rookie_ids = load_rookie_ids(season)
        df_full = df[df["roster_role"] == "FLEX"].drop_duplicates("player_id")
        allp = compute_dst_setup(allp, flex_all, df_full, tim, tou, dst_feat, rookie_ids,
                                 weather, snaps, week)
    else:
        allp["_setup_score"] = np.nan
        allp["_setup_tier"] = ""
        allp["_setup_facts"] = ""

    allp = compute_quality(allp)

    # displayed rows: FLEX projection > 2.0
    disp = allp[allp["final_projection"] > PROJECTION_THRESHOLD].copy()
    disp["_value_raw"] = disp["final_projection"] / (disp["salary"] / 1000.0)
    disp["_value_z"] = zscore(disp["_value_raw"])
    disp = disp.sort_values(["_q", "final_projection", "player_id"],
                            ascending=[False, False, True]).reset_index(drop=True)
    disp["overall_rank"] = range(1, len(disp) + 1)
    disp["rank"] = disp.groupby("position").cumcount() + 1

    qb_by_team = {}
    for _, r in skill[skill["position"] == "QB"].iterrows():
        if r["_team_pos_rank"] == 1:
            qb_by_team[r["team"]] = r["player_name"]
    shown = set(disp["player_id"])
    cpt_own = {pid: _num(r, "estimated_ownership_pct", 0.0) for pid, r in cpt_by_pid.items() if pid in shown}
    top_cpt_pid = max(cpt_own, key=cpt_own.get) if cpt_own else None

    ctx = {
        "display_matchup": display_matchup, "depth_matchup": depth_matchup, "dst_other": dst_other,
        "tim": tim, "tou": tou, "usage_lookup": usage_lookup, "k_usage": k_usage,
        "weather": weather, "dst_miss": load_dst_typical_miss(), "log_ok": bool(game_log),
        "qb_by_team": qb_by_team, "top_cpt_pid": top_cpt_pid,
    }

    rows = []
    for _, row in disp.iterrows():
        pos = row["position"]
        cpt_row = cpt_by_pid.get(row["player_id"])
        factors, rationale = build_rationale(row, cpt_row, ctx)
        is_skill = pos in SKILL_POSITIONS
        rows.append({
            "position": pos,
            "rank": int(row["rank"]),
            "overall_rank": int(row["overall_rank"]),
            "player_id": row["player_id"],
            "player_name": row["player_name"],
            "team": row["team"],
            "opponent": row["opponent"],
            "salary": row["salary"],
            "final_projection": row["final_projection"],
            "estimated_ownership_pct": row["estimated_ownership_pct"],
            "confidence": int(row["confidence"]),
            "composite_score": row["final_projection"],
            "top_factors": factors,
            "rationale": rationale,
            "badge": ", ".join(_risk_badges(row)),
            "is_bonus": False,
            "role_security": round(float(row["_rs"]), 1) if is_skill else np.nan,
            "role_tier": row["_role_tier"] if (is_skill or pos == "K") else "",
            "risk_tier": row["_risk_tier"] if is_skill else "",
            "setup_score": row["_setup_score"] if pos == "DST" else np.nan,
            "conf_basis": round(float(row["_q"]), 3),
            "cpt_salary": cpt_row["salary"] if cpt_row is not None else np.nan,
            "cpt_projection": cpt_row["final_projection"] if cpt_row is not None else np.nan,
            "cpt_ownership_pct": _num(cpt_row, "estimated_ownership_pct") if cpt_row is not None else np.nan,
            "value_per_k": round(float(row["_value_raw"]), 2),
            "matchup_tier": row["_m_tier_q"] if pos not in ("K", "DST") else "",
            "env_tier": row["_env_tier"],
            "history_trend": _history_trend(row),
            "setup_tier": row["_setup_tier"] if pos == "DST" else "",
            "tag_bar": _tag_bar(row, tim),
        })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS + V4_EXTRA_COLUMNS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate-id", type=str, required=True)
    parser.add_argument("--out", type=str, default=None,
                        help="Write the CSV here instead of output/cheat_sheet_{site}_{slate_id}.csv")
    args = parser.parse_args()

    sheet = build_cheat_sheet_showdown(args.site, args.slate_id, args.season, args.week)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
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
