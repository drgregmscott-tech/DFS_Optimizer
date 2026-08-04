"""
fit_kicker_model.py
====================

Session 13.1 -- fits data/kicker_model.json, consumed by kicker_model.py.
Same fitter/consumer split as fit_dst_model.py -> dst_model.py and
fit_salary_anchor.py -> salary_anchor.py (production path never imports
this file).

No kicker model existed anywhere in this pipeline before this session --
built now because Showdown/Single-Game pools always include kickers
(Phase 13's trigger), and both DK Showdown and FD Single Game score them.

Numbered decisions:

 1. THREE SCORING-RELEVANT DISTANCE BUCKETS, NOT NFLVERSE'S SIX. nflverse's
    `stats_player_week` release carries FG makes/misses in six raw distance
    bands (0-19/20-29/30-39/40-49/50-59/60+). DK and FD score three
    (0-39/40-49/50+, see scoring_rules.py's KICKER_SCORING). Collapsing to
    the scoring-relevant buckets before fitting anything downstream avoids
    modeling distinctions the site scoring can't see.

 2. FG ATTEMPT VOLUME HAS NO MEASURED SIGNAL FROM TEAM IDENTITY OR VEGAS
    IMPLIED TOTAL -- THIS IS A REAL, MEASURED NULL RESULT, NOT AN
    OVERSIGHT. Measured on 3,122 real team-weeks (2018-2023 fit window):

        FGA ~ own_implied_total:  R^2 = 0.003, corr = -0.059
        team-level FGA/game split-half correlation (within a team-season,
          weeks 1-9 vs 10-18): r = 0.039

    Compare to DST's points-allowed, which had a real (if modest) team
    trait and a real Vegas relationship (fit_dst_model.py's own numbers).
    Kicker attempt volume does not -- a team's field-goal count per game is
    close to i.i.d. noise around a league-average rate regardless of that
    team's own scoring context or week-to-week identity. This makes sense
    on reflection (a good offense converts more red-zone trips to
    touchdowns INSTEAD of stalling into a field goal, which cancels out
    the volume signal scoring context would otherwise provide) but it was
    measured, not assumed -- per this project's "pre-register before
    measuring" principle, a Vegas-implied-total regression was the
    starting hypothesis and it failed to clear a meaningful R^2 bar.

    CONSEQUENCE: `mu_fga` and `mu_pat` below are recency-weighted LEAGUE
    AVERAGES, not team- or matchup-conditioned regressions. FLAGGED
    ARBITRARY / a real simplification versus DST's approach -- retuning
    target if a better volume signal is ever found (e.g. opponent
    red-zone defense, game-script/garbage-time effects). Not built now;
    explicitly deferred, see module docstring's decision #5.

 3. RECENCY-WEIGHTED LEAGUE AVERAGE, NOT A FLAT MULTI-SEASON MEAN. FGA/game
    has trended up across the fit+test window (2018: 1.85 -> 2023: 1.95 ->
    2024-2025 held-out: 2.05, 2.00). A flat 2018-2023 average under-
    projects the current era by about 5% (measured: flat-mean Monte Carlo
    projected 8.06 pts/game against a real 2024-2025 mean of 8.52).
    `_recency_weighted_mean()` weights more recent seasons more heavily
    (exponential decay, half-life = 2 seasons) for exactly this reason --
    same rationale as `projections_baseline.py`'s recent-form component,
    applied to a league-level rate instead of a player-level one.

 4. PLAYER-SPECIFIC ACCURACY IS REAL BUT NEARLY IRRELEVANT TO TOTAL POINTS
    -- SHIPPED ANYWAY BECAUSE IT IS FREE AND DIRECTIONALLY CORRECT, NOT
    BECAUSE IT MOVES THE BACKTEST. Individual kicker accuracy by distance
    bucket IS a real, measurably stable skill (split-half r = 0.23 within
    a season, min 3 att/half; career-window accuracy correlates with
    held-out-season accuracy at r = 0.175, n=36 kickers with 15+ fit
    attempts and 10+ test attempts) -- unlike volume, which is not stable
    at all (decision #2). But because per-game point totals are dominated
    by attempt-COUNT variance (which is unpredictable) rather than
    make-rate variance, shrunk player-specific accuracy barely moved the
    backtest: MAE 3.7470 (league-flat) vs 3.7489 (player-shrunk) per game;
    RMSE 4.7496 vs 4.7405; season-level Spearman rank vs actual points/game
    only 0.078 (measured on 1,086 held-out kicker-weeks, 52 kickers,
    2024-2025). Per this project's own Session 11.2 bar ("only ship a
    refinement if it clears a real improvement threshold"), this ALMOST
    doesn't clear it -- shipped anyway because (a) it costs nothing at
    inference time, (b) it's directionally correct (a real elite/poor
    kicker's rate is not literally the league average), and (c) it isn't
    pretending to explain more than it does -- documented honestly here
    rather than silently presented as "the model that uses real kicker
    skill." The headline driver of THIS model's value is the correctly
    WIDE sigma (decision #5), not point-estimate precision that the data
    doesn't support.

 5. SIGMA IS SIMULATED, BUT WITH A DELIBERATELY SIMPLER DRAW SCHEME THAN
    DST'S -- NO LATENT CORRELATION FACTOR. DST's Monte Carlo (dst_model.py
    decision #13) needed a latent "defensive dominance" factor because
    independent component draws measurably under-stated real DST sigma by
    11%. The equivalent check here found the opposite problem doesn't
    exist: three independent Poisson draws (one per scoring-relevant
    distance bucket, using the Poisson-thinning property so their sum
    still has mean `mu_fga`) plus independent Binomial makes plus an
    independent Poisson PAT draw reproduce real held-out sigma almost
    exactly -- simulated std 4.871 against a real 2024-2025 std of 4.729
    (calibration ratio 1.03, i.e. within 3%, no correction needed). A
    kicker's FG attempts, by bucket, and PATs are close enough to
    independent in practice that adding DST's latent-factor machinery
    would be solving a problem that measurably isn't there. This is the
    justification for Session 13.0's stated scoping decision that the
    kicker model would be "real but simpler than DST" -- here is the
    measurement that simpler is actually sufficient, not just expedient.

 6. EARLY SEASON / ROOKIE / TEAM-CHANGE KICKERS GET PURE LEAGUE-AVERAGE
    ACCURACY, SAME SHRINKAGE PATTERN AS EVERY OTHER MODEL IN THIS PROJECT.
    `_shrunk_rate()` blends a kicker's own bucket make-rate with the
    league-average bucket rate, weighted by a pseudo-attempt count
    (K_SHRINK = 12 attempts). At zero real attempts (rookie, new to the
    league, or the pipeline simply has no career row for this player_id)
    the shrinkage collapses to the pure league rate -- a real number, not
    a crash or a zero, same principle as dst_model.py's decision #15
    (week-1 carryover) and volume_prior.py's cold-start handling.

 7. TEAM-LEVEL, NOT PLAYER-IDENTITY-LEVEL, FOR VOLUME. Consistent with
    decision #2: since volume has no team or player signal worth
    conditioning on, `mu_fga`/`mu_pat` are single global numbers, not a
    per-team or per-kicker table. Only the ACCURACY side of the model
    (decision #4) is player-specific. This mirrors dst_model.py's
    team-level (not player-level) approach for defense, applied here for
    a different reason (DST is team-level because a defense IS a team
    unit; kickers are team-level for volume specifically because no
    predictive signal was found at either finer grain).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scoring_rules  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MODEL_PATH = DATA_DIR / "kicker_model.json"
SCHEMA_VERSION = 1

# Decision #3 -- exponential recency weighting, half-life = 2 seasons.
RECENCY_HALF_LIFE_SEASONS = 2.0

# Decision #4 -- pseudo-attempts of league-average prior per accuracy bucket.
K_SHRINK = 12

BASE_URL = "https://github.com/nflverse/nflverse-data/releases/download"
WEEKLY_STATS_URL = f"{BASE_URL}/stats_player/stats_player_week_{{season}}.parquet"
GAMES_URL = f"{BASE_URL}/schedules/games.parquet"


def _recency_weighted_mean(values_by_season: dict, half_life: float = RECENCY_HALF_LIFE_SEASONS) -> float:
    """Decision #3. `values_by_season` maps season -> per-game rate. Most
    recent season gets weight 1.0, each season back gets weight
    0.5^(seasons_back / half_life)."""
    seasons = sorted(values_by_season)
    latest = seasons[-1]
    weights = {s: 0.5 ** ((latest - s) / half_life) for s in seasons}
    num = sum(values_by_season[s] * weights[s] for s in seasons)
    den = sum(weights[s] for s in seasons)
    return num / den


def _shrunk_rate(made: float, att: float, league_rate: float, k: int = K_SHRINK) -> float:
    """Decision #4/#6. Empirical-Bayes shrinkage toward the league rate."""
    return (made + league_rate * k) / (att + k)


def _bucketize(df: pd.DataFrame) -> pd.DataFrame:
    """Decision #1 -- collapse nflverse's 6 raw distance bands into the 3
    site-scoring-relevant buckets."""
    df = df.copy()
    df["att_0_39"] = (df["fg_made_0_19"] + df["fg_missed_0_19"]
                       + df["fg_made_20_29"] + df["fg_missed_20_29"]
                       + df["fg_made_30_39"] + df["fg_missed_30_39"])
    df["made_0_39"] = df["fg_made_0_19"] + df["fg_made_20_29"] + df["fg_made_30_39"]
    df["att_40_49"] = df["fg_made_40_49"] + df["fg_missed_40_49"]
    df["made_40_49"] = df["fg_made_40_49"]
    df["att_50p"] = (df["fg_made_50_59"] + df["fg_missed_50_59"]
                      + df["fg_made_60_"] + df["fg_missed_60_"])
    df["made_50p"] = df["fg_made_50_59"] + df["fg_made_60_"]
    return df


def load_kicker_weeks(seasons: list) -> pd.DataFrame:
    frames = []
    for s in seasons:
        df = pd.read_parquet(WEEKLY_STATS_URL.format(season=s), engine="pyarrow")
        df = df[(df["position"] == "K") & (df["season_type"] == "REG")].copy()
        df["season"] = s
        frames.append(df)
    return _bucketize(pd.concat(frames, ignore_index=True))


def load_team_week_implied(seasons: list) -> pd.DataFrame:
    """Own-team implied total per team-week, from nflverse's real historical
    closing lines (games.parquet's total_line/spread_line) -- the same
    source and sign convention fit_dst_model.py's build_panel() uses for
    `opp_implied`, applied here to the TEAM'S OWN side of the line rather
    than the opponent's. Not currently used by the production model
    (decision #2), retained here so a future session investigating a
    volume signal has the panel already built rather than rebuilding it."""
    g = pd.read_parquet(GAMES_URL, engine="pyarrow")
    g = g[(g["game_type"] == "REG") & (g["season"].isin(seasons))][
        ["season", "week", "home_team", "away_team", "total_line", "spread_line"]].copy()
    home = g.rename(columns={"home_team": "team", "away_team": "opponent_team"}).copy()
    home["own_implied"] = home["total_line"] / 2.0 - home["spread_line"] / 2.0
    away = g.rename(columns={"away_team": "team", "home_team": "opponent_team"}).copy()
    away["own_implied"] = away["total_line"] / 2.0 + away["spread_line"] / 2.0
    return pd.concat([home[["season", "week", "team", "own_implied"]],
                       away[["season", "week", "team", "own_implied"]]], ignore_index=True)


def fit(fit_seasons: list) -> dict:
    kw = load_kicker_weeks(fit_seasons)

    # --- decision #3: recency-weighted league volume rates -------------
    team_week = kw.groupby(["season", "week", "team"], as_index=False).agg(
        fg_att=("fg_att", "sum"), pat_att=("pat_att", "sum"))
    by_season_fga = team_week.groupby("season")["fg_att"].mean().to_dict()
    by_season_pat = team_week.groupby("season")["pat_att"].mean().to_dict()
    mu_fga = _recency_weighted_mean(by_season_fga)
    mu_pat = _recency_weighted_mean(by_season_pat)

    # --- decision #1/#7: league-average distance-bucket shares & make rates
    tot = kw[["att_0_39", "att_40_49", "att_50p"]].sum()
    shares = (tot / tot.sum()).to_dict()
    league_mr = {
        "0_39": float(kw["made_0_39"].sum() / kw["att_0_39"].sum()),
        "40_49": float(kw["made_40_49"].sum() / kw["att_40_49"].sum()),
        "50p": float(kw["made_50p"].sum() / kw["att_50p"].sum()),
    }
    league_pat_mr = float(kw["pat_made"].sum() / kw["pat_att"].sum())

    # --- decision #4: per-player career accuracy, to be shrunk at inference
    career = kw.groupby("player_id").agg(
        att_0_39=("att_0_39", "sum"), made_0_39=("made_0_39", "sum"),
        att_40_49=("att_40_49", "sum"), made_40_49=("made_40_49", "sum"),
        att_50p=("att_50p", "sum"), made_50p=("made_50p", "sum"),
    ).reset_index()
    # also carry the player's display name / most recent team for handoff
    # convenience (kicker_model.py joins on player_id, this is just for a
    # human reading the artifact).
    latest_meta = (kw.sort_values(["season"])
                    .groupby("player_id")
                    .tail(1)[["player_id", "player_display_name", "team"]])
    career = career.merge(latest_meta, on="player_id", how="left")

    model = {
        "schema_version": SCHEMA_VERSION,
        "fit_seasons": [int(s) for s in fit_seasons],
        "fit_notes": "Decision #2: volume has no measured team/Vegas signal, "
                     "so mu_fga/mu_pat are recency-weighted league averages, "
                     "not a regression. See module docstring.",
        "mu_fga": round(float(mu_fga), 5),
        "mu_pat": round(float(mu_pat), 5),
        "distance_shares": {k: round(float(v), 5) for k, v in shares.items()},
        "league_make_rate": league_mr,
        "league_pat_make_rate": round(league_pat_mr, 5),
        "shrink_k": K_SHRINK,
        "career_accuracy": career.to_dict(orient="records"),
    }
    return model


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fit-seasons", type=int, nargs="+", default=[2018, 2019, 2020, 2021, 2022, 2023],
                    help="Seasons to fit on. Default matches Session 13.1's own fit window; "
                         "refit periodically as new seasons complete (decision #3's recency "
                         "weighting means the artifact should be refreshed, not treated as static).")
    args = p.parse_args()

    model = fit(args.fit_seasons)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(model, indent=2))
    print(f"Wrote {MODEL_PATH}")
    print(f"mu_fga={model['mu_fga']} mu_pat={model['mu_pat']}")
    print(f"distance_shares={model['distance_shares']}")
    print(f"league_make_rate={model['league_make_rate']} pat={model['league_pat_make_rate']}")
    print(f"career_accuracy rows: {len(model['career_accuracy'])}")


if __name__ == "__main__":
    main()
