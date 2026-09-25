"""
statline_model.py
==================

Session 10.3a -- the stat-line projection model (the CONSUMER).

Projects a per-player STAT LINE (attempts/carries/targets/receptions/yards/
TDs), simulates it, scores every draw with the site's exact rules
(scoring_rules.py), and returns a per-player MEAN and SIGMA. This is the
structural change Phase 10's design calls "Gap 1" -- it is what makes
sigma-from-composition, prop ingestion and share reconciliation possible at
all, none of which can be done against a direct-points projection.

Read `fit_statline_variance.py` for where the variance parameters come from.
This file never imports the fitter.

Numbered decisions:

  1. MONTE CARLO, NOT AN ANALYTIC MEAN. DK pays +3 at 300 passing / 100
     rushing / 100 receiving yards, which are step functions, so
     E[points] != points(E[stats]). A player averaging 85 receiving yards
     has a real chance of clearing 100; scoring his mean line awards him
     exactly none of that. Simulating and averaging gets both the mean and
     the sigma right in one pass, and handles the yards/TD correlation
     natively instead of by an independence assumption. This is the same
     argument the ROADMAP already makes for DST's scoring brackets.

  2. ITS OWN RNG, NEVER THE GLOBAL ONE. Every draw comes from a
     `np.random.Generator` created here from an explicit seed. Session
     10.2's bug #3 was RNG state leakage: an extra draw in one arm shifted
     the state for every later week and silently un-pinned the synthetic
     field that the whole measurement depends on. Touching `np.random`'s
     global state from inside the projection path would reintroduce exactly
     that failure, one layer deeper and harder to see.

  3. VOLUME FROM OWN RECENT USAGE, EFFICIENCY SHRUNK TO POSITION MEAN.
     Volume is the sticky, forecastable part; per-opportunity efficiency
     (especially TD rate) is mostly noise on a 1-16 game sample. Volume uses
     projections_baseline.py's OWN recency weights, deliberately, so that a
     comparison against the Session 10.1 baseline isolates the stat-line
     decomposition instead of confounding it with a different recency
     scheme.

  4. EMPIRICAL-BAYES SHRINKAGE ON RATES, in denominator units:
         rate = (own_numerator + K * position_rate) / (own_denominator + K)
     A player with 200 carries barely moves toward the positional mean; one
     with 12 carries is mostly the positional mean. The K values below are
     ARBITRARY starting points chosen here -- not user-confirmed, not fit.
     Flagged per this project's convention (same status as
     OWNERSHIP_SOFTMAX_TEMPERATURE and Session 10.2's cold-start k). They
     are the first thing to retune once there is a tradeoff curve to fit
     against.

  5. CURRENT-SEASON HISTORY ONLY, weeks STRICTLY BEFORE the target week.
     Same lookahead guard and same contract as projections_baseline.py, so
     the two engines see identical information and the comparison is fair.
     Consequence, stated rather than hidden: week 1 is still unbuildable
     (no prior weeks -> no volume), exactly as for the legacy engine.
     Cross-season carryover and the salary cold-start are Session 10.3b.

  6. SIGMA IS IDIOSYNCRATIC BY CONSTRUCTION. Every player is drawn
     independently, so the returned sigma contains no team-level correlated
     component. That is the correct thing for Phase 10's objective
     (`sum(mean) - lambda * idiosyncratic sigma`), because the design keeps
     correlated variance in the optimizer's stacking CONSTRAINTS rather than
     the objective. Stated explicitly so Session 10.5 does not have to guess
     which kind of sigma this is.

  7. SHARE RECONCILIATION AGAINST TEAM VOLUME, NORMALIZED TO THE POOL'S OWN
     HISTORICAL SHARE -- never to 1.0. The slate pool is a subset of a
     team's real players, so forcing pool targets to sum to team pass
     attempts would inflate every pool player by whatever the missing
     bench accounts for. Instead: predict team volume, multiply by the share
     of that volume these same players historically took, and rescale to
     match. Past RECONCILE_FAIL_THRESHOLD the rescale is a hard error, not a
     silent correction -- the ROADMAP requires "fail loud past threshold",
     and a 40% rescale means the volume model or the team mapping is broken,
     which is worth stopping for.

  8. WHAT IS DELIBERATELY NOT PROJECTED: two-point conversions, punt/kick
     return TDs, and offensive fumble-recovery TDs. All three are real
     scoring on both sites and all three are close to unforecastable noise.
     scoring_rules.py honours them when supplied; this model leaves them at
     zero, which slightly understates every player by the same tiny amount.
     Named so it is a known gap rather than an oversight.

 9. VOLUME IS PARTICIPATION-WEIGHTED, i.e. UNCONDITIONAL. Found by the
     first real run of this engine, via decision #7's fail-loud, and it is
     the one real bug of this session. A recency-weighted average over a
     player's history averages only the games he APPEARED in, which is a
     volume conditional on playing -- so a backup who started once looks
     like a full-time starter forever. Concretely: Cooper Rush, DAL, 2021
     week 10, appeared in exactly one prior week (week 8, 40 pass attempts
     covering an injured Dak Prescott) and was therefore projected at 40
     attempts. Summed with Prescott's 36.4, the pool projected 77.5 pass
     attempts for a team that threw 39.6.

     Fixed by multiplying volume by the share of the TEAM's last five PLAYED
     weeks in which the player recorded a stat line (team-relative, so a
     past bye is not counted as an absence). Rush goes to 0.2 x 40 = 8,
     Prescott to 0.8 x 36.4 = 29.1, and the team total lands near its real
     value. A full-time starter has participation 1.0 and is unaffected.

     What this deliberately does NOT solve: a player returning from a long
     injury is under-projected until he accumulates appearances, because
     participation cannot distinguish "was hurt, is healthy now" from "is a
     backup". Session 5.1's status_check.py already zeroes players ruled OUT,
     and the role-change flag that would handle the returning-starter case is
     Session 10.3b. Named as a known limitation, not an oversight.

     Note this is a real error the LEGACY engine also makes -- it over-
     projects part-time players for the same reason -- but nothing there ever
     surfaced it, because a points average has no team-level constraint to
     violate. Decision #7's reconciliation is what made it visible.

 11. SESSION 10.3b -- PRICE IS A COLD-START PRIOR ON VOLUME, and nothing
     more by default. The mechanism lives in volume_prior.py (read its
     decisions #1-#8 for the measured evidence); this module only calls it.
     `apply_volume_prior()` is a no-op unless a caller passes an artifact,
     so an existing Session 10.3a run is byte-for-byte unchanged.

 12. SESSION 10.3b -- `{comp}_mu_raw` IS NOW STORED ALONGSIDE `{comp}_mu`.
     `_mu` is the participation-weighted (unconditional) volume decision #9
     built; `_mu_raw` is the same number BEFORE participation is applied.
     Both are kept because the role-change override (volume_prior.py
     decision #3) works by RECOMPUTING `_mu = _mu_raw * participation_eff`.
     Recovering `_mu_raw` by dividing `_mu` by participation would divide by
     zero for exactly the players the override exists for.

 13. SESSION 10.3b -- TEAM VOLUME IS VEGAS-ANCHORED WHEN AN ARTIFACT IS
     SUPPLIED, replacing decision #10's deliberately-left-open alternative.
     Measured out-of-sample (probe B): pass attempts R2 0.0652 -> 0.0799,
     carries 0.0394 -> 0.0667. Note what that also says -- the team-history
     prediction this module has anchored reconciliation to since Session
     10.3a explains under 7% of the variance in either channel. See
     volume_prior.py decision #8; reconciliation is not thereby wrong, it is
     just normalizing to a weaker number than its role suggests.

     Decision #10 stands otherwise: the matchup/vegas MULTIPLIERS still
     scale efficiency, not volume. What changes is that the team-level
     TARGET reconciliation normalizes to is now a fitted function of the
     line rather than of team history alone.

 14. SESSION 10.3b -- WEEK 1 IS BUILDABLE, which supersedes decision #5's
     closing sentence. At week 1 there is no history at all, so:
       - team volume comes from volume_prior's `no_history` specification
         (league mean tilted by the line -- prior-season carryover measured
         WORSE than the league mean, volume_prior.py decision #6),
       - player volume is price_share x that team volume, since the
         cold-start weight is 1.0 at games_played = 0,
       - participation is BYPASSED rather than applied. This is the trap:
         `_participation()` returns 0.0 when the team has no played weeks,
         and multiplying a price-predicted volume by it would return the
         engine to a pool of zeros while looking like it had worked.
       - reconciliation's non-exclusive pool share falls back to the
         PRICE-implied pool share (`share_basis = "price"`), because there
         is no historical pool share to take.

 15. SESSION 10.3b -- THE ROLE-CHANGE OVERRIDE RAISES PARTICIPATION, and is
     the direct fix for the limitation decision #9 named and left open. Its
     strength is volume_prior.py's FITTED slope, not a constant chosen here.

 17. SESSION 10.3b -- COLD-START EFFICIENCY IS THE POSITION MEAN, FILLED
     EXPLICITLY. The design note for this card asserted that efficiency at
     cold start was already handled because _shrink() returns the position
     mean at a zero denominator. That was WRONG: _shrink() is only reached
     for players build_usage() emits a row for, and a zero-history player is
     not one of them. His rates come out of the left join as NaN, and NaN
     times a correctly cold-started volume is NaN. fill_cold_start_rates()
     closes it, using the same artifact values _shrink() would have used.

 16. SESSION 10.3b -- AN EMPTY build_usage() STILL CARRIES ITS SCHEMA. It
     used to return a bare `pd.DataFrame()`, which has no `player_id` column,
     so every caller's merge raised `KeyError: 'player_id'`. Latent through
     all of Session 10.3a because week 1 was skipped before the merge was
     reached; it killed all four week-1 backtests on the first run in which
     week 1 was buildable. An empty result is a valid result and has to be
     shaped like one.

 10. THE MARKET FACTOR IS APPLIED TO EFFICIENCY, NOT VOLUME. matchup_factor
     and vegas_factor arrive from Sessions 2.2/2.3 as "1.0 = league average"
     multipliers; they scale the yards-per-opportunity and TD-per-
     opportunity rates, leaving volume driven by the player's own role. The
     defensible alternative -- game environment also moves team pass volume
     -- needs a real Vegas-to-team-volume model, which is Session 10.3b.
     Flagged as a decision, not a discovered truth: at a uniform factor the
     two choices are nearly the same on the mean and differ mainly in the
     variance structure and in how often a bonus threshold is crossed.

 18. SESSION 15.2C -- TEAMMATE VOLUME IS NOW CORRELATED WITHIN simulate(),
     replacing decision #15's note (in fit_statline_variance.py's own
     docstring) that every player was drawn fully independently. Session
     15.2b tried this and rejected it because it made a real coverage
     backtest WORSE; Session 15.2c found why (r already absorbed the
     team-level swing, so adding a shock on top double-counted it) and
     fixed it at the source: fit_statline_variance.py's r is now fit NET
     of the team-level share (its own decision #8), so the shock this
     module adds back is additive information, not a duplicate.

     Mechanically: before the per-player loop, one shared shock array
     (length n_sims) is drawn per (team, component) present in
     variance["team_shock"] -- every player on that team who isn't in
     team_shock["excluded_pairs"] uses the SAME shock array, which is
     what makes their simulated volumes move together instead of
     independently. Each player's own mean is shifted by
     `redistribution_shock_scale * sqrt(r / (r + 1)) * pass_through_slope
     * his own {comp}_hist_share * shock` before drawing -- the
     `sqrt(r/(r+1))` term exactly cancels a real, verified inflation the
     negative binomial's own mu^2/r term otherwise introduces when its
     mean is randomized (Jensen's inequality on a convex function); the
     `redistribution_shock_scale` in the artifact is a second, empirical
     correction found by grid search against a real held-out coverage
     backtest, not derivable in closed form. Both corrections are
     fit_statline_variance.py's to own (decision #9); this module only
     reads and applies them. `{comp}_hist_share` is apply_volume_prior()'s
     own existing audit column, reused as-is rather than recomputed --
     it is the closest available live match to what the backtest that
     validated this mechanism was actually measured against.

     A missing/old artifact (no "team_shock" key, or
     redistribution_shock_scale absent) degrades to exactly today's
     independent draws -- this is additive to decision #15's mechanism,
     never a hard requirement of it.

 19. SESSION 15.3 -- A GENUINELY MISSING CURRENT-SEASON FILE IS WEEK 1,
     NOT AN ERROR. `load_history()` used to hard-stop (`SystemExit`) if
     `weekly_stats_{season}.parquet` didn't exist at all. That guard was
     right for the wrong reason: it never actually fired on a real live
     build, because `current_slate.json`'s season field had been left on
     the prior completed season, so `load_history()` always found a
     populated (if stale) file. Corrected to the slate's real season, a
     genuine real-season week 1 build hits exactly the case decision #14
     already exists to handle -- except `ingest_historical.py`'s own
     `ingest_weekly_stats()` deliberately never writes a placeholder file
     for a season with no games played yet (see its docstring), so that
     file's total absence is the NORMAL week-1 state, not a sign of a
     broken setup.

     `load_history()` now prints a clear note and returns an empty frame
     instead of raising, mirroring `load_depth_chart()`'s own established
     graceful-degradation pattern rather than inventing a second one.
     `build_usage()`, `team_defense_history()`, and `team_volume_history()`
     each guard against this now being a genuinely COLUMNLESS empty frame
     (not just zero rows in an otherwise-real frame) before doing anything
     that would require a specific column to exist on it -- `build_usage()`
     then falls straight through to decision #16's own already-correct
     schema-carrying empty result, unchanged.

 20. SESSION 15.3 -- A SATURATED CURVE CAN'T DIFFERENTIATE PLAYERS IT WAS
     NEVER ASKED TO TELL APART. apply_volume_prior()'s Session 14.0b fix
     normalizes a team's price_share down when it sums past 1.0 -- correct
     when the underlying values still carry real information, broken when
     share_from_salary()'s curve has already flattened near its ceiling
     for MULTIPLE teammates at once, since proportionally normalizing
     near-identical numbers just splits evenly, discarding whatever real
     salary gap remains. Confirmed on a real live Showdown slate: three
     same-team QBs priced $9,400/$7,400/$6,000 (a real ~57% gap) all
     evaluated to 0.97-0.98 pre-normalization, because the curve was fit
     almost entirely on Classic salaries, where a real backup is rarely
     priced anywhere near this zone -- it was never asked to differentiate
     WITHIN it. The existing fix then divided three near-equal numbers by
     their own sum: a dead-even ~33/33/33 split.

     Fixed by falling back to real salary (raised to a power, since the
     curve can no longer express the gap but salary still can) among any
     (team, component) group with 2+ saturated players, before the
     existing Session 14.0b normalization runs -- the two compose rather
     than one replacing the other. Checked directly against every other
     position's own fitted curve in this exact artifact: RB/WR/TE top out
     at 0.775/0.308/0.276 respectively even at their fitted salary
     maximums, nowhere near the saturation threshold, because those roles
     are genuinely shared even among real starters -- confirmed to have
     ZERO effect on them on this same real slate. Only a position whose
     real-world role is genuinely winner-take-all can saturate multiple
     teammates at once, which in practice is QB alone.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

import scoring_rules

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

ARTIFACT_PATH = DATA_DIR / "statline_variance.json"

# Decision #3 -- projections_baseline.py's own weights, most recent first.
RECENCY_WEIGHTS = np.array([0.35, 0.25, 0.20, 0.12, 0.08])

# Decision #4 -- ARBITRARY shrinkage strengths, in denominator units.
# NOT fit, NOT user-confirmed. First retuning target.
SHRINK_K = {
    "yards": 40.0,   # yards per opportunity
    "td": 120.0,     # TDs per opportunity -- shrunk hardest, it is the noisiest
    "catch": 40.0,   # receptions per target
    "int": 400.0,    # interceptions per attempt
}

# Decision #7 -- past this proportional rescale, reconciliation is an error,
# but only once the volume involved is material (see RECONCILE_MIN_VOLUME).
RECONCILE_FAIL_THRESHOLD = 0.40
# Below this predicted team-component volume the relative test carries no
# information, so it is not allowed to fail the run. ARBITRARY, flagged.
RECONCILE_MIN_VOLUME = 10.0

# Decision #20 (Session 15.3): a share_from_salary() curve stops
# differentiating players once it flattens out near its ceiling -- see
# apply_volume_prior()'s own note at the normalization step below for the
# full real-slate finding. SATURATED_SHARE_THRESHOLD marks "the curve has
# effectively stopped telling players apart here"; SATURATED_SALARY_POWER
# is the exponent used to fall back to real salary (which the curve can no
# longer express) among players caught in that flat zone. Both are UNFIT
# starting guesses -- chosen so a real $9,400/$7,400/$6,000 same-team QB
# trio split roughly 71/22/8 rather than the ~33/33/33 a saturated curve's
# own values would otherwise produce -- retuning targets for Session 11.1
# once real logged ownership/actuals exist to fit them against.
SATURATED_SHARE_THRESHOLD = 0.90
# apply_volume_prior(floor_share_fix=True): depth rank at/above which a
# floor-priced zero-history player is never excluded.
FLOOR_SHARE_GUARD = {"RB": 1, "WR": 3, "TE": 1}
SATURATED_SALARY_POWER = 5

# Week 2 post-mortem finding (2026): the cold-start price prior is the right
# answer in real Week 1, where nobody has history. From Week 2 on, a
# RB/WR/TE with ZERO appearances while his team HAS played is not "no
# information" -- he was inactive or a healthy scratch, and that absence is
# itself strong evidence. Measured on the real 2026 Week 2 main slate: 254 of
# 465 skill players had no Week 1 stat line, the pool projected them 2.9x the
# touches they actually got (actual/projected 0.35), and the freed-up volume
# had been stolen from real starters (starters >= $4.7k saw ~1.36x their
# projected opportunity). By price: <= $4.0k absent players got ~15-26% of
# projected touches; $4.0-4.5k roughly matched; the 2 players >= $4.5k
# (injury returnees / newly promoted starters) were UNDER-projected. The
# 2026 sample is thin above $4.5k, so the fade-out follows an out-of-sample
# check on 2018-21 weeks 2-4 (~1,000 absent RB/WR/TE): absent players priced
# <= $4.0k were dead (<=1 touch) 73-83% of the time and got ~0.3x the
# touches of same-priced players who had appeared; at $4.5-5.5k (n=18) about
# half were still dead, ~0.33x touches. So the discount fades linearly from
# full at $4.0k to none at $5.5k. Treat the constants as a starting point to
# re-fit as weeks accumulate, not a final answer.
ABSENT_PLAYER_FACTOR = 0.25          # price-volume multiplier at/below the floor salary
ABSENT_DISCOUNT_FULL_SALARY = 4000   # full discount at or below this salary
ABSENT_DISCOUNT_NONE_SALARY = 5500   # no discount at or above this salary; linear between
# Systemic-breakage gates (decision #7). All ARBITRARY, flagged.
RECONCILE_MAX_VIOLATION_SHARE = 0.25   # share of material pairs allowed to violate
RECONCILE_EXTREME_SCALE = 3.0          # ratio part of the single-pair breakage test
# ...but a ratio alone is scale-free and misleads at low volume, so a single
# pair must ALSO be off by this many absolute units (roughly two games' worth
# of one component) to count as breakage. See decision #7's second revision.
RECONCILE_EXTREME_ABS = 60.0
# The systemic "share of pairs violating" test needs enough pairs to mean
# anything -- on a full slate there are ~80. Below this, only the absolute
# breakage test applies, so a small or unusual slate cannot abort spuriously.
RECONCILE_MIN_PAIRS_FOR_SHARE_TEST = 20
# Components whose volume is EXCLUSIVE to the players in the pool -- see
# decision #7's "exclusive resource" note. Pass attempts belong to quarterbacks;
# the pool contains the team's quarterbacks; so the pool's share is ~1.0 and no
# historical share should be consulted at all.
# 2026-09-24 backstop: no real QB projects past this many pass attempts in a game;
# reconcile_team_shares() clamps and warns rather than let a scale blow-up through
# (wk1 rebuild had Cousins/Murray/Geno Smith at 119-135).
QB_PASS_ATT_CAP = 55.0
EXCLUSIVE_COMPONENTS = {"pass"}

DEFAULT_SIMS = 4000
DEFAULT_SEED = 20103

# Component -> which stat-line columns it fills.
_COMPONENT_STATS = {
    "pass": ("pass_att", "pass_yd", "pass_td"),
    "rush": ("rush_att", "rush_yd", "rush_td"),
    "recv": ("targets", "rec_yd", "rec_td"),
}

_CACHE = {}


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------

def load_variance(path: Path | None = None) -> dict:
    """Load and memoize the fitted variance artifact. Hard error if missing --
    same reasoning as salary_anchor.py's decision #2: a silent no-op would
    make a backtest report 'the stat-line model didn't help' when the truth
    is that its variance parameters never loaded."""
    p = Path(path) if path else ARTIFACT_PATH
    key = str(p)
    if key in _CACHE:
        return _CACHE[key]
    if not p.exists():
        raise SystemExit(
            f"Stat-line variance artifact {p} does not exist.\n"
            f"Fit it first:\n"
            f"    python3 scripts/fit_statline_variance.py\n"
            f"(Not falling back to guessed dispersion -- that would silently "
            f"produce a sigma nobody fit.)")
    art = json.loads(p.read_text())
    if art.get("schema_version") != 1:
        raise SystemExit(
            f"{p.name} has schema_version={art.get('schema_version')}, expected 1. "
            f"Refit with the current fit_statline_variance.py.")
    _CACHE[key] = art
    return art


# ---------------------------------------------------------------------------
# The draw scheme (decision #1, #2)
# ---------------------------------------------------------------------------

def _num(value, default=0.0) -> float:
    """NaN-safe scalar coercion.

    Deliberately NOT `value or default`: NaN is TRUTHY in Python, so the
    idiomatic `getattr(row, col, 0.0) or 0.0` passes NaN straight through.
    That is exactly how a player with no history for a component put a NaN
    TD-rate into rng.binomial and crashed the first real run of this engine
    (`ValueError: p < 0, p > 1 or p contains NaNs`). Same silent-corruption
    class this project has been bitten by repeatedly -- guarded once, here,
    rather than at each call site.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(v):
        return float(default)
    return v


def _draw_latent(rng, latent_sd, size):
    """Shared game-quality multiplier, mean 1. Gamma keeps it non-negative
    and right-skewed, which is the real shape of a good game."""
    if latent_sd <= 1e-9:
        return np.ones(size, dtype=float)
    shape = 1.0 / (latent_sd ** 2)
    return rng.gamma(shape, 1.0 / shape, size=size)


def _draw_volume(rng, mu, r, size):
    """Negative binomial with mean mu, Var = mu + mu^2/r.

    Session 15.2c, decision #18: `mu` may now be a scalar (today's plain
    independent draw) OR an array of length `size` -- one mean per
    simulation, used when a player's mean has been shifted by a shared
    team-level shock so his draw is correlated with his teammates'.
    """
    r = max(_num(r, 1.0), 1e-3)
    mu_arr = np.asarray(mu, dtype=float)
    if mu_arr.ndim == 0:
        mu_val = _num(mu, 0.0)
        if mu_val <= 1e-9:
            return np.zeros(size, dtype=float)
        p = r / (r + mu_val)
        return rng.negative_binomial(r, p, size=size).astype(float)
    # Array-valued mu: one draw per simulation, at that simulation's own
    # (shocked) mean. Clipped at 0 -- a shock can push a small mu negative,
    # which has no meaning for a volume count.
    mu_arr = np.clip(mu_arr, 0.0, None)
    p = np.clip(r / (r + mu_arr), 1e-9, 1.0)
    out = np.zeros(size, dtype=float)
    nonzero = mu_arr > 1e-9
    if nonzero.any():
        out[nonzero] = rng.negative_binomial(r, p[nonzero]).astype(float)
    return out


def _draw_yards(rng, mean_yards, cv):
    """Gamma given the (already latent-scaled) mean. Non-negative,
    right-skewed. Zero mean -> zero yards, no draw."""
    out = np.zeros_like(mean_yards, dtype=float)
    pos = mean_yards > 1e-9
    if not pos.any():
        return out
    cv = max(float(cv), 1e-3)
    shape = 1.0 / (cv ** 2)
    out[pos] = rng.gamma(shape, mean_yards[pos] * cv ** 2)
    return out


def _draw_component(rng, n_sims, mu_vol, r, yd_rate, td_rate, cv, latent_sd):
    """One component's (volume, yards, TDs) draws. The latent is shared
    between yards and TDs, which is what reproduces their measured
    within-player correlation instead of assuming independence."""
    latent = _draw_latent(rng, latent_sd, n_sims)
    vol = _draw_volume(rng, mu_vol, r, n_sims)
    yards = _draw_yards(rng, vol * _num(yd_rate) * latent, cv)
    p_td = np.clip(np.nan_to_num(td_rate * latent, nan=0.0), 0.0, 0.95)
    tds = rng.binomial(vol.astype(int), p_td).astype(float)
    return vol, yards, tds


def _simulated_yards_td_corr(latent_sd, yards_cv, td_rate, mean_volume,
                             seed=12345, n_sims=200_000):
    """Used by fit_statline_variance.py's calibration (its decision #6) to
    solve for the latent SD that reproduces a measured correlation. Lives
    here, not in the fitter, so the calibration runs against the real draw
    scheme rather than a second copy of it."""
    rng = np.random.default_rng(seed)
    r = 8.0  # representative; the correlation is driven by the latent, not r
    _, yards, tds = _draw_component(
        rng, n_sims, float(mean_volume), r, 1.0, float(td_rate),
        float(yards_cv), float(latent_sd))
    if tds.std() < 1e-9 or yards.std() < 1e-9:
        return 0.0
    return float(np.corrcoef(yards, tds)[0, 1])


# ---------------------------------------------------------------------------
# Usage table: per-player mean volume + shrunk efficiency (decisions #3-#5)
# ---------------------------------------------------------------------------

def _recency_weighted(values: np.ndarray) -> float:
    v = np.asarray(values, dtype=float)[-len(RECENCY_WEIGHTS):][::-1]
    if v.size == 0:
        return 0.0
    w = RECENCY_WEIGHTS[:v.size]
    return float(np.dot(v, w / w.sum()))


def load_history(season: int, week: int) -> pd.DataFrame:
    """Decision #5: REG games strictly before the target week.

    Decision #19 (Session 15.3): a season whose weekly_stats_{season}.
    parquet doesn't exist AT ALL -- not "exists but has zero rows before
    this week", genuinely absent -- is treated the same real, expected
    condition ingest_historical.py's own ingest_weekly_stats() already
    treats a season with no games played yet: not a config mistake.
    That ingestion function deliberately never writes a placeholder file
    for such a season (see its own docstring), so this case is the normal
    result of asking for a brand-new season's history before its first
    game, not a sign anything is broken.

    Confirmed real, not hypothetical (Session 15.3): current_slate.json's
    season field had been left on the prior completed season rather than
    the slate's real season, which meant every real call here always found
    a populated (if stale) file and this path never actually ran. With the
    field corrected to the slate's real season, a genuine real-season week
    1 build hits exactly this case.

    Mirrors load_depth_chart()'s established "missing file -> print a
    clear note, return an empty frame, degrade gracefully" pattern rather
    than dst_model.py's separate allow_missing parameter -- every real
    caller here (build_usage(), team_defense_history(),
    team_volume_history()) always wants this same behavior for THIS
    season; there is no second, must-exist "prior season" call to this
    function the way dst_model.py has to distinguish current vs. prior, so
    a parameter to opt in/out would have nothing to switch between.

    A genuine setup mistake (e.g. a season that SHOULD have real data,
    simply never ingested) still prints the same NOTE -- visible in the
    run's own output -- so this does not silently swallow a real problem,
    it just no longer hard-stops the whole build over the one condition
    (a brand-new season, week 1) decision #14 already exists to handle.
    """
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not path.exists():
        print(
            f"NOTE: {path} not found -- treating season {season} as having "
            f"no games played yet (same condition ingest_historical.py's "
            f"ingest_weekly_stats() already expects and skips -- see its "
            f"docstring). Falling back to decision #14's week-1 cold-start "
            f"path for every position. If season {season} should already "
            f"have real data, double-check: run scripts/ingest_historical.py "
            f"--season {season} to confirm."
        )
        return pd.DataFrame()
    df = pd.read_parquet(path)
    season_type_col = "season_type" if "season_type" in df.columns else "game_type"
    df = df[(df[season_type_col] == "REG") & (df["week"] < week)].copy()
    num = df.select_dtypes(include=[np.number]).columns
    df[num] = df[num].fillna(0.0)
    return df


def _shrink(own_num, own_den, pos_rate, k):
    den = float(own_den) + float(k)
    if den <= 0:
        return float(pos_rate)
    return (float(own_num) + float(k) * float(pos_rate)) / den


def team_weeks_played(hist: pd.DataFrame) -> dict:
    """team -> sorted list of weeks that team actually played (handles byes).
    Needed by decision #9's participation rate: a past bye must not count
    as a week the player was absent."""
    return {t: sorted(g["week"].unique().tolist())
            for t, g in hist.groupby("team")}


def _participation(player_weeks, team_wks, lookback: int) -> float:
    """Decision #10. Share of the team's last `lookback` played weeks in which
    this player actually recorded a stat line."""
    if not team_wks:
        return 0.0
    recent = team_wks[-lookback:]
    if not recent:
        return 0.0
    appeared = len(set(player_weeks) & set(recent))
    return min(appeared / len(recent), 1.0)


def build_usage(season: int, week: int, variance: dict) -> pd.DataFrame:
    """Per-player, per-component EXPECTED volume and shrunk efficiency rates,
    from that player's own prior-week history this season.

    Returns one row per player_id with flat `{component}_{field}` columns.
    """
    hist = load_history(season, week)
    from fit_statline_variance import COMPONENTS  # whitelist only; no fitting

    # Decision #19 (Session 15.3): hist can now be a genuinely columnless
    # empty frame (load_history()'s missing-file case), not only a
    # populated-file-but-zero-matching-rows empty frame. team_weeks_played()
    # and the groupby below both require a real "team"/"player_id" column
    # to exist even on zero rows -- guard both rather than let either raise
    # a KeyError before decision #16's own schema-carrying empty result
    # (below) is ever reached.
    team_wks = team_weeks_played(hist) if not hist.empty else {}
    lookback = len(RECENCY_WEIGHTS)

    rows = []
    for pid, g in (hist.groupby("player_id") if not hist.empty else []):
        g = g.sort_values("week")
        pos = str(g["position"].iloc[-1])
        if pos not in COMPONENTS:
            continue
        vpos = variance["positions"].get(pos)
        if vpos is None:
            continue
        hist_team = str(g["team"].iloc[-1])
        # Decision #9: convert conditional volume into EXPECTED volume.
        part = _participation(g["week"].tolist(),
                             team_wks.get(hist_team, []), lookback)
        rec = {"player_id": pid, "position": pos, "games_played": int(len(g)),
               "hist_team": hist_team, "participation": round(part, 4)}
        for name, vol_stat, yd_stat, td_stat in COMPONENTS[pos]:
            comp = vpos["components"][name]
            # rw() averages over games the player APPEARED in, so it is a
            # conditional-on-playing volume; participation makes it
            # unconditional.
            mu_raw = _recency_weighted(g[vol_stat].to_numpy())
            mu = mu_raw * part
            den = float(g[vol_stat].sum())
            # Decision #12: keep BOTH. The role-change override recomputes
            # mu from mu_raw, and mu/participation is a divide-by-zero for
            # precisely the players that override exists for.
            rec[f"{name}_mu_raw"] = mu_raw
            rec[f"{name}_mu"] = mu
            rec[f"{name}_hist_vol"] = den
            recent_wks = team_wks.get(hist_team, [])[-lookback:]
            rec[f"{name}_recent_vol"] = float(
                g[g["week"].isin(recent_wks)][vol_stat].sum())
            rec[f"{name}_yd_rate"] = _shrink(
                g[yd_stat].sum(), den, comp["yards_per_opportunity"], SHRINK_K["yards"])
            rec[f"{name}_td_rate"] = _shrink(
                g[td_stat].sum(), den, comp["td_per_opportunity"], SHRINK_K["td"])
        # receptions per target, and QB interceptions per attempt
        if "recv" in dict((c[0], c) for c in COMPONENTS[pos]):
            rec["catch_rate"] = _shrink(
                g["receptions"].sum(), g["targets"].sum(),
                vpos["catch_rate"], SHRINK_K["catch"])
        if pos == "QB":
            rec["int_rate"] = _shrink(
                g["passing_interceptions"].sum(), g["attempts"].sum(),
                vpos["int_per_attempt"], SHRINK_K["int"])
        rows.append(rec)

    usage = pd.DataFrame(rows)
    if usage.empty:
        # Session 10.3b, decision #16 -- FOUND BY THE FIRST REAL RUN.
        #
        # This used to return a bare `pd.DataFrame()`: empty AND columnless.
        # Every caller then did `players.merge(usage, on="player_id")`, which
        # raises `KeyError: 'player_id'` because the key column does not
        # exist. That was invisible for the whole of Session 10.3a because
        # week 1 was skipped before this line was ever reached -- the moment
        # Session 10.3b made week 1 buildable, all four week-1 backtests died
        # here.
        #
        # An empty frame must still carry its SCHEMA. Returning the full
        # column set (the union over every position's components, which is
        # what a populated frame's columns are) makes the merge a clean
        # all-NaN left join, which is exactly what "no player has any
        # history" should mean.
        cols = {"player_id": str, "position": str, "hist_team": str}
        num = ["games_played", "participation", "catch_rate", "int_rate"]
        for _pos, _cs in COMPONENTS.items():
            for _n, _v, _y, _t in _cs:
                num += [f"{_n}_mu_raw", f"{_n}_mu", f"{_n}_hist_vol",
                        f"{_n}_recent_vol", f"{_n}_yd_rate", f"{_n}_td_rate"]
        usage = pd.DataFrame({c: pd.Series(dtype=t) for c, t in cols.items()})
        for c in dict.fromkeys(num):
            usage[c] = pd.Series(dtype=float)
        return usage
    return usage


def load_depth_chart() -> pd.DataFrame:
    """Session 15.2. The latest real depth-chart snapshot -- see
    ingest_historical.py's ingest_depth_charts() for how/why it's written
    to a fixed, non-season-suffixed path (data/depth_charts_current.parquet)
    rather than the season-suffixed convention every other load_*/import_*
    function here uses. Returns [player_id, team, position, depth_rank]
    for QB/RB/WR/TE only -- the only positions
    apply_confirmed_starter_override() has a use for.

    Non-fatal if the file is missing, mirroring ingest_depth_charts()'s own
    non-fatal handling of a failed pull: returns an empty, correctly-shaped
    frame rather than raising, so a missing depth-chart pull degrades the
    confirmed-starter override back to a no-op instead of aborting the
    whole projection build over one enrichment feed.
    """
    path = DATA_DIR / "depth_charts_current.parquet"
    if not path.exists():
        print(f"NOTE: {path} not found -- confirmed-starter override "
              f"unavailable this run (see ingest_historical.py's "
              f"ingest_depth_charts()).")
        return pd.DataFrame(columns=["player_id", "team", "position", "depth_rank"])
    df = pd.read_parquet(path)
    df["dt"] = pd.to_datetime(df["dt"])
    latest = df[df["dt"] == df["dt"].max()].copy()
    latest = latest[latest["pos_abb"].isin(["QB", "RB", "WR", "TE"])]
    latest = latest.rename(columns={"gsis_id": "player_id", "pos_abb": "position",
                                    "pos_rank": "depth_rank"})
    return latest[["player_id", "team", "position", "depth_rank"]].dropna(subset=["player_id"])


def promote_depth_for_out_qbs(depth_chart: pd.DataFrame,
                              injury_status: pd.DataFrame | None) -> pd.DataFrame:
    """2026-09-25 fix (WAS wk3: Daniels OUT, Mariota projected on 12.5 pass att).
    The depth chart still lists an OUT starting QB as QB1, so the QB guard in
    apply_volume_prior() kept giving him the team's pass volume and suppressed
    the real starter's price share; status_check.py then zeroed him, leaving
    the backup with the leftovers. Drop OUT QBs from the chart and re-rank the
    rest so the next QB up is QB1 for volume/reconcile purposes. QB only
    (RB/WR/TE OUT cases stay on the A4 backup-boost path). No-op without a
    status pull or chart."""
    if (depth_chart is None or depth_chart.empty or injury_status is None
            or injury_status.empty):
        return depth_chart
    out_ids = set(injury_status.loc[injury_status["status"].isin(["OUT", "DOUBTFUL"]), "player_id"].astype(str))
    is_qb = depth_chart["position"] == "QB"
    dropped = is_qb & depth_chart["player_id"].astype(str).isin(out_ids)
    if not dropped.any():
        return depth_chart
    d = depth_chart[~dropped].copy()
    qb = d["position"] == "QB"
    d["depth_rank"] = pd.to_numeric(d["depth_rank"], errors="coerce")
    d["depth_rank"] = d["depth_rank"].astype(float)
    d.loc[qb, "depth_rank"] = (d[qb].groupby("team")["depth_rank"]
                               .rank(method="first"))
    for team, nm in depth_chart.loc[dropped].groupby("team")["player_id"].apply(list).items():
        print(f"OUT QB promotion: {team} QB(s) {nm} OUT -> next QB on the chart is QB1.")
    return d


def load_injury_status(week: int) -> pd.DataFrame:
    """Ad Hoc Session A4. The latest real `status_check.py pull` output for
    this week (output/player_status_{week}_{timestamp}.csv -- see
    status_check.py's run_pull()), picked by filename timestamp since
    unlike load_depth_chart() there's no single fixed-path file to read.

    Non-fatal if none exists, same reasoning as load_depth_chart(): a
    missing/not-yet-run pull degrades the injury-driven role-change boost
    in apply_confirmed_starter_override() back to a no-op rather than
    aborting the build. Returns [player_id, team, position, status].
    """
    out_dir = REPO_ROOT / "output"
    matches = sorted(out_dir.glob(f"player_status_{week}_*.csv"))
    if not matches:
        print(f"NOTE: no output/player_status_{week}_*.csv found -- "
              f"injury-driven role-change boost unavailable this run "
              f"(see status_check.py pull).")
        return pd.DataFrame(columns=["player_id", "team", "position", "status"])
    latest = pd.read_csv(matches[-1])
    return latest[["player_id", "team", "position", "status"]]


def team_defense_history(season: int, week: int) -> pd.DataFrame:
    """Session 15.2b. Recency-weighted CARRIES ALLOWED per team -- the
    defensive mirror of team_volume_history()'s own-offense numbers,
    computed the identical way (same RECENCY_WEIGHTS, same "strictly
    before `week`" cutoff via load_history()).

    Feeds the rush with_history specification's opp_rush_allowed term
    (fit_volume_prior.py / volume_prior.py decision #6 -- see that file's
    docstring for the full probe). Only rush is fit with this term right
    now, so only carries_allowed is computed here; if pass or recv are
    ever probed and shipped with an equivalent term, this function is
    where their allowed-volume columns would be added too.

    A team's opponent in a given week is the mode of every one of its
    players' `opponent_team` values that week (exact, not inferred --
    every real player row names the same opponent). Returns one row per
    team that has played at least one game with a recorded opponent;
    empty at week 1, same as team_volume_history().
    """
    hist = load_history(season, week)
    lookback = len(RECENCY_WEIGHTS)
    if hist.empty or "opponent_team" not in hist.columns:
        return pd.DataFrame(columns=["team", "carries_allowed"])

    off = hist.groupby(["week", "team"], as_index=False)["carries"].sum()
    off = off.rename(columns={"carries": "team_rush"})
    opp = hist.dropna(subset=["opponent_team"]).groupby(
        ["week", "team"])["opponent_team"].agg(
        lambda s: s.value_counts().idxmax()).reset_index()
    tw = off.merge(opp, on=["week", "team"], how="left")
    allowed = off.rename(columns={"team": "opponent_team",
                                  "team_rush": "carries_allowed"})
    tw = tw.merge(allowed, on=["week", "opponent_team"], how="left")

    out = []
    for team, g in tw.groupby("team"):
        recent = g.sort_values("week")["carries_allowed"].dropna().to_numpy()
        recent = recent[-lookback:]
        if len(recent):
            out.append({"team": team, "carries_allowed": _recency_weighted(recent)})
    return pd.DataFrame(out)


def team_volume_history(season: int, week: int) -> pd.DataFrame:
    """Recency-weighted team-level volume, for decision #7's reconciliation.
    Empty at week 1, same as team_defense_history() just above -- decision
    #19 (Session 15.3): hist can now be empty because the season's file
    doesn't exist yet, not only because it exists with zero rows before
    this week. Same empty-columns-would-KeyError reasoning as that
    function's own guard."""
    hist = load_history(season, week)
    if hist.empty:
        return pd.DataFrame(columns=[
            "team", "team_attempts", "team_carries", "team_targets",
            "hist_attempts", "hist_carries", "hist_targets",
            "recent_attempts", "recent_carries", "recent_targets",
        ])
    lookback = len(RECENCY_WEIGHTS)
    out = []
    for (team,), g in hist.groupby(["team"]):
        per_week = g.groupby("week")[["attempts", "carries", "targets"]].sum().sort_index()
        recent_weeks = per_week.index.tolist()[-lookback:]
        rec = g[g["week"].isin(recent_weeks)]
        out.append({
            "team": team,
            "team_attempts": _recency_weighted(per_week["attempts"].to_numpy()),
            "team_carries": _recency_weighted(per_week["carries"].to_numpy()),
            "team_targets": _recency_weighted(per_week["targets"].to_numpy()),
            "hist_attempts": float(g["attempts"].sum()),
            "hist_carries": float(g["carries"].sum()),
            "hist_targets": float(g["targets"].sum()),
            # Recent-window totals: decision #7's share estimate uses these so a
            # mid-season depth-chart change is reflected instead of averaged away.
            "recent_attempts": float(rec["attempts"].sum()),
            "recent_carries": float(rec["carries"].sum()),
            "recent_targets": float(rec["targets"].sum()),
        })
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Session 10.3b -- Vegas-anchored team volume and the price prior
# (decisions #11-#15). All of it is INERT unless a caller passes an artifact.
# ---------------------------------------------------------------------------

# component -> (predicted team column, history-basis column) in the frame
# team_volume_history() returns.
_TEAM_PRED_COL = {"pass": "team_attempts", "rush": "team_carries",
                  "recv": "team_targets"}


def vegas_anchored_team_volume(team_vol: pd.DataFrame, vegas: pd.DataFrame,
                               artifact: dict, teams=None,
                               opp_rush_allowed: pd.Series = None) -> pd.DataFrame:
    """Decision #13/#14. Replace each team's predicted volume with the fitted
    function of (team history, implied total, spread).

    `team_vol` may be EMPTY -- that is week 1, and the `no_history`
    specification is used instead for every team in `teams`. `vegas` must be
    indexed by team and carry `implied_total` and `spread`.

    The pre-anchor value is preserved as `{col}_history`, because the
    role-change flag's `hist_share` denominator has to stay the history-based
    number: comparing a player's history-derived volume against a
    Vegas-derived team total would fold the team change into what is supposed
    to be a PLAYER-level divergence.

    Session 15.2b: `opp_rush_allowed`, if given, is a Series indexed by
    team naming that team's UPCOMING opponent's own recency-weighted
    carries-allowed (team_defense_history(), already resolved through the
    opponent map by the caller -- this function only ever dealt in
    per-team history before, and resolving "my opponent's number" here
    would need the opponent map as a second new argument for no benefit).
    Only passed through for the rush component; volume_prior.py's own
    `terms` check is what actually decides whether a fitted spec needs it,
    so passing this for a site/artifact that hasn't been refit with the
    new term is harmless.
    """
    import volume_prior

    week1 = team_vol is None or team_vol.empty
    if week1:
        if teams is None:
            raise SystemExit(
                "vegas_anchored_team_volume() was given no team history and "
                "no team list. Week 1 needs the pool's teams to build a "
                "no-history team volume for -- refusing to invent one.")
        out = pd.DataFrame({"team": sorted(set(teams))})
    else:
        out = team_vol.copy()

    it = out["team"].map(vegas["implied_total"]) if "implied_total" in vegas else np.nan
    sp = out["team"].map(vegas["spread"]) if "spread" in vegas else np.nan
    oda = out["team"].map(opp_rush_allowed) if opp_rush_allowed is not None else None

    for comp, col in _TEAM_PRED_COL.items():
        hist_vals = None
        if not week1 and col in out.columns:
            out[f"{col}_history"] = out[col]
            hist_vals = out[col]
        kwargs = {}
        if comp == "rush" and oda is not None:
            kwargs["opp_defense_allowed"] = oda
        out[col] = volume_prior.predict_team_volume(
            artifact, comp, it, sp, history_volume=hist_vals, **kwargs)
    return out


def fill_cold_start_rates(pool: pd.DataFrame, variance: dict) -> pd.DataFrame:
    """Decision #17. Give a zero-history player the POSITION MEAN efficiency
    rate instead of NaN.

    build_usage() only emits rows for players who have history, so after the
    left join a zero-history player has NaN for every `{comp}_yd_rate`,
    `{comp}_td_rate`, `catch_rate` and `int_rate`. Session 10.3b's design
    note claimed this was already handled -- "_shrink() returns the position
    mean when the denominator is zero" -- but that is only true for a player
    build_usage() actually PROCESSED. A player with no history never reaches
    _shrink() at all, so nothing fills the rate and the whole cold-start
    volume gets multiplied by NaN.

    The value used is the same position mean _shrink() would have returned at
    a zero denominator, read from the same variance artifact, so a cold-start
    player and a zero-denominator player land on exactly the same number
    rather than on two independently-plausible ones.

    Only fills NaN -- a player with history keeps every rate he earned.
    """
    from fit_statline_variance import COMPONENTS

    df = pool.copy()
    filled = 0
    for pos, cs in COMPONENTS.items():
        vpos = variance["positions"].get(pos)
        if vpos is None:
            continue
        mask = df["position"].astype(str) == pos
        if not mask.any():
            continue
        for name, _v, _y, _t in cs:
            comp = vpos["components"].get(name)
            if comp is None:
                continue
            for col, key in ((f"{name}_yd_rate", "yards_per_opportunity"),
                             (f"{name}_td_rate", "td_per_opportunity")):
                if col not in df.columns:
                    df[col] = np.nan
                need = mask & df[col].isna()
                filled += int(need.sum())
                df.loc[need, col] = float(comp[key])
        # Match the populated path EXACTLY: build_usage() sets catch_rate
        # only for positions that have a recv component, and int_rate only
        # for QB. Filling them more widely would be harmless (nothing reads
        # them) but would make a cold-start row differ in shape from a
        # normal one, which is the kind of small inconsistency that costs an
        # hour three sessions later.
        has_recv = any(n == "recv" for n, _v, _y, _t in cs)
        for col, key in (("catch_rate", "catch_rate"),
                         ("int_rate", "int_per_attempt")):
            if key not in vpos:
                continue
            if col == "catch_rate" and not has_recv:
                continue
            if col == "int_rate" and pos != "QB":
                continue
            if col not in df.columns:
                df[col] = np.nan
            need = mask & df[col].isna()
            filled += int(need.sum())
            df.loc[need, col] = float(vpos[key])
    if filled:
        print(f"Cold-start efficiency: filled {filled} NaN rate cell(s) with "
              f"position means (decision #17).")
    return df


def absent_player_price_factor(df: pd.DataFrame, tv: pd.DataFrame) -> pd.Series:
    """Per-row multiplier (1.0 = untouched) applied to the price-implied
    volume of RB/WR/TE players who have no stat line this season while their
    team already has played games. See ABSENT_PLAYER_FACTOR's comment for the
    evidence. No-op in real Week 1 (no team has history, `tv` empty), for
    players with any appearance, for QBs (handled by the confirmed-starter
    override), and for anyone priced at/above ABSENT_DISCOUNT_NONE_SALARY."""
    factor = pd.Series(1.0, index=df.index, dtype=float)
    if tv is None or len(tv) == 0:
        return factor
    team_has_history = df["team"].isin(tv.index)
    absent = (pd.to_numeric(df["games_played"], errors="coerce").fillna(0) == 0)         & team_has_history & df["position"].astype(str).isin(["RB", "WR", "TE"])
    sal = pd.to_numeric(df["salary"], errors="coerce").astype(float).fillna(0.0)
    span = float(ABSENT_DISCOUNT_NONE_SALARY - ABSENT_DISCOUNT_FULL_SALARY)
    ramp = ((sal - ABSENT_DISCOUNT_FULL_SALARY) / span).clip(0.0, 1.0)
    f = ABSENT_PLAYER_FACTOR + (1.0 - ABSENT_PLAYER_FACTOR) * ramp
    return factor.where(~absent, f)


def apply_volume_prior(pool: pd.DataFrame, artifact: dict,
                       team_vol: pd.DataFrame,
                       weight_floor: float = None, k: float = None,
                       role_change: bool = True,
                       absent_discount: bool = False,
                       depth_chart: pd.DataFrame = None,
                       floor_share_fix: bool = False,
                       floor_share_max_salary: float = 4200) -> pd.DataFrame:
    """Decisions #11, #12, #15.

    `floor_share_fix` (default False = unchanged): see the inline block of
    the same name below.

    `depth_chart` (2026-09-23 projection review fix): optional, same frame
    load_depth_chart() returns ([player_id, team, position, depth_rank]).
    When given, suppresses QB `pass_price_share` for any QB the real depth
    chart positively lists as NOT rank 1 -- see the inline comment at its
    use site below for the confirmed real-data bug this closes. Backward
    compatible: every existing caller that doesn't pass it (probe_reconcile_
    gap.py) gets the prior, unpatched behavior exactly.

    `absent_discount` (default False = every prior caller unchanged) turns on
    absent_player_price_factor(). Pass True ONLY when `pool`'s history is the
    CURRENT season's games before this week (real Week 2+). It must stay off
    for real Week 1, where the 2025 lookback makes a zero-history player a
    rookie / zero-snap player, for whom the price prior is exactly right. Blend a price-implied volume into `{comp}_mu`
    and apply the role-change participation override.

    `pool` needs: position, salary, participation, games_played, and the
    `{comp}_mu` / `{comp}_mu_raw` columns build_usage() produced. `team_vol`
    is the (already Vegas-anchored) team frame.

    Returns the pool with `{comp}_mu` updated and an audit trail added:
    `{comp}_price_share`, `{comp}_hist_share`, `volume_prior_weight`,
    `participation_effective`, `role_change_flag`. The audit columns are not
    decoration -- reconciliation's week-1 price basis reads
    `{comp}_price_share` directly (decision #14), and Session 10.3a's
    experience was that an unlogged volume adjustment is untraceable after
    the fact.
    """
    import volume_prior
    from fit_statline_variance import COMPONENTS

    if weight_floor is None:
        weight_floor = volume_prior.DEFAULT_WEIGHT_FLOOR
    if k is None:
        k = volume_prior.DEFAULT_COLD_START_K

    df = pool.copy()
    tv = team_vol.set_index("team") if not team_vol.empty else pd.DataFrame()

    if "participation" not in df.columns:
        df["participation"] = 0.0
    if "games_played" not in df.columns:
        df["games_played"] = 0
    df["participation"] = pd.to_numeric(df["participation"],
                                        errors="coerce").fillna(0.0)
    df["games_played"] = pd.to_numeric(df["games_played"],
                                       errors="coerce").fillna(0).astype(int)

    comps = sorted({c for cs in COMPONENTS.values() for c, _v, _y, _t in cs})
    for comp in comps:
        df[f"{comp}_price_share"] = 0.0
        df[f"{comp}_hist_share"] = np.nan
        df[f"{comp}_price_volume"] = 0.0

    # --- price-implied share, and the volume it implies -------------------
    # Pass 1: raw price-implied share per (position, component), straight
    # from the salary curve, no cross-player awareness yet.
    for pos, cs in COMPONENTS.items():
        mask = df["position"].astype(str) == pos
        if not mask.any():
            continue
        for comp, _v, _y, _t in cs:
            ps = volume_prior.share_from_salary(
                artifact, pos, comp, df.loc[mask, "salary"])
            df.loc[mask, f"{comp}_price_share"] = ps

    # 2026-09-23 projection review fix -- confirmed real bug, not a guess.
    # share_from_salary()'s QB|pass curve does NOT decay to ~0 at the salary
    # floor (lowest knot ~$4042 -> 0.224 share, flat-extrapolated below
    # that). A real DK/FD classic slate lists every rostered QB -- starter,
    # primary backup, often a 3rd/4th emergency arm -- each priced near the
    # floor, and EACH ONE independently draws that ~0.22+ share. None of
    # them individually clears SATURATED_SHARE_THRESHOLD (decision #20 below
    # only fires when 2+ teammates are BOTH >=0.90; backups never are), so
    # they fall straight through to the generic team-sum normalization,
    # which treats every backup's share as equally informative as the
    # starter's and divides the real team pass volume among all of them.
    # Confirmed on real 2026 wk1/wk2 data (e.g. CIN wk1: Joe Burrow got
    # 22.1 proj pass attempts while Flacco/Johnson/Clifford -- none of whom
    # would ever throw a pass -- collectively drew another ~14): recomputing
    # the same price-share math as if each real starter were the only QB in
    # the pool reproduces real pass-attempt totals almost exactly (mean bias
    # -0.9 attempts vs the diluted pipeline's +7.7 across 43 real QB
    # player-weeks) -- see HANDOFF_projections_model_review.md section 6 for
    # the full trace. QB is uniquely exposed: decision #20's own note below
    # already established RB/WR/TE's curves top out at 0.78/0.31/0.28,
    # nowhere near saturation even fully rostered, because those roles are
    # genuinely shared even among real starters -- QB is the one position
    # here that is genuinely winner-take-all.
    #
    # Fix: zero `pass_price_share` for any QB the real depth chart
    # POSITIVELY lists as not rank 1 at QB for his team. A player with no
    # depth-chart match at all (missing pull, or a team the snapshot didn't
    # cover) is left untouched -- same "absence of a signal is not itself a
    # signal" rule apply_confirmed_starter_override() already applies to
    # this exact data source, a few lines later in the caller. This never
    # blocks a legitimate in-week promotion: apply_confirmed_starter_
    # override(), called right after this function returns, recomputes a
    # promoted player's mu directly from his own mu_raw/participation and
    # does not read price_share at all, so a real elevated backup with
    # established history is restored regardless of what this does to his
    # price side. Only the true depth-chart-#2-or-lower case (never
    # promoted, never plays) is what this suppresses.
    df["_qb_backup_suppress"] = False
    if depth_chart is not None and not depth_chart.empty and "pass_price_share" in df.columns:
        qb_chart = depth_chart[depth_chart["position"] == "QB"]
        has_entry = df["player_id"].astype(str).isin(
            set(qb_chart["player_id"].astype(str)))
        qb1_ids = set(qb_chart.loc[qb_chart["depth_rank"] == 1, "player_id"].astype(str))
        is_qb = df["position"].astype(str) == "QB"
        suppress = is_qb & has_entry & ~df["player_id"].astype(str).isin(qb1_ids)
        # 2026-09-24 guard (projection re-check, HANDOFF_projections_model_
        # review.md section 10): a QB with NO depth-chart entry on a team
        # whose chart DOES name a QB1 is not that team's starter either --
        # left untouched he soaked up volume (wk3 MIN: unlisted Max Brosmer,
        # 0 games, got 16.3 attempts vs. depth-chart QB1 Kyler Murray's
        # 13.7). Teams the snapshot does not cover at QB are still left
        # alone ("absence of a signal is not itself a signal" for a whole
        # missing team).
        qb1_teams = set(qb_chart.loc[qb_chart["depth_rank"] == 1, "team"].astype(str))
        suppress = suppress | (is_qb & ~has_entry & df["team"].astype(str).isin(qb1_teams))
        # Depth-chart QB1 flag, consumed by reconcile_team_shares(): a moved
        # starter's volume IS his current team's volume.
        df["depth_qb1"] = is_qb & df["player_id"].astype(str).isin(qb1_ids)
        if suppress.any():
            df.loc[suppress, "pass_price_share"] = 0.0
            # Stashed, not applied to pass_mu yet -- decision #15's role-
            # change block below unconditionally recomputes every {comp}_mu
            # from {comp}_mu_raw for ALL rows (same "runs after, wins"
            # pattern apply_depth_chart_usage_prior()'s own docstring
            # already flags), so suppressing pass_mu here would just get
            # silently overwritten. Applied instead at the very end of this
            # function, after that recompute and the cold-start blend both
            # run -- see the end of this function for why pass_mu ALSO
            # needs this, not just pass_price_share.
            df["_qb_backup_suppress"] = suppress

    # 2026-09-24 floor-share fix (analysis/proj_h, re-tested on the
    # multi-season backtest in analysis/backtest_multi/REPORT_followups.md).
    # OFF by default. Zero-history (0 games in the lookback) RB/WR/TE priced
    # at or below `floor_share_max_salary` get price_share = 0 BEFORE the
    # Session 14.0b normalisation, so they add no mu to reconciliation's
    # raw_sum and the real contributors are rescaled up. A player the depth
    # chart ranks at or above FLOOR_SHARE_GUARD[pos] is never excluded.
    if floor_share_fix:
        gp = pd.to_numeric(df.get("games_played"), errors="coerce").fillna(0)
        sal = pd.to_numeric(df["salary"], errors="coerce")
        pos_s = df["position"].astype(str)
        floor = pos_s.isin(list(FLOOR_SHARE_GUARD)) & gp.eq(0) & (sal <= floor_share_max_salary)
        if depth_chart is not None and not depth_chart.empty:
            rank = df["player_id"].astype(str).map(
                depth_chart.assign(player_id=depth_chart["player_id"].astype(str))
                .groupby("player_id")["depth_rank"].min())
            floor &= ~(rank.notna() & (rank <= pos_s.map(FLOOR_SHARE_GUARD)))
        for comp in comps:
            df.loc[floor, f"{comp}_price_share"] = 0.0
        print(f"Floor-share fix: zeroed price share for {int(floor.sum())} zero-history "
              f"floor-priced RB/WR/TE.")

    # Decision #20 (Session 15.3): the Session 14.0b fix just below handles
    # a team's price_share SUM exceeding 1.0 -- but it assumes the
    # individual pre-normalization values still carry real information to
    # normalize BY. That breaks when share_from_salary()'s curve has
    # already flattened out near its ceiling for MULTIPLE teammates at
    # once: the curve was fit almost entirely on Classic salaries, where a
    # real backup is essentially never priced anywhere near the zone where
    # the curve stops differentiating players, so it was never asked to
    # tell two saturated players apart. Confirmed on a real live Showdown
    # slate: three same-team QBs priced $9,400 / $7,400 / $6,000 (a real,
    # meaningful ~57% salary gap top to bottom) ALL evaluated to
    # 0.97-0.98 pre-normalization. The Session 14.0b fix below then
    # divides three near-identical numbers by their own sum, producing a
    # dead-even ~33/33/33 split that throws the real salary gap away
    # entirely -- proportional normalization cannot recover information
    # the curve's own output no longer contains.
    #
    # Fix: within any (team, component) group where 2+ players are at or
    # above SATURATED_SHARE_THRESHOLD, replace their price_share with real
    # salary (raised to SATURATED_SALARY_POWER, which the curve can no
    # longer express but salary still can), normalized among just that
    # saturated subgroup. Only ever touches players already indistinguishable
    # to the curve -- a group with at most one saturated player is
    # completely untouched, same as before this fix.
    #
    # Self-scoping, not a QB-specific special case: RB/WR/TE's own fitted
    # curves top out at 0.775/0.308/0.276 respectively even at the top of
    # their fitted salary range (checked directly against this artifact),
    # nowhere near SATURATED_SHARE_THRESHOLD, because those roles are
    # genuinely shared even among real starters. Only a position whose
    # real-world role is genuinely winner-take-all can ever saturate
    # multiple teammates at once, which in practice is QB alone.
    for comp in comps:
        col = f"{comp}_price_share"
        saturated = df[col] >= SATURATED_SHARE_THRESHOLD
        n_saturated_on_team = df[col].where(saturated).groupby(df["team"]).transform("count")
        is_multi_saturated = saturated & (n_saturated_on_team >= 2)
        if is_multi_saturated.any():
            salary_pow = pd.to_numeric(df["salary"], errors="coerce").astype(float) \
                .fillna(0.0).clip(lower=0.0) ** SATURATED_SALARY_POWER
            group_total = salary_pow.where(is_multi_saturated) \
                .groupby(df["team"]).transform("sum")
            df[col] = np.where(
                is_multi_saturated & (group_total > 0),
                salary_pow / group_total,
                df[col],
            )

    # Session 14.0b FIX: share_from_salary() answers "what's THIS player's
    # expected share of team volume" independently per player -- nothing
    # constrains the SUM across a team's roster to stay at or below 1.0.
    # Harmless when only one or two players sit near the salary floor;
    # broken when several zero-history players share an identical floor
    # salary, because the curve is degenerate at the boundary and hands
    # every one of them the SAME share, stacking on top of the real
    # contributors instead of splitting one finite pool. Found on a real DK
    # Week 1 2026 slate: four zero-history RBs at GB's $4000 floor
    # collectively claimed ~85% of the team's rush volume on top of the
    # real starter and backup -- which is what actually tripped Session
    # 10's reconciliation fail-loud. Session 14.0's engine cutover didn't
    # cause this; it's a pre-existing Phase 10 gap that a real slate with
    # this many legitimately-included zero-history floor-priced players
    # (Session 13.5b's rookie-matching fix) had never exercised before.
    #
    # Fix: normalize {comp}_price_share within (team, component), summed
    # ACROSS every position that contributes to that component -- rush
    # isn't RB-exclusive (a QB scramble or WR jet sweep both count), so the
    # normalization has to match how reconciliation itself already treats
    # a component, not split further by position. Only rescales when the
    # raw sum exceeds 1.0; a sum UNDER 1.0 is left untouched, since that's
    # the legitimate case where the pool doesn't fully cover team volume,
    # which the existing _pool_share()/reconciliation machinery already
    # handles correctly and is not this bug.
    #
    # Runs AFTER decision #20 above, on purpose: with an entirely-saturated
    # team/component group, decision #20 already normalizes that group to
    # sum to exactly 1.0, so this step is a no-op for it (scale=1.0). It
    # still does real work if some OTHER, non-saturated player on the same
    # team/component also carries a small price_share -- their share adds
    # on top, and this rescales the whole group back down to 1.0, exactly
    # as it already did before decision #20 existed.
    for comp in comps:
        col = f"{comp}_price_share"
        team_sum = df.groupby("team")[col].transform("sum")
        with np.errstate(divide="ignore", invalid="ignore"):
            scale = np.where(team_sum > 1.0, 1.0 / team_sum, 1.0)
        df[col] = df[col] * scale

    # Pass 2: price_volume from the NORMALIZED share, plus hist_share
    # (unrelated to price_share itself -- kept in this pass, same
    # structural position as the original single-pass loop had it).
    for pos, cs in COMPONENTS.items():
        mask = df["position"].astype(str) == pos
        if not mask.any():
            continue
        for comp, _v, _y, _t in cs:
            col = _TEAM_PRED_COL[comp]
            team_pred = df.loc[mask, "team"].map(
                tv[col] if (len(tv) and col in tv.columns) else {})
            team_pred = pd.to_numeric(team_pred, errors="coerce").fillna(0.0)
            df.loc[mask, f"{comp}_price_volume"] = (
                df.loc[mask, f"{comp}_price_share"] * team_pred.to_numpy(float))

            # hist_share against the HISTORY team volume, never the anchored
            # one -- see vegas_anchored_team_volume()'s docstring.
            hcol = f"{col}_history"
            src = hcol if (len(tv) and hcol in tv.columns) else None
            if src is not None and f"{comp}_mu" in df.columns:
                denom = pd.to_numeric(
                    df.loc[mask, "team"].map(tv[src]), errors="coerce")
                mu = pd.to_numeric(df.loc[mask, f"{comp}_mu"],
                                   errors="coerce").fillna(0.0)
                with np.errstate(divide="ignore", invalid="ignore"):
                    hs = np.where(denom.to_numpy(float) > 1e-9,
                                  mu.to_numpy(float) / denom.to_numpy(float),
                                  np.nan)
                df.loc[mask, f"{comp}_hist_share"] = hs

    # --- decision #15: role change raises participation -------------------
    df["participation_effective"] = df["participation"]
    df["role_change_flag"] = False
    if role_change:
        prim = df["position"].astype(str).map(volume_prior.PRIMARY_COMPONENT)
        hs = pd.Series(np.nan, index=df.index, dtype=float)
        ps = pd.Series(0.0, index=df.index, dtype=float)
        for comp in comps:
            m = prim == comp
            if m.any():
                hs.loc[m] = df.loc[m, f"{comp}_hist_share"]
                ps.loc[m] = df.loc[m, f"{comp}_price_share"]
        part_eff, flag = volume_prior.role_change_participation(
            artifact, df["participation"], hs, ps)
        df["participation_effective"] = part_eff
        df["role_change_flag"] = flag
        # Decision #12: recompute from _mu_raw, never by dividing _mu.
        for comp in comps:
            raw, mu = f"{comp}_mu_raw", f"{comp}_mu"
            if raw in df.columns and mu in df.columns:
                df[mu] = pd.to_numeric(df[raw], errors="coerce").fillna(0.0)                          * df["participation_effective"]

    # --- decision #11: the cold-start blend -------------------------------
    w = volume_prior.cold_start_weight(df["games_played"], weight_floor, k)
    df["volume_prior_weight"] = w
    absent_factor = (absent_player_price_factor(df, tv) if absent_discount
                     else pd.Series(1.0, index=df.index)).to_numpy(float)
    df["absent_player_factor"] = absent_factor
    for comp in comps:
        mu = f"{comp}_mu"
        if mu not in df.columns:
            continue
        # NOTE the price side is NOT multiplied by participation. That is
        # decision #14's "bypass", and it is structural rather than a special
        # case: participation corrects a CONDITIONAL history average, while a
        # price-predicted share is already unconditional. Multiplying would
        # send every week-1 player to zero (participation is 0.0 when the
        # team has no played weeks) while looking like the prior had run.
        undiscounted = volume_prior.blend_volume(
            df[mu], df[f"{comp}_price_volume"], w)
        discounted = volume_prior.blend_volume(
            df[mu], df[f"{comp}_price_volume"] * absent_factor, w)
        # The volume taken off absent players is REALLOCATED to their
        # teammates who do have a role (factor == 1.0), pro rata, not
        # dropped: team volume is fixed, so someone must absorb it. Doing it
        # here (rather than leaving it to reconcile_team_shares) keeps every
        # team's pool sum unchanged, so the fail-loud reconciliation test
        # keeps measuring model breakage instead of this intended shift.
        freed = pd.Series(np.asarray(undiscounted, float) - np.asarray(discounted, float),
                          index=df.index).groupby(df["team"]).transform("sum")
        receivers = pd.Series(absent_factor >= 1.0 - 1e-12, index=df.index)             & (pd.Series(np.asarray(discounted, float), index=df.index) > 0)
        recv_total = pd.Series(np.asarray(discounted, float), index=df.index)             .where(receivers, 0.0).groupby(df["team"]).transform("sum")
        boost = np.where(receivers & (recv_total > 1e-9),
                         1.0 + freed / recv_total.where(recv_total > 1e-9, np.nan), 1.0)
        df[mu] = np.asarray(discounted, float) * np.nan_to_num(boost, nan=1.0)

    # 2026-09-23 projection review fix, part 2 -- confirmed real bug, not a
    # guess. Zeroing `pass_price_share` above (this function's first fix)
    # only touches the COLD-START blend, which is a no-op whenever a QB's
    # own `games_played` >= COLD_START_MAX_GAMES (4.0) -- true for nearly
    # every established starter once real season history exists (confirmed
    # via a real rebuild: Joe Burrow's week-1 `games_played`=8 gives
    # `cold_start_weight()`=0.0 exactly, so the earlier fix alone changed
    # his projection by <1 attempt). The bias for THOSE players traces to a
    # separate mechanism: `reconcile_team_shares()` computes each team's
    # "pass" pool `raw_sum` (EXCLUSIVE_COMPONENTS -- pool_share is always
    # 1.0) by summing `pass_mu` for every player CURRENTLY on that team,
    # with no check that a backup QB's own `pass_mu_raw` (his OWN
    # recency-weighted history, from build_usage()) actually came from
    # THIS team. Confirmed on the real CIN wk1 2026 slate: Josh Johnson
    # (CIN's real QB3, priced at the $4000 floor) has `hist_team`=WAS --
    # he genuinely started/relieved for Washington, not Cincinnati, in the
    # lookback window -- yet his own real WAS-derived mu (~11.4 attempts)
    # still summed into CIN's reconciliation pool. That inflated CIN's
    # `raw_sum` to 58.6 against a real target of 36.6, so reconciliation's
    # `scale` (target/raw_sum = 0.624) cut EVERY Bengal QB's mu by 38% --
    # including Joe Burrow's own mu_raw of 35.36, which was already an
    # accurate, undiluted estimate of his real volume before this scaling
    # ever touched it (his real week-1 2026 attempts: 35).
    #
    # Fix: zero `pass_mu` (not just `pass_price_share`) for the same
    # depth-chart-confirmed non-QB1 backups this function already
    # suppresses, applied here (the last point in this function that
    # touches mu, after the role-change recompute above and the cold-start
    # blend both run, so nothing downstream inside THIS function can
    # silently undo it the way happened when the fix was first tried
    # earlier in the function body). This does not need a separate
    # reallocation step: reconcile_team_shares() runs right after this
    # function returns and will naturally scale the real starter's now-
    # uncontaminated mu UP to the team's real target, which is exactly
    # what should happen. Backup's own final projection loses whatever
    # phantom cross-team volume he was carrying -- an acceptable, and
    # usually correct, cost for a $4000-floor QB3 who was never taking
    # real snaps for his new team.
    if df["_qb_backup_suppress"].any() and "pass_mu" in df.columns:
        df.loc[df["_qb_backup_suppress"], "pass_mu"] = 0.0
    df = df.drop(columns=["_qb_backup_suppress"])
    return df


# ---------------------------------------------------------------------------
# Depth-chart usage-share prior (Session (this change))
# ---------------------------------------------------------------------------

def apply_depth_chart_usage_prior(pool: pd.DataFrame, team_vol: pd.DataFrame,
                                  depth_chart: pd.DataFrame) -> pd.DataFrame:
    """Real-world review of the Week 1 2026 slate: Bucky Irving (TB, the
    confirmed #1 RB by depth chart) was outprojected on DK by Kenny Gainwell
    (TB, confirmed #2) despite Irving getting nearly double Gainwell's real
    projected touches (12.9 rush + 1.8 targets vs 5.1 rush + 4.5 targets).
    Investigated live: the math behind each number was internally correct
    (DK's per-reception scoring genuinely values Gainwell's target volume
    highly) -- the actual problem is upstream, in build_usage()'s per-
    component volume, which is purely each player's OWN recency-weighted
    history. Gainwell's own history includes a bigger receiving role earned
    in a different context; Irving (10 games played, presumably a smaller
    complementary role before this season) has no history of his own yet
    that reflects being the real lead back. Neither number is wrong given
    ONLY the player's own box scores -- both are blind to what a same-rank
    peer's REAL role actually looks like right now.

    Unlike apply_confirmed_starter_override() below (which only fires at
    raw participation ~0, and only ever RAISES participation), this checks
    EVERY component a position has (not just the one PRIMARY_COMPONENT) and
    corrects in BOTH directions -- an over-credited backup's share is pulled
    down, not just an under-credited starter's pulled up. Per an explicit
    user requirement: no hardcoded per-position drop-off percentage, no
    manual "is this team a committee" flag. The peer baseline is instead
    computed FRESH from this run's own real player pool: for every
    (position, component, depth_rank) group, the median real share-of-team-
    volume other players at that same rank are showing THIS week, from
    real carries/targets data already in `pool` -- so a genuine committee
    shows up as a naturally small gap between rank 1 and rank 2's medians,
    and a real workhorse hierarchy shows up as a naturally large one,
    without this function ever encoding which is which.

    Each player's own share is blended toward that peer median with
    volume_prior.cold_start_weight()'s existing fade-by-games-played shape
    (reused rather than inventing new blend math) -- heavy weight on the
    peer baseline when his own sample is thin or cross-context, fading as
    his own current-role history accumulates. Only ever adjusts `{comp}_mu`
    (never `{comp}_mu_raw`, which apply_confirmed_starter_override() below
    still needs untouched as the pure own-history number for its own
    hist_share_raw math) and never touches participation itself.

    Runs LAST in the pipeline -- AFTER apply_volume_prior() AND
    apply_confirmed_starter_override(), immediately before reconciliation
    -- see build_projections_statline.py. Originally placed before apply_
    volume_prior(); moved after a real bug was found live: that function's
    own decision #15 role-change block unconditionally recomputes every
    {comp}_mu from {comp}_mu_raw for ALL rows, which silently discarded
    this prior's correction before it ever reached final_projection. This
    position is the only one nothing downstream can overwrite.

    Session (this change) -- the blend weight is no longer a single flat
    floor. Real backtesting against actual Week 1 2026 contest results
    showed a flat floor moved Gainwell's inflated share in the right
    direction but too weakly, while naively raising the floor for ANY big
    divergence from the peer median also would have wrongly suppressed
    Jahmyr Gibbs (a real, legitimately elite ~50%-owned workhorse whose
    own share is high because he earned it, not because of stale history).
    The fix distinguishes the two with a real, per-team signal instead of
    raw distance-from-league-median: a genuine WITHIN-TEAM inversion,
    where a worse-(depth-)ranked teammate's own share exceeds a better-
    ranked one's for the same component (Gainwell's TB #2 outshares
    Irving's TB #1 on receiving; nobody on Gibbs' real DET roster
    outshares him on anything). Only a real inversion like that boosts the
    blend weight (up to DEPTH_RANK_MAX_WEIGHT_FLOOR); an elite player with
    no such teammate keeps the original, much gentler floor. See
    volume_prior.DEPTH_RANK_INVERSION_SATURATION's comment for the full
    reasoning and the real numbers this was validated against.

    No-op (returns `pool` unchanged) if depth_chart is missing/empty, same
    "absence of a signal is not itself a signal" handling used throughout
    this file. Adds audit columns `{comp}_rank_baseline_share` and
    `{comp}_usage_prior_ratio` (NaN/1.0 respectively where not eligible) so
    every adjustment this makes is traceable after the fact.
    """
    import volume_prior
    from fit_statline_variance import COMPONENTS

    df = pool.copy()
    if depth_chart is None or depth_chart.empty or "team" not in df.columns:
        return df
    if team_vol is None or len(team_vol) == 0:
        return df

    df = df.merge(depth_chart[["player_id", "depth_rank"]], on="player_id", how="left")
    tv = team_vol.set_index("team")

    games_played = pd.to_numeric(df.get("games_played"), errors="coerce").fillna(0.0)
    # Session (this change) -- the games-played TAPER (how much a thin own-
    # sample defers to any external signal) is still shared and computed
    # once here; the FLOOR it decays toward is no longer one flat constant
    # -- see the inversion-boosted `effective_floor` computed per (pos,
    # comp) below, which replaces cold_start_weight()'s single-scalar
    # floor with a per-row one for the same formula.
    taper = np.clip(
        (volume_prior.COLD_START_MAX_GAMES - games_played) / volume_prior.COLD_START_MAX_GAMES,
        0.0, 1.0)
    base_component = (
        volume_prior.DEPTH_RANK_COLD_START_K
        / (volume_prior.DEPTH_RANK_COLD_START_K + games_played)
    ) * taper

    lo, hi = volume_prior.USAGE_PRIOR_RATIO_BOUNDS

    def _rank_prefix_suffix_bounds(team_s, depth_rank_s, share_s):
        """For each row (within one (pos, comp) pass), returns
        (better_rank_min_share, worse_rank_max_share): the min own_share
        among teammates with a STRICTLY better (numerically lower) depth
        rank, and the max own_share among teammates with a STRICTLY worse
        (higher) depth rank -- NaN where no such teammate has a usable
        share. This is the real, per-team signal that distinguishes a
        genuine inversion (Gainwell out-sharing Irving on receiving,
        despite being TB's #2) from a legitimately elite outlier (Gibbs,
        whom no real DET teammate out-shares on anything) -- see
        volume_prior.DEPTH_RANK_INVERSION_SATURATION's comment for the
        full real-data reasoning."""
        better_min = pd.Series(np.nan, index=team_s.index)
        worse_max = pd.Series(np.nan, index=team_s.index)
        tmp = pd.DataFrame({"team": team_s, "depth_rank": depth_rank_s, "share": share_s})
        for _, g in tmp.dropna(subset=["depth_rank"]).groupby("team"):
            g = g.sort_values("depth_rank")
            shares = g["share"].to_numpy(float)
            n = len(shares)
            bmin = np.full(n, np.nan)
            running, seen = np.inf, False
            for i in range(n):
                bmin[i] = running if seen else np.nan
                if np.isfinite(shares[i]):
                    running, seen = min(running, shares[i]), True
            wmax = np.full(n, np.nan)
            running, seen = -np.inf, False
            for i in range(n - 1, -1, -1):
                wmax[i] = running if seen else np.nan
                if np.isfinite(shares[i]):
                    running, seen = max(running, shares[i]), True
            better_min.loc[g.index] = bmin
            worse_max.loc[g.index] = wmax
        return better_min, worse_max

    for pos, cs in COMPONENTS.items():
        pos_mask = df["position"].astype(str) == pos
        if not pos_mask.any():
            continue
        for comp, _v, _y, _t in cs:
            col = _TEAM_PRED_COL.get(comp)
            raw_col, mu_col = f"{comp}_mu_raw", f"{comp}_mu"
            hcol = f"{col}_history" if col else None
            if not hcol or hcol not in tv.columns or raw_col not in df.columns:
                continue

            # `comp` names (rush/recv) are shared across positions (RB and
            # WR both have a "recv" entry in COMPONENTS, for instance), so
            # these audit columns must be created ONCE and then only ever
            # written for THIS position's rows below -- an earlier bug had
            # this line unconditionally reset the whole column on every
            # position's pass, silently wiping out a prior position's
            # audit trail (though never the actual mu_col fix itself, since
            # that assignment is already correctly scoped to `eligible`,
            # which is position-specific).
            baseline_col, ratio_col = f"{comp}_rank_baseline_share", f"{comp}_usage_prior_ratio"
            if baseline_col not in df.columns:
                df[baseline_col] = np.nan
            if ratio_col not in df.columns:
                df[ratio_col] = 1.0

            m = pos_mask & df["depth_rank"].notna()
            if not m.any():
                continue

            denom = pd.to_numeric(df.loc[m, "team"].map(tv[hcol]), errors="coerce")
            raw = pd.to_numeric(df.loc[m, raw_col], errors="coerce")
            own_share = pd.Series(np.nan, index=df.index)
            own_share.loc[m] = np.where(
                denom.to_numpy(float) > 1e-9,
                raw.to_numpy(float) / denom.to_numpy(float), np.nan)

            # Real, this-run-only peer baseline -- never a stored/fitted
            # assumption. Restricted to rows with a real sample of their own
            # (MIN_GAMES_FOR_BASELINE) and a nonzero share, so players who
            # never touch the ball don't drag a rank's baseline toward zero.
            reliable = (
                m & (games_played >= volume_prior.MIN_GAMES_FOR_BASELINE)
                & (own_share > volume_prior.ROLE_CHANGE_MIN_HIST_SHARE)
            )
            baseline_input = pd.DataFrame({
                "depth_rank": df.loc[reliable, "depth_rank"],
                "own_share": own_share.loc[reliable],
            })
            group_counts = baseline_input.groupby("depth_rank").size()
            group_medians = baseline_input.groupby("depth_rank")["own_share"].median()
            valid_ranks = group_counts[group_counts >= volume_prior.MIN_BASELINE_SAMPLE].index
            rank_baseline = pd.Series(np.nan, index=df.index)
            rank_baseline.loc[m] = df.loc[m, "depth_rank"].map(
                group_medians.reindex(valid_ranks))

            eligible = (
                m & own_share.notna()
                & (own_share > volume_prior.ROLE_CHANGE_MIN_HIST_SHARE)
                & rank_baseline.notna()
            )
            df.loc[m, baseline_col] = rank_baseline.loc[m]
            if not eligible.any():
                continue

            # Real within-team inversion check (this (pos, comp) pass only)
            # -- see _rank_prefix_suffix_bounds() and volume_prior.DEPTH_
            # RANK_INVERSION_SATURATION's docstring for the full "why".
            better_min, worse_max = _rank_prefix_suffix_bounds(
                df.loc[m, "team"], df.loc[m, "depth_rank"], own_share.loc[m])
            divergence_down = (own_share.loc[m] - better_min).clip(lower=0.0)
            divergence_up = (worse_max - own_share.loc[m]).clip(lower=0.0)
            min_gap = volume_prior.DEPTH_RANK_MIN_INVERSION_GAP
            divergence_down = divergence_down.where(divergence_down > min_gap, 0.0)
            divergence_up = divergence_up.where(divergence_up > min_gap, 0.0)
            saturation = volume_prior.DEPTH_RANK_INVERSION_SATURATION
            inversion_boost = pd.concat([
                (divergence_down / saturation).clip(upper=1.0),
                (divergence_up / saturation).clip(upper=1.0),
            ], axis=1).max(axis=1).fillna(0.0)

            effective_floor = (
                volume_prior.DEPTH_RANK_WEIGHT_FLOOR
                + (volume_prior.DEPTH_RANK_MAX_WEIGHT_FLOOR - volume_prior.DEPTH_RANK_WEIGHT_FLOOR)
                * inversion_boost
            )
            w_full = pd.Series(np.nan, index=df.index)
            w_full.loc[m] = (
                effective_floor + (1.0 - effective_floor) * base_component.loc[m]
            ).clip(lower=0.0, upper=1.0)

            w = w_full.loc[eligible]
            target_share = (1 - w) * own_share.loc[eligible] + w * rank_baseline.loc[eligible]
            ratio = (target_share / own_share.loc[eligible]).clip(lower=lo, upper=hi)

            df.loc[eligible, ratio_col] = ratio
            df.loc[eligible, mu_col] = (
                pd.to_numeric(df.loc[eligible, mu_col], errors="coerce").fillna(0.0) * ratio
            )

    return df.drop(columns=["depth_rank"], errors="ignore")


def load_manual_role_overrides(season: int, week: int) -> pd.DataFrame:
    """Session (this change) -- the week-by-week escape hatch for real
    breaking news (a coach announcing a role change mid-week) that no data
    feed can reflect yet. Deliberately NOT automated: this is a manually
    created/edited file, same additive-and-optional convention as
    ownership_heuristic.py's load_name_recognition_flags() -- missing file
    or missing player is a no-op, never an error, and nothing here infers
    an override on its own.

    Expected file: data/manual_role_overrides_{season}_{week}.csv with
    columns [player_id, component, override_share, notes]. `component` is
    one of "pass"/"rush"/"recv" (matches COMPONENTS' own naming) and
    `override_share` is a share-of-team-volume number in the same units as
    apply_depth_chart_usage_prior()'s own own_share/rank_baseline_share
    (e.g. 0.55 = 55% of the team's real volume for that component).
    """
    path = DATA_DIR / f"manual_role_overrides_{season}_{week}.csv"
    cols = ["player_id", "component", "override_share", "notes"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path, dtype={"player_id": str})
    missing = {"player_id", "component", "override_share"} - set(df.columns)
    if missing:
        raise SystemExit(f"{path} is missing expected columns: {sorted(missing)}.")
    return df


def apply_manual_role_overrides(pool: pd.DataFrame, team_vol: pd.DataFrame,
                                overrides: pd.DataFrame) -> pd.DataFrame:
    """Applies `load_manual_role_overrides()`'s rows LAST, after
    apply_depth_chart_usage_prior() -- a manual override should always win
    over the automatic real-data correction, since it exists specifically
    for a case the data can't reflect yet. No-op if `overrides` is empty.
    """
    df = pool.copy()
    if overrides is None or overrides.empty or "team" not in df.columns:
        return df

    tv = team_vol.set_index("team") if len(team_vol) else pd.DataFrame()
    participation = pd.to_numeric(df.get("participation"), errors="coerce").fillna(0.0)

    for _, row in overrides.iterrows():
        pid, comp, share = row["player_id"], str(row["component"]), float(row["override_share"])
        col = _TEAM_PRED_COL.get(comp)
        mu_col = f"{comp}_mu"
        hcol = f"{col}_history" if col else None
        if not hcol or hcol not in tv.columns or mu_col not in df.columns:
            print(f"WARNING: manual role override for player_id={pid}, "
                  f"component={comp} could not be applied (missing team "
                  f"history column or {mu_col}) -- skipped.", file=sys.stderr)
            continue
        match = df["player_id"] == pid
        if not match.any():
            print(f"WARNING: manual role override for player_id={pid} does "
                  f"not match any player in this pool -- skipped.", file=sys.stderr)
            continue
        team_hist = pd.to_numeric(df.loc[match, "team"].map(tv[hcol]), errors="coerce")
        df.loc[match, mu_col] = (share * team_hist * participation.loc[match]).to_numpy()

    return df


# ---------------------------------------------------------------------------
# Confirmed-starter override (Session 15.2)
# ---------------------------------------------------------------------------

def apply_confirmed_starter_override(pool: pd.DataFrame, team_vol: pd.DataFrame,
                                     depth_chart: pd.DataFrame,
                                     injury_status: pd.DataFrame | None = None) -> pd.DataFrame:
    """Session 15.2, decision #1 -- fixes a real production bug the Session
    15 preseason dry run's hunt for more Jones/Leonard-shaped situations
    turned up: a returning-from-injury (or newly-traded) starter with
    EXACTLY 0.0 raw participation -- appeared in none of his team's last 5
    played games -- gets a literal 0.0 final_projection, not merely a low
    one. Confirmed on the real Week 1 2026 DK/FD slates: Sam LaPorta,
    Tucker Kraft, Garrett Wilson, Rome Odunze and Kyler Murray all came out
    at 0.0 despite being real, rostered, real-money-priced players.

    Root cause: apply_volume_prior()'s role-change override above (decisions
    #2-#5) can only RAISE participation by comparing a player's own
    history-derived share (hist_share) against his price-implied share
    (price_share) -- and at raw participation EXACTLY 0.0 that comparison
    is broken twice over. First, hist_share is itself built from mu, which
    is mu_raw multiplied by that same zero, so hist_share is always 0.0
    too -- the override's own "no divide by near-zero" guard
    (ROLE_CHANGE_MIN_HIST_SHARE) blocks it from running at all. Second,
    even patching that guard doesn't help: probed against real 2025
    history and the real Week 1 2026 DK/FD salary files (Session 15.2), a
    real injury-returning starter's price consistently runs at 40-70% of
    his OWN established share, not above it -- DK/FD price in a caution
    discount for re-injury risk, they don't predict a bigger role than his
    history shows. The override's very shape -- raise participation only
    when price implies MORE role than history -- points the wrong
    direction for this specific group. No amount of guard-patching fixes a
    formula built to detect the opposite pattern.

    What this does instead: for a player at raw participation ~0, check a
    REAL signal rather than inferring one from price -- today's actual
    team depth chart (`depth_chart`, see load_depth_chart()). If he's the
    confirmed #1 at his position AND his own established share from games
    he actually played (`{comp}_mu_raw`, never touched by the participation
    multiplier, so it survives a total recent absence) clears the same
    ROLE_CHANGE_MIN_HIST_SHARE bar the existing override already uses --
    give him full credit for that established role
    (participation_effective = 1.0) and recompute every one of his
    components' mu from mu_raw accordingly (same recompute-from-raw
    pattern as decision #12 above). A player who ISN'T the confirmed #1 --
    a real committee/lost-job case -- is left completely untouched.
    Session 15.2 confirmed this correctly distinguishes Alvin Kamara and
    Michael Penix Jr. (both genuinely #2 on today's real depth chart --
    Travis Etienne Jr. and Tua Tagovailoa are the actual #1s) from LaPorta/
    Kraft/Wilson/Odunze/Murray (all confirmed #1s). A player with no
    depth-chart match at all is likewise left untouched, not zeroed --
    same "absence of a signal is not itself a signal" handling
    build_projections_statline.py's AUDIT_COLUMNS comment already
    documents for participation_effective elsewhere in this pipeline.

    Originally scoped to raw participation ~0 ONLY, not partial cases
    (Daniel Jones/Jayden Daniels, at partial credit via the existing
    role-change override above). Session 15.2 probed widening this to all
    partial-participation players and rejected it: it does fix Jones/
    Daniels, but also moves 30+ ordinary healthy players (Josh Allen,
    Justin Herbert, Saquon Barkley, among others) who simply missed one
    game somewhere in their own last-5 window for a normal, non-injury
    reason.

    Session (this change) revisits that rejection: the blanket widening was
    right to reject (it can't tell Jones/Daniels apart from Herbert), but
    leaving ALL partial-participation players untouched was itself a real
    bug, confirmed live on the Week 1 2026 slate -- Herbert and ~27 similar
    confirmed #1 starters with a completely clean CURRENT injury report were
    getting materially suppressed participation_effective (e.g. Herbert at
    0.8) purely from a meaningless prior-season finale rest game, which then
    dragged their ownership_heuristic.py chalk score/estimated ownership
    down relative to players with a near-identical raw projection. The gap
    between the two rejected/adopted designs is `injury_status`: a second,
    narrower eligibility block below now promotes a confirmed #1 starter's
    partial participation to 1.0 ONLY when today's real injury report has
    NO flag on him at all (absent, or explicitly ACTIVE) -- Jones/Daniels
    stay excluded because they (or an equivalent genuinely-hurt/benched
    player) carry a real QUESTIONABLE/DOUBTFUL/OUT flag, or fail
    `established_role`, so they are unaffected by this second block and
    keep whatever partial credit the role-change override above already
    gives them.

    Validated against real reconciliation (Session 15.2): running the real
    reconcile_team_shares() before and after this override on the real
    Week 1 2026 DK/FD pools raised zero fail-loud violations on either
    side. The affected teams needing a bigger rescale afterward is the
    documented, intended reconciliation behavior for a returning player
    (see reconcile_team_shares()'s own docstring, which cites SEA's real
    2021 week 10 1.59x rescale for an actual four-week-absence return as
    the template for "real football, not breakage").

    Called AFTER apply_volume_prior() and BEFORE reconcile_team_shares(),
    same position in the pipeline the role-change override already
    occupies -- so a fixed player's restored volume flows through
    reconciliation exactly like everyone else's, rather than bypassing it.

    Returns `pool` with `participation_effective`, every `{comp}_mu`, and
    two new audit columns updated: `confirmed_starter_flag` (bool, mirrors
    `role_change_flag`'s existing pattern) and `hist_share_raw` (the
    share-from-games-actually-played number this override is built on --
    logged for the same reason every other volume adjustment in this file
    is logged: an unlogged adjustment is untraceable after the fact).

    Ad Hoc Session A4, decision #1 -- extends the same "check a real
    signal, not price" pattern to the in-week case this was originally
    built for but didn't yet cover: a starter ruled OUT mid-week, AFTER
    salaries already locked, whose backup's price never moves because
    nothing in the pricing feed re-runs post-lock. `injury_status`
    (optional, see load_injury_status() -- a real `status_check.py pull`
    for the week) is joined against the depth chart's #1 at each
    team/position; if that #1 is OUT, his #2 is boosted the identical way
    a confirmed #1 returning from absence is boosted above (participation_
    effective -> 1.0, every {comp}_mu recomputed from mu_raw) gated on the
    SAME established-role bar (his own hist_share_raw clearing
    ROLE_CHANGE_MIN_HIST_SHARE from games he's actually played). A backup
    with no games of his own to judge by is deliberately left untouched --
    this mechanism checks a real signal, it doesn't guess one for a
    total unknown. Flagged via a separate `role_change_injury_flag`
    column so this path stays traceable apart from the returning-starter
    path above. `injury_status=None` (the default) makes this whole block
    a no-op, matching the missing-depth-chart no-op above -- so existing
    callers that don't pass it are unaffected.
    """
    import volume_prior
    from fit_statline_variance import COMPONENTS

    df = pool.copy()
    df["confirmed_starter_flag"] = False
    df["role_change_injury_flag"] = False
    df["hist_share_raw"] = np.nan

    if depth_chart is None or depth_chart.empty or "team" not in df.columns:
        return df

    df = df.merge(depth_chart[["player_id", "depth_rank"]], on="player_id", how="left")

    prim = df["position"].astype(str).map(volume_prior.PRIMARY_COMPONENT)
    tv = team_vol.set_index("team") if len(team_vol) else pd.DataFrame()
    hist_share_raw = pd.Series(np.nan, index=df.index, dtype=float)
    for comp, col in _TEAM_PRED_COL.items():
        m = prim == comp
        hcol = f"{col}_history"
        if not m.any() or hcol not in tv.columns:
            continue
        denom = pd.to_numeric(df.loc[m, "team"].map(tv[hcol]), errors="coerce")
        raw = pd.to_numeric(df.loc[m, f"{comp}_mu_raw"], errors="coerce")
        hist_share_raw.loc[m] = np.where(denom.to_numpy(float) > 1e-9,
                                         raw.to_numpy(float) / denom.to_numpy(float),
                                         np.nan)
    df["hist_share_raw"] = hist_share_raw

    zero_participation = pd.to_numeric(df["participation"], errors="coerce").fillna(0.0) <= 1e-9
    confirmed_starter = df["depth_rank"] == 1
    established_role = df["hist_share_raw"] > volume_prior.ROLE_CHANGE_MIN_HIST_SHARE
    eligible = zero_participation & confirmed_starter & established_role

    df.loc[eligible, "confirmed_starter_flag"] = True
    df.loc[eligible, "participation_effective"] = 1.0

    # Ad Hoc Session A4, decision #1 -- the in-week OUT-after-lock case.
    injury_eligible = pd.Series(False, index=df.index)
    if injury_status is not None and not injury_status.empty:
        out_ids = set(
            injury_status.loc[injury_status["status"] == "OUT", "player_id"])
        starters_out = (depth_chart["depth_rank"] == 1) & (
            depth_chart["player_id"].isin(out_ids))
        out_team_pos = set(
            zip(depth_chart.loc[starters_out, "team"],
                depth_chart.loc[starters_out, "position"]))
        backup = df["depth_rank"] == 2
        backup_of_out_starter = pd.Series(
            list(zip(df["team"], df["position"])), index=df.index
        ).isin(out_team_pos)
        injury_eligible = (
            backup & backup_of_out_starter & established_role & ~eligible)

    df.loc[injury_eligible, "role_change_injury_flag"] = True
    df.loc[injury_eligible, "participation_effective"] = 1.0
    eligible = eligible | injury_eligible

    # Session (this change), decision -- the partial-participation
    # counterpart to the zero-participation case above, deliberately NOT
    # folded into it. The docstring above explains why a blanket widening
    # was rejected in Session 15.2: it would also promote real committee/
    # lost-job players (Daniel Jones, Jayden Daniels) who happen to be at
    # partial rather than zero participation. But real-world review of the
    # Week 1 2026 slate showed the opposite failure mode going UNCAUGHT:
    # confirmed #1 starters with a completely clean current injury report
    # (Justin Herbert among ~28 others) were getting materially suppressed
    # participation_effective (e.g. 0.8) purely because they sat one
    # meaningless late-season game the PRIOR year (a playoff-seeding rest
    # day) -- there is no reasonable read of "healthy, confirmed starter,
    # nothing wrong per today's real injury report" that should feed a
    # lower participation_effective into ownership's chalk/ownership model
    # (see ownership_heuristic.py's participation_confidence multiplier).
    #
    # The fix distinguishes the two cases the same way the injury-eligible
    # block above already does -- by checking `injury_status`, the one real
    # signal available, rather than trying to infer "was that specific
    # missed game meaningless" from schedule/standings data this pipeline
    # doesn't have. A player who IS flagged QUESTIONABLE/DOUBTFUL/OUT on the
    # current pull is excluded here and left to whatever partial credit the
    # existing role-change override already gives him -- that is real signal
    # this block must not override. `established_role` is the same bar used
    # everywhere else in this function, so a genuine committee back who
    # simply doesn't have a real starter's history share still won't qualify
    # even with a clean injury report.
    clean_injury_report = pd.Series(True, index=df.index)
    if injury_status is not None and not injury_status.empty:
        flagged_ids = set(
            injury_status.loc[injury_status["status"] != "ACTIVE", "player_id"])
        clean_injury_report = ~df["player_id"].isin(flagged_ids)

    participation_num = pd.to_numeric(df["participation"], errors="coerce").fillna(0.0)
    partial_participation = (participation_num > 1e-9) & (participation_num < 1.0 - 1e-9)

    clean_starter_partial = (
        confirmed_starter & established_role & clean_injury_report
        & partial_participation & ~eligible
    )

    df["clean_starter_partial_flag"] = False
    df.loc[clean_starter_partial, "clean_starter_partial_flag"] = True
    df.loc[clean_starter_partial, "participation_effective"] = 1.0
    eligible = eligible | clean_starter_partial

    for pos, cs in COMPONENTS.items():
        pos_mask = eligible & (df["position"].astype(str) == pos)
        if not pos_mask.any():
            continue
        for name, _v, _y, _t in cs:
            raw_col, mu_col = f"{name}_mu_raw", f"{name}_mu"
            if raw_col in df.columns and mu_col in df.columns:
                df.loc[pos_mask, mu_col] = pd.to_numeric(
                    df.loc[pos_mask, raw_col], errors="coerce").fillna(0.0)

    return df.drop(columns=["depth_rank"], errors="ignore")


# ---------------------------------------------------------------------------
# Share reconciliation (decision #7)
# ---------------------------------------------------------------------------

_RECONCILE_SPECS = [
    # (component, mu col, team predicted col, team full-season col,
    #  team recent col, player full-season col, player recent col)
    ("recv", "recv_mu", "team_targets", "hist_targets", "recent_targets",
     "recv_hist_vol", "recv_recent_vol"),
    ("rush", "rush_mu", "team_carries", "hist_carries", "recent_carries",
     "rush_hist_vol", "rush_recent_vol"),
    ("pass", "pass_mu", "team_attempts", "hist_attempts", "recent_attempts",
     "pass_hist_vol", "pass_recent_vol"),
]

# Minimum recent-window volume before the recent share is trusted over the
# full-season one. ARBITRARY, flagged.
RECENT_SHARE_MIN_VOLUME = 25.0


def _pool_share(comp, sub, hist_sub, tv, team, team_hist_col, team_recent_col,
                hist_vol_col, recent_vol_col):
    """What share of the team's volume should these pool players receive?

    Decision #7, second revision -- driven by two real 2021 failures that
    broke in OPPOSITE directions:

      NYJ wk13, only Zach Wilson played. Full-season share 48%, recent-5
      share 11%. He threw ~30.
      CAR wk15, only Cam Newton played. Full-season share 17%, recent-5
      share 47%.

    No backward-looking share gets both right, because the right answer in
    both cases has nothing to do with history: pass attempts are an
    EXCLUSIVE resource. They belong to quarterbacks, the pool contains the
    team's quarterbacks, so the pool's share is 1.0 and the reconciliation's
    job is simply to distribute the team's predicted attempts among whichever
    quarterbacks are available, in proportion to their recent usage. That is
    the correct behaviour in a backtest (one QB in the pool -> he gets it
    all) AND in a live run (several QBs in the pool -> each gets an
    expected-value slice, which is the honest answer under uncertainty).

    Rushing and receiving are NOT exclusive -- the slate pool genuinely
    misses bench players -- so those keep a share estimate, but taken over
    the recent window rather than the full season, so a mid-season backfield
    or target-share change is reflected instead of averaged away. Falls back
    to the full-season share when the recent window is too thin to trust.

    Session 15.2 -- `hist_sub` vs `sub`. `sub` is the pool grouped by each
    player's CURRENT team (this slate's roster). `hist_sub` is the pool
    grouped by each player's team AS OF the games his own recent/hist
    volume was actually produced in. For the large majority of players
    these are the same team and this distinction is a no-op. For a player
    who changed teams over the offseason, they are not -- and asking "how
    much of team X's own recent history does our pool capture" using
    `sub` (current team) answers a different, wrong question: it credits
    team X with a traded-away player's production that team X no longer
    has, while failing to credit the player's OWN real recent production
    to the team it actually happened for. Confirmed real and material on
    the real Week 1 2026 slate: 70 players league-wide had a current team
    different from their 2025 team, several with substantial volume
    (Travis Etienne Jr., 79 recent rush attempts, JAX in 2025 -> NO on
    this slate; Rico Dowdle, 62, CAR -> PIT). Carolina's own rush pool
    share came out at 55.7% purely from Dowdle's real production being
    attributed to Pittsburgh instead. `sub` (current team) is still what
    price_share and the eventual rescale use below -- a traded player's
    SALARY and his own final projection still need to reflect his new
    team's context. Only the numerator of "how much of team X's own
    history survives in today's pool" changes.
    """
    if comp in EXCLUSIVE_COMPONENTS:
        return 1.0, "exclusive"
    # Decision #14: week 1 has no historical pool share to take, but it DOES
    # have a price-implied one -- the sum of the pool's price-predicted
    # shares IS an estimate of the pool's share of team volume, and it is
    # the only such estimate available before a game is played. Used only
    # when the history-based bases below are unavailable. Price reflects
    # the player's CURRENT-team role, so this deliberately uses `sub`
    # (current team), not `hist_sub`.
    price_col = f"{comp}_price_share"
    have_history = team_recent_col in tv.columns and team in tv.index
    if not have_history and price_col in sub:
        ps = float(sub[price_col].fillna(0.0).sum())
        if ps > 0:
            return min(ps, 1.0), "price"
    team_recent = float(tv.at[team, team_recent_col])
    pool_recent = float(hist_sub[recent_vol_col].fillna(0.0).sum()) if recent_vol_col in hist_sub else 0.0
    if team_recent >= RECENT_SHARE_MIN_VOLUME and pool_recent > 0:
        return min(pool_recent / team_recent, 1.0), "recent"
    team_hist = float(tv.at[team, team_hist_col])
    pool_hist = float(hist_sub[hist_vol_col].fillna(0.0).sum())
    if team_hist <= 1e-9 or pool_hist <= 1e-9:
        return None, "unavailable"
    return min(pool_hist / team_hist, 1.0), "full_season"


def reconcile_team_shares(pool: pd.DataFrame, team_vol: pd.DataFrame,
                          fail_threshold: float = RECONCILE_FAIL_THRESHOLD,
                          full_usage: pd.DataFrame | None = None) -> tuple:
    """Rescale each team's pool volume to match (predicted team volume) x
    (the share of team volume these same players took historically).

    Returns (pool, report). Raises SystemExit if any team/component needs a
    rescale beyond `fail_threshold` -- the ROADMAP's mandatory fail-loud.

    Session (this change) -- `full_usage`, new and optional. Real bug found
    live: `_pool_share()`'s "recent"/"full_season" numerator (how much of
    team X's own historical volume survives in today's pool) was computed
    from `pool` itself -- which for a SUBSET slate (an "afternoon"-only or
    "early"-only contest covering a handful of that week's real games) is
    missing every player whose CURRENT team isn't one of those few games,
    even when that player's HISTORY still legitimately belongs to a team
    that IS in the slate. Confirmed real on the Week 1 2026 DK afternoon
    slate: Michael Carter (hist_team=ARI, 42 of ARI's own recent 86 rush
    attempts, current team=TEN) is absent from the afternoon slate's salary
    file simply because TEN's game isn't in that window -- not because he
    left the league. That silently dropped ARI's own measured "recent
    share" from 73/86 (85%, the real number, seen correctly on the full
    "main" slate which does include a TEN game) to 19/86 (22%), producing
    an absurd, fail-loud-tripping team-implied target.

    `full_usage` -- the ENTIRE league's real recency-weighted usage table
    (statline_model.build_usage()'s own unfiltered output, computed once
    per season/week from real box scores, before any slate-specific salary
    merge -- see build_projections_statline.py) -- fixes this at the root:
    it has every player who has actually recorded real production this
    recency window, regardless of which teams happen to be bundled into
    the CURRENT build's own slate. Grouping by hist_team against this
    complete table means a traded/moved player's own history is credited
    to his old team consistently, whether or not his new team's game
    happens to be in this particular slate. `pool` is still what actually
    gets rescaled/projected below -- only the SHARE numerator's source
    changes. Backward-compatible: omitting `full_usage` falls back to the
    prior (slate-scoped) behavior, so a caller that hasn't been updated
    yet still runs, just with the original bug.
    """
    pool = pool.copy()
    tv = team_vol.set_index("team")
    report = []
    violations = []

    # Session 15.2 -- grouped once, by each player's HISTORICAL team (see
    # _pool_share()'s docstring for the full "why"). Falls back to current
    # team when hist_team is missing/NaN (a true no-history rookie has
    # nothing to misattribute either way, and an older pool built before
    # this session's build_projections_statline.py change simply won't
    # have the column -- same graceful degradation, not a hard dependency).
    #
    # Session (this change) -- the grouping SOURCE is now `full_usage` when
    # given (see docstring above), not the slate-scoped `pool`, so a
    # subset slate's incomplete player list can't silently corrupt this
    # calculation. `sub`/`raw_sum`/the actual rescale below still operate
    # on `pool` -- only the share numerator's source table changes.
    hist_source = full_usage if full_usage is not None and not full_usage.empty else pool
    # `full_usage` (statline_model.build_usage()'s own raw output) only ever
    # has `hist_team`, never a `team` column -- unlike `pool`, which has
    # both. Only fall back to `team` when it actually exists (`pool`'s own
    # case, where a merge can leave hist_team NaN for an unmatched row).
    if "hist_team" in hist_source.columns:
        hist_team_series = hist_source["hist_team"]
        if "team" in hist_source.columns:
            hist_team_series = hist_team_series.fillna(hist_source["team"])
    else:
        hist_team_series = hist_source["team"]
    hist_groups = hist_source.groupby(hist_team_series).groups

    for (comp, mu_col, team_pred_col, team_hist_col, team_recent_col,
         hist_vol_col, recent_vol_col) in _RECONCILE_SPECS:
        if mu_col not in pool.columns:
            continue
        for team, idx in pool.groupby("team").groups.items():
            if team not in tv.index:
                continue  # bye / unmapped team; handled upstream
            sub = pool.loc[idx]
            # 2026-09-23 projection review fix -- confirmed real bug, not a
            # guess (found while tracing the QB price-share dilution fix
            # above to a real rebuild: Joe Burrow's own accurate, already-
            # correct pass_mu of 35.36 was cut to 22.1 by THIS step alone,
            # not the price-share one). `raw_sum` sums `mu_col` over every
            # player CURRENTLY on `team` in the pool -- but `mu_col` at this
            # point is each player's OWN recency-weighted volume, which for
            # a player whose `hist_team` differs from his current team
            # reflects a DIFFERENT team's real offense (a trade, a
            # practice-squad promotion, or -- as here -- a new team simply
            # rostering a real journeyman backup who started/relieved
            # elsewhere last season). That inflates `raw_sum` with volume
            # that has nothing to do with `team`'s real passing/rushing/
            # receiving distribution, so `scale = target/raw_sum` then cuts
            # every REAL contributor on `team` to compensate for a phantom
            # teammate. Confirmed and quantified on the real 2026 wk1 DK
            # slate: CIN's pass raw_sum was 58.6 against a real target of
            # 36.6 (scale 0.624) purely because Josh Johnson (CIN's real
            # QB3, hist_team=WAS -- he played for Washington, not
            # Cincinnati, last season) contributed his own ~11.4-attempt
            # WAS-based mu into CIN's pool sum. Not QB-specific: the same
            # scan across every team's `rush` component on that slate found
            # scale factors of 0.53-0.75x almost league-wide (MIA, CLE,
            # BUF, LAC, PHI, HOU, BAL, CIN, LV, TB, MIN, PIT, IND, WAS, ...)
            # -- RB is not winner-take-all like QB, so a handful of
            # cross-team-history bench backs on EVERY team's roster adds up
            # to a broad, not isolated, downward bias.
            #
            # This function already has the fix's own justification and
            # data source built in -- `_pool_share()`'s own docstring
            # (Session 15.2) established that a player's OWN mu/volume
            # should be attributed to the team his `hist_team` says it
            # actually came from, not whichever team currently rosters him,
            # and already applies that rule to the SHARE numerator (`hist_
            # sub` above). It was never extended to `raw_sum`, the
            # denominator that actually drives `scale` -- this closes that
            # gap using the exact same `hist_team` column (already carried
            # through from build_usage(), per build_projections_statline.py
            # Session 15.2's comment) rather than a new data source or a
            # new, unvalidated heuristic. A player with no `hist_team` at
            # all (a true rookie/no-history case) is KEPT in the sum -- his
            # own mu is 0 either way, so this only ever excludes a REAL,
            # non-zero, provably-misattributed contribution, never a
            # legitimate teammate's. `sub` (unfiltered) is still what the
            # `scale` factor gets APPLIED to below -- a traded/misattributed
            # player's own final projection still reflects his new team's
            # context, same as `_pool_share()`'s own numerator/denominator
            # split already does for the share fraction.
            hist_team_col = sub["hist_team"] if "hist_team" in sub.columns else None
            if hist_team_col is not None:
                attributable = hist_team_col.isna() | (hist_team_col.astype(str) == str(team))
                # 2026-09-24 guard: a depth-chart QB1 who changed teams (wk1
                # Cousins/Murray/Geno Smith/Willis, wk3 Murray) IS this
                # team's passing volume now -- excluding him left only his
                # backups' tiny mu in raw_sum, so `scale` (target/raw_sum)
                # blew up and was then applied to the starter himself
                # (Cousins 134 pass att / 62 pts, actual 15.8).
                if "depth_qb1" in sub.columns:
                    attributable = attributable | sub["depth_qb1"].fillna(False).astype(bool)
                raw_sum = float(sub.loc[attributable, mu_col].fillna(0.0).sum())
            else:
                raw_sum = float(sub[mu_col].fillna(0.0).sum())
            if raw_sum <= 1e-9:
                continue
            hist_idx = hist_groups.get(team, pd.Index([]))
            # `hist_idx` indexes into `hist_source` (== `pool` unless
            # `full_usage` was given), NOT necessarily `pool` -- see the
            # Session (this change) note above.
            hist_sub = hist_source.loc[hist_idx] if len(hist_idx) else sub
            pool_share, share_basis = _pool_share(
                comp, sub, hist_sub, tv, team, team_hist_col, team_recent_col,
                hist_vol_col, recent_vol_col)
            if pool_share is None:
                continue
            target = float(tv.at[team, team_pred_col]) * pool_share
            if target <= 1e-9:
                continue
            scale = target / raw_sum
            report.append({"team": team, "component": comp,
                           "pool_share": round(pool_share, 4),
                           "share_basis": share_basis,
                           "raw_sum": round(raw_sum, 2), "target": round(target, 2),
                           "scale": round(scale, 4),
                           "abs_delta": round(abs(target - raw_sum), 2)})
            # Decision #7, materiality gate: the relative test alone is
            # meaningless at low volume. A 1.6x rescale on 9 pass attempts is
            # 5 attempts of noise (a team with two injured QBs); the same
            # ratio on 550 attempts would be a catastrophe. Require BOTH a
            # relative violation AND a material absolute one. The rescale
            # still APPLIES below the floor -- only the fail-loud is gated.
            # An EXCLUSIVE component's target is structural (the team's whole
            # volume), so its scale is a normalization by construction, not a
            # signal about model health -- participation weighting deliberately
            # holds each quarterback below a full workload and reconciliation
            # is what restores the team total. Observed routinely at 2-13x on
            # perfectly healthy weeks. Reporting those as "violations" would
            # bury the rush/recv signal that does carry information, so
            # exclusive components are exempt from the RATIO test and remain
            # subject to the absolute-breakage test below.
            material = max(target, raw_sum) >= RECONCILE_MIN_VOLUME
            if comp in EXCLUSIVE_COMPONENTS:
                if abs(target - raw_sum) >= RECONCILE_EXTREME_ABS:
                    violations.append((team, comp, scale, raw_sum, target))
            elif material and abs(scale - 1.0) > fail_threshold:
                violations.append((team, comp, scale, raw_sum, target))
            pool.loc[idx, mu_col] = sub[mu_col].fillna(0.0) * scale
            if mu_col == "pass_mu":
                over = pool.loc[idx, mu_col] > QB_PASS_ATT_CAP
                if over.any():
                    print(f"WARNING share reconciliation: {team} pass_mu above the "
                          f"{QB_PASS_ATT_CAP:.0f}-attempt cap after a {scale:.2f}x rescale "
                          f"-- clamped: "
                          + ", ".join(f"{pool.loc[i, 'player_id']}={pool.loc[i, mu_col]:.0f}"
                                      for i in over[over].index))
                    pool.loc[over[over].index, mu_col] = QB_PASS_ATT_CAP

    # Decision #7, systemic vs local: a SINGLE team needing a big rescale is
    # usually real football -- an injured QB room, a mid-season backfield
    # change -- and reconciliation repairing it is the feature, not a fault.
    # What indicates BREAKAGE (wrong team mapping, broken volume model) is
    # either many teams violating at once, or one team violating absurdly.
    # Verified on real 2021 week 10: SEA needed 1.59x purely because Russell
    # Wilson was returning from a four-week absence, which decision #10
    # already documents as a known limitation. Aborting the run for that
    # would make the engine unusable on ordinary weeks.
    if violations:
        n_material = sum(
            1 for r in report
            if max(r["target"], r["raw_sum"]) >= RECONCILE_MIN_VOLUME)
        share = len(violations) / max(n_material, 1)
        # Decision #7, second revision: breakage needs BOTH an extreme ratio
        # and a material ABSOLUTE discrepancy. Every real 2021 failure was
        # under half a game's volume (NYJ 13.4 attempts, CAR 11.3) while the
        # ratio looked alarming purely because the denominator was small. A
        # broken team mapping shows |delta| in the hundreds, not the teens.
        extreme = [v for v in violations
                   if (v[2] > RECONCILE_EXTREME_SCALE
                       or v[2] < 1.0 / RECONCILE_EXTREME_SCALE)
                   and abs(v[4] - v[3]) >= RECONCILE_EXTREME_ABS]
        # Worst first. The caller (backtest_harness) truncates a failing
        # subprocess's output, and on the first Session 10.3a run that
        # truncation cut the message off after the FIRST violation in team
        # order -- which was a 2.00x pair, while the message said "beyond
        # 3.0x". The pair that actually tripped the gate was invisible. So:
        # sort by severity, and name the offending pairs in the FIRST line
        # rather than only in the list below it.
        def _fmt(v):
            t, c, sc, rs, tg = v
            return (f"    {t} {c}: needed {sc:.2f}x rescale "
                    f"(pool sum {rs:.1f} vs team-implied target {tg:.1f})")
        ordered = sorted(violations, key=lambda v: -abs(v[2] - 1.0))
        lines = "\n".join(_fmt(v) for v in ordered)
        print(f"NOTE share reconciliation: {len(violations)}/{n_material} material "
              f"team/component pair(s) needed a rescale beyond "
              f"{fail_threshold:.0%}:\n{lines}")
        systemic = (n_material >= RECONCILE_MIN_PAIRS_FOR_SHARE_TEST
                    and share > RECONCILE_MAX_VIOLATION_SHARE)
        if systemic or extreme:
            if extreme:
                worst = sorted(extreme, key=lambda v: -abs(v[2] - 1.0))
                reason = (f"{len(extreme)} pair(s) beyond "
                          f"{RECONCILE_EXTREME_SCALE:.1f}x -- "
                          + "; ".join(
                              f"{t} {c} {sc:.2f}x (pool {rs:.1f} vs target {tg:.1f})"
                              for t, c, sc, rs, tg in worst[:3]))
            else:
                reason = (f"{share:.0%} of {n_material} material pairs violated "
                          f"(limit {RECONCILE_MAX_VIOLATION_SHARE:.0%}) -- worst: "
                          + "; ".join(
                              f"{t} {c} {sc:.2f}x"
                              for t, c, sc, rs, tg in ordered[:3]))
            raise SystemExit(
                f"statline share reconciliation FAILED (decision #7): {reason}\n"
                f"All violations, worst first:\n{lines}\n"
                f"This is the ROADMAP's mandatory fail-loud. A discrepancy this "
                f"widespread is not one odd depth chart -- it means the volume "
                f"model, the team mapping, or the pool composition is wrong, and "
                f"silently rescaling would hide it. Investigate before trusting "
                f"any projection from this week.")

    return pool, pd.DataFrame(report)


# ---------------------------------------------------------------------------
# Simulation (decisions #1, #2, #6, #8, #9)
# ---------------------------------------------------------------------------

def simulate(pool: pd.DataFrame, site: str, variance: dict,
             n_sims: int = DEFAULT_SIMS, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    """Simulate every player's stat line, score each draw with `site`'s exact
    rules, and return per-player mean/sigma plus the mean stat line.

    `pool` needs: player_id, position, team, and the usage columns
    build_usage()/apply_volume_prior() produced (including {comp}_hist_share),
    plus `market_factor` (matchup x vegas, decision #10).

    Session 15.2c, decision #18: teammates' volumes are now correlated via
    a shared per-(team, component) shock, drawn once before the per-player
    loop below so every player on a team uses the SAME shock realization.
    Session 15.2b tried this and rejected it (see its own note, preserved
    in fit_statline_variance.py's decision #7, for why an unchanged `r`
    made it worse); Session 15.2c found why and fixed it at the source --
    `r` itself is now fit net of the team-level share, so this module adds
    real, additive information rather than double-counting. See decision
    #18 above for the full mechanics and SESSION_LOG.md Session 15.2c for
    the coverage-backtest numbers that validated it.
    """
    from fit_statline_variance import COMPONENTS

    rng = np.random.default_rng(seed)  # decision #2: never the global RNG
    results = []

    # --- decision #18: one shared shock per (team, component) ------------
    team_shock_cfg = variance.get("team_shock", {})
    shock_scale = _num(team_shock_cfg.get("redistribution_shock_scale"), 0.0)
    excluded_pairs = {tuple(p) for p in team_shock_cfg.get("excluded_pairs", [])}
    team_shocks = {}  # (team, comp_name) -> shock array, length n_sims
    if shock_scale > 0 and "team" in pool.columns:
        for team, _ in pool.groupby("team"):
            for name in ("pass", "rush", "recv"):
                cfg = team_shock_cfg.get(name)
                if not cfg:
                    continue
                team_shocks[(team, name)] = rng.normal(
                    0.0, cfg["residual_sd"], size=n_sims)

    for row in pool.itertuples(index=False):
        pos = getattr(row, "position")
        if pos not in COMPONENTS:
            continue
        vpos = variance["positions"][pos]
        factor = _num(getattr(row, "market_factor", 1.0), 1.0)
        if factor <= 0:
            factor = 1.0
        team = getattr(row, "team", None)

        draws = {c: np.zeros(n_sims, dtype=float) for c in scoring_rules.STATLINE_COLUMNS}

        for name, vol_stat, yd_stat, td_stat in COMPONENTS[pos]:
            comp = vpos["components"][name]
            mu = _num(getattr(row, f"{name}_mu", 0.0))

            # Decision #18: shift mu by this player's slice of his team's
            # shared shock, unless this (position, component) pair is
            # excluded (WR/rush -- see fit_statline_variance.py decision
            # #8) or no shock exists for this team/component/artifact.
            # Weather (scripts/weather.py): the passing chain (pass/recv)
            # gets an efficiency + volume factor; rushing gets a volume lift.
            # All neutral 1.0 when the columns are absent.
            if name == "rush":
                wx_eff, wx_vol = 1.0, _num(getattr(row, "rush_vol_factor", 1.0), 1.0)
            else:
                wx_eff = _num(getattr(row, "pass_eff_factor", 1.0), 1.0)
                wx_vol = _num(getattr(row, "pass_vol_factor", 1.0), 1.0)
            wx_eff = wx_eff if wx_eff > 0 else 1.0
            wx_vol = wx_vol if wx_vol > 0 else 1.0
            mu = mu * wx_vol

            mu_for_draw = mu
            shock = team_shocks.get((team, name)) if team is not None else None
            if (shock is not None and (pos, name) not in excluded_pairs
                    and mu > 1e-9):
                hist_share = _num(getattr(row, f"{name}_hist_share", None), 0.0)
                r_val = _num(comp.get("r"), 0.0)
                if hist_share > 0 and r_val > 0:
                    slope = team_shock_cfg[name]["pass_through_slope"]
                    c = np.sqrt(r_val / (r_val + 1.0))
                    mu_for_draw = mu + shock_scale * c * slope * hist_share * shock

            # Decision #10: the market factor scales efficiency, not volume.
            yd_rate = _num(getattr(row, f"{name}_yd_rate", 0.0)) * factor * wx_eff
            td_rate = _num(getattr(row, f"{name}_td_rate", 0.0)) * factor * wx_eff
            vol, yards, tds = _draw_component(
                rng, n_sims, mu_for_draw, comp["r"], yd_rate, td_rate,
                comp["yards_cv"], comp["latent_sd"])
            vcol, ycol, tcol = _COMPONENT_STATS[name]
            draws[vcol] += vol
            draws[ycol] += yards
            draws[tcol] += tds

        # Receptions from targets (decision #4's shrunk catch rate).
        if draws["targets"].any():
            cr = float(np.clip(_num(getattr(row, "catch_rate", None),
                                        vpos["catch_rate"]), 0.0, 1.0))
            draws["rec"] = rng.binomial(draws["targets"].astype(int), cr).astype(float)

        if pos == "QB" and draws["pass_att"].any():
            ir = float(np.clip(_num(getattr(row, "int_rate", None),
                                        vpos.get("int_per_attempt", 0.0)), 0.0, 0.5))
            draws["pass_int"] = rng.binomial(draws["pass_att"].astype(int), ir).astype(float)

        touches = draws["rush_att"] + draws["rec"]
        fr = float(vpos["fumbles_lost_per_touch"])
        if fr > 0 and touches.any():
            draws["fumbles_lost"] = rng.binomial(touches.astype(int), fr).astype(float)

        # Decision #8: 2pt / return TD / fumble-recovery TD stay at zero.
        pts = scoring_rules.score_statline(draws, site)

        rec = {"player_id": getattr(row, "player_id"),
               "statline_mean": float(pts.mean()),
               "statline_sigma": float(pts.std(ddof=1)),
               "statline_p90": float(np.percentile(pts, 90)),
               "statline_p10": float(np.percentile(pts, 10))}
        for c in ("pass_att", "pass_yd", "pass_td", "rush_att", "rush_yd",
                  "rush_td", "targets", "rec", "rec_yd", "rec_td"):
            rec[f"proj_{c}"] = float(draws[c].mean())
        results.append(rec)

    return pd.DataFrame(results)
