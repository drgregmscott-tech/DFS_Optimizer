"""
build_projections.py
=====================

Session 2.4 -- Full Blend Pipeline.

For a given site (DK/FD), season, and target week, merges the outputs of
Sessions 2.1-2.3 plus that site's salary file into one clean weekly
projections table: final_projections_{site}_{slate_id}.csv

final_projection = (0.5 * season_avg + 0.5 * recent_form) * matchup_factor * vegas_factor

Decisions 1-8b are unchanged from prior sessions (see git history for full
docstring). Decision #9 is new this session:

9. Salary-file-based opponent map fallback. When the schedule-based
opponent_map comes back empty for the slate's teams -- e.g. a Madden Sim
slate whose --week has no real NFL games in schedules_{season}.parquet --
build_opponent_map_from_vegas() infers matchups from the vegas file using
over_under as the game key: teams sharing the same over_under value are
opponents. This is unambiguous for DK Madden Sim slates because each game
has a distinct total. The fallback only fires when the schedule produces
zero pairs for slate teams; real-season runs are unaffected.

FIX (same session): output filename is now final_projections_{site}_{slate_id}.csv
(was final_projections_{site}_{week}.csv). Two slates in the same week no
longer overwrite each other. --slate-id drives both the salary input file
and the output file.

Usage:
python3 build_projections.py --site dk --season 2025 --week 23 --slate-id madden_07312026
python3 build_projections.py --site dk --season 2025 --week 10 --slate-id classic_wk10
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import SITE_CONFIGS, normalize_team
from ownership_heuristic import (
    compute_chalk_scores, compute_estimated_ownership,
    build_showdown_role_group, compute_showdown_role_budgets,
    compute_position_slot_budgets,
)
import salary_anchor

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"

POSITIONS = ["QB", "RB", "WR", "TE"]
BASELINE_WEIGHT = 0.5
RECENT_FORM_WEIGHT = 0.5
SALARY_ANCHOR_WEIGHT_DEFAULT = 0.0
NO_GAME_SENTINEL = "BYE_OR_UNKNOWN"
DST_ASSUMED_GAMES_PLAYED = 99

# Session 13.3 -- Showdown / Single-Game projection & scoring multiplier.
# Both sites confirmed identical (Session 13.2 handoff): the captain-
# equivalent slot (DK's CPT, FD's MVP) scores 1.5x the FLEX-priced
# player's points. No per-site special-casing needed here.
CAPTAIN_MULTIPLIER = 1.5
CAPTAIN_ROLES = {"CPT", "MVP"}


# ---------------------------------------------------------------------------
# Step 0: Load inputs
# ---------------------------------------------------------------------------

def load_baseline_recent_form(site, season, week):
    path = OUTPUT_DIR / f"baseline_recent_form_{site}_{season}_{week}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run projections_baseline.py --site {site} "
            f"--season {season} --week {week} first (Session 2.1)."
        )
    return pd.read_csv(path, dtype={"player_id": str})


def load_matchup_factors(site, season, week):
    path = OUTPUT_DIR / f"matchup_factors_{site}_{season}_{week}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run projections_matchup.py --site {site} "
            f"--season {season} --week {week} first (Session 2.2)."
        )
    return pd.read_csv(path)


def load_vegas_implied_totals(slate_id):
    """Session 13.5-pause Bug Fix (decision #10 continued): was keyed by
    `week`, not `slate_id`. `week` here was never anything but a filename
    label borrowed from the (unrelated) historical-stats-lookback week --
    see vegas_odds.py's module docstring for the full reasoning and the
    real slate this caused a wrong-data-reused bug on. Keying by slate_id
    instead removes the NFL-week concept from vegas lookup entirely, so
    preseason/Madden-Sim/Thanksgiving/playoff slates -- none of which have
    a clean "NFL week" -- no longer need one just to find their own vegas
    file, and two different slates can never collide on a shared week
    number the way vegas_implied_totals_23.csv did here.
    """
    path = OUTPUT_DIR / f"vegas_implied_totals_{slate_id}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run vegas_odds.py --slate-id {slate_id} first (Session 2.3)."
        )
    return pd.read_csv(path)


def load_salaries(site, slate_id):
    path = DATA_DIR / f"salaries_{site}_{slate_id}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run ingest_salaries.py --site {site} "
            f"--slate-id {slate_id} first (Session 1.3)."
        )
    site_id_col = SITE_CONFIGS[site]["site_id_col"]
    df = pd.read_csv(path, dtype={"player_id": str, site_id_col: str})
    required = {"player_id", "name", "salary", "normalized_team", "position_upper", site_id_col}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path} is missing expected columns: {sorted(missing)}. "
            f"ingest_salaries.py output schema may have changed."
        )
    return df


def load_schedule(season):
    path = DATA_DIR / f"schedules_{season}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run ingest_historical.py --season {season}."
        )
    df = pd.read_parquet(path)
    season_type_col = "season_type" if "season_type" in df.columns else (
        "game_type" if "game_type" in df.columns else None
    )
    if season_type_col is None or not {"week", "home_team", "away_team"}.issubset(df.columns):
        raise SystemExit(
            f"{path} missing expected columns. Present: {sorted(df.columns)}."
        )
    df = df[df[season_type_col] == "REG"]
    return df[["week", "home_team", "away_team"]].copy()


# ---------------------------------------------------------------------------
# Step 1: Opponent map -- schedule-based with vegas fallback (decision #9)
# ---------------------------------------------------------------------------

def load_real_team_for_week(season, week):
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not path.exists():
        print(f"NOTE: {path} not found -- skipping team-drift correction.", file=sys.stderr)
        return False, pd.Series(dtype=object)
    df = pd.read_parquet(path)
    season_type_col = "season_type" if "season_type" in df.columns else "game_type"
    wk = df[(df[season_type_col] == "REG") & (df["week"] == week)]
    if wk.empty:
        return False, pd.Series(dtype=object)
    return True, wk.drop_duplicates(subset=["player_id"]).set_index("player_id")["team"]


def build_opponent_map(schedule, week):
    """Team -> opponent from real NFL schedule for given week."""
    wk = schedule[schedule["week"] == week]
    opp_map = {}
    for row in wk.itertuples():
        opp_map[row.home_team] = row.away_team
        opp_map[row.away_team] = row.home_team
    return opp_map


def build_opponent_map_from_salaries(salaries, site):
    """Decision #9 (extended -- real FD Week 1 2026 slate): infer matchups
    directly from the salary file's own game-pairing column.

    DK's salary CSV export carries this as a column literally named
    'Game Info', with values like 'CHI@BAL 07/31/2026 12:00PM ET'. This
    function originally only recognized that exact column name, on the
    (untested) assumption FD's export matched it. It does not: a real FD
    Week 1 2026 export carries the same AWAY@HOME pairing under a
    differently-named column, 'Game', with no trailing date/time (e.g.
    'NO@DET'). Both strings parse identically with the existing logic
    below, since FD's is a strict prefix of DK's format -- only the
    column name needed to change.

    Team codes are then run through normalize_team(), which the original
    version did not do. This is not a defensive add: the same real FD
    export uses 'JAC' for Jacksonville, while every other part of this
    pipeline (schedules, vegas, DST) normalizes to 'JAX'
    (BASE_TEAM_ABBREV_MAP). Without normalizing here, a Jacksonville game
    would parse successfully but produce an opponent-map key that never
    matches normalized_team anywhere downstream -- silently, with no
    error, exactly the NOR/NO failure mode BASE_TEAM_ABBREV_MAP's own
    comment already describes for a different team. `site` is required
    (not optional) so this can never silently normalize against the
    wrong site's overrides.

    This is the most reliable source of matchup information for any
    slate type -- Madden Sim, preseason, or regular season -- because it
    reflects exactly what the site has on the slate, regardless of
    whether a matching NFL schedule week exists.

    Parses each unique game string, extracts the two team abbreviations,
    and builds the bidirectional team -> opponent map. Falls back
    gracefully (empty map) if neither known column is present or a value
    is malformed.
    """
    game_col = next(
        (c for c in ("Game Info", "Game") if c in salaries.columns), None)
    if game_col is None:
        return {}

    opp_map = {}
    seen = set()
    for game_info in salaries[game_col].dropna().unique():
        # DK: "AWAY@HOME DATE TIME ET" e.g. "CHI@BAL 07/31/2026 12:00PM ET"
        # FD: "AWAY@HOME" e.g. "NO@DET" -- split(" ")[0] is a no-op on FD's
        # string and strips DK's trailing date/time, so one line handles both.
        matchup_part = game_info.split(" ")[0]
        if "@" not in matchup_part:
            continue
        away, home = matchup_part.split("@", 1)
        away = normalize_team(away.strip(), site)
        home = normalize_team(home.strip(), site)
        game_key = tuple(sorted([away, home]))
        if game_key in seen:
            continue
        seen.add(game_key)
        opp_map[away] = home
        opp_map[home] = away
    return opp_map


# ---------------------------------------------------------------------------
# Step 2: Vegas factors
# ---------------------------------------------------------------------------

def build_vegas_factors(vegas, opponent_map):
    vegas = vegas.copy()
    vegas["expected_opponent"] = vegas["team"].map(opponent_map)
    this_week = vegas[vegas["opponent"] == vegas["expected_opponent"]].copy()
    this_week = this_week.drop_duplicates(subset=["team"])

    if this_week.empty:
        print(
            "WARNING: no vegas rows matched this week's schedule -- "
            "every player gets neutral vegas_factor=1.0.",
            file=sys.stderr,
        )
        return pd.DataFrame(columns=["team", "vegas_factor", "opponent", "implied_total", "over_under"])

    league_avg = this_week["implied_total"].mean()
    this_week["vegas_factor"] = this_week["implied_total"] / league_avg
    keep_cols = ["team", "vegas_factor", "opponent", "implied_total"]
    if "over_under" in this_week.columns:
        keep_cols.append("over_under")
    return this_week[keep_cols]


# ---------------------------------------------------------------------------
# Session 10.4 -- distributional DST
# ---------------------------------------------------------------------------

def _build_dst_distributional(salaries, vegas, site, season, week, sims, seed,
                              opponent_map=None, vegas_factors=None):
    """Decision #10 (Session 13.5-pause Bug Fix A): `opponent_map` and
    `vegas_factors` are new. Before this fix, DST's opponent/opp_implied/
    opp_sack_allowed_rate/opp_dropbacks/opponent-QB were all resolved
    independently of the Game-Info opponent_map that skill players and
    kickers already use (build_opponent_map_from_salaries(), decision #9),
    straight from the raw vegas file's real-2025-schedule opponent column.
    On any slate where the in-slate pairing differs from the real schedule
    (every Madden Sim slate, every preseason Showdown slate so far), that
    meant a defense's own simulation ran against the wrong offense's rates
    AND its own displayed opponent/implied_total/over_under disagreed with
    its own team's skill players in the output CSV / Slate Overview panel.
    Confirmed real via a real ARI/CAR Showdown slate and a real Madden
    slate -- see Handoff_13.5_Pause_BugFixes.md, Bug Fix Session A.

    `opponent_map` is threaded into dst_model.build_features() so the
    SIMULATION's opponent-conditioned inputs use the correct in-slate
    opponent (dst_model.py decision #23).

    `vegas_factors` (already built by build_vegas_factors() for skill
    players) is used to source the DISPLAYED implied_total/over_under --
    option 2, full consistency: a DST row and its own team's skill players
    must show identical opponent/implied_total/over_under, including
    falling back to the same 0.0 default when no matching vegas line exists
    for the in-slate pairing (a real, separate data-availability gap on
    preseason/Madden slates -- Handoff's "Bug/Question B", not fixed here).
    This is display-only: the simulation itself still uses the real
    per-team vegas/team-stats data for the corrected opponent (best real
    signal available), even on rows where the stricter "matched a vegas
    line for this exact in-slate pairing" filter used for display comes up
    empty.
    """
    import dst_model

    defense_values = SITE_CONFIGS[site]["defense_position_values"]
    site_id_col = SITE_CONFIGS[site]["site_id_col"]
    dst = salaries[salaries["position_upper"].isin(defense_values)].copy()
    dst = dst[dst["player_id"].notna()]
    dst = dst.rename(columns={
        "normalized_team": "team", "position_upper": "position",
        "name": "player_name", site_id_col: "site_player_id",
    })[["player_id", "player_name", "position", "team", "salary", "site_player_id"]]

    model_obj = dst_model.load_model()
    games = None
    games_path = DATA_DIR / "games.parquet"
    if games_path.exists():
        games = pd.read_parquet(games_path)

    teams = sorted(dst["team"].dropna().unique())
    feat = dst_model.build_features(season, week, teams, vegas, model_obj, games=games,
                                    opponent_map=opponent_map)
    sim = dst_model.simulate(
        feat, site, model_obj,
        n_sims=sims or dst_model.DEFAULT_SIMS,
        seed=seed if seed is not None else dst_model.DEFAULT_SEED)

    sim = sim.merge(feat[["team", "has_game", "opponent", "own_implied",
                           "over_under", "opp_implied"]], on="team", how="left")
    dst = dst.merge(sim, on="team", how="left")

    n_bye = int((~dst["has_game"].fillna(False)).sum())
    played = dst["has_game"].fillna(False)

    league_avg = float(vegas["implied_total"].mean())
    dst["vegas_factor"] = np.where(
        played & dst["opp_implied"].notna() & (dst["opp_implied"] > 0),
        league_avg / dst["opp_implied"].replace(0, np.nan), 1.0)

    dst["final_projection"] = dst["final_projection"].fillna(0.0).clip(lower=0.0)
    dst.loc[~played, "final_projection"] = 0.0
    dst["sigma"] = dst["sigma"].fillna(0.0)
    dst.loc[~played, "sigma"] = 0.0
    dst["season_avg"] = dst["final_projection"]
    dst["recent_form"] = dst["final_projection"]

    league_proj = float(dst.loc[played, "final_projection"].mean()) if played.any() else 0.0
    dst["matchup_factor"] = np.where(
        played & (league_proj > 0), dst["final_projection"] / max(league_proj, 1e-9), 1.0)

    dst["opponent"] = dst["opponent"].where(played).fillna("BYE_OR_UNKNOWN")

    # Decision #10 continued -- see this function's docstring. Display-only:
    # source implied_total/over_under from the same vegas_factors table
    # skill players/kickers use, not the raw per-team vegas row, so a
    # defense agrees with its own team's skill players in the output.
    if vegas_factors is not None:
        vf = vegas_factors.drop_duplicates(subset=["team"]).set_index("team")
        dst["implied_total"] = dst["team"].map(vf["implied_total"]) if "implied_total" in vf.columns else np.nan
        dst["over_under"] = dst["team"].map(vf["over_under"]) if "over_under" in vf.columns else np.nan
    else:
        # Safety net only -- build_projections.py's own pipeline always
        # passes vegas_factors. Falls back to the pre-fix raw-vegas value
        # rather than crashing if some other caller doesn't supply it.
        dst["implied_total"] = dst["own_implied"]
    dst["implied_total"] = dst["implied_total"].where(played).fillna(0.0)
    dst["over_under"] = dst["over_under"].where(played).fillna(0.0)
    dst["dst_p10"] = dst["p10"].fillna(0.0).where(played, 0.0)
    dst["dst_p90"] = dst["p90"].fillna(0.0).where(played, 0.0)

    print(f"{n_bye} defense(s) had no game this week (bye) -- final_projection forced to 0.0.")
    print(f"DST model: distributional (Session 10.4). "
          f"mean projection {dst.loc[played, 'final_projection'].mean():.2f}, "
          f"sigma {dst.loc[played, 'sigma'].mean():.2f} "
          f"(range {dst.loc[played, 'sigma'].min():.2f}-{dst.loc[played, 'sigma'].max():.2f}).")

    return dst[[
        "player_id", "player_name", "position", "team", "salary", "site_player_id",
        "season_avg", "recent_form", "matchup_factor", "vegas_factor",
        "final_projection", "opponent", "implied_total", "over_under",
        "sigma", "dst_p10", "dst_p90",
    ]]


def _build_kicker_projections(salaries, site, opponent_map):
    """Session 13.1 -- wires kicker_model.py into the main projections
    output, alongside skill positions and DST.

    Unlike DST, the kicker model itself is NOT team- or matchup-conditioned
    (fit_kicker_model.py decision #2 -- no measured volume signal from
    team identity or Vegas implied total), so this function's only real
    jobs are: (a) select the K rows from the salary pool, (b) hand them to
    kicker_model.project_kickers(), and (c) zero out any kicker whose team
    has no game this week -- same fail-loud bye handling as
    _build_dst_distributional's decision #16 equivalent, since a bye-week
    kicker with a nonzero projection would be a real bug, not a modeling
    nuance.

    Returns an empty (correctly-columned) DataFrame when the slate has no
    K rows at all -- true for every classic DK/FD slate today (FD has
    carried no K slot since 2018; DK classic has never had one), and
    expected to be nonempty once Session 13.2's Showdown ingest ships.
    """
    import kicker_model

    site_id_col = SITE_CONFIGS[site]["site_id_col"]
    k = salaries[salaries["position_upper"] == "K"].copy()
    k = k[k["player_id"].notna()]
    k = k.rename(columns={
        "normalized_team": "team", "position_upper": "position",
        "name": "player_name", site_id_col: "site_player_id",
    })[["player_id", "player_name", "position", "team", "salary", "site_player_id"]]

    empty_cols = [
        "player_id", "player_name", "position", "team", "salary", "site_player_id",
        "season_avg", "recent_form", "matchup_factor", "vegas_factor",
        "final_projection", "opponent", "implied_total", "over_under",
        "sigma", "dst_p10", "dst_p90",
    ]
    if k.empty:
        return pd.DataFrame(columns=empty_cols)

    model_obj = kicker_model.load_model()
    proj = kicker_model.project_kickers(k[["player_id", "team"]], model_obj, site=site)
    k = k.merge(proj[["player_id", "final_projection", "sigma", "p10", "p90"]],
                on="player_id", how="left")

    k["opponent"] = k["team"].map(opponent_map)
    played = k["opponent"].notna()
    n_bye = int((~played).sum())
    k.loc[~played, ["final_projection", "sigma", "p10", "p90"]] = 0.0
    k["opponent"] = k["opponent"].fillna(NO_GAME_SENTINEL)

    # season_avg/recent_form/matchup_factor/vegas_factor/implied_total/
    # over_under have no equivalent in this model (decision #2 -- no
    # team-conditioned signal exists to put in them) -- carried as neutral
    # placeholders so the output schema matches skill/DST rows exactly,
    # same pattern DST uses for the columns skill positions don't have.
    k["season_avg"] = k["final_projection"]
    k["recent_form"] = k["final_projection"]
    k["matchup_factor"] = 1.0
    k["vegas_factor"] = 1.0
    k["implied_total"] = 0.0
    k["over_under"] = 0.0
    k = k.rename(columns={"p10": "dst_p10", "p90": "dst_p90"})  # reuse DST's p10/p90 column names, not position-specific

    print(f"Kicker model (Session 13.1): {len(k)} kicker(s) in pool, {n_bye} bye/no-game. "
          f"mean projection {k.loc[played, 'final_projection'].mean() if played.any() else 0.0:.2f}, "
          f"mean sigma {k.loc[played, 'sigma'].mean() if played.any() else 0.0:.2f}.")

    return k[empty_cols]


def build_dst_projections(salaries, vegas, site, *, model="legacy",
                           season=None, week=None, sims=None, seed=None,
                           opponent_map=None, vegas_factors=None):
    if model not in ("legacy", "distributional"):
        raise SystemExit(f"build_dst_projections: unknown model {model!r}.")
    if model == "distributional":
        if season is None or week is None:
            raise SystemExit("build_dst_projections(model='distributional') needs season and week.")
        return _build_dst_distributional(salaries, vegas, site, season, week, sims, seed,
                                         opponent_map=opponent_map, vegas_factors=vegas_factors)

    defense_values = SITE_CONFIGS[site]["defense_position_values"]
    site_id_col = SITE_CONFIGS[site]["site_id_col"]
    avg_ppg_col = SITE_CONFIGS[site]["avg_ppg_col"]
    dst = salaries[salaries["position_upper"].isin(defense_values)].copy()
    dst = dst[dst["player_id"].notna()]
    if avg_ppg_col not in dst.columns:
        raise SystemExit(
            f"build_dst_projections (legacy): expected column '{avg_ppg_col}' "
            f"for site='{site}'. Columns present: {sorted(dst.columns.tolist())}."
        )
    dst = dst.rename(columns={
        "normalized_team": "team", "position_upper": "position",
        "name": "player_name", site_id_col: "site_player_id",
    })[["player_id", "player_name", "position", "team", "salary", "site_player_id", avg_ppg_col]]

    dst["season_avg"] = dst[avg_ppg_col].fillna(0.0)
    dst["recent_form"] = dst["season_avg"]
    dst = dst.drop(columns=[avg_ppg_col])
    dst["matchup_factor"] = 1.0

    implied_by_team = vegas.drop_duplicates(subset=["team"]).set_index("team")["implied_total"]
    league_avg = vegas["implied_total"].mean()
    over_under_by_team = None
    if "over_under" in vegas.columns:
        over_under_by_team = vegas.drop_duplicates(subset=["team"]).set_index("team")["over_under"]

    # If a salary-derived opponent_map was provided (decision #9 fallback),
    # use it instead of the vegas file opponent column -- the vegas file maps
    # each team to its real NFL opponent, not its Madden Sim opponent.
    if opponent_map:
        opponent_by_team = pd.Series(opponent_map)
    else:
        opponent_by_team = vegas.drop_duplicates(subset=["team"]).set_index("team")["opponent"]

    has_game = dst["team"].isin(opponent_by_team.index)
    n_bye = (~has_game).sum()

    dst["opponent"] = dst["team"].map(opponent_by_team).where(has_game)
    dst["implied_total"] = dst["team"].map(implied_by_team).where(has_game)
    if over_under_by_team is not None:
        dst["over_under"] = dst["team"].map(over_under_by_team).where(has_game)
    else:
        dst["over_under"] = None

    opp_implied = dst["team"].map(opponent_by_team).map(implied_by_team)
    dst["vegas_factor"] = league_avg / opp_implied
    dst["vegas_factor"] = dst["vegas_factor"].where(has_game, 1.0)
    dst["final_projection"] = (dst["season_avg"] * dst["vegas_factor"]).clip(lower=0.0)
    dst.loc[~has_game, "final_projection"] = 0.0

    print(f"{n_bye} defense(s) had no game this week (bye) -- final_projection forced to 0.0.")

    dst["opponent"] = dst["opponent"].fillna("BYE_OR_UNKNOWN")
    dst["implied_total"] = dst["implied_total"].fillna(0.0)
    dst["over_under"] = dst["over_under"].fillna(0.0)

    return dst[[
        "player_id", "player_name", "position", "team", "salary", "site_player_id",
        "season_avg", "recent_form", "matchup_factor", "vegas_factor",
        "final_projection", "opponent", "implied_total", "over_under",
    ]]


# ---------------------------------------------------------------------------
# Ownership + salary anchor
# ---------------------------------------------------------------------------

def add_ownership_columns(df, site, layered=True):
    scored = compute_chalk_scores(df, site)
    scored = compute_estimated_ownership(scored, site)
    # Week 2 post-mortem: replace the heuristic estimate with the layered
    # model (heuristic + optimizer-implied exposure + salary/reliability
    # layer). DK only, and a no-op without data/ownership_model_dk.json or on
    # any failure -- see ownership_model.py. layered=False returns the pure
    # heuristic (used by fit_ownership_model.py to build its own features).
    if layered:
        import ownership_model
        scored = ownership_model.refine_ownership(
            scored, site, compute_position_slot_budgets(site))
    keep = ["player_id", "chalk_score", "estimated_ownership_pct"]
    if "estimated_ownership_pct_heuristic" in scored.columns:
        keep.append("estimated_ownership_pct_heuristic")
    ownership_cols = scored[keep]
    merged = df.merge(ownership_cols, on="player_id", how="left")
    n_missing = merged["chalk_score"].isna().sum()
    if n_missing:
        raise SystemExit(
            f"add_ownership_columns: {n_missing} player(s) got no chalk_score -- "
            f"player_id dtype/duplicate mismatch?"
        )
    return merged


def apply_salary_anchor(df, site, weight, cold_start, k):
    artifact = salary_anchor.load_anchor(site)
    out = df.copy()
    out["salary_anchor"] = salary_anchor.anchor_points(artifact, out["position"], out["salary"])
    w = salary_anchor.effective_weight(weight, out["_anchor_games"], cold_start, k)
    no_game = out["opponent"].astype(str) == NO_GAME_SENTINEL
    w = pd.Series(w, index=out.index).where(~no_game, 0.0)
    out["final_projection_pre_anchor"] = out["final_projection"]
    out["anchor_weight_used"] = w.round(4)
    out["final_projection"] = salary_anchor.blend(
        out["final_projection"], out["salary_anchor"], w.to_numpy()
    )
    out["points_above_anchor"] = (out["final_projection"] - out["salary_anchor"]).round(4)
    out.loc[no_game, "points_above_anchor"] = 0.0
    n_blended = int((w > 0).sum())
    n_excluded = int(no_game.sum())
    n_rescued = int(((out["final_projection_pre_anchor"] == 0.0) & (out["final_projection"] > 0.0)).sum())
    mode = f"cold-start schedule (floor {weight}, k={k})" if cold_start else f"flat weight {weight}"
    print(f"Salary anchor ON -- {mode}. Blended {n_blended}/{len(out)} rows; "
          f"{n_excluded} confirmed-no-game excluded; {n_rescued} cold-start rescued.")
    return out


# ---------------------------------------------------------------------------
# Session 13.3 -- Showdown / Single-Game projection & scoring multiplier
# ---------------------------------------------------------------------------

def is_showdown_slate(salaries):
    """Detect a Showdown/Single-Game salary file via the `slate_format`
    column Session 13.2 added to ingest_salaries.py's output. Falls back
    to False (classic behavior) if the column is entirely absent -- e.g.
    a salary file produced by a pre-13.2 build of ingest_salaries.py --
    preserving full backward compatibility, same discipline Session 13.2
    itself followed for this same column.

    Fails loudly if the column is present but mixed (more than one
    distinct value) -- a single salary file should never span two
    formats; that would indicate two slates got concatenated or the
    ingest step is corrupted, not a legitimate state to silently handle.
    """
    if "slate_format" not in salaries.columns:
        return False
    formats = salaries["slate_format"].dropna().unique()
    if len(formats) > 1:
        raise SystemExit(
            f"Salary file has mixed slate_format values {sorted(formats)} -- "
            f"expected exactly one format for the whole slate. "
            f"ingest_salaries.py output may be corrupted, or two slates' "
            f"salary files got concatenated by mistake."
        )
    return bool(len(formats)) and formats[0] == "showdown"


def apply_captain_multiplier(flex_out, captain_salaries, site):
    """Session 13.3: derive the CPT (DK) / MVP (FD) row's projection from
    the already-built FLEX-priced player's projection, rather than
    re-running the full projection pipeline a second time. Applies
    uniformly across whichever model produced the FLEX projection (skill
    stat-line model, DST model, or Session 13.1's kicker model) -- no
    per-position special-casing, matching the roadmap card's explicit
    intent.

    Salary and site_player_id are NOT re-derived -- they're taken as-is
    from the raw ingest, which already carries the site's real 1.5x
    captain-priced salary (Session 13.2).

    sigma/dst_p10/dst_p90 (present for DST/kicker rows only) are also
    scaled by 1.5x: captain points are a deterministic 1.5x rescaling of
    the same underlying points distribution, not an independent draw, so
    Var(1.5X) = 1.5^2 * Var(X) -> sigma scales by exactly 1.5x, and the
    percentile bounds (also linear functions of the same distribution)
    scale the same way.

    Fails loudly (not a silent left-join drop) if any FLEX player has no
    matching CPT/MVP row -- Showdown salary files should always carry
    both linked rows for every player (Session 13.2's ingest contract).
    """
    site_id_col = SITE_CONFIGS[site]["site_id_col"]
    link_cols = captain_salaries[["player_id", "salary", site_id_col, "roster_role"]].rename(
        columns={site_id_col: "site_player_id"}
    )

    base = flex_out.drop(columns=["salary", "site_player_id", "roster_role"], errors="ignore")
    cap = base.merge(link_cols, on="player_id", how="left")

    unlinked = cap[cap["roster_role"].isna()]
    if not unlinked.empty:
        raise SystemExit(
            f"apply_captain_multiplier: {len(unlinked)} FLEX player(s) had no "
            f"matching CPT/MVP row in the salary file -- every player in a "
            f"Showdown pool should have both rows (Session 13.2). Unlinked "
            f"player_id(s): {unlinked['player_id'].tolist()[:10]}"
            f"{'...' if len(unlinked) > 10 else ''}."
        )

    for col in ["final_projection", "season_avg", "recent_form",
                "sigma", "dst_p10", "dst_p90",
                # Session 14.0: build_projections_statline.py's own p10/p90
                # audit columns use a different name than DST/kicker's
                # dst_p10/dst_p90 -- scaled the same way for the same reason
                # (a deterministic 1.5x rescaling of the same distribution).
                # Absent (and therefore a no-op) on the legacy engine.
                "statline_p10", "statline_p90"]:
        if col in cap.columns:
            cap[col] = cap[col] * CAPTAIN_MULTIPLIER

    return cap


def add_showdown_ownership_columns(df, site):
    """Session 13.3b: real Showdown ownership computation, replacing
    Session 13.3's original NaN placeholder (see that decision's original
    rationale below -- still correct as far as it goes, it just stopped
    one step short of actually building the fix it called for).

    Reuses ownership_heuristic.py's existing 5-feature chalk_score blend
    and softmax ownership-share mechanism completely unchanged -- the
    only thing that differs for Showdown is the GROUPING unit: classic
    groups by position_group (roster slots are position-specific);
    Showdown has no position-based slots at all, just one CPT/MVP-
    equivalent slot and N FLEX slots with ANY position eligible in
    either. build_showdown_role_group()/compute_showdown_role_budgets()
    supply that alternate grouping, anchored to the same real
    roster-slot math as classic's decision #5 (SITE_CONFIGS[site]
    ['showdown']['roster_slots'], Session 13.2), not a guess.

    Same UNFIT starting-guess blend weights and softmax temperature as
    classic -- no real Showdown ownership data exists any more than real
    classic ownership data does, so this doesn't pretend to be better
    calibrated than the classic heuristic it's built from. Session
    11.1's already-planned retuning (once real ownership data exists)
    now covers both classic and Showdown groupings, not a second
    separate set of magic numbers to track.

    Original Session 13.3 rationale for why this couldn't just reuse
    classic's add_ownership_columns() unchanged: Phase 11's model was FIT
    (informally, as an unfit starting guess) against classic's
    position-grouped concentration pattern, and CPT selection behaves
    very differently from FLEX selection. That's still true -- it's why
    the grouping had to change, not why ownership had to be skipped
    entirely.
    """
    df = df.copy()
    df["_showdown_role_group"] = build_showdown_role_group(df)
    budgets = compute_showdown_role_budgets(site)

    scored = compute_chalk_scores(df, site, group_col="_showdown_role_group")
    scored = compute_estimated_ownership(
        scored, site, group_col="_showdown_role_group", budgets=budgets
    )

    # Merge on (player_id, roster_role), NOT player_id alone -- a Showdown
    # pool has TWO rows per player_id (FLEX + CPT/MVP), and a player's CPT
    # ownership share is a genuinely different real-world quantity from
    # their FLEX ownership share (different salary, different group, often
    # a different chalk_score), unlike classic where player_id is unique
    # per pool.
    ownership_cols = scored[["player_id", "roster_role", "chalk_score", "estimated_ownership_pct"]]
    merged = df.drop(columns=["_showdown_role_group"]).merge(
        ownership_cols, on=["player_id", "roster_role"], how="left"
    )
    n_missing = merged["chalk_score"].isna().sum()
    if n_missing:
        raise SystemExit(
            f"add_showdown_ownership_columns: {n_missing} player-role row(s) "
            f"got no chalk_score -- player_id/roster_role dtype or duplicate "
            f"mismatch?"
        )
    merged["ownership_available"] = True
    return merged


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_final_projections(site, season, week, slate_id,
                             anchor_weight=SALARY_ANCHOR_WEIGHT_DEFAULT,
                             anchor_cold_start=False,
                             anchor_k=salary_anchor.DEFAULT_COLD_START_K,
                             dst_model_mode="legacy",
                             dst_sims=None,
                             dst_seed=None,
                             vegas_slate_id=None):
    """`vegas_slate_id` (Session 13.5-pause Bug Fix, decision #10
    continued): defaults to `slate_id` -- the common case, one vegas pull
    per slate. Vegas lines are site-agnostic (vegas_odds.py's own
    docstring), and DK/FD normally share the same slate_id string for the
    same real-world slate (confirmed in data/current_slate.json), so a
    site's own slate_id is the right default. Only needs to be passed
    explicitly when a site's own slate_id genuinely diverges from the
    slate_id vegas_odds.py was actually run with (e.g. an automation run
    that pulls vegas once under DK's slate_id and reuses it for FD's
    build) -- refresh_data.yml passes this explicitly for exactly that
    reason.
    """
    baseline = load_baseline_recent_form(site, season, week)
    matchup = load_matchup_factors(site, season, week)
    vegas = load_vegas_implied_totals(vegas_slate_id if vegas_slate_id else slate_id)
    salaries = load_salaries(site, slate_id)
    schedule = load_schedule(season)

    # Session 13.3: Showdown/Single-Game pools carry TWO linked rows per
    # player (FLEX-priced + CPT/MVP-priced, Session 13.2). Running the
    # existing projection pipeline on both would double-process every
    # player and silently give the CPT/MVP row an un-multiplied
    # projection. Instead, the whole pipeline below runs on the FLEX-only
    # rows (build_salaries) -- which look exactly like a classic pool, so
    # every downstream function is reused completely unchanged -- and the
    # CPT/MVP rows are derived afterward via apply_captain_multiplier().
    showdown = is_showdown_slate(salaries)
    if showdown:
        build_salaries = salaries[salaries["roster_role"] == "FLEX"].copy()
        captain_salaries = salaries[salaries["roster_role"].isin(CAPTAIN_ROLES)].copy()
        if build_salaries.empty or captain_salaries.empty:
            raise SystemExit(
                f"{slate_id}: slate_format='showdown' but roster_role values "
                f"don't split into FLEX + {sorted(CAPTAIN_ROLES)} as expected "
                f"(Session 13.2 ingest contract). roster_role values present: "
                f"{sorted(salaries['roster_role'].dropna().unique())}."
            )
        print(f"Showdown slate detected (Session 13.3): {len(build_salaries)} FLEX row(s), "
              f"{len(captain_salaries)} captain-equivalent row(s).")
    else:
        build_salaries = salaries
        captain_salaries = None

    # Primary: schedule-based opponent map.
    opponent_map = build_opponent_map(schedule, week)

    # Decision #9: if the schedule has no entries for any slate team,
    # fall back to inferring matchups from vegas over_under values.
    slate_teams = set(build_salaries["normalized_team"].dropna().unique())
    schedule_covered = slate_teams & set(opponent_map.keys())
    if not schedule_covered:
        print(
            f"NOTE: schedule has no week-{week} games for slate teams -- "
            f"falling back to vegas over_under pairing (decision #9, Madden Sim path).",
            file=sys.stderr,
        )
        opponent_map = build_opponent_map_from_salaries(build_salaries, site)
        if opponent_map:
            games_found = sorted(set(
                tuple(sorted([k, opponent_map[k]])) for k in opponent_map
            ))
            print(f"  Inferred {len(games_found)} game(s) from salary file: {games_found}", file=sys.stderr)
        else:
            print("  WARNING: could not infer any opponent pairs from salary file. "
                  "All skill players will get opponent=BYE_OR_UNKNOWN.", file=sys.stderr)

    vegas_factors = build_vegas_factors(vegas, opponent_map)

    # Skill-player pool from salary file.
    players = build_salaries[build_salaries["position_upper"].isin(POSITIONS)].copy()
    players = players[players["player_id"].notna()]
    players = players.rename(columns={"normalized_team": "team", "position_upper": "position"})
    site_id_col = SITE_CONFIGS[site]["site_id_col"]
    players = players[["player_id", "name", "position", "team", "salary", site_id_col]].rename(
        columns={"name": "player_name", site_id_col: "site_player_id"}
    )

    # Decision #4: auto-correct team drift for already-played weeks.
    week_was_played, real_team_this_week = load_real_team_for_week(season, week)
    players["no_real_game_this_week"] = False
    if week_was_played:
        corrected = players["player_id"].map(real_team_this_week)
        played_mask = corrected.notna()
        n_corrected = (played_mask & (corrected != players["team"])).sum()
        players.loc[played_mask, "team"] = corrected[played_mask]
        # Partial week (e.g. only Thursday's game has stats): a player whose
        # own team hasn't played yet is not "no real game". See the same
        # guard in build_projections_statline.py.
        teams_played = set(real_team_this_week.dropna().unique())
        not_yet_played = ~played_mask & ~players["team"].isin(teams_played)
        players["no_real_game_this_week"] = ~played_mask & ~not_yet_played
        n_no_game = players["no_real_game_this_week"].sum()
        print(f"{n_corrected} player(s) had their team corrected from the salary file's "
              f"snapshot to their real week-{week} team (decision #4a, in-season trade).")
        print(f"{n_no_game} player(s) had no real game at all in week {week} (bye/inactive/"
              f"not yet debuted) -- matchup_factor/vegas_factor forced to neutral 1.0 rather "
              f"than trusting the salary file's team (decision #4b).")

    df = players.merge(baseline[["player_id", "season_avg", "recent_form", "games_played"]],
                       on="player_id", how="left")

    n_no_history = df["season_avg"].isna().sum()
    df["season_avg"] = df["season_avg"].fillna(0.0)
    df["recent_form"] = df["recent_form"].fillna(0.0)
    df["games_played"] = df["games_played"].fillna(0).astype(int)

    df["opponent"] = df["team"].map(opponent_map)
    df.loc[df["no_real_game_this_week"], "opponent"] = None

    matchup_lookup = matchup.set_index(["team", "position"])["matchup_factor"]
    df["matchup_factor"] = df.apply(
        lambda r: matchup_lookup.get((r["opponent"], r["position"])), axis=1
    )
    n_no_matchup = df["matchup_factor"].isna().sum()
    df["matchup_factor"] = df["matchup_factor"].fillna(1.0)

    merge_cols = ["team", "vegas_factor", "implied_total"]
    if "over_under" in vegas_factors.columns:
        merge_cols.append("over_under")
    df = df.merge(vegas_factors[merge_cols], on="team", how="left")
    df.loc[df["no_real_game_this_week"], "vegas_factor"] = None
    df.loc[df["no_real_game_this_week"], "implied_total"] = None
    if "over_under" in df.columns:
        df.loc[df["no_real_game_this_week"], "over_under"] = None
    n_no_vegas = df["vegas_factor"].isna().sum()
    df["vegas_factor"] = df["vegas_factor"].fillna(1.0)

    df["final_projection"] = (
        (BASELINE_WEIGHT * df["season_avg"] + RECENT_FORM_WEIGHT * df["recent_form"])
        * df["matchup_factor"]
        * df["vegas_factor"]
    ).clip(lower=0.0)

    df.loc[df["no_real_game_this_week"], "final_projection"] = 0.0

    print(f"{n_no_history} player(s) had no season_avg/recent_form yet (0.0 fallback, "
          f"expected for rookies/midseason signings).")
    print(f"{n_no_matchup} player(s) had no matchup_factor found for (opponent, position) "
          f"(1.0 neutral fallback -- check opponent map / bye weeks).")
    print(f"{n_no_vegas} player(s) had no vegas_factor found for their team "
          f"(1.0 neutral fallback -- check line posting / bye weeks).")

    if "over_under" not in df.columns:
        df["over_under"] = None
    df["opponent"] = df["opponent"].fillna("BYE_OR_UNKNOWN")
    df["implied_total"] = df["implied_total"].fillna(0.0)
    df["over_under"] = df["over_under"].fillna(0.0)

    out_cols = [
        "player_id", "player_name", "position", "team", "salary", "site_player_id",
        "season_avg", "recent_form", "matchup_factor", "vegas_factor",
        "final_projection", "opponent", "implied_total", "over_under",
    ]
    skill_out = df[out_cols]
    # Decision #11 (Session 13.5-pause Bug Fix, closes Session 13.4's
    # flagged _dst_extra gap): skill players have no per-player uncertainty
    # model today, so sigma/dst_p10/dst_p90 are a neutral 0.0 placeholder
    # here -- same pattern kicker_out already uses for columns ITS model
    # has no signal for (season_avg/recent_form/etc, see that function).
    skill_out = skill_out.assign(sigma=0.0, dst_p10=0.0, dst_p90=0.0)

    dst_out = build_dst_projections(build_salaries, vegas, site,
                                    model=dst_model_mode, season=season,
                                    week=week, sims=dst_sims, seed=dst_seed,
                                    opponent_map=opponent_map if opponent_map else None,
                                    vegas_factors=vegas_factors)
    _dst_extra = None
    if "sigma" in dst_out.columns:
        _dst_extra = dst_out[["player_id", "sigma", "dst_p10", "dst_p90"]].copy()
        dst_out = dst_out.drop(columns=["sigma", "dst_p10", "dst_p90"])
    # Same 0.0 placeholder as skill_out -- overwritten with the real values
    # below for the distributional model (legacy DST never computed sigma
    # at all, so this stays 0.0 there, same as before this fix).
    dst_out = dst_out.assign(sigma=0.0, dst_p10=0.0, dst_p90=0.0)

    skill_out = skill_out.assign(_anchor_games=df["games_played"].to_numpy())
    dst_out = dst_out.assign(
        _anchor_games=(dst_out["season_avg"] > 0).map(
            {True: DST_ASSUMED_GAMES_PLAYED, False: 0}
        ).astype(int)
    )

    kicker_out = _build_kicker_projections(build_salaries, site, opponent_map)
    kicker_out = kicker_out.assign(
        _anchor_games=(kicker_out["season_avg"] > 0).map(
            {True: DST_ASSUMED_GAMES_PLAYED, False: 0}
        ).astype(int) if len(kicker_out) else pd.Series(dtype=int)
    )

    out = pd.concat([skill_out, dst_out, kicker_out], ignore_index=True)

    # Decision #11 continued: merge DST's real sigma/dst_p10/dst_p90 back in.
    # These were already computed by the distributional model (dst_model.
    # simulate) but got dropped into _dst_extra and never reattached --
    # Session 13.4's flagged gap, closed here. `player_id` is guaranteed
    # unique at this point in the pipeline (one row per skill/DST/kicker
    # player) -- Showdown's CPT-role duplicate rows don't exist yet, those
    # get derived further down via apply_captain_multiplier(), which
    # correctly carries these columns forward from the FLEX row it copies
    # (see that function's column-scaling loop). .update() overrides the
    # 0.0 placeholder above only for the player_ids _dst_extra actually
    # has -- everyone else (skill players; DST under the legacy model,
    # which never computed sigma) keeps the 0.0 placeholder unchanged.
    if _dst_extra is not None:
        out = out.set_index("player_id")
        out.update(_dst_extra.set_index("player_id"))
        out = out.reset_index()

    anchor_on = anchor_weight > 0 or anchor_cold_start
    if anchor_on:
        out = apply_salary_anchor(out, site, anchor_weight, anchor_cold_start, anchor_k)
    out = out.drop(columns=["_anchor_games"])

    # Session 13.3: derive CPT/MVP rows from the FLEX-priced projections
    # just built, apply the ownership decision (see module docstring), and
    # stamp roster_role/slate_format on every row so the output schema is
    # identical in shape for classic and Showdown (Session 13.2 precedent).
    if showdown:
        out["roster_role"] = "FLEX"
        captain_out = apply_captain_multiplier(out, captain_salaries, site)
        out = pd.concat([out, captain_out], ignore_index=True)
        out["slate_format"] = "showdown"
        out = add_showdown_ownership_columns(out, site)
    else:
        out = add_ownership_columns(out, site)
        out["roster_role"] = None
        out["slate_format"] = "classic"
        out["ownership_available"] = True

    out = out.sort_values("final_projection", ascending=False).reset_index(drop=True)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate-id", required=True,
                        help="e.g. classic_wk10 or madden_07312026. "
                             "Names the salary input file AND the output file.")
    parser.add_argument("--vegas-slate-id", default=None,
                        help="Which vegas_implied_totals_{X}.csv to read, if it's NOT "
                             "the same as --slate-id (e.g. FD build reusing a vegas "
                             "pull made under DK's slate_id). Defaults to --slate-id.")
    parser.add_argument("--salary-anchor-weight", type=float, default=SALARY_ANCHOR_WEIGHT_DEFAULT)
    parser.add_argument("--salary-anchor-cold-start", action="store_true")
    parser.add_argument("--salary-anchor-k", type=float, default=salary_anchor.DEFAULT_COLD_START_K)
    parser.add_argument("--dst-model", choices=["legacy", "distributional"],
                        default="distributional")
    parser.add_argument("--dst-sims", type=int, default=None)
    parser.add_argument("--dst-seed", type=int, default=None)
    args = parser.parse_args()

    result = build_final_projections(
        args.site, args.season, args.week, args.slate_id,
        anchor_weight=args.salary_anchor_weight,
        anchor_cold_start=args.salary_anchor_cold_start,
        anchor_k=args.salary_anchor_k,
        dst_model_mode=args.dst_model,
        dst_sims=args.dst_sims,
        dst_seed=args.dst_seed,
        vegas_slate_id=args.vegas_slate_id,
    )

    # FIX: output named by slate_id, not week -- two slates in same week never collide.
    out_path = OUTPUT_DIR / f"final_projections_{args.site}_{args.slate_id}.csv"
    result.to_csv(out_path, index=False)
    print(f"Wrote {len(result)} rows to {out_path}")

    # Session 13.3b: ownership is now real for both classic AND Showdown
    # (Showdown's original NaN placeholder was replaced once the
    # roster_role-grouped heuristic was built -- see add_showdown_ownership_columns).
    # A plain isnull() check is correct again for every column.
    nulls = result.isnull().any(axis=1).sum()
    neg = (result["final_projection"] < 0).sum()
    # PRE-EXISTING BUG (found incidentally during Session 13.3 validation, fixed
    # here since it's a one-line correction, not a 13.3 feature): this checked
    # site_id_col (the RAW salary file's ID column name, e.g. "ID"/"Id"), which
    # never exists in `result` -- the pipeline renames it to `site_player_id`
    # early on. The check always silently reported "N/A" instead of actually
    # validating, for both classic and Showdown output, since this script was
    # first written.
    missing_id = result["site_player_id"].isna().sum() if "site_player_id" in result.columns else "N/A"

    print(f"  Nulls in any column: {nulls} (should be 0)")
    print(f"  Negative final_projection: {neg} (should be 0)")

    chalk_bad = ((result["chalk_score"] < 0) | (result["chalk_score"] > 100)).sum()
    own_bad = ((result["estimated_ownership_pct"] < 0) | (result["estimated_ownership_pct"] > 100)).sum()
    print(f"  chalk_score out of [0,100] range: {chalk_bad} (should be 0)")
    print(f"  estimated_ownership_pct out of [0,100] range: {own_bad} (should be 0)")

    is_showdown_output = "slate_format" in result.columns and result["slate_format"].eq("showdown").any()
    if is_showdown_output:
        cpt_roles = result[result["roster_role"].isin(CAPTAIN_ROLES)]
        flex_roles = result[result["roster_role"] == "FLEX"]
        check = cpt_roles.merge(flex_roles[["player_id", "final_projection"]],
                                 on="player_id", suffixes=("_cpt", "_flex"))
        ratio = check["final_projection_cpt"] / check["final_projection_flex"].replace(0, np.nan)
        bad_ratio = ((ratio - CAPTAIN_MULTIPLIER).abs() > 1e-6).sum()
        n_no_flex_signal = check["final_projection_flex"].eq(0).sum()
        print(f"  CPT/MVP final_projection == {CAPTAIN_MULTIPLIER}x linked FLEX "
              f"projection: {len(check) - bad_ratio}/{len(check)} rows match "
              f"exactly ({bad_ratio} mismatch, should be 0; "
              f"{n_no_flex_signal} row(s) had 0 FLEX projection so ratio is "
              f"undefined -- checked separately below).")
        zero_mismatch = check[check["final_projection_flex"].eq(0) &
                              check["final_projection_cpt"].ne(0)]
        print(f"  Zero-FLEX-projection rows with a nonzero CPT/MVP projection: "
              f"{len(zero_mismatch)} (should be 0).")
        role_totals = result.groupby("roster_role")["estimated_ownership_pct"].sum()
        print(f"  estimated_ownership_pct summed per roster_role (sanity spot-check, "
              f"printed above in more detail by add_showdown_ownership_columns): "
              f"{role_totals.round(1).to_dict()}")

    print(f"  Missing site_player_id (DK/FD's own ID -- needed for the Download Lineups import feature): {missing_id} (should be 0)")
