"""
fit_statline_variance.py
=========================

Session 10.3a -- the FITTER for the stat-line variance model.

Same fitter/consumer split as Session 10.2's fit_salary_anchor.py /
salary_anchor.py: this is an occasional offline job with the estimation
machinery in it, and `statline_model.py` is the small stable thing the
projection path imports every run. The production path never imports this.

What it fits, per position, from real nflverse weekly stats:

  * VOLUME dispersion -- a negative-binomial `r` for each volume stat
    (pass attempts, carries, targets), so simulated volume has the real
    week-to-week spread instead of Poisson's.
  * YARDS dispersion -- the coefficient of variation of actual yards around
    volume x the player's own per-opportunity rate.
  * YARDS<->TD correlation -- the measured within-player correlation, which
    the consumer reproduces with a shared latent game-quality factor. The
    ROADMAP's validation line for this card requires exactly this ("an
    empirical within-player yards/TD correlation adjustment, not an
    independence assumption").
  * POSITION-MEAN efficiency rates -- the shrinkage targets the consumer
    pulls a thin-sample player toward.

Numbered decisions:

  1. THE ARTIFACT IS SITE-AGNOSTIC (`data/statline_variance.json`, no site
     in the name). A stat line is real football; it does not know what DK
     pays for a reception. Only the CONVERTER is site-specific
     (scoring_rules.py). This is deliberately unlike salary_anchor, which
     had to be per site because prices and scoring both differ. Consequence
     worth stating: unlike every other FD component in this project, this
     one is NOT blocked on real FD data -- it is fit once and both sites use
     it.

  2. METHOD-OF-MOMENTS NEGATIVE BINOMIAL, pooled over player-seasons with at
     least MIN_GAMES games. Var = mu + mu^2/r, so r = sum(mu^2) /
     sum(max(var - mu, 0)). Pooling over player-seasons rather than fitting
     per player is intentional: a per-player r on 6-16 games is noise, and
     the consumer needs a stable positional constant, not a personal one.

  3. ONLY REAL COMPONENTS PER POSITION -- a hard whitelist, not "whatever
     has rows". This one is load-bearing. Pooling blindly produces garbage
     from trick plays: measured over 2014-2021, RB "passing TD per attempt"
     comes out 0.163 and WR's 0.199, off a handful of gadget throws. Feeding
     those to a simulator would have every RB in the pool throwing
     touchdowns. Anything outside the whitelist is fixed at zero and never
     simulated.

  4. ZERO-VOLUME GAMES ARE KEPT in the volume dispersion fit and EXCLUDED
     from the efficiency fits. A week where a player got no carries is real
     information about his volume distribution (that is exactly the downside
     the sigma should capture), but it carries no information about his yards
     per carry, and dividing by it is undefined.

  5. FAIL LOUD ON THIN DATA rather than shipping a curve fit on nothing --
     the same guard Session 10.2 had to add to its own fitter after it
     counted rows instead of bins and let an unfittable FD curve through
     twice. Every whitelisted component must clear MIN_GROUPS player-seasons
     or the fit raises before anything reaches disk.

  6. THE LATENT SD IS SOLVED FOR, NOT GUESSED. The consumer reproduces the
     measured yards<->TD correlation via a shared latent multiplier; the
     value of that latent's SD which produces the measured correlation is
     found here by bisection against the consumer's own simulator, and
     stored. So the correlation is calibrated, not asserted. If a future
     change to the simulator breaks the calibration, re-running this fitter
     is what re-establishes it.

  7. SESSION 15.2B -- team_shock IS A NEW ARTIFACT SECTION, AND A NEW
     ORDERING DEPENDENCY: this fitter must now run AFTER fit_volume_prior.py
     has written a team-volume artifact, because fit_team_shock() computes
     real residuals against that model's own predictions rather than a
     second, independent measurement of team volume. Two real numbers per
     component (residual_sd, pass_through_slope) -- kept separate rather
     than multiplied into one, because the slope is a real, measured,
     component-specific football fact (0.51 rush, 0.76 pass, 0.84 recv on
     2021 data, t = 8-20 in every case) and folding it away would hide
     that. See fit_team_shock()'s own docstring for the full reasoning and
     SESSION_LOG.md Session 15.2b for the probe that established both
     numbers before this was built.

  8. SESSION 15.2C -- CONDITIONAL r, NET OF THE TEAM-LEVEL SHOCK. Session
     15.2b found that fit_volume_dispersion()'s r ALREADY bakes in enough
     of a player's real team-context swings that adding team_shock on top
     of an unchanged r over-inflates team-total variance (a real,
     measured teammate correlation, t = 28-60, that nonetheless made a
     1,062-team-week coverage backtest WORSE at every scale tested).
     fit_team_shock()'s own OLS-through-origin regression (y = slope * x,
     x = team_residual * hist_share) already computes, for every real
     player-week, a residual (y - slope * x) that is BY CONSTRUCTION
     uncorrelated with the team-level piece -- so re-fitting r against
     `actual - slope * x` instead of raw `actual` (same MIN_GAMES gate,
     same method-of-moments formula fit_volume_dispersion() already uses)
     targets ONLY the within-team redistribution variance, leaving the
     team-level share to be carried by team_shock instead of double-
     counted. Verified on real 2014-2021 data: r rises for every
     (position, component) pair as expected (removing real variance can
     only raise r), with the team-level share of each pair's excess
     variance ranging 26%-59% -- except WR/rush (EXCLUDED_PAIRS below).

     EXCLUDED_PAIRS: WR/rush's team-level share came out NEGATIVE (-39%)
     on real data -- subtracting the pooled rush slope's estimate made
     WR rushing's leftover variance BIGGER, not smaller. Real football
     reason: the "rush" component's slope is fit pooled across QB
     scrambles, RB carries, and WR jet sweeps together, and that pool is
     completely dominated by QB/RB volume (22,017 player-weeks vs. WR's
     1,582) -- a team throwing more or fewer carries overall doesn't
     meaningfully predict how many jet sweeps a WR gets. WR/rush keeps
     fit_volume_dispersion()'s own r untouched and is never shocked.
     Confirmed with the user (a football-knowledge call, not the
     pipeline's to make) before shipping.

  9. SESSION 15.2C -- THE SHOCK ITSELF NEEDS TWO CORRECTIONS BEFORE IT
     CAN BE ADDED BACK, both found by a real 2022-2024 held-out coverage
     backtest (genuinely out-of-sample for volume_prior_dk.json AND
     team_shock, both fit only on 2014-2021):

     a. A negative binomial's own extra-Poisson variance term is
        mu^2/r -- convex in mu. Randomizing a player's mu via a shared
        team-level shock therefore inflates his OWN simulated variance
        by a further (1 + 1/r) beyond the shock's own variance (law of
        total variance + Jensen's inequality; verified numerically
        before shipping). Exactly cancelled by scaling that player's own
        slice of the shared shock by sqrt(r / (r + 1)) -- using THAT
        player's own (new, decomposed) r -- before adding it to his mu.
        Computed at simulate() time from the live r, not stored, so a
        future refit of r can never silently drift out of sync with this
        correction.

     b. Even after (a), the backtest still over-covered for rush and
        recv. Real teammates' redistribution noise is CLOSE TO a
        zero-sum system within a team-week (one player getting more than
        his historical share predicts usually means a teammate got
        less, because the real team total is fixed) but not exactly --
        hist_share doesn't sum to exactly 1.0 across a team's real
        contributors (1.25 on average for recv, checked directly), so
        this has no clean closed-form second correction. Empirically
        grid-searched instead, the same way decision #6's latent_sd is
        solved against the real simulator rather than guessed: one
        scale factor, REDISTRIBUTION_SHOCK_SCALE below, found
        independently for pass/rush/recv and landing on the same value
        (0.70) all three times -- not a coincidence one would expect
        from three separately-noisy searches, more likely a generic
        property of the mixture rather than a component-specific
        football fact (unlike pass_through_slope, which genuinely does
        differ by component). Confirmed this restores near-nominal
        coverage on the same real held-out backtest before shipping.
        See SESSION_LOG.md Session 15.2c for the full grid and numbers.

Usage:
  python3 scripts/fit_statline_variance.py --seasons 2014 2015 2016 2017 2018 2019 2020 2021
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from statline_model import _recency_weighted  # noqa: E402 -- Session 15.2b

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
sys.path.insert(0, str(Path(__file__).resolve().parent))

SCHEMA_VERSION = 1
ARTIFACT_PATH = DATA_DIR / "statline_variance.json"

POSITIONS = ["QB", "RB", "WR", "TE"]
MIN_GAMES = 6        # player-seasons below this are excluded from dispersion fits
MIN_GROUPS = 30      # decision #5: fewer qualifying player-seasons than this is fatal
MIN_EFF_ROWS = 200   # decision #5: efficiency fits need this many usable rows

# Decision #3 -- the whitelist. (component, volume stat, yards stat, td stat).
# "component" is the consumer's simulation unit.
COMPONENTS = {
    "QB": [("pass", "attempts", "passing_yards", "passing_tds"),
           ("rush", "carries", "rushing_yards", "rushing_tds")],
    "RB": [("rush", "carries", "rushing_yards", "rushing_tds"),
           ("recv", "targets", "receiving_yards", "receiving_tds")],
    "WR": [("recv", "targets", "receiving_yards", "receiving_tds"),
           ("rush", "carries", "rushing_yards", "rushing_tds")],
    "TE": [("recv", "targets", "receiving_yards", "receiving_tds")],
}

# Session 15.2b: the team-shock fit's own component->real-stat mapping.
# Deliberately separate from COMPONENTS above (which is position-keyed and
# whitelist-shaped) -- this one only needs the three team-level volume
# stats fit_volume_prior.py's own team_volume model predicts.
TEAM_SHOCK_STAT_COL = {"pass": "attempts", "rush": "carries", "recv": "targets"}

# Session 15.2c decision #8 -- (position, component) pairs excluded from
# the conditional-r decomposition and the shock, football judgment call,
# not the pipeline's to make on its own. See decision #8's own text.
EXCLUDED_SHOCK_PAIRS = {("WR", "rush")}

# Session 15.2c decision #9b -- found by grid search against a real
# 2022-2024 held-out coverage backtest (SESSION_LOG.md Session 15.2c),
# NOT re-measured by this fitter every run (the backtest itself is a
# throwaway probe, not shipped pipeline code). Re-run that backtest
# methodology if r or team_shock's own inputs change materially enough
# that this constant's validity should be re-checked.
REDISTRIBUTION_SHOCK_SCALE = 0.70

# Ratio in [0,1] clipping for the efficiency CV fit -- guards against a
# divide-by-near-zero producing a 40x ratio that dominates an SD.
RATIO_CLIP = (0.0, 6.0)


def load_history(seasons: list) -> pd.DataFrame:
    frames = []
    for s in seasons:
        path = DATA_DIR / f"weekly_stats_{s}.parquet"
        if not path.exists():
            raise SystemExit(
                f"{path} not found. Run ingest_historical.py --season {s} first "
                f"(Session 1.2). Not silently skipping a season -- the fit's "
                f"provenance has to match what it claims.")
        frames.append(pd.read_parquet(path))
    df = pd.concat(frames, ignore_index=True)
    season_type_col = "season_type" if "season_type" in df.columns else "game_type"
    df = df[(df[season_type_col] == "REG") & (df["position"].isin(POSITIONS))].copy()
    num = df.select_dtypes(include=[np.number]).columns
    df[num] = df[num].fillna(0.0)
    return df


def fit_volume_dispersion(df: pd.DataFrame, pos: str, vol_stat: str) -> dict:
    """Decision #2 + #4: method-of-moments NB r, zero-volume weeks kept."""
    d = df[df["position"] == pos]
    g = d.groupby(["player_id", "season"])[vol_stat].agg(["mean", "var", "count"])
    g = g[(g["count"] >= MIN_GAMES) & (g["mean"] > 0.5)]
    if len(g) < MIN_GROUPS:
        raise SystemExit(
            f"fit_statline_variance: only {len(g)} qualifying player-seasons for "
            f"{pos}/{vol_stat} (need {MIN_GROUPS}). Decision #5 -- refusing to "
            f"ship a dispersion constant fit on this little data. Add seasons.")
    excess = (g["var"] - g["mean"]).clip(lower=0.0)
    den = float(excess.sum())
    r = float((g["mean"] ** 2).sum() / den) if den > 0 else 1e6
    return {"r": round(r, 4), "n_player_seasons": int(len(g)),
            "mean_volume": round(float(g["mean"].mean()), 3)}


def fit_efficiency(df: pd.DataFrame, pos: str, vol_stat: str, yd_stat: str,
                   td_stat: str) -> dict:
    """Position-mean rates, yards CV, and the yards<->TD correlation."""
    d = df[df["position"] == pos]

    vol_total = float(d[vol_stat].sum())
    if vol_total <= 0:
        raise SystemExit(f"fit_statline_variance: zero total {vol_stat} for {pos}.")
    yd_rate = float(d[yd_stat].sum() / vol_total)
    td_rate = float(d[td_stat].sum() / vol_total)

    # Decision #4: efficiency fit on rows with real volume only.
    used = d[d[vol_stat] > 0].copy()
    own = used.groupby(["player_id", "season"]).agg(
        yd_sum=(yd_stat, "sum"), vol_sum=(vol_stat, "sum"), n=(yd_stat, "size"))
    own = own[own["n"] >= MIN_GAMES]
    own["own_rate"] = own["yd_sum"] / own["vol_sum"].replace(0, np.nan)
    m = used.merge(own[["own_rate"]], left_on=["player_id", "season"],
                   right_index=True, how="inner")
    if len(m) < MIN_EFF_ROWS:
        raise SystemExit(
            f"fit_statline_variance: only {len(m)} usable rows for the "
            f"{pos}/{yd_stat} efficiency fit (need {MIN_EFF_ROWS}). Decision #5.")
    expected = m[vol_stat] * m["own_rate"]
    ratio = (m[yd_stat] / expected.replace(0, np.nan)).dropna()
    ratio = ratio[(ratio > RATIO_CLIP[0]) & (ratio < RATIO_CLIP[1])]
    yd_cv = float(ratio.std())

    # Within-player yards<->TD correlation, player-season means removed.
    cd = d.copy()
    cnt = cd.groupby(["player_id", "season"])["week"].transform("size")
    cd = cd[cnt >= MIN_GAMES]
    yd_dev = cd[yd_stat] - cd.groupby(["player_id", "season"])[yd_stat].transform("mean")
    td_dev = cd[td_stat] - cd.groupby(["player_id", "season"])[td_stat].transform("mean")
    corr = float(yd_dev.corr(td_dev))

    return {
        "yards_per_opportunity": round(yd_rate, 5),
        "td_per_opportunity": round(td_rate, 5),
        "yards_cv": round(yd_cv, 4),
        "yards_td_corr_target": round(corr, 4),
        "n_efficiency_rows": int(len(ratio)),
        "n_corr_rows": int(len(cd)),
    }


def fit_int_rate(df: pd.DataFrame) -> float:
    d = df[df["position"] == "QB"]
    return round(float(d["passing_interceptions"].sum() / max(d["attempts"].sum(), 1.0)), 5)


def fit_catch_rate(df: pd.DataFrame, pos: str) -> float:
    d = df[df["position"] == pos]
    return round(float(d["receptions"].sum() / max(d["targets"].sum(), 1.0)), 5)


def fit_fumble_rate(df: pd.DataFrame, pos: str) -> float:
    """Lost fumbles per touch (carries + receptions). Small but DK/FD both
    price it, and it is one of the few negative terms a skill player has."""
    d = df[df["position"] == pos]
    cols = [c for c in ("sack_fumbles_lost", "rushing_fumbles_lost",
                        "receiving_fumbles_lost") if c in d.columns]
    fum = float(d[cols].sum().sum()) if cols else 0.0
    touches = float((d["carries"] + d["receptions"]).sum())
    return round(fum / max(touches, 1.0), 6)


def calibrate_latent_sd(cv: float, corr_target: float, td_rate: float,
                        mean_volume: float, seed: int = 12345) -> float:
    """Decision #6: solve for the latent game-quality SD that reproduces the
    MEASURED yards<->TD correlation under the consumer's own draw scheme.

    Deliberately imports the consumer so the calibration is against the code
    that will actually run, not a second copy of it -- the project's own
    lesson that a reimplementation is where the bug hides.
    """
    import statline_model

    lo, hi = 0.0, 3.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        got = statline_model._simulated_yards_td_corr(
            latent_sd=mid, yards_cv=cv, td_rate=td_rate,
            mean_volume=mean_volume, seed=seed)
        if got < corr_target:
            lo = mid
        else:
            hi = mid
    return round(0.5 * (lo + hi), 4)


def _net_gamma_cv(cv_total: float, latent_sd: float) -> float:
    """2026-09-26 double-count fix. The simulator draws yards ~ Gamma(mean =
    vol*rate*L, cv_g) with L ~ Gamma(mean 1, sd latent_sd), so the TOTAL CV of
    yards/(vol*rate) is sqrt((1+cv_g^2)(1+latent_sd^2) - 1). The measured
    ratio CV is that total, so the gamma's own cv must be net of the latent."""
    v = (1.0 + cv_total ** 2) / (1.0 + latent_sd ** 2) - 1.0
    return float(np.sqrt(max(v, 1e-6)))


def fit_yards_net(df: pd.DataFrame, pos: str, vol_stat: str, yd_stat: str,
                  td_stat: str, cv_weight: str = "volume") -> dict:
    """Measured TOTAL yards-ratio CV (optionally volume-weighted: the ratio's CV
    falls ~1/sqrt(volume), and the constant-cv simulator should match the
    players who carry real volume) + the within-player yards<->TD corr."""
    eff = fit_efficiency(df, pos, vol_stat, yd_stat, td_stat)
    if cv_weight == "volume":
        d = df[(df["position"] == pos) & (df[vol_stat] > 0)]
        own = d.groupby(["player_id", "season"]).agg(
            y=(yd_stat, "sum"), v=(vol_stat, "sum"), n=(yd_stat, "size"))
        own = own[own["n"] >= MIN_GAMES]
        own["own_rate"] = own["y"] / own["v"].replace(0, np.nan)
        m = d.merge(own[["own_rate"]], left_on=["player_id", "season"],
                    right_index=True, how="inner")
        ratio = m[yd_stat] / (m[vol_stat] * m["own_rate"]).replace(0, np.nan)
        ok = ratio.notna() & (ratio > RATIO_CLIP[0]) & (ratio < RATIO_CLIP[1])
        eff["yards_cv_total"] = round(float(np.sqrt(np.average(
            (ratio[ok] - 1.0) ** 2, weights=m.loc[ok, vol_stat]))), 4)
    else:
        eff["yards_cv_total"] = eff["yards_cv"]
    eff["yards_cv_total_unweighted"] = eff.pop("yards_cv")
    return eff


def calibrate_latent_sd_net(cv_total: float, corr_target: float, td_rate: float,
                            mean_volume: float, seed: int = 12345) -> tuple:
    """Decision #6 re-done net of the latent: bisect latent_sd so the simulated
    yards<->TD corr hits the target WHILE the total yards CV given volume stays
    at cv_total (cv_g = _net_gamma_cv(cv_total, latent_sd)). latent_sd is capped
    just below cv_total (cv_g -> 0); if the target is unreachable the cap is used
    and flagged."""
    import statline_model

    def corr(ls):
        return statline_model._simulated_yards_td_corr(
            latent_sd=ls, yards_cv=_net_gamma_cv(cv_total, ls), td_rate=td_rate,
            mean_volume=mean_volume, seed=seed)
    hi_cap = 0.98 * cv_total
    if corr(hi_cap) < corr_target:
        return round(hi_cap, 4), round(_net_gamma_cv(cv_total, hi_cap), 4), True
    lo, hi = 0.0, hi_cap
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if corr(mid) < corr_target:
            lo = mid
        else:
            hi = mid
    ls = round(0.5 * (lo + hi), 4)
    return ls, round(_net_gamma_cv(cv_total, ls), 4), False


def refit_yards_net(base: dict, seasons: list, cv_weight: str = "volume") -> dict:
    """2026-09-26: copy `base` and replace ONLY yards_cv / latent_sd (and the
    corr target) with the net-of-latent parameterisation fit on `seasons`.
    Volume r, rates (the MEAN-relevant shrinkage targets), team_shock etc. are
    untouched, so the change is variance-only."""
    import copy
    out = copy.deepcopy(base)
    df = load_history(seasons)
    print(f"Net-of-latent yards refit on {len(df):,} REG player-weeks, seasons "
          f"{min(seasons)}-{max(seasons)}, cv_weight={cv_weight}.")
    for pos in POSITIONS:
        for name, vol_stat, yd_stat, td_stat in COMPONENTS[pos]:
            c = out["positions"][pos]["components"][name]
            e = fit_yards_net(df, pos, vol_stat, yd_stat, td_stat, cv_weight)
            ls, cvg, capped = calibrate_latent_sd_net(
                e["yards_cv_total"], e["yards_td_corr_target"],
                c["td_per_opportunity"], c["mean_volume"])
            c["legacy_yards_cv"], c["legacy_latent_sd"] = c["yards_cv"], c["latent_sd"]
            c["legacy_yards_td_corr_target"] = c["yards_td_corr_target"]
            c.update(yards_cv=cvg, latent_sd=ls, yards_cv_total=e["yards_cv_total"],
                     yards_cv_total_unweighted=e["yards_cv_total_unweighted"],
                     yards_td_corr_target=e["yards_td_corr_target"],
                     latent_capped=bool(capped))
            print(f"  {pos:>3} {name:<5} cv_total={e['yards_cv_total']:.3f} "
                  f"corr={e['yards_td_corr_target']:.3f} -> latent_sd={ls:.3f} "
                  f"gamma cv={cvg:.3f}{' (CAPPED)' if capped else ''}  "
                  f"[legacy cv {c['legacy_yards_cv']:.3f} latent {c['legacy_latent_sd']:.3f}]")
    out["yards_parameterisation"] = {
        "mode": "net_of_latent", "fit_date": date.today().isoformat(),
        "seasons": sorted(int(s) for s in seasons), "cv_weight": cv_weight,
        "note": ("2026-09-26 double-count fix: yards_cv is now the gamma's OWN cv, net "
                 "of the shared latent, so total CV of yards/(vol*rate) = yards_cv_total. "
                 "legacy_* keep the old values. Only yards_cv/latent_sd/corr target changed; "
                 "r, rates and team_shock are the base artifact's (means unaffected).")}
    return out


def fit_team_shock(seasons: list, team_volume_path=None) -> tuple:
    """Returns (team_shock_dict, conditional_r_dict) -- the second element
    is Session 15.2c's {(position, comp): r} decomposition, consumed by
    fit() to overwrite each non-excluded pair's live r in `positions`. See
    decisions #8/#9 above for the full reasoning.

    Session 15.2b. Two real, measured numbers per component (pass, rush,
    recv), both needed to give the simulator a real team-level volume shock
    instead of treating a team's predicted total as a known constant:

    * residual_sd -- how far off fit_volume_prior.py's own team-total
      prediction typically lands on a real week, in the same units as the
      stat itself (attempts/carries/targets). This is NOT what gets drawn
      straight into a player's own mean -- see pass_through_slope.

    * pass_through_slope -- of a real team-week's total-volume surprise
      (actual minus predicted), how much of it a given player's own volume
      actually absorbs, proportional to his own historical share of the
      team. Measured by regressing each player's own (actual - expected)
      volume against (team's actual - team's predicted) x that player's
      own historical share, through the origin, on real weekly stats. A
      slope of 1 would mean a player's volume moves in perfect lockstep
      with his expected share of a team-level surprise; 0 would mean
      team-level surprises never reach individual players at all -- which
      is what the simulator has implicitly assumed until now (every
      player's volume drawn fully independently; see statline_model.py's
      decision #15).

    THESE ARE KEPT SEPARATE, NOT MULTIPLIED TOGETHER HERE, because the
    slope is not the same across components and folding it into a single
    scalar would hide a real football fact: measured on 2021 (t = 8-20 in
    every component, real and not close to zero), rush's slope is 0.51 but
    pass's is 0.76 and recv's is 0.84. Rush volume gets redistributed
    between backs in ways a share-of-history number does not anticipate
    (which back the coaches actually leaned on that specific game); pass
    attempts and targets concentrate predictably on the same few players.
    A single shared constant here would have understated the pass/recv
    shock by roughly a third and this is exactly the kind of thing decision
    #2's "measured, not assumed" rule exists to catch.

    Needs a fitted team-volume artifact to compute real residuals against
    (fit_volume_prior.py must run first -- a new ordering dependency
    between these two fitters that did not exist before this session).
    Reads data/volume_prior_dk.json specifically: team_volume's own
    coefficients come out numerically identical for dk and fd, since real
    NFL game stats and Vegas lines do not know what site is being played,
    so the DK file is exactly as valid as the FD one here and picking one
    arbitrarily beats reading both and asserting they agree.
    """
    import fit_volume_prior as fvp
    import volume_prior as vp

    tv_path = Path(team_volume_path) if team_volume_path else DATA_DIR / "volume_prior_dk.json"
    if not tv_path.exists():
        raise SystemExit(
            f"{tv_path} not found. fit_team_shock() needs a fitted team-volume "
            f"artifact to compute real prediction residuals against -- run "
            f"fit_volume_prior.py (either site) before fit_statline_variance.py.")
    with open(tv_path) as f:
        team_volume = json.load(f)["team_volume"]

    panel = fvp.build_team_panel("dk", seasons)
    stats = load_history(seasons)
    out = {}
    conditional_r = {}  # Session 15.2c: {(position, comp): r_new}

    for comp in ("pass", "rush", "recv"):
        needed = [f"hist_{comp}", "implied_total", "team_spread"]
        if comp == "rush":
            needed.append("opp_rush_allowed")
        p = panel.dropna(subset=needed).copy()

        kwargs = {}
        if comp == "rush":
            kwargs["opp_defense_allowed"] = p["opp_rush_allowed"].to_numpy(float)
        pred = vp.predict_team_volume(
            {"team_volume": team_volume}, comp,
            p["implied_total"].to_numpy(float), p["team_spread"].to_numpy(float),
            history_volume=p[f"hist_{comp}"].to_numpy(float), **kwargs)
        p["team_pred"] = pred
        p["team_residual"] = p[f"real_{comp}"] - p["team_pred"]

        if len(p) < MIN_GROUPS:
            raise SystemExit(
                f"fit_team_shock: only {len(p)} team-weeks for {comp} (need "
                f"{MIN_GROUPS}). Decision #5's standing rule -- refusing to "
                f"ship a shock SD fit on this little.")
        residual_sd = float(p["team_residual"].std())

        # Player-level pass-through regression. Real team code (not
        # team_norm) throughout, matching load_history()'s own key space --
        # see build_team_panel()'s own `team` column, added in this same
        # session specifically so this join would not need a second,
        # divergent copy of the panel-building logic.
        col = TEAM_SHOCK_STAT_COL[comp]
        pred_lookup = p.set_index(["season", "week", "team"])[["team_pred", "team_residual"]]
        d = stats[stats["position"].isin(POSITIONS)]

        rows = []
        for (season, team), g in d.groupby(["season", "team"]):
            g = g.sort_values("week")
            weeks = sorted(g["week"].unique().tolist())
            # Session 15.2b perf note: team_hist and each player's own
            # recency-weighted history are the SAME number for every
            # player sharing a (season, team, week) -- computed once per
            # team-week here, not once per player as an earlier draft of
            # this loop did, which was redoing identical work ~10x per
            # week for no reason and made a full-history refit
            # impractically slow.
            weekly_team_totals = g.groupby("week")[col].sum().sort_index()
            player_hist_by_week = {}  # week -> {player_id: recency-weighted own history}
            for week in weeks:
                prior = g[g["week"] < week]
                phist = {}
                for pid, pg in prior.groupby("player_id"):
                    phist[pid] = _recency_weighted(
                        pg.sort_values("week")[col].to_numpy(float))
                player_hist_by_week[week] = phist

            for week in weeks:
                key = (season, week, team)
                if key not in pred_lookup.index:
                    continue
                team_pred, team_residual = pred_lookup.loc[key]
                team_hist = _recency_weighted(
                    weekly_team_totals[weekly_team_totals.index < week].to_numpy(float))
                if not np.isfinite(team_hist) or team_hist <= 0:
                    continue
                week_rows = g.loc[g["week"] == week, ["player_id", "position", col]]
                this_week = dict(zip(week_rows["player_id"], week_rows[col]))
                this_week_pos = dict(zip(week_rows["player_id"], week_rows["position"]))
                for pid, own_hist in player_hist_by_week[week].items():
                    if not np.isfinite(own_hist) or own_hist <= 0.5:
                        continue
                    hist_share = own_hist / team_hist
                    if not (0.0 <= hist_share <= 1.5):
                        continue
                    player_actual = float(this_week.get(pid, 0.0))
                    player_expected = hist_share * team_pred
                    # Session 15.2c: position/player_id/season/actual kept
                    # (not just x, y) so the SAME regression basis can be
                    # reused below to decompose r -- see decision #8.
                    rows.append({"x": team_residual * hist_share,
                                "y": player_actual - player_expected,
                                "position": this_week_pos.get(pid),
                                "player_id": pid, "season": season,
                                "actual": player_actual})

        reg = pd.DataFrame(rows)
        if len(reg) < MIN_GROUPS:
            raise SystemExit(
                f"fit_team_shock: only {len(reg)} player-weeks for {comp}'s "
                f"pass-through regression (need {MIN_GROUPS}). Refusing to "
                f"ship a slope fit on this little.")
        x, y = reg["x"].to_numpy(float), reg["y"].to_numpy(float)
        slope = float(np.sum(x * y) / np.sum(x * x))
        resid = y - slope * x
        se = float(np.sqrt(np.sum(resid ** 2) / (len(x) - 1)) / np.sqrt(np.sum(x ** 2)))
        t = slope / se if se > 0 else 0.0

        out[comp] = {"residual_sd": round(residual_sd, 4),
                    "pass_through_slope": round(slope, 4),
                    "pass_through_t": round(t, 3),
                    "n_team_weeks": int(len(p)),
                    "n_player_weeks": int(len(reg))}
        print(f"  team_shock {comp:<5} residual_sd={residual_sd:6.2f}  "
              f"pass_through_slope={slope:.4f} (t={t:.2f}, n={len(reg)})")

        # Session 15.2c decision #8: decompose r per POSITION for this
        # component (the regression above is pooled across positions,
        # but r is consumed per position -- see decision #8's own text
        # for why these need different grains). `adjusted_actual` removes
        # exactly the team-level piece (slope * x) that the regression
        # above already fit, leaving only the within-team redistribution
        # variance for r to target -- same MIN_GAMES gate, same
        # method-of-moments formula fit_volume_dispersion() uses, so the
        # two r's are directly comparable and only ever differ in which
        # series' variance goes in.
        for pos, comps_for_pos in COMPONENTS.items():
            if comp not in [c for c, *_ in comps_for_pos]:
                continue
            if (pos, comp) in EXCLUDED_SHOCK_PAIRS:
                continue
            sub = reg[reg["position"] == pos].copy()
            if sub.empty:
                continue
            sub["adjusted_actual"] = sub["actual"] - slope * sub["x"]
            g2 = sub.groupby(["player_id", "season"]).agg(
                mean=("actual", "mean"), var_adj=("adjusted_actual", "var"),
                n=("actual", "count"))
            g2 = g2[(g2["n"] >= MIN_GAMES) & (g2["mean"] > 0.5)]
            if len(g2) < MIN_GROUPS:
                raise SystemExit(
                    f"fit_team_shock: only {len(g2)} qualifying player-seasons "
                    f"for {pos}/{comp}'s conditional r (need {MIN_GROUPS}). "
                    f"Decision #5's standing rule -- refusing to ship a "
                    f"dispersion constant fit on this little data.")
            excess = (g2["var_adj"] - g2["mean"]).clip(lower=0.0)
            den = float(excess.sum())
            r_new = float((g2["mean"] ** 2).sum() / den) if den > 0 else 1e6
            conditional_r[(pos, comp)] = round(r_new, 4)
            print(f"    conditional r  {pos:>3} {comp:<5} -> {r_new:7.2f} "
                  f"(n_player_seasons={len(g2)})")

    out["excluded_pairs"] = [list(k) for k in sorted(EXCLUDED_SHOCK_PAIRS)]
    out["redistribution_shock_scale"] = REDISTRIBUTION_SHOCK_SCALE
    # Audit convenience only -- the live values actually consumed by
    # simulate() are positions[pos]["components"][comp]["r"], set by
    # fit()'s caller below. This is just a readable record, in one place,
    # of what this decomposition produced.
    out["conditional_r_reference"] = {f"{pos}/{comp}": r
                                      for (pos, comp), r in conditional_r.items()}
    return out, conditional_r

def fit(seasons: list, team_volume_path=None) -> dict:
    df = load_history(seasons)
    print(f"Fitting on {len(df):,} REG player-weeks, seasons {min(seasons)}-{max(seasons)}.")

    positions = {}
    for pos in POSITIONS:
        comps = {}
        for name, vol_stat, yd_stat, td_stat in COMPONENTS[pos]:
            vol = fit_volume_dispersion(df, pos, vol_stat)
            eff = fit_efficiency(df, pos, vol_stat, yd_stat, td_stat)
            latent_sd = calibrate_latent_sd(
                eff["yards_cv"], eff["yards_td_corr_target"],
                eff["td_per_opportunity"], vol["mean_volume"])
            comps[name] = {"volume_stat": vol_stat, **vol, **eff,
                           "latent_sd": latent_sd}
            print(f"  {pos:>3} {name:<5} r={vol['r']:7.2f}  "
                  f"yd/opp={eff['yards_per_opportunity']:6.3f}  "
                  f"td/opp={eff['td_per_opportunity']:.4f}  "
                  f"cv={eff['yards_cv']:.3f}  "
                  f"corr target={eff['yards_td_corr_target']:.3f} "
                  f"-> latent_sd={latent_sd:.3f}")
        entry = {"components": comps, "fumbles_lost_per_touch": fit_fumble_rate(df, pos)}
        if pos != "QB":
            entry["catch_rate"] = fit_catch_rate(df, pos)
        else:
            entry["catch_rate"] = fit_catch_rate(df, "QB")
            entry["int_per_attempt"] = fit_int_rate(df)
        positions[pos] = entry

    print("\nTeam-shock calibration (Session 15.2b/15.2c):")
    team_shock, conditional_r = fit_team_shock(seasons, team_volume_path)

    # Session 15.2c decision #8: replace each non-excluded pair's live r
    # with the team-shock-decomposed value (net of team-level variance).
    # The pre-decomposition value is kept under r_independent purely for
    # audit -- statline_model.simulate() only ever reads `r`. Excluded
    # pairs (WR/rush) are simply absent from conditional_r and keep
    # fit_volume_dispersion()'s own r untouched.
    print("\nApplying Session 15.2c conditional-r decomposition:")
    for (pos, comp), r_new in conditional_r.items():
        entry = positions[pos]["components"][comp]
        entry["r_independent"] = entry["r"]
        entry["r"] = r_new
        print(f"  {pos:>3} {comp:<5} r_independent={entry['r_independent']:7.2f} "
              f"-> r={r_new:7.2f}")

    return {
        "schema_version": SCHEMA_VERSION,
        "fit_date": date.today().isoformat(),
        "seasons": sorted(int(s) for s in seasons),
        "n_rows": int(len(df)),
        "min_games_per_player_season": MIN_GAMES,
        "notes": ("Site-agnostic by design (decision #1) -- a stat line is real "
                  "football; only scoring_rules.py is site-specific. Component "
                  "whitelist per position is decision #3; anything outside it is "
                  "never simulated. team_shock (Session 15.2b/15.2c) needs a "
                  "fitted team-volume artifact to exist first -- see "
                  "fit_team_shock()'s own docstring. Each non-excluded "
                  "position/component's live `r` is the Session 15.2c "
                  "conditional value (net of team-level variance, decision #8); "
                  "the pre-decomposition value is under r_independent. "
                  "team_shock.redistribution_shock_scale and .excluded_pairs "
                  "(decision #9) are read directly by statline_model.simulate() "
                  "-- see its own docstring."),
        "positions": positions,
        "team_shock": team_shock,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+",
                        default=list(range(2014, 2022)),
                        help="Seasons to pool. Default 2014-2021 (the window "
                             "where Session 10.0's salary+stats data both exist).")
    parser.add_argument("--out", default=None)
    parser.add_argument("--team-volume-prior", default=None,
                        help="Volume-prior artifact whose team_volume the team-shock fit uses "
                             "(default data/volume_prior_dk.json). For leave-one-season-out refits.")
    parser.add_argument("--net-latent-from", default=None,
                        help="2026-09-26 double-count fix: copy this base artifact and refit ONLY "
                             "yards_cv/latent_sd net of the latent on --seasons (variance-only).")
    parser.add_argument("--cv-weight", default="volume", choices=["volume", "none"])
    args = parser.parse_args()

    if args.net_latent_from:
        artifact = refit_yards_net(json.loads(Path(args.net_latent_from).read_text()),
                                   args.seasons, args.cv_weight)
    else:
        artifact = fit(args.seasons, args.team_volume_prior)
    out_path = Path(args.out) if args.out else ARTIFACT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1))

    print(f"\nWrote {out_path} (schema_version {SCHEMA_VERSION}).")
    print("Site-agnostic -- both DK and FD read this same file (decision #1).")
