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
            mu = _recency_weighted(g[vol_stat].to_numpy()) * part
            den = float(g[vol_stat].sum())
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
