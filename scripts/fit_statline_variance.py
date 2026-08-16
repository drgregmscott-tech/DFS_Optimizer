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


def fit_team_shock(seasons: list) -> dict:
    """Session 15.2b. Two real, measured numbers per component (pass, rush,
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

    tv_path = DATA_DIR / "volume_prior_dk.json"
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
                this_week = dict(zip(g.loc[g["week"] == week, "player_id"],
                                    g.loc[g["week"] == week, col]))
                for pid, own_hist in player_hist_by_week[week].items():
                    if not np.isfinite(own_hist) or own_hist <= 0.5:
                        continue
                    hist_share = own_hist / team_hist
                    if not (0.0 <= hist_share <= 1.5):
                        continue
                    player_actual = float(this_week.get(pid, 0.0))
                    player_expected = hist_share * team_pred
                    rows.append({"x": team_residual * hist_share,
                                "y": player_actual - player_expected})

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

    return out


def fit(seasons: list) -> dict:
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

    print("\nTeam-shock calibration (Session 15.2b):")
    team_shock = fit_team_shock(seasons)

    return {
        "schema_version": SCHEMA_VERSION,
        "fit_date": date.today().isoformat(),
        "seasons": sorted(int(s) for s in seasons),
        "n_rows": int(len(df)),
        "min_games_per_player_season": MIN_GAMES,
        "notes": ("Site-agnostic by design (decision #1) -- a stat line is real "
                  "football; only scoring_rules.py is site-specific. Component "
                  "whitelist per position is decision #3; anything outside it is "
                  "never simulated. team_shock (Session 15.2b) needs a fitted "
                  "team-volume artifact to exist first -- see fit_team_shock()'s "
                  "own docstring."),
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
    args = parser.parse_args()

    artifact = fit(args.seasons)
    out_path = Path(args.out) if args.out else ARTIFACT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1))

    print(f"\nWrote {out_path} (schema_version {SCHEMA_VERSION}).")
    print("Site-agnostic -- both DK and FD read this same file (decision #1).")
