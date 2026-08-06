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
    """Negative binomial with mean mu, Var = mu + mu^2/r."""
    mu = _num(mu, 0.0)
    if mu <= 1e-9:
        return np.zeros(size, dtype=float)
    r = max(_num(r, 1.0), 1e-3)
    p = r / (r + mu)
    return rng.negative_binomial(r, p, size=size).astype(float)


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
    """Decision #5: REG games strictly before the target week."""
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Run ingest_historical.py --season {season} "
            f"first (Session 1.2).")
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

    team_wks = team_weeks_played(hist)
    lookback = len(RECENCY_WEIGHTS)

    rows = []
    for pid, g in hist.groupby("player_id"):
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


def team_volume_history(season: int, week: int) -> pd.DataFrame:
    """Recency-weighted team-level volume, for decision #7's reconciliation."""
    hist = load_history(season, week)
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
                               artifact: dict, teams=None) -> pd.DataFrame:
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

    for comp, col in _TEAM_PRED_COL.items():
        hist_vals = None
        if not week1 and col in out.columns:
            out[f"{col}_history"] = out[col]
            hist_vals = out[col]
        out[col] = volume_prior.predict_team_volume(
            artifact, comp, it, sp, history_volume=hist_vals)
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


def apply_volume_prior(pool: pd.DataFrame, artifact: dict,
                       team_vol: pd.DataFrame,
                       weight_floor: float = None, k: float = None,
                       role_change: bool = True) -> pd.DataFrame:
    """Decisions #11, #12, #15. Blend a price-implied volume into `{comp}_mu`
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
        df[mu] = volume_prior.blend_volume(
            df[mu], df[f"{comp}_price_volume"], w)
    return df


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


def _pool_share(comp, sub, tv, team, team_hist_col, team_recent_col,
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
    """
    if comp in EXCLUSIVE_COMPONENTS:
        return 1.0, "exclusive"
    # Decision #14: week 1 has no historical pool share to take, but it DOES
    # have a price-implied one -- the sum of the pool's price-predicted
    # shares IS an estimate of the pool's share of team volume, and it is
    # the only such estimate available before a game is played. Used only
    # when the history-based bases below are unavailable.
    price_col = f"{comp}_price_share"
    have_history = team_recent_col in tv.columns and team in tv.index
    if not have_history and price_col in sub:
        ps = float(sub[price_col].fillna(0.0).sum())
        if ps > 0:
            return min(ps, 1.0), "price"
    team_recent = float(tv.at[team, team_recent_col])
    pool_recent = float(sub[recent_vol_col].fillna(0.0).sum()) if recent_vol_col in sub else 0.0
    if team_recent >= RECENT_SHARE_MIN_VOLUME and pool_recent > 0:
        return min(pool_recent / team_recent, 1.0), "recent"
    team_hist = float(tv.at[team, team_hist_col])
    pool_hist = float(sub[hist_vol_col].fillna(0.0).sum())
    if team_hist <= 1e-9 or pool_hist <= 1e-9:
        return None, "unavailable"
    return min(pool_hist / team_hist, 1.0), "full_season"


def reconcile_team_shares(pool: pd.DataFrame, team_vol: pd.DataFrame,
                          fail_threshold: float = RECONCILE_FAIL_THRESHOLD) -> tuple:
    """Rescale each team's pool volume to match (predicted team volume) x
    (the share of team volume these same players took historically).

    Returns (pool, report). Raises SystemExit if any team/component needs a
    rescale beyond `fail_threshold` -- the ROADMAP's mandatory fail-loud.
    """
    pool = pool.copy()
    tv = team_vol.set_index("team")
    report = []
    violations = []

    for (comp, mu_col, team_pred_col, team_hist_col, team_recent_col,
         hist_vol_col, recent_vol_col) in _RECONCILE_SPECS:
        if mu_col not in pool.columns:
            continue
        for team, idx in pool.groupby("team").groups.items():
            if team not in tv.index:
                continue  # bye / unmapped team; handled upstream
            sub = pool.loc[idx]
            raw_sum = float(sub[mu_col].fillna(0.0).sum())
            if raw_sum <= 1e-9:
                continue
            pool_share, share_basis = _pool_share(
                comp, sub, tv, team, team_hist_col, team_recent_col,
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

    `pool` needs: player_id, position, and the usage columns build_usage()
    produced, plus `market_factor` (matchup x vegas, decision #10).
    """
    from fit_statline_variance import COMPONENTS

    rng = np.random.default_rng(seed)  # decision #2: never the global RNG
    results = []

    for row in pool.itertuples(index=False):
        pos = getattr(row, "position")
        if pos not in COMPONENTS:
            continue
        vpos = variance["positions"][pos]
        factor = _num(getattr(row, "market_factor", 1.0), 1.0)
        if factor <= 0:
            factor = 1.0

        draws = {c: np.zeros(n_sims, dtype=float) for c in scoring_rules.STATLINE_COLUMNS}

        for name, vol_stat, yd_stat, td_stat in COMPONENTS[pos]:
            comp = vpos["components"][name]
            mu = _num(getattr(row, f"{name}_mu", 0.0))
            # Decision #10: the market factor scales efficiency, not volume.
            yd_rate = _num(getattr(row, f"{name}_yd_rate", 0.0)) * factor
            td_rate = _num(getattr(row, f"{name}_td_rate", 0.0)) * factor
            vol, yards, tds = _draw_component(
                rng, n_sims, mu, comp["r"], yd_rate, td_rate,
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
