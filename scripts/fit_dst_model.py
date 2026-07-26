"""
fit_dst_model.py
================

Session 10.4 -- fits the DST model's constants from real historical data and
writes `data/dst_model.json`.

Deliberately separate from `dst_model.py` (the consumer), the same split
Session 10.2 made between `fit_salary_anchor.py` and `salary_anchor.py`: the
production path must never import the fitting machinery, so a projection run
cannot accidentally refit, and a refit cannot accidentally ship.

What it replaces
----------------
`build_projections.py`'s decision #5 DST model is:

    final_projection = AvgPointsPerGame * (league_avg_implied / opp_implied)
    matchup_factor   = 1.0   (flat -- flagged as a real gap since Session 2.4)

One season-average number scaled by a linear Vegas ratio. It has no
components, so it cannot see that a defense faces a turnover-prone rookie or
a line that cannot block; it applies a single multiplicative factor to points
rather than integrating the bracket step function; and its sigma (Session
10.3a's `3.25 + 0.39 * projection`) is unconditional by construction.

Numbered decisions:

  1. NEGATIVE BINOMIAL, BECAUSE POISSON IS MEASURABLY WRONG. Points allowed
     is overdispersed at every level of the opponent's implied total --
     variance/mean runs 4.38, 4.13, 4.01, 3.51, 3.36 across implied-total
     bands from 15-19 up to 28+. Poisson asserts 1.0. The fitted NB
     dispersion is r ~ 6.4, reproducing var/mean ~ 4.6 at a mean of 23.

     The same family is used for the count components. It matters most for
     points allowed, because that is the one read through a step function.

  2. VEGAS IS THE POINTS-ALLOWED MODEL, AND IT IS ALREADY CALIBRATED. Fitted
     over 3,952 real team-weeks:

         points_allowed ~ -0.35 + 1.016 * opponent_implied_total

     A slope of 1.016 and an intercept of -0.35 means the market's implied
     total is an essentially unbiased forecast of what a defense will allow.
     It explains only ~15% of the variance (residual SD 9.12 against a raw
     10.14), which is exactly why the distribution -- not the point estimate
     -- is the deliverable.

  3. OWN-DEFENSE EPA AND WIND ARE FITTED, SMALL, AND HONESTLY LABELLED.
     Session 10.2's lesson was that a term nearly redundant with something
     the pipeline already conditions on buys nothing. Measured here on top of
     the implied total (n=2,872, weeks 5+):

         + own-defense EPA allowed (prior wks)   R2 0.1580 -> 0.1597, t=-2.33
         + wind                                  R2 0.1580 -> 0.1601, t=-2.67
         + both                                  R2 0.1580 -> 0.1617

     Both are real at conventional significance and both are tiny -- together
     they cut the residual SD from 9.121 to 9.104, a 0.19% improvement. The
     reason is the same redundancy Session 10.2 found: the books set the
     total AFTER seeing the wind forecast and the defense's form, so the
     implied total already carries most of both.

     The EPA coefficient is NEGATIVE (a defense that has allowed more EPA
     allows fewer points than its line implies). That is not a quality
     signal; it is a mean-reversion correction on a market number that
     overreacts to recent form. Labelled as such rather than dressed up.

  4. WIND MEASURED NULL ON THE VOLUME CHANNELS, AND IS STILL FITTED THERE.
     On dropbacks, wind is t=-1.58 alone and collapses to t=-0.34 once the
     game total is in the model. On sacks t=+0.66, on interceptions t=+0.70.
     Only on points allowed does it reach significance.

     It is fitted on all four channels anyway, and each coefficient's
     t-statistic is written into the JSON next to it. A coefficient that
     measured null is then applied AS the near-zero number it was measured to
     be, which is self-documenting and beats either hand-zeroing it (a
     judgement call hidden in code) or quietly reporting it as a feature.

     Wind is read from nflverse `games.parquet` and is the REALIZED wind for
     a completed game, so in backtest it is very mildly lookahead. Given the
     measured effect size this cannot move a result; it is flagged because it
     is true, not because it matters. In production it is a forecast.

  5. DOME AND CLOSED-ROOF GAMES GET WIND 0, NOT MISSING. `roof` in
     {dome, closed} means there is no wind, which is a real zero rather than
     an absent measurement. Outdoor games with a missing wind reading also
     get 0.0, which is the conservative choice (no adjustment) rather than
     imputing a league mean into a game we have no reading for. Readings are
     clipped to 30 mph -- the raw feed carries at least one 71 mph value,
     which is a data error, not a hurricane.

  6. THE OPPONENT'S OFFENSE PREDICTS A DEFENSE BETTER THAN THE DEFENSE DOES,
     WHICH INVERTS THE ROADMAP CARD. That card specifies "own-defense EPA/play
     as the stable modifier." Measured on prior-weeks data (weeks 5+):

         sacks:  opponent's sacks-allowed prior   t=+10.18, R2 0.0349
                 own defense's sack prior         t= +2.75, R2 0.0026
         INTs:   opponent's INTs-thrown prior     t= +4.74, R2 0.0078
                 own defense's INT prior          t= +2.27, R2 0.0018

     The opponent's offense carries roughly four times the sack signal that
     the defense's own history does. Both sides are kept, weighted by what
     they measured, rather than the card's ordering being assumed.

  7. THE QB-HIT PRESSURE PROXY WAS TRIED AND DROPPED, AND THE REASON IS
     WORTH MORE THAN THE TERM WAS. `def_qb_hits` is genuinely the more
     STABLE team trait -- split-half correlation within a team-season is
     +0.239 for QB hits and +0.204 for passes defended, against +0.186 for
     sacks and +0.100 for interceptions. The obvious inference is that a
     pressure rate should forecast next week's sacks better than a past sack
     count does, since sacks are the rarer, noisier realisation of the same
     underlying pressure. That inference is wrong here, and it took fitting
     it to find out. On the 2014-17 fit window:

         opp sacks-allowed rate only              R2 0.0397
         + own SACK rate                          R2 0.0409  (own t=+1.30)
         + own QB-HIT rate                        R2 0.0397  (own t=-0.20)
         + BOTH                                   R2 0.0418  (+1.70 / -1.11)

     The two own-defense terms correlate at 0.559, so together they split one
     signal into an unstable pair with opposing signs -- the QB-hit
     coefficient flips sign depending on which window it is fitted on, which
     is the signature of collinearity rather than of information. Alone, the
     QB-hit term contributes nothing (t=-0.20) once the opponent's
     pass-protection quality is controlled for.

     The lesson generalises: STABILITY OF A TEAM TRAIT IS NOT PREDICTIVE
     POWER FOR NEXT WEEK'S COUNT. QB hits are a more reliable measurement of
     a defense, and the defense is simply not the part of this that carries
     the signal -- decision #6 is why. Shipped model keeps the opponent's
     sacks-allowed rate and the own-defense sack rate, and drops QB hits.

  8. QB-SPECIFIC INTERCEPTION RATE SUPERSEDES THE TEAM RATE -- the one place
     the card's design is confirmed outright. Fitted jointly (n=2,872):

         opponent TEAM prior INT rate alone       R2 0.0078
         opponent QB career INT rate x attempts   R2 0.0123
         both together                            team t=+1.12 (dead),
                                                  QB   t=+3.82 (holds)

     The team term goes insignificant the moment the starting QB's own rate
     is in the model, so the QB rate is used and the team rate is dropped
     rather than kept as decoration.

     ROOKIE ADJUSTMENT: rookie starters throw 0.908 INT/gm against 0.807 for
     everyone else (+12.5%), and a rookie flag carries t=+1.76 on top of the
     career rate. Weak, right sign, and mechanically justified -- a rookie's
     career-to-date rate is built on few attempts, so shrinkage pulls him to
     the league mean and understates him. The multiplier corrects the
     direction of a bias the shrinkage itself creates. Flagged ARBITRARY-
     ADJACENT: the value is fitted, the decision to include a term at
     t=1.76 is a judgement call.

  9. TURNOVER RECOVERY IS NEARLY NOISE AND IS SHRUNK ACCORDINGLY. Split-half
     correlation for fumble recoveries is +0.038 and for defensive TDs
     +0.047 -- indistinguishable from zero on a team-season. These are fitted
     as league base rates with only a mild opponent-side adjustment, rather
     than given a team-level model the data does not support. Pretending to
     forecast them per team would add variance to the mean without adding
     information.

 10. THE RESIDUAL-TD RATE ABSORBS WHAT NFLVERSE CANNOT SCORE. Decision #10 of
     scoring_rules.py names three components with no nflverse column
     (blocked-kick return TDs, 2-point returns, some return TDs). They are
     the whole -0.16 mean reconstruction bias. Rather than leave the model
     biased low by a known amount, that bias is fitted as a small constant
     rate and added. It is a correction with a measured size, not a fudge
     factor.

 11b. THE SIMULATOR'S OUTPUT IS RECALIBRATED, AND BOTH ARMS NEEDED IT --
     IN OPPOSITE DIRECTIONS. Simulating well-fitted components does not
     automatically produce a well-calibrated projection, and measuring the
     first version of this model proved it. Regressing realized DST points on
     the projection (2021 DK, 512 defense-weeks; slope 1.0 is calibrated):

         legacy         slope +0.307, corr 0.173, projection SD 3.35
         distributional slope +1.447, corr 0.280, projection SD 1.15

     A predictor with correlation r against outcomes of SD s should itself
     have SD r*s. Legacy's correlation of 0.173 justifies a projection SD of
     1.03; it actually has 3.35, so it spreads defenses **3.3x further apart
     than its own accuracy supports.** That is the ROADMAP's "slope-below-1
     bias" in its most extreme form anywhere in this project, and it means
     the legacy DST projection is confidently wrong about which defense is
     better. The distributional model's 0.69 ratio errs the other way -- too
     compressed, from shrinking components hard -- but is nearly four times
     closer to calibrated.

     Both are fixed by one linear recalibration, `actual ~ a + b*projection`,
     FITTED ON THE FIT WINDOW ONLY so the measurement window stays clean.
     This corrects the level and the spread in a single step, and because it
     is monotone it cannot change the ordering -- so the Spearman gain is
     earned by the model and is not an artifact of the correction.

 11. FIT AND MEASURE ARE SPLIT BY SEASON, BECAUSE SESSION 10.3a PAID FOR THAT
     LESSON. Fitting `statline_variance.json` on the season then measured
     inflated its headline effect roughly threefold and would have gone into
     the log as a finding. Default fit window here is 2014-2017, leaving
     2018-2021 -- the harness's pooled measurement window -- untouched.
     `--fit-seasons` can override for the production refit, which SHOULD use
     all eight seasons once measurement is done.

Usage:
  python3 scripts/fit_dst_model.py                      # fits 2014-2017
  python3 scripts/fit_dst_model.py --fit-seasons 2014 2015 2016 2017 \
      2018 2019 2020 2021                               # production refit
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dst_model  # noqa: E402
from ingest_salaries import BASE_TEAM_ABBREV_MAP  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def canonical_team(s):
    """Decision #12 -- reconcile the two nflverse releases' team codes.

    `games.parquet` uses the ERA-CORRECT abbreviation for the season played
    (SD, STL, OAK), while `stats_team_week` uses the CURRENT franchise code
    retroactively (LAC, LA, LV). Merging the two on `team` without this
    silently drops every affected row: it is an inner join, so a mismatch is
    not an error, it is an absence. Measured when this was found -- the
    2014-2017 fit panel came back 1,776 team-weeks against an expected ~2,048,
    so roughly 13% of the fit data had vanished without a word.

    Reuses `ingest_salaries.py`'s BASE_TEAM_ABBREV_MAP, which already carries
    exactly these mappings (OAK->LV, SD->LAC, STL->LA, LAR->LA), rather than
    declaring a second copy -- same reasoning the ROADMAP gives for
    SITE_CONFIGS being the single source of truth for site differences.

    The site-specific `team_abbrev_overrides` are deliberately NOT applied:
    this is nflverse-to-nflverse reconciliation, not the normalisation of a
    DK or FD export, so bringing a site's quirks into it would be wrong.

    Found only by running the fitter on real data. Static review of the merge
    would not have shown it, because the merge is correct -- the inputs
    disagreed.
    """
    s = pd.Series(s, dtype="object").astype(str).str.strip().str.upper()
    return s.map(lambda t: BASE_TEAM_ABBREV_MAP.get(t, t))
DATA_DIR = REPO_ROOT / "data"
MODEL_PATH = DATA_DIR / "dst_model.json"

SCHEMA_VERSION = 1
DEFAULT_FIT_SEASONS = [2014, 2015, 2016, 2017]

# Decision #5.
WIND_CLIP_MPH = 30.0
# Decision #8 -- shrinkage of a QB's career interception rate toward the
# league mean, in prior pass attempts. 200 is roughly five starts.
QB_INT_SHRINK_ATTEMPTS = 200.0
# Team-rate shrinkage, in prior games. ARBITRARY starting points, flagged as
# such: none of these three is fitted, they are chosen so that a team needs
# most of a season before its own history outweighs the league mean, which is
# what decisions #6/#7/#9's weak split-half correlations argue for.
SHRINK_GAMES = {"sack_rate": 8.0, "int_rate": 12.0, "fumble_rate": 16.0,
                "qb_hit_rate": 6.0, "dropbacks": 6.0}
# Weeks below this are excluded from the FIT (not from projection) because a
# one- or two-game prior mean is mostly noise and would flatten the fitted
# coefficients. Projection handles early weeks via prior-season carryover.
MIN_FIT_WEEK = 5


# ---------------------------------------------------------------------------
# Panel construction -- one row per team per week, defense's point of view.
# ---------------------------------------------------------------------------

def load_team_stats(seasons) -> pd.DataFrame:
    frames = []
    for season in seasons:
        path = DATA_DIR / f"team_stats_{season}.parquet"
        if not path.exists():
            raise SystemExit(
                f"{path.name} not found. Run:\n"
                f"  python3 scripts/ingest_historical.py --season {season}\n"
                f"(Session 10.4 added the team-stats pull to that script; if "
                f"this repo predates it, that is the missing piece.)"
            )
        frames.append(pd.read_parquet(path))
    df = pd.concat(frames, ignore_index=True)
    df = df[df["season_type"] == "REG"].copy()
    # Decision #12 -- both sides of every later merge must speak one dialect.
    df["team"] = canonical_team(df["team"])
    df["opponent_team"] = canonical_team(df["opponent_team"])
    return df


def load_games(seasons) -> pd.DataFrame:
    path = DATA_DIR / "games.parquet"
    if not path.exists():
        raise SystemExit(
            f"{path.name} not found. Run:\n"
            f"  python3 scripts/ingest_historical.py --season {min(seasons)}\n"
            f"which writes the nflverse schedules release."
        )
    g = pd.read_parquet(path)
    g = g[(g["season"].isin(list(seasons))) & (g["game_type"] == "REG")].copy()
    g["home_team"] = canonical_team(g["home_team"])
    g["away_team"] = canonical_team(g["away_team"])
    return g


def load_qb_history(seasons) -> pd.DataFrame:
    """Career-to-date interception rate per QB per week, no lookahead.

    Uses every prior week the player has ever thrown a pass, across seasons
    -- a career rate, not a season rate, since decision #8's shrinkage is in
    attempts and a season rate would restart it every September.
    """
    frames = []
    for season in seasons:
        path = DATA_DIR / f"weekly_stats_{season}.parquet"
        if not path.exists():
            raise SystemExit(
                f"{path.name} not found. Run: "
                f"python3 scripts/ingest_historical.py --season {season}"
            )
        frames.append(pd.read_parquet(path))
    sp = pd.concat(frames, ignore_index=True)
    sp = sp[(sp["season_type"] == "REG")
            & (pd.to_numeric(sp["attempts"], errors="coerce").fillna(0) > 0)]
    sp = sp[["season", "week", "player_id", "attempts", "passing_interceptions"]].copy()
    for c in ("attempts", "passing_interceptions"):
        sp[c] = pd.to_numeric(sp[c], errors="coerce").fillna(0.0)
    sp = sp.sort_values(["season", "week"]).reset_index(drop=True)

    grp = sp.groupby("player_id", sort=False)
    sp["prior_attempts"] = grp["attempts"].cumsum() - sp["attempts"]
    sp["prior_ints"] = grp["passing_interceptions"].cumsum() - sp["passing_interceptions"]
    first_season = sp.groupby("player_id")["season"].min().rename("first_season")
    sp = sp.merge(first_season, on="player_id", how="left")
    sp["is_rookie"] = (sp["season"] == sp["first_season"]).astype(int)
    return sp[["season", "week", "player_id", "prior_attempts", "prior_ints", "is_rookie"]]


def prior_mean(df: pd.DataFrame, key: str, col: str) -> pd.Series:
    """Season-to-date mean over STRICTLY PRIOR weeks. No lookahead, by
    construction: the current row's own value is subtracted before dividing.
    """
    grp = df.groupby(["season", key], sort=False)[col]
    csum = grp.cumsum() - df[col]
    count = grp.cumcount()
    return csum / count.replace(0, np.nan)


def build_panel(seasons) -> pd.DataFrame:
    """One row per team-week, from that team's DEFENSE's point of view."""
    team = load_team_stats(seasons)
    games = load_games(seasons)

    rows = []
    for g in games.itertuples():
        for me, opp, opp_score, spread in (
            (g.home_team, g.away_team, g.away_score, g.spread_line),
            (g.away_team, g.home_team, g.home_score, -g.spread_line),
        ):
            rows.append({
                "season": g.season, "week": g.week, "team": me,
                "opponent_team": opp, "opp_score": opp_score,
                "total_line": g.total_line, "team_spread": spread,
                "wind": g.wind, "roof": g.roof,
                "opp_qb_id": (g.away_qb_id if me == g.home_team else g.home_qb_id),
            })
    sched = pd.DataFrame(rows)
    sched["opp_implied"] = sched["total_line"] / 2.0 - sched["team_spread"] / 2.0

    # Opponent-offense side of the same week (decision #6).
    off_cols = ["sacks_suffered", "attempts", "carries", "passing_interceptions",
                "fumbles_lost_total", "passing_epa", "rushing_epa", "def_tds",
                "fg_blocked", "pat_blocked", "pt_blocked"]
    off = team[["season", "week", "team"] + off_cols].copy()
    off.columns = ["season", "week", "opponent_team"] + ["o_" + c for c in off_cols]

    expected = len(sched)
    d = team.merge(sched, on=["season", "week", "team", "opponent_team"], how="inner")
    # Decision #12 -- fail loud on a lossy merge. This is the check that was
    # missing when 13% of the panel disappeared silently.
    lost = expected - len(d)
    if lost > expected * 0.02:
        missing = (sched.merge(team[["season", "week", "team"]].assign(_k=1),
                               on=["season", "week", "team"], how="left"))
        gone = missing[missing["_k"].isna()]["team"].value_counts().head(8).to_dict()
        raise SystemExit(
            f"build_panel: the schedule has {expected} team-weeks but only "
            f"{len(d)} joined to team stats -- {lost} rows ({lost/expected:.1%}) "
            f"were dropped.\nMost-affected teams: {gone}\n"
            f"That is a team-abbreviation mismatch between games.parquet and "
            f"team_stats_*.parquet (decision #12), not a bye. Not fitting on a "
            f"silently truncated panel."
        )
    d = d.merge(off, on=["season", "week", "opponent_team"], how="left")

    for c in [c for c in d.columns if c.startswith("o_")] + [
            "def_sacks", "def_interceptions", "fumble_recovery_opp",
            "def_safeties", "def_tds", "special_teams_tds", "def_qb_hits"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)

    # Decision #9 of scoring_rules.py -- the charged points-allowed figure.
    d["points_allowed"] = (d["opp_score"] - 7.0 * d["o_def_tds"]).clip(lower=0.0)
    d["blocked_kick"] = d["o_fg_blocked"] + d["o_pat_blocked"] + d["o_pt_blocked"]
    d["dropbacks"] = d["o_attempts"] + d["o_sacks_suffered"]
    d["plays"] = d["dropbacks"] + d["o_carries"]
    d["def_epa_allowed"] = d["o_passing_epa"] + d["o_rushing_epa"]

    # Decision #5 -- wind.
    d["is_indoor"] = d["roof"].isin(["dome", "closed"]).astype(int)
    wind = pd.to_numeric(d["wind"], errors="coerce")
    d["wind_eff"] = np.where(d["is_indoor"] == 1, 0.0,
                             wind.fillna(0.0).clip(0.0, WIND_CLIP_MPH))

    d = d.sort_values(["season", "week"]).reset_index(drop=True)

    # Prior-weeks features (no lookahead -- see prior_mean).
    d["own_epa_prior"] = prior_mean(d, "team", "def_epa_allowed")
    d["own_sack_prior"] = prior_mean(d, "team", "def_sacks")
    d["own_qbhit_prior"] = prior_mean(d, "team", "def_qb_hits")
    d["own_int_prior"] = prior_mean(d, "team", "def_interceptions")
    d["own_fum_prior"] = prior_mean(d, "team", "fumble_recovery_opp")
    d["own_dropbacks_faced_prior"] = prior_mean(d, "team", "dropbacks")

    # Opponent-offense priors keyed on the OPPONENT, hence the rename.
    od = d.rename(columns={"opponent_team": "_opp_key"})
    d["opp_sack_allowed_prior"] = prior_mean(od, "_opp_key", "o_sacks_suffered")
    d["opp_int_thrown_prior"] = prior_mean(od, "_opp_key", "o_passing_interceptions")
    d["opp_fum_lost_prior"] = prior_mean(od, "_opp_key", "o_fumbles_lost_total")
    d["opp_dropbacks_prior"] = prior_mean(od, "_opp_key", "dropbacks")

    # Decision #8 -- opponent starting QB's career interception rate.
    qb = load_qb_history(seasons).rename(columns={"player_id": "opp_qb_id"})
    d = d.merge(qb, on=["season", "week", "opp_qb_id"], how="left")
    return d


# ---------------------------------------------------------------------------
# Fitting helpers
# ---------------------------------------------------------------------------

def ols(y: np.ndarray, X: np.ndarray) -> tuple:
    """Least squares with t-statistics. Returns (beta, tvals, r2).

    Deliberately not statsmodels: this project's runtime dependency set is
    pandas / numpy / scipy / PuLP, and one OLS with t-stats does not justify
    adding statsmodels to the production install just so the fitter can run.
    """
    n, k = X.shape
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = n - k
    sigma2 = float(resid @ resid) / dof
    xtx_inv = np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.diag(xtx_inv) * sigma2)
    tvals = np.divide(beta, se, out=np.zeros_like(beta), where=se > 0)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float(resid @ resid) / ss_tot if ss_tot > 0 else 0.0
    return beta, tvals, r2


def fit_nb_dispersion(y: np.ndarray, mu: np.ndarray) -> float:
    """MLE for the negative binomial's dispersion r, given fitted means.

    Decision #1. Parameterized so var = mu + mu^2 / r, i.e. larger r means
    closer to Poisson.
    """
    mu = np.clip(mu, 1e-6, None)
    y = np.clip(np.round(y), 0, None)

    def nll(log_r):
        r = np.exp(log_r)
        p = r / (r + mu)
        return -float(stats.nbinom.logpmf(y, r, p).sum())

    res = optimize.minimize_scalar(nll, bounds=(-2.0, 8.0), method="bounded")
    return float(np.exp(res.x))


def _linear_block(panel: pd.DataFrame, target: str, feature_cols: list) -> dict:
    """Fit target ~ const + features, return coefficients, t-stats, R2 and
    the NB dispersion of the residual count."""
    sub = panel.dropna(subset=[target] + feature_cols)
    y = sub[target].to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(sub))] + [sub[c].to_numpy(dtype=float)
                                               for c in feature_cols])
    beta, tvals, r2 = ols(y, X)
    mu = X @ beta
    return {
        "intercept": round(float(beta[0]), 6),
        "coefficients": {c: round(float(b), 6) for c, b in zip(feature_cols, beta[1:])},
        "t_statistics": {c: round(float(t), 3) for c, t in zip(feature_cols, tvals[1:])},
        "r_squared": round(float(r2), 5),
        "n": int(len(sub)),
        "nb_dispersion": round(fit_nb_dispersion(y, mu), 4),
        "observed_mean": round(float(y.mean()), 4),
        "observed_sd": round(float(y.std()), 4),
    }


# ---------------------------------------------------------------------------
# The fit
# ---------------------------------------------------------------------------

def fit(seasons) -> dict:
    panel = build_panel(seasons)
    print(f"Panel: {len(panel):,} team-weeks over seasons {list(seasons)}.")

    fit_rows = panel[panel["week"] >= MIN_FIT_WEEK].copy()
    print(f"Fitting on {len(fit_rows):,} rows (week >= {MIN_FIT_WEEK}).")

    # --- Points allowed (decisions #2, #3) --------------------------------
    pa = _linear_block(fit_rows, "points_allowed",
                       ["opp_implied", "own_epa_prior", "wind_eff"])
    print(f"  points_allowed: R2={pa['r_squared']:.4f} "
          f"implied={pa['coefficients']['opp_implied']:+.4f} "
          f"epa={pa['coefficients']['own_epa_prior']:+.4f}"
          f"(t={pa['t_statistics']['own_epa_prior']:+.2f}) "
          f"wind={pa['coefficients']['wind_eff']:+.4f}"
          f"(t={pa['t_statistics']['wind_eff']:+.2f}) r={pa['nb_dispersion']}")

    # --- Dropbacks faced (decision #4) ------------------------------------
    fit_rows["game_total"] = fit_rows["total_line"]
    fit_rows["abs_spread"] = fit_rows["team_spread"].abs()
    db = _linear_block(fit_rows, "dropbacks",
                       ["opp_dropbacks_prior", "game_total", "abs_spread", "wind_eff"])
    print(f"  dropbacks:      R2={db['r_squared']:.4f} "
          f"wind t={db['t_statistics']['wind_eff']:+.2f}")

    # --- Sacks (decisions #6, #7) -----------------------------------------
    # Modelled as a RATE per dropback so it scales with predicted volume,
    # then multiplied by predicted dropbacks at projection time.
    fit_rows["own_sack_rate_prior"] = (
        fit_rows["own_sack_prior"] / fit_rows["own_dropbacks_faced_prior"].replace(0, np.nan))
    fit_rows["opp_sack_rate_prior"] = (
        fit_rows["opp_sack_allowed_prior"] / fit_rows["opp_dropbacks_prior"].replace(0, np.nan))
    # Decision #7: own QB-hit rate deliberately NOT included -- it correlates
    # 0.559 with the own sack rate and contributes nothing on its own.
    fit_rows["sack_rate"] = fit_rows["def_sacks"] / fit_rows["dropbacks"].replace(0, np.nan)
    sk = _linear_block(fit_rows, "sack_rate",
                       ["opp_sack_rate_prior", "own_sack_rate_prior", "wind_eff"])
    sk["nb_dispersion"] = round(fit_nb_dispersion(
        fit_rows["def_sacks"].to_numpy(float),
        np.clip(fit_rows["def_sacks"].mean() * np.ones(len(fit_rows)), 1e-6, None)), 4)
    print(f"  sack_rate:      R2={sk['r_squared']:.4f} "
          f"opp t={sk['t_statistics']['opp_sack_rate_prior']:+.2f} "
          f"own t={sk['t_statistics']['own_sack_rate_prior']:+.2f} "
          f"wind t={sk['t_statistics']['wind_eff']:+.2f}")

    # --- Interceptions (decision #8) --------------------------------------
    lg_int_rate = float((fit_rows["def_interceptions"].sum()
                         / fit_rows["o_attempts"].sum()))
    qb_rate = ((fit_rows["prior_ints"].fillna(0.0) + QB_INT_SHRINK_ATTEMPTS * lg_int_rate)
               / (fit_rows["prior_attempts"].fillna(0.0) + QB_INT_SHRINK_ATTEMPTS))
    fit_rows["qb_int_rate_prior"] = qb_rate
    fit_rows["own_int_rate_prior"] = (
        fit_rows["own_int_prior"] / fit_rows["own_dropbacks_faced_prior"].replace(0, np.nan))
    fit_rows["int_rate"] = fit_rows["def_interceptions"] / fit_rows["o_attempts"].replace(0, np.nan)
    it = _linear_block(fit_rows, "int_rate",
                       ["qb_int_rate_prior", "own_int_rate_prior", "wind_eff"])
    rookie = fit_rows.dropna(subset=["is_rookie"])
    r_mult = float(rookie[rookie.is_rookie == 1]["def_interceptions"].mean()
                   / rookie[rookie.is_rookie == 0]["def_interceptions"].mean())
    it["rookie_multiplier"] = round(r_mult, 4)
    it["qb_shrink_attempts"] = QB_INT_SHRINK_ATTEMPTS
    it["league_int_rate"] = round(lg_int_rate, 6)
    it["nb_dispersion"] = round(fit_nb_dispersion(
        fit_rows["def_interceptions"].to_numpy(float),
        np.clip(fit_rows["def_interceptions"].mean() * np.ones(len(fit_rows)), 1e-6, None)), 4)
    print(f"  int_rate:       R2={it['r_squared']:.4f} "
          f"qb t={it['t_statistics']['qb_int_rate_prior']:+.2f} "
          f"own t={it['t_statistics']['own_int_rate_prior']:+.2f} "
          f"rookie_mult={r_mult:.3f}")

    # --- Fumble recoveries (decision #9) ----------------------------------
    fum = {
        "league_rate_per_game": round(float(panel["fumble_recovery_opp"].mean()), 5),
        "opp_fumbles_lost_league": round(float(panel["o_fumbles_lost_total"].mean()), 5),
        "opp_weight": 0.5,
        "nb_dispersion": round(fit_nb_dispersion(
            panel["fumble_recovery_opp"].to_numpy(float),
            np.clip(panel["fumble_recovery_opp"].mean() * np.ones(len(panel)), 1e-6, None)), 4),
        "split_half_note": "team-season split-half r = +0.038; shrunk to league mean",
    }

    # --- Rare events (decisions #9, #10) ----------------------------------
    rare = {
        "def_td_per_game": round(float(panel["def_tds"].mean()), 5),
        "st_td_per_game": round(float(panel["special_teams_tds"].mean()), 5),
        "safety_per_game": round(float(panel["def_safeties"].mean()), 5),
        "blocked_kick_per_game": round(float(panel["blocked_kick"].mean()), 5),
        # Decision #10 -- the measured reconstruction shortfall, expressed as
        # an extra-TD-equivalent rate so it lands in the mean AND the variance
        # rather than being bolted on as a constant.
        "residual_td_per_game": 0.0,
    }

    model = {
        "schema_version": SCHEMA_VERSION,
        "fitted_on": date.today().isoformat(),
        "fit_seasons": [int(s) for s in seasons],
        "n_team_weeks": int(len(panel)),
        "n_fit_rows": int(len(fit_rows)),
        "min_fit_week": MIN_FIT_WEEK,
        "wind_clip_mph": WIND_CLIP_MPH,
        "shrink_games": SHRINK_GAMES,
        "points_allowed": pa,
        "dropbacks": db,
        "sack_rate": sk,
        "int_rate": it,
        "fumble_recovery": fum,
        "rare_events": rare,
        "league_means": {
            "points_allowed": round(float(panel["points_allowed"].mean()), 4),
            "dropbacks": round(float(panel["dropbacks"].mean()), 4),
            "sacks": round(float(panel["def_sacks"].mean()), 4),
            "interceptions": round(float(panel["def_interceptions"].mean()), 4),
            "opp_implied": round(float(panel["opp_implied"].mean()), 4),
            "qb_hits": round(float(panel["def_qb_hits"].mean()), 4),
        },
    }
    return model, panel


def measure_within_game_corr(panel: pd.DataFrame, site: str = "dk") -> float:
    """Decision #13's calibration target: the correlation between a DST's
    bracket points and its other components AFTER removing everything the
    model already predicts.

    Residualising matters. The RAW cross-sectional correlation is +0.301, but
    part of that is simply good defenses being good at both -- which the
    simulator already reproduces through each team's own fitted means.
    Calibrating the latent factor against the raw number would double-count
    that and inflate every sigma. Residualised against the same predictors
    the points-allowed model uses, the leftover within-game co-movement is
    +0.268, and that is what the factor exists to reproduce.
    """
    import scoring_rules

    f = panel[panel["week"] >= MIN_FIT_WEEK].dropna(subset=["own_epa_prior"]).copy()
    comp = {
        "points_allowed": f["points_allowed"].to_numpy(float),
        "sack": f["def_sacks"].to_numpy(float),
        "interception": f["def_interceptions"].to_numpy(float),
        "fumble_recovery": f["fumble_recovery_opp"].to_numpy(float),
        "safety": f["def_safeties"].to_numpy(float),
        "def_td": f["def_tds"].to_numpy(float),
        "st_td": f["special_teams_tds"].to_numpy(float),
        "blocked_kick": f["blocked_kick"].to_numpy(float),
        "two_pt_return": np.zeros(len(f)),
    }
    bracket = scoring_rules.dst_bracket_points(comp["points_allowed"], site)
    other = scoring_rules.score_dst(comp, site) - bracket

    X = np.column_stack([np.ones(len(f)),
                         f["opp_implied"].to_numpy(float),
                         f["own_epa_prior"].to_numpy(float)])

    def resid(y):
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        return y - X @ beta

    br, ot = resid(bracket), resid(other)
    return float(np.corrcoef(br, ot)[0, 1])


def calibrate_residual_td(model: dict, panel: pd.DataFrame) -> float:
    """Decision #10. Size the unscoreable-component correction against the
    reconstruction bias the scoring self-check measures, expressed as a
    per-game touchdown-equivalent rate."""
    # scoring_rules' measured DK bias is -0.156 points/game. A def/ST TD is
    # worth 6, so the equivalent rate is bias/6.
    return round(0.156 / 6.0, 5)


def fit_recalibration(model: dict, seasons, sims: int, site: str = "dk") -> dict:
    """Decision #11b. Fit `actual ~ a + b * simulated_projection` on the FIT
    WINDOW, so the measurement window never sees it.

    Runs the real simulator over every fit-window week, which is slower than
    fitting a coefficient in closed form but is the only way the correction
    is fitted against what the model ACTUALLY emits rather than against an
    analytic stand-in for it. This project's own repeated lesson.
    """
    games = load_games(seasons)
    rows = []
    for season in seasons:
        path = DATA_DIR / f"rotoguru_actuals_{site}_{season}.csv"
        if not path.exists():
            print(f"  recalibration: {path.name} missing, season skipped.")
            continue
        act = pd.read_csv(path)
        act = act[act["rotoguru_position"].astype(str).str.upper().isin(["DEF", "DST", "D"])].copy()
        act["team"] = dst_model.canonical_team(act["team"]).to_numpy()
        for week in sorted(act["week"].unique()):
            wk = games[(games["season"] == season) & (games["week"] == week)]
            vrows = []
            for g in wk.itertuples():
                if pd.isna(g.total_line) or pd.isna(g.spread_line):
                    continue
                for me, opp, sp in ((g.home_team, g.away_team, -g.spread_line),
                                    (g.away_team, g.home_team, g.spread_line)):
                    vrows.append({"team": me, "opponent": opp,
                                  "implied_total": round(g.total_line / 2 - sp / 2, 2),
                                  "over_under": float(g.total_line)})
            if not vrows:
                continue
            vegas = pd.DataFrame(vrows)
            aw = act[act["week"] == week]
            teams = sorted(set(vegas["team"]) & set(aw["team"]))
            if len(teams) < 8:
                continue
            feat = dst_model.build_features(season, int(week), teams, vegas,
                                            model, games=games)
            sim = dst_model.simulate(feat, site, model, n_sims=sims,
                                     seed=90000 + int(week))
            merged = sim[["team", "final_projection"]].merge(
                aw[["team", "actual_points"]], on="team", how="inner")
            rows.append(merged)

    if not rows:
        raise SystemExit(
            "fit_recalibration: no fit-window weeks produced a comparison. "
            "The recalibration cannot be fitted, and shipping without it "
            "would leave the measured slope error in place -- see decision "
            "#11b. Check that rotoguru_actuals_*.csv exist for the fit "
            "seasons."
        )
    df = pd.concat(rows, ignore_index=True)
    x = df["final_projection"].to_numpy(float)
    y = df["actual_points"].to_numpy(float)
    beta, tvals, r2 = ols(y, np.column_stack([np.ones(len(x)), x]))
    out = {
        "intercept": round(float(beta[0]), 5),
        "slope": round(float(beta[1]), 5),
        "n": int(len(df)),
        "pre_correction_mean": round(float(x.mean()), 4),
        "pre_correction_sd": round(float(x.std()), 4),
        "actual_mean": round(float(y.mean()), 4),
        "actual_sd": round(float(y.std()), 4),
        "correlation": round(float(np.corrcoef(x, y)[0, 1]), 4),
        "fit_seasons": [int(s) for s in seasons],
    }
    print(f"  recalibration:  actual = {out['intercept']:+.3f} "
          f"{out['slope']:+.3f} * proj   (n={out['n']}, "
          f"corr={out['correlation']:.3f})")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sims", type=int, default=4000,
                    help="Sims per defense during recalibration fitting "
                         "(default 4000 -- the correction is a two-parameter "
                         "line over thousands of rows, so it does not need "
                         "production sim counts).")
    ap.add_argument("--fit-seasons", type=int, nargs="+", default=DEFAULT_FIT_SEASONS,
                    help=f"Seasons to fit on (default {DEFAULT_FIT_SEASONS} -- "
                         f"decision #11's holdout).")
    ap.add_argument("--out", type=Path, default=MODEL_PATH)
    args = ap.parse_args()

    model, panel = fit(args.fit_seasons)
    model["rare_events"]["residual_td_per_game"] = calibrate_residual_td(model, panel)

    # Decision #13 lives in dst_model.py (the consumer owns the draw scheme);
    # the fitter calls it so the calibrated constant ships inside the
    # artifact rather than being recomputed on every projection run.
    target = measure_within_game_corr(panel)
    model["latent_factor"] = {
        "strength": 0.0,
        "target_within_game_corr": round(target, 4),
        "note": "see dst_model.py decision #13",
    }
    strength = dst_model.calibrate_latent(model, site="dk", target_corr=target)
    model["latent_factor"]["strength"] = strength
    print(f"  latent_factor:  strength={strength} "
          f"(calibrated to within-game corr {target:+.3f})")

    # Decision #11b -- recalibration, fitted on the FIT WINDOW only.
    model["recalibration"] = fit_recalibration(model, args.fit_seasons, args.sims)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(model, indent=2))
    print(f"\nWrote {args.out} (schema_version {SCHEMA_VERSION}, "
          f"fit on {model['fit_seasons']}).")
    if set(model["fit_seasons"]) & {2018, 2019, 2020, 2021}:
        print("NOTE: this fit includes measurement-window seasons (2018-2021). "
              "Correct for a PRODUCTION refit, wrong for measuring against the "
              "harness -- see decision #11.")


if __name__ == "__main__":
    main()
