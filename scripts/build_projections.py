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
from ingest_salaries import SITE_CONFIGS
from ownership_heuristic import compute_chalk_scores, compute_estimated_ownership
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


def load_vegas_implied_totals(week):
    path = OUTPUT_DIR / f"vegas_implied_totals_{week}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run vegas_odds.py --week {week} first (Session 2.3)."
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


def build_opponent_map_from_salaries(salaries):
    """Decision #9: infer matchups directly from the salary file Game Info column.

    The DK salary CSV export contains a Game Info column with values like
    'CHI@BAL 07/31/2026 12:00PM ET'. This is the most reliable source of
    matchup information for any slate type -- Madden Sim, preseason, or
    regular season -- because it reflects exactly what DK has on the slate,
    regardless of whether a matching NFL schedule week exists.

    Parses each unique game string, extracts the two team abbreviations, and
    builds the bidirectional team -> opponent map. Falls back gracefully if
    the Game Info column is absent or malformed.
    """
    if "Game Info" not in salaries.columns:
        return {}

    opp_map = {}
    seen = set()
    for game_info in salaries["Game Info"].dropna().unique():
        # Format: "AWAY@HOME DATE TIME ET" e.g. "CHI@BAL 07/31/2026 12:00PM ET"
        matchup_part = game_info.split(" ")[0]  # "CHI@BAL"
        if "@" not in matchup_part:
            continue
        away, home = matchup_part.split("@", 1)
        away = away.strip().upper()
        home = home.strip().upper()
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

def _build_dst_distributional(salaries, vegas, site, season, week, sims, seed):
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
    feat = dst_model.build_features(season, week, teams, vegas, model_obj, games=games)
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
    dst["implied_total"] = dst["own_implied"].where(played).fillna(0.0)
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
                           opponent_map=None):
    if model not in ("legacy", "distributional"):
        raise SystemExit(f"build_dst_projections: unknown model {model!r}.")
    if model == "distributional":
        if season is None or week is None:
            raise SystemExit("build_dst_projections(model='distributional') needs season and week.")
        return _build_dst_distributional(salaries, vegas, site, season, week, sims, seed)

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

def add_ownership_columns(df, site):
    scored = compute_chalk_scores(df, site)
    scored = compute_estimated_ownership(scored, site)
    ownership_cols = scored[["player_id", "chalk_score", "estimated_ownership_pct"]]
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
# Main build function
# ---------------------------------------------------------------------------

def build_final_projections(site, season, week, slate_id,
                             anchor_weight=SALARY_ANCHOR_WEIGHT_DEFAULT,
                             anchor_cold_start=False,
                             anchor_k=salary_anchor.DEFAULT_COLD_START_K,
                             dst_model_mode="legacy",
                             dst_sims=None,
                             dst_seed=None):
    baseline = load_baseline_recent_form(site, season, week)
    matchup = load_matchup_factors(site, season, week)
    vegas = load_vegas_implied_totals(week)
    salaries = load_salaries(site, slate_id)
    schedule = load_schedule(season)

    # Primary: schedule-based opponent map.
    opponent_map = build_opponent_map(schedule, week)

    # Decision #9: if the schedule has no entries for any slate team,
    # fall back to inferring matchups from vegas over_under values.
    slate_teams = set(salaries["normalized_team"].dropna().unique())
    schedule_covered = slate_teams & set(opponent_map.keys())
    if not schedule_covered:
        print(
            f"NOTE: schedule has no week-{week} games for slate teams -- "
            f"falling back to vegas over_under pairing (decision #9, Madden Sim path).",
            file=sys.stderr,
        )
        opponent_map = build_opponent_map_from_salaries(salaries)
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
    players = salaries[salaries["position_upper"].isin(POSITIONS)].copy()
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
        players["no_real_game_this_week"] = ~played_mask
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

    dst_out = build_dst_projections(salaries, vegas, site,
                                    model=dst_model_mode, season=season,
                                    week=week, sims=dst_sims, seed=dst_seed,
                                    opponent_map=opponent_map if opponent_map else None)
    _dst_extra = None
    if "sigma" in dst_out.columns:
        _dst_extra = dst_out[["player_id", "sigma", "dst_p10", "dst_p90"]].copy()
        dst_out = dst_out.drop(columns=["sigma", "dst_p10", "dst_p90"])

    skill_out = skill_out.assign(_anchor_games=df["games_played"].to_numpy())
    dst_out = dst_out.assign(
        _anchor_games=(dst_out["season_avg"] > 0).map(
            {True: DST_ASSUMED_GAMES_PLAYED, False: 0}
        ).astype(int)
    )

    kicker_out = _build_kicker_projections(salaries, site, opponent_map)
    kicker_out = kicker_out.assign(
        _anchor_games=(kicker_out["season_avg"] > 0).map(
            {True: DST_ASSUMED_GAMES_PLAYED, False: 0}
        ).astype(int) if len(kicker_out) else pd.Series(dtype=int)
    )

    out = pd.concat([skill_out, dst_out, kicker_out], ignore_index=True)

    anchor_on = anchor_weight > 0 or anchor_cold_start
    if anchor_on:
        out = apply_salary_anchor(out, site, anchor_weight, anchor_cold_start, anchor_k)
    out = out.drop(columns=["_anchor_games"])

    out = add_ownership_columns(out, site)
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
    )

    # FIX: output named by slate_id, not week -- two slates in same week never collide.
    out_path = OUTPUT_DIR / f"final_projections_{args.site}_{args.slate_id}.csv"
    result.to_csv(out_path, index=False)
    print(f"Wrote {len(result)} rows to {out_path}")

    nulls = result.isnull().any(axis=1).sum()
    neg = (result["final_projection"] < 0).sum()
    chalk_bad = ((result["chalk_score"] < 0) | (result["chalk_score"] > 100)).sum()
    own_bad = ((result["estimated_ownership_pct"] < 0) | (result["estimated_ownership_pct"] > 100)).sum()
    site_id_col = SITE_CONFIGS[args.site]["site_id_col"]
    missing_id = result[site_id_col].isna().sum() if site_id_col in result.columns else "N/A"
    print(f"  Nulls in any column: {nulls} (should be 0)")
    print(f"  Negative final_projection: {neg} (should be 0)")
    print(f"  chalk_score out of [0,100] range: {chalk_bad} (should be 0)")
    print(f"  estimated_ownership_pct out of [0,100] range: {own_bad} (should be 0)")
    print(f"  Missing site_player_id (DK/FD's own ID -- needed for the Download Lineups import feature): {missing_id} (should be 0)")
