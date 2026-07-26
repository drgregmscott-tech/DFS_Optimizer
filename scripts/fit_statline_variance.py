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

Usage:
  python3 scripts/fit_statline_variance.py --seasons 2014 2015 2016 2017 2018 2019 2020 2021
"""

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

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

    return {
        "schema_version": SCHEMA_VERSION,
        "fit_date": date.today().isoformat(),
        "seasons": sorted(int(s) for s in seasons),
        "n_rows": int(len(df)),
        "min_games_per_player_season": MIN_GAMES,
        "notes": ("Site-agnostic by design (decision #1) -- a stat line is real "
                  "football; only scoring_rules.py is site-specific. Component "
                  "whitelist per position is decision #3; anything outside it is "
                  "never simulated."),
        "positions": positions,
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
