"""
probe_statline_priors.py
========================

Session 10.3b -- the PRE-TEST, run BEFORE any of this card's four build items
are implemented.

This script builds nothing and ships nothing. It answers, on real data already
on disk, the four questions Session 10.3b's card assumes the answers to. Both
of the two sessions before it (10.3a, 10.4) tested their own card's premises
first and both times something came back FALSE and changed the build -- 10.3a
found its core bet was within 0.02 MAE of a null before writing a line, and
10.4 found two of its stated premises wrong. This is that step for 10.3b.

It is deliberately a separate, throwaway-able script rather than flags on the
real fitter, because a probe that lives inside the production path is a probe
that eventually gets shipped by accident.

  ---------------------------------------------------------------------
  THE FOUR QUESTIONS, and what a FALSE answer would change
  ---------------------------------------------------------------------

  A. DOES PRICE PREDICT VOLUME SHARE BETTER THAN OWN HISTORY DOES, AND IS
     ITS ERROR DECORRELATED FROM HISTORY'S?

     The card says to fit `E[target_share | salary, position]` and use it as
     a prior on the stat-line VOLUME inputs. That is only worth building if
     price carries information history does not.

     Phase 10's own design intro is explicit that "blending helps in
     proportion to error DECORRELATION, not component count." Session 10.3a
     then measured a real instance of this: a volume x efficiency model
     against points-averaging came in at 5.20 vs 5.18 MAE with residual
     correlation 0.965 -- almost perfectly redundant, and the blend was a
     null. Salary and usage history could easily be the same story, because
     a site prices a player largely off his recent usage.

     A FALSE answer here (price no better, errors correlated > ~0.9) kills
     build item 1 as a mid-season component and reduces it to a pure
     cold-start mechanism, which is item 2 and is already proven.

  B. DOES VEGAS ADD ANYTHING TO TEAM VOLUME OVER TEAM HISTORY ALONE?

     Build item 4 replaces statline_model.py's team-history volume
     prediction with a Vegas-anchored one. Session 10.4 is the caution here:
     it measured Vegas as an almost perfectly calibrated points-allowed
     forecast that still explained only ~15% of the variance, and it found
     wind null on EVERY volume channel because books price the forecast into
     the line. Team pass attempts may be the same -- and the theory argues
     SPREAD should matter more than TOTAL for volume (favourites run out the
     clock, trailing teams throw), which is not what "Vegas-anchored team
     volume" implies if it is read as the implied total.

     This probe tests total and spread SEPARATELY and out-of-sample. A null
     kills item 4, which is the largest and least-motivated of the four.

  C. IS A WEEK-1 TEAM-VOLUME PREDICTION SANE ENOUGH TO BUILD ON?

     This is the structural finding that reordered this card's build.
     Cold-starting the stat-line engine is NOT just "give a zero-history
     player a share." In week 1:
       - statline_model.load_history() returns an empty frame, so
       - team_volume_history() returns an EMPTY DataFrame, so
       - reconciliation cannot run at all, and
       - _participation() returns 0.0 for every player, which would multiply
         any price-predicted volume straight back to zero.
     A player share is meaningless without a team total to take a share OF.
     So item 2 (cold start) DEPENDS on item 4 (a team-volume source that is
     not this season's history) -- they are not independent bullets.

     This probe measures the only two candidate week-1 sources against the
     realized week-1 team volumes: prior-season carryover (the mechanism
     dst_model.py's decision #15 already uses and Session 10.4's addendum
     already hardened), and prior-season carryover tilted by that week's
     real Vegas line.

  D. WHAT, CONCRETELY, IS THE ROLE-CHANGE FLAG -- AND WHICH WAY DOES IT
     POINT?

     The card lists "role-change flag" with no mechanism, and the ROADMAP's
     Phase 10 design intro contains an instruction that may be backwards for
     this pipeline: "suppress the salary anchor's weight when a role change
     is flagged -- a stale price is exactly the value spot we're trying to
     beat."

     That assumes the PRICE is the stale signal. On a weekly DFS slate the
     site reprices every player every week with real money behind it, while
     our usage history is by construction weeks old -- so the price is
     plausibly the FRESH signal and the history is the stale one, i.e. the
     exact opposite instruction. Session 10.3a's two catalogued failures are
     both this case: Zach Wilson (NYJ 2021 wk13) and Cam Newton (CAR 2021
     wk15) both returned to a starting role that no backward-looking share
     could see.

     The only role-change signal that can be MEASURED on the 2014-2021
     bootstrap is a price-vs-history divergence -- a depth chart or an injury
     report is live-only data this project has no historical archive of, so
     a flag built on those could not be backtested at all. This probe tests
     whether divergence predicts the part of realized share that history
     misses. If it does, the flag is defined, backtestable and free.

  ---------------------------------------------------------------------
  WHAT THIS SCRIPT REUSES RATHER THAN REIMPLEMENTS
  ---------------------------------------------------------------------

  Every number here has to be comparable to what the real engine would
  produce, so the history side is computed with statline_model.py's OWN
  primitives (RECENCY_WEIGHTS, _recency_weighted, _participation,
  team_weeks_played) and the isotonic side with fit_salary_anchor.py's OWN
  machinery (isotonic_pava, _add_top_endpoint_knot, interp_knots). A probe
  that reimplements the thing it is measuring measures the reimplementation.

  The one thing it does mirror is load_history()'s per-week slicing, purely
  for speed (136 parquet reads otherwise). `--verify-mirror` asserts the
  mirror is byte-identical to the real function on a sample week and is ON by
  default, because a silently-diverged mirror would invalidate everything
  below.

  ---------------------------------------------------------------------
  Usage
  ---------------------------------------------------------------------

    python3 scripts/probe_statline_priors.py --site dk

  Defaults reproduce Session 10.3a's holdout split (fit 2014-17, measure
  2018-21) so a positive result here is out-of-sample by construction.
  10.3a's transferable lesson was that fitting on the season then measured
  inflated its effect roughly threefold -- do not run this with overlapping
  windows and then quote the numbers.

    python3 scripts/probe_statline_priors.py --site dk --probes A D
    python3 scripts/probe_statline_priors.py --site dk --dump-panel

Output: printed only. Nothing is written to data/ -- no artifact from a probe
should ever be loadable by the production path.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import statline_model  # noqa: E402
import statlite  # noqa: E402
from fit_salary_anchor import (  # noqa: E402
    _add_top_endpoint_knot,
    interp_knots,
    isotonic_pava,
)
from fit_statline_variance import COMPONENTS  # noqa: E402
from ingest_salaries import normalize_team  # noqa: E402

GAMES_CACHE = DATA_DIR / "nflverse_games.csv"

# (component -> the weekly_stats column holding that component's VOLUME).
# Mirrors statline_model._COMPONENT_STATS' volume slot and COMPONENTS' second
# tuple element; asserted against COMPONENTS at import so the two cannot drift.
VOLUME_COL = {"pass": "attempts", "rush": "carries", "recv": "targets"}
for _pos, _comps in COMPONENTS.items():
    for _name, _vol, _yd, _td in _comps:
        assert VOLUME_COL[_name] == _vol, (
            f"VOLUME_COL[{_name}] disagrees with fit_statline_variance.COMPONENTS "
            f"({VOLUME_COL[_name]} vs {_vol}). The probe would measure a different "
            f"quantity than the engine uses.")

# Binning for the share curve. Shares are a much cheaper quantity to bin than
# points (every player-week has one, and it is bounded), so a lower row floor
# than fit_salary_anchor's 200 is defensible -- but it is still ARBITRARY and
# flagged, exactly like every other unfit constant in this project.
SHARE_N_BINS = 20
SHARE_MIN_BIN_ROWS = 150

# Games-played buckets for probe A's breakdown. The whole cold-start argument
# is that price should win at the LEFT of this table and lose at the right;
# printing it as one pooled number would hide precisely that.
GP_BUCKETS = [(0, 1), (2, 3), (4, 6), (7, 99)]

# Probe D's two catalogued cases, from Session 10.3a's reconciliation work.
CATALOGUED_CASES = [
    (2021, 13, "NYJ", "Zach Wilson", "pass"),
    (2021, 15, "CAR", "Cam Newton", "pass"),
]

_HIST_CACHE = {}


# ---------------------------------------------------------------------------
# History loading -- a cached MIRROR of statline_model.load_history()
# ---------------------------------------------------------------------------

def _season_history(season: int) -> pd.DataFrame:
    """Full REG-season weekly stats, loaded once per season."""
    if season in _HIST_CACHE:
        return _HIST_CACHE[season]
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Run ingest_historical.py --season {season} "
            f"(Session 1.2). Not skipping it silently -- a missing season "
            f"would quietly change which window this probe reports.")
    df = pd.read_parquet(path)
    col = "season_type" if "season_type" in df.columns else "game_type"
    df = df[df[col] == "REG"].copy()
    num = df.select_dtypes(include=[np.number]).columns
    df[num] = df[num].fillna(0.0)
    _HIST_CACHE[season] = df
    return df


def hist_before(season: int, week: int) -> pd.DataFrame:
    """Same contract as statline_model.load_history(): REG weeks STRICTLY
    before `week`. Verified identical by verify_mirror()."""
    df = _season_history(season)
    return df[df["week"] < week].copy()


def verify_mirror(season: int, week: int) -> None:
    """Fail loud if the cached mirror has drifted from the real loader.

    Every history-side number in this probe comes from the mirror. If it
    diverged -- a different season_type filter, a different fillna -- every
    comparison below would be against a straw man and the probe would look
    like it was measuring the engine when it was not.
    """
    real = statline_model.load_history(season, week)
    mine = hist_before(season, week)
    if len(real) != len(mine):
        raise SystemExit(
            f"Mirror check FAILED: statline_model.load_history({season},{week}) "
            f"returned {len(real)} rows, this script's hist_before() returned "
            f"{len(mine)}. The cached loader has drifted from the real one; "
            f"fix hist_before() before trusting anything this probe prints.")
    a = real.sort_values(["player_id", "week"]).reset_index(drop=True)
    b = mine.sort_values(["player_id", "week"]).reset_index(drop=True)
    for c in ("attempts", "carries", "targets"):
        if c in a.columns and not np.allclose(a[c].to_numpy(float),
                                              b[c].to_numpy(float)):
            raise SystemExit(
                f"Mirror check FAILED on column '{c}' for {season} wk{week}.")
    print(f"  Mirror check OK ({season} wk{week}: {len(real)} rows identical "
          f"to statline_model.load_history).")


# ---------------------------------------------------------------------------
# Panel construction
# ---------------------------------------------------------------------------

def available_weeks(site: str, season: int) -> list:
    """Weeks that have a MATCHED salary file (Session 10.0's bootstrap).
    Derived from what is on disk rather than assumed to be 1..17, so a
    partially-materialized season reports honestly instead of erroring."""
    weeks = []
    for p in sorted(DATA_DIR.glob(f"salaries_{site}_rotoguru_{season}_wk*.csv")):
        stem = p.stem.rsplit("_wk", 1)[-1]
        if stem.isdigit():
            weeks.append(int(stem))
    return sorted(weeks)


def load_salary_week(site: str, season: int, week: int) -> pd.DataFrame:
    path = DATA_DIR / f"salaries_{site}_rotoguru_{season}_wk{week}.csv"
    df = pd.read_csv(path, dtype={"player_id": str})
    need = {"player_id", "name", "salary", "normalized_team", "position_upper"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path.name} is missing {sorted(missing)}. ingest_salaries.py's "
            f"schema changed -- not guessing at column names.")
    df = df[df["player_id"].notna()].copy()
    df["salary"] = pd.to_numeric(df["salary"], errors="coerce")
    # Same rule as fit_salary_anchor decision #2: an unpurchasable price
    # carries no market information, which is the only thing being fit.
    df = df[df["salary"].notna() & (df["salary"] > 0)]
    return df[["player_id", "name", "salary", "normalized_team", "position_upper"]]
    # NOTE: caller renames `name` -> `player_name` before itertuples(). A
    # column literally called "name" is legal in a namedtuple but sits one
    # typo away from pandas' own `.name` attribute semantics, and this project
    # has lost a day to exactly that class of silent wrong-column read.


def team_totals(week_stats: pd.DataFrame) -> pd.DataFrame:
    """Realized team volume for one week, over EVERY player, not just the
    slate pool -- the denominator of a share has to be the whole team or the
    share is not a share."""
    g = week_stats.groupby("team")[["attempts", "carries", "targets"]].sum()
    return g.rename(columns={"attempts": "team_pass", "carries": "team_rush",
                             "targets": "team_recv"})


def build_panel(site: str, seasons: list) -> pd.DataFrame:
    """One row per (season, week, player, component).

    Carries, for each row:
      salary, position                 -- the price side
      realized_share                   -- the target
      hist_share                       -- what statline_model's own volume
                                          model implies, computed with its
                                          primitives
      games_played, participation      -- the cold-start / role-change axes
    """
    rows = []
    for season in seasons:
        weeks = available_weeks(site, season)
        if not weeks:
            print(f"  {season}: no matched salary files -- skipped.")
            continue
        season_stats = _season_history(season)
        for week in weeks:
            wk_stats = season_stats[season_stats["week"] == week]
            if wk_stats.empty:
                continue
            tt = team_totals(wk_stats)
            hist = hist_before(season, week)
            team_wks = statline_model.team_weeks_played(hist)
            lookback = len(statline_model.RECENCY_WEIGHTS)

            sal = load_salary_week(site, season, week)
            sal = sal.rename(columns={"name": "player_name"})
            realized = wk_stats.set_index("player_id")

            # PERFORMANCE, and it is not a micro-optimization: the first
            # version of this loop recomputed the team's recent-window volume
            # inside the per-player, per-component body -- a full boolean scan
            # of the history frame roughly 190,000 times on the real eight-
            # season panel. Precomputed once per week instead. Found by
            # running it, like everything else in this project.
            recent_pg = {}
            for _t, _wks in team_wks.items():
                _rw = _wks[-lookback:]
                if not _rw:
                    continue
                _sub = hist[hist["team"].eq(_t) & hist["week"].isin(_rw)]
                for _c, _vs in VOLUME_COL.items():
                    recent_pg[(_t, _c)] = float(_sub[_vs].sum()) / max(len(_rw), 1)

            # Per-player history, computed ONCE per week rather than per row.
            hist_by_pid = {pid: g.sort_values("week")
                           for pid, g in hist.groupby("player_id")}

            for r in sal.itertuples(index=False):
                pid = r.player_id
                pos = str(r.position_upper).upper()
                if pos not in COMPONENTS:
                    continue
                if pid not in realized.index:
                    continue  # did not record a stat line: no realized share
                rr = realized.loc[pid]
                if isinstance(rr, pd.DataFrame):
                    rr = rr.iloc[0]
                real_team = str(rr["team"])
                if real_team not in tt.index:
                    continue

                g = hist_by_pid.get(pid)
                gp = 0 if g is None else int(len(g))
                if g is not None:
                    hist_team = str(g["team"].iloc[-1])
                    part = statline_model._participation(
                        g["week"].tolist(), team_wks.get(hist_team, []), lookback)
                else:
                    part = 0.0

                for name, vol_stat, _yd, _td in COMPONENTS[pos]:
                    team_tot = float(tt.at[real_team, f"team_{name}"])
                    if team_tot <= 0:
                        continue
                    realized_share = float(rr[vol_stat]) / team_tot

                    if g is None:
                        hist_share = np.nan
                    else:
                        # statline_model.build_usage()'s exact volume:
                        # participation-weighted recency average.
                        mu = statline_model._recency_weighted(
                            g[vol_stat].to_numpy()) * part
                        # Expressed as a share of the team's RECENT volume,
                        # so it is on the same scale as realized_share.
                        # Denominator is the HISTORY team's recent per-game
                        # volume, while realized_share's denominator is the
                        # team the player actually played for this week. For a
                        # mid-season trade those differ -- deliberately: this
                        # column is what the model WOULD have predicted, and
                        # the model only knows the history team.
                        team_per_game = recent_pg.get((hist_team, name), 0.0)
                        hist_share = (mu / team_per_game
                                      if team_per_game > 1e-9 else np.nan)

                    rows.append({
                        "season": season, "week": week, "player_id": pid,
                        "name": r.player_name, "position": pos, "component": name,
                        "team": real_team, "salary": float(r.salary),
                        "realized_share": realized_share,
                        "hist_share": hist_share,
                        "games_played": gp, "participation": part,
                        "realized_volume": float(rr[vol_stat]),
                        "team_volume": team_tot,
                    })
        print(f"  {season}: {len(weeks)} week(s) panelled.")
    panel = pd.DataFrame(rows)
    if panel.empty:
        raise SystemExit(
            "Panel is empty. Check that data/salaries_{site}_rotoguru_*.csv "
            "and data/weekly_stats_*.parquet both exist for the requested "
            "seasons (Sessions 10.0 and 1.2).")
    return panel


# ---------------------------------------------------------------------------
# Small stats helpers
# ---------------------------------------------------------------------------

def ols(X: np.ndarray, y: np.ndarray):
    """Least squares with t-stats. numpy only -- SciPy is deliberately not a
    dependency of this repo (Session 10.4's statlite note)."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    dof = max(n - k, 1)
    s2 = float(resid @ resid) / dof
    xtx_inv = np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.clip(np.diag(xtx_inv) * s2, 0.0, None))
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, beta / se, 0.0)
    return beta, se, t, dof


def r2(y, yhat):
    y = np.asarray(y, float)
    yhat = np.asarray(yhat, float)
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def mae(y, yhat):
    return float(np.abs(np.asarray(y, float) - np.asarray(yhat, float)).mean())


# ---------------------------------------------------------------------------
# The share curve (reuses fit_salary_anchor's machinery -- decision reuse)
# ---------------------------------------------------------------------------

def fit_share_curve(df: pd.DataFrame, n_bins=SHARE_N_BINS,
                    min_rows=SHARE_MIN_BIN_ROWS):
    """E[share | salary] as isotonic-on-binned-means piecewise-linear knots.

    Identical construction to fit_salary_anchor.fit_position(), on `share`
    instead of `actual_points`, and using that module's own PAVA and
    top-endpoint-extension functions rather than a second copy. If this
    probe says the mechanism works, the real fitter is that module's
    machinery pointed at a different column -- which is exactly what the
    card asked for.
    """
    d = df.sort_values("salary").reset_index(drop=True)
    n = len(d)
    if n < min_rows * 2:
        return None
    try:
        d["_bin"] = pd.qcut(d["salary"], q=max(min(n_bins, n // min_rows), 2),
                            duplicates="drop", labels=False)
    except ValueError:
        d["_bin"] = 0
    grp = d.groupby("_bin").agg(
        salary_mean=("salary", "mean"),
        share_mean=("realized_share", "mean"),
        rows=("realized_share", "size"),
    ).sort_values("salary_mean").reset_index(drop=True)
    grp = grp[grp["rows"] >= min(min_rows, grp["rows"].max())]
    if len(grp) < 3:
        return None
    xs = grp["salary_mean"].to_numpy(float)
    ys = isotonic_pava(grp["share_mean"].to_numpy(float),
                       grp["rows"].to_numpy(float))
    xs, ys, _syn = _add_top_endpoint_knot(xs, ys, float(d["salary"].max()))
    return [[float(x), float(y)] for x, y in zip(xs, ys)]


def fit_and_apply_curves(panel: pd.DataFrame, fit_seasons: list,
                        test_seasons: list, verbose: bool = True):
    """Fit E[share|salary] per (position, component) on `fit_seasons`, apply
    to `test_seasons`. Shared by probes A and D so the two can never drift
    apart -- probe D's role-change divergence is defined AGAINST probe A's
    curve, and two independent copies of that fit would eventually disagree.

    Reports UNFITTED pairs loudly. The first run of this probe silently
    produced no TE/recv curve and said nothing about it -- every TE row then
    vanished from the pooled numbers, which would have read as "the pooled
    result" while being a result with a whole position missing. That is the
    silent-drop failure class this project keeps getting bitten by, so the
    accounting is printed unconditionally rather than behind a flag.
    """
    fit = panel[panel["season"].isin(fit_seasons)]
    test = panel[panel["season"].isin(test_seasons)].copy()
    if fit.empty or test.empty:
        return None, None, None

    wanted = sorted({(p, c) for p, cs in COMPONENTS.items()
                     for c, _v, _y, _t in cs})
    curves, unfitted = {}, []
    for pos, comp in wanted:
        sub = fit[(fit["position"] == pos) & (fit["component"] == comp)]
        k = fit_share_curve(sub) if len(sub) else None
        if k is None:
            unfitted.append((pos, comp, len(sub)))
        else:
            curves[(pos, comp)] = k

    if verbose:
        print(f"\n  Fitted {len(curves)}/{len(wanted)} (position, component) "
              f"share curve(s) on {sorted(fit_seasons)} ({len(fit):,} rows).")
        for (pos, comp), k in sorted(curves.items()):
            print(f"    {pos:>2}/{comp:<4} {len(k):>2} knots  "
                  f"${k[0][0]:>6.0f}->{k[0][1]:.3f} .. "
                  f"${k[-1][0]:>6.0f}->{k[-1][1]:.3f}")
        if unfitted:
            print(f"\n    !! NOT FITTED (too few fit rows to bin at "
                  f"min {SHARE_MIN_BIN_ROWS}/bin):")
            for pos, comp, n in unfitted:
                print(f"       {pos}/{comp}  n={n:,}")
            print(f"       Every test row for those pairs is EXCLUDED below. "
                  f"On the real\n       eight-season panel this list should be "
                  f"empty or near it -- if a\n       core pair (QB/pass, "
                  f"RB/rush, WR/recv, TE/recv) is here, lower\n       "
                  f"SHARE_MIN_BIN_ROWS before reading any number in this probe.")

    test["price_share"] = np.nan
    for (pos, comp), k in curves.items():
        m = (test["position"] == pos) & (test["component"] == comp)
        if m.any():
            test.loc[m, "price_share"] = interp_knots(
                k, test.loc[m, "salary"].to_numpy(float))

    n_all = len(test)
    n_no_curve = int(test["price_share"].isna().sum())
    ev = test.dropna(subset=["price_share", "hist_share", "realized_share"])
    n_no_hist = n_all - n_no_curve - len(ev)
    if verbose:
        print(f"\n  Evaluation set on {sorted(test_seasons)}: {len(ev):,} of "
              f"{n_all:,} test rows.")
        print(f"    dropped {n_no_curve:,} with no fitted curve, "
              f"{n_no_hist:,} with no usable history share")
        print(f"    (a zero-history player has no hist_share by definition, so "
              f"the pooled\n     comparison below is necessarily on players "
              f"history CAN speak to -- which\n     biases it TOWARD history. "
              f"Read the gp 0-1 bucket for the other side.)")
    return curves, test, ev


# ---------------------------------------------------------------------------
# PROBE A -- price vs history as a predictor of volume share
# ---------------------------------------------------------------------------

def probe_a(panel: pd.DataFrame, fit_seasons: list, test_seasons: list):
    print("\n" + "=" * 78)
    print("PROBE A -- does PRICE predict volume share better than OWN HISTORY,")
    print("           and is its error DECORRELATED from history's?")
    print("=" * 78)
    print("Pre-registered reading, written before the run:")
    print("  * price MUST beat history at games_played 0-1 (that is cold start,")
    print("    and Session 10.2 already proved the mechanism on points).")
    print("  * the interesting question is games_played 7+, where history is")
    print("    strongest. If price loses there AND residual correlation is")
    print("    above ~0.9, build item 1 is a null as a mid-season component --")
    print("    the same shape as Session 10.3a's 5.20-vs-5.18 pre-test -- and")
    print("    should be reduced to cold start only.")

    curves, test, ev = fit_and_apply_curves(panel, fit_seasons, test_seasons)
    if ev is None:
        print("  INSUFFICIENT DATA for the requested split -- skipped.")
        return

    def _line(label, sub):
        if len(sub) < 30:
            return f"    {label:<14} n={len(sub):>6}   (too few rows to read)"
        y = sub["realized_share"].to_numpy(float)
        p = sub["price_share"].to_numpy(float)
        h = sub["hist_share"].to_numpy(float)
        # statlite.spearmanr returns a SciPy-shaped result OBJECT, not a
        # tuple -- unpacking it raises. Found by running this probe, not by
        # reading it, which is this project's usual way of finding things.
        rho_p = statlite.spearmanr(p, y).statistic
        rho_h = statlite.spearmanr(h, y).statistic
        ep, eh = p - y, h - y
        rc = float(np.corrcoef(ep, eh)[0, 1]) if len(ep) > 2 else float("nan")
        # A 50/50 blend is the cheapest possible read on whether combining
        # them helps at all -- not a proposed weight, just a decorrelation
        # check in the units that matter.
        blend = 0.5 * p + 0.5 * h
        return (f"    {label:<14} n={len(sub):>6}   "
                f"MAE price {mae(y, p):.4f} / hist {mae(y, h):.4f} / "
                f"50-50 {mae(y, blend):.4f}   "
                f"rho price {rho_p:+.3f} / hist {rho_h:+.3f}   "
                f"resid corr {rc:+.3f}")

    print("\n  --- Pooled, then split by games of usage history ---")
    print(_line("ALL", ev))
    for lo, hi in GP_BUCKETS:
        sub = ev[(ev["games_played"] >= lo) & (ev["games_played"] <= hi)]
        print(_line(f"gp {lo}-{hi}", sub))

    print("\n  --- By component (the mid-season question, gp >= 4 only) ---")
    mid = ev[ev["games_played"] >= 4]
    for (pos, comp), sub in sorted(mid.groupby(["position", "component"])):
        print(_line(f"{pos}/{comp}", sub))

    print("\n  HOW TO READ THIS: 'resid corr' is the number that decides the")
    print("  card. Near 1.0 means price and history are the same signal and a")
    print("  blend cannot help no matter how it is weighted (Phase 10 design")
    print("  intro; Session 10.3a's 0.965). Below ~0.7 with comparable MAE")
    print("  means there is real independent information to blend.")


# ---------------------------------------------------------------------------
# PROBE B -- does Vegas add to team volume over team history?
# ---------------------------------------------------------------------------

def load_lines(site: str) -> pd.DataFrame:
    """(season, week, team) -> implied_total, spread, over_under, from the
    same real historical lines backtest_harness.build_vegas_file() uses."""
    if not GAMES_CACHE.exists():
        raise SystemExit(
            f"{GAMES_CACHE} not found. Run the backtest harness once (it "
            f"downloads nflverse games.csv), or fetch it manually. Probe B "
            f"and C both need real historical lines.")
    g = pd.read_csv(GAMES_CACHE)
    g = g[g["total_line"].notna() & g["spread_line"].notna()]
    rows = []
    for r in g.itertuples():
        total, spread = float(r.total_line), float(r.spread_line)
        # spread_line is positive when HOME is favoured (harness convention).
        rows.append({"season": int(r.season), "week": int(r.week),
                     "team": normalize_team(r.home_team, site),
                     "team_spread": -spread, "over_under": total,
                     "implied_total": total / 2 + spread / 2})
        rows.append({"season": int(r.season), "week": int(r.week),
                     "team": normalize_team(r.away_team, site),
                     "team_spread": spread, "over_under": total,
                     "implied_total": total / 2 - spread / 2})
    return pd.DataFrame(rows)


def build_team_panel(site: str, seasons: list) -> pd.DataFrame:
    """(season, week, team) with realized volume and the recency-weighted
    history prediction statline_model.team_volume_history() would produce."""
    lines = load_lines(site)
    rows = []
    for season in seasons:
        stats = _season_history(season)
        weeks = sorted(stats["week"].unique().tolist())
        for week in weeks:
            if week < 3:
                continue  # need at least a couple of prior weeks for history
            hist = stats[stats["week"] < week]
            wk = stats[stats["week"] == week]
            tt = team_totals(wk)
            for team in tt.index:
                th = hist[hist["team"] == team]
                if th.empty:
                    continue
                per_week = th.groupby("week")[["attempts", "carries", "targets"]] \
                             .sum().sort_index()
                rows.append({
                    "season": season, "week": week,
                    "team_norm": normalize_team(team, site),
                    "real_pass": float(tt.at[team, "team_pass"]),
                    "real_rush": float(tt.at[team, "team_rush"]),
                    "hist_pass": statline_model._recency_weighted(
                        per_week["attempts"].to_numpy()),
                    "hist_rush": statline_model._recency_weighted(
                        per_week["carries"].to_numpy()),
                })
    tp = pd.DataFrame(rows)
    merged = tp.merge(lines, left_on=["season", "week", "team_norm"],
                      right_on=["season", "week", "team"], how="left")
    # Session 10.4's bug #1 was a merge that lost 13% of its panel SILENTLY,
    # because an inner join treats a team-code mismatch as an absence rather
    # than an error. Same guard here, same 2% threshold.
    lost = float(merged["implied_total"].isna().mean())
    if lost > 0.02:
        raise SystemExit(
            f"Team/line merge lost {lost:.1%} of rows (limit 2%). That is the "
            f"Session 10.4 bug #1 signature -- era-correct team codes in "
            f"games.csv against current codes in weekly_stats. Fix the "
            f"normalization before reading probe B or C.")
    return merged.dropna(subset=["implied_total"])


def probe_b(site: str, fit_seasons: list, test_seasons: list):
    print("\n" + "=" * 78)
    print("PROBE B -- does VEGAS add anything to TEAM VOLUME over team history?")
    print("=" * 78)
    print("Pre-registered reading, written before the run:")
    print("  * SPREAD should matter more than TOTAL, because game script -- not")
    print("    scoring environment -- is what moves attempts vs carries. If the")
    print("    card's phrase 'Vegas-anchored team volume' is read as the implied")
    print("    TOTAL and only the spread carries signal, the card is wrong about")
    print("    its own mechanism and should be corrected rather than satisfied.")
    print("  * a null on both kills build item 4, the largest of the four.")

    tp = build_team_panel(site, sorted(set(fit_seasons) | set(test_seasons)))
    fit = tp[tp["season"].isin(fit_seasons)]
    test = tp[tp["season"].isin(test_seasons)]
    if fit.empty or test.empty:
        print("  INSUFFICIENT DATA -- skipped.")
        return
    print(f"\n  Panel: {len(fit):,} fit team-weeks / {len(test):,} test "
          f"team-weeks (out-of-sample).")

    for target, hist_col, label in (("real_pass", "hist_pass", "PASS ATTEMPTS"),
                                    ("real_rush", "hist_rush", "CARRIES")):
        print(f"\n  --- {label} ---")
        specs = [
            ("history only", ["hist"]),
            ("+ implied total", ["hist", "it"]),
            ("+ spread", ["hist", "spread"]),
            ("+ both", ["hist", "it", "spread"]),
        ]
        for name, terms in specs:
            def design(d):
                cols = [np.ones(len(d))]
                if "hist" in terms:
                    cols.append(d[hist_col].to_numpy(float))
                if "it" in terms:
                    cols.append(d["implied_total"].to_numpy(float))
                if "spread" in terms:
                    cols.append(d["team_spread"].to_numpy(float))
                return np.column_stack(cols)

            Xf, yf = design(fit), fit[target].to_numpy(float)
            beta, se, t, dof = ols(Xf, yf)
            Xt, yt = design(test), test[target].to_numpy(float)
            pred = Xt @ beta
            names = ["const"] + [n for n in ("hist", "it", "spread") if n in terms]
            tstr = "  ".join(f"{n}={tv:+.2f}" for n, tv in zip(names, t) if n != "const")
            print(f"    {name:<16} out-of-sample R2 {r2(yt, pred):+.4f}  "
                  f"MAE {mae(yt, pred):5.2f}   in-sample t: {tstr}")

    print("\n  HOW TO READ THIS: compare the '+ ...' rows' out-of-sample R2 to")
    print("  'history only'. An improvement in the third decimal is not a")
    print("  component worth building -- Session 10.4 rejected wind on exactly")
    print("  this basis (real t-stat, no usable effect, books price it in).")


# ---------------------------------------------------------------------------
# PROBE C -- is a WEEK-1 team volume prediction sane enough to build on?
# ---------------------------------------------------------------------------

def probe_c(site: str, seasons: list):
    print("\n" + "=" * 78)
    print("PROBE C -- is a WEEK-1 team-volume prediction sane enough to build on?")
    print("=" * 78)
    print("Why this gates build item 2 rather than sitting beside it:")
    print("  In week 1 statline_model.load_history() is empty, so")
    print("  team_volume_history() returns an EMPTY frame, reconciliation cannot")
    print("  run, and _participation() is 0.0 for every player -- which would")
    print("  multiply any price-predicted volume straight back to zero. A player")
    print("  share needs a team total to be a share OF. Cold start therefore")
    print("  DEPENDS on a non-history team-volume source; the card lists the two")
    print("  as independent bullets and they are not.")
    print("  Candidate sources measured here: prior-season carryover (the")
    print("  mechanism dst_model.py decision #15 already uses), and carryover")
    print("  tilted by that week's real line.")

    lines = load_lines(site)
    rows = []
    for season in seasons:
        prior = season - 1
        if not (DATA_DIR / f"weekly_stats_{prior}.parquet").exists():
            print(f"  {season}: no {prior} history on disk -- cannot test "
                  f"carryover, skipped.")
            continue
        ph = _season_history(prior)
        pg = ph.groupby(["team", "week"])[["attempts", "carries"]].sum() \
               .groupby("team").mean()
        # Normalize the PRIOR season's team codes too. Without this, a
        # relocation (STL->LA 2016, SD->LAC 2017, OAK->LV 2020) looks like a
        # franchise with no history and gets excluded -- three teams silently
        # missing from a 32-row week-1 panel. Same root cause as Session
        # 10.4's bug #1, caught here before it could bite.
        pg.index = [normalize_team(t, site) for t in pg.index]
        pg = pg.groupby(level=0).mean()
        cur = _season_history(season)
        wk1 = cur[cur["week"] == 1]
        if wk1.empty:
            continue
        tt = team_totals(wk1)
        league_pass = float(tt["team_pass"].mean())
        league_rush = float(tt["team_rush"].mean())
        for team in tt.index:
            tn = normalize_team(team, site)
            src = tn if tn in pg.index else None
            if src is None:
                # A franchise relocation the normalization did not bridge.
                # Reported, never silently league-averaged -- that is the
                # substitution dst_model.py decision #16 refuses to make.
                print(f"    NOTE {season} wk1: no prior-season row for {team} "
                      f"(normalized {tn}) -- excluded, not league-averaged.")
                continue
            ln = lines[(lines["season"] == season) & (lines["week"] == 1)
                       & (lines["team"] == tn)]
            rows.append({
                "season": season, "team": team,
                "real_pass": float(tt.at[team, "team_pass"]),
                "real_rush": float(tt.at[team, "team_rush"]),
                "carry_pass": float(pg.at[src, "attempts"]),
                "carry_rush": float(pg.at[src, "carries"]),
                "league_pass": league_pass, "league_rush": league_rush,
                "implied_total": float(ln["implied_total"].iloc[0]) if len(ln) else np.nan,
                "team_spread": float(ln["team_spread"].iloc[0]) if len(ln) else np.nan,
            })
    d = pd.DataFrame(rows)
    if d.empty:
        print("  INSUFFICIENT DATA -- skipped.")
        return
    d = d.dropna(subset=["implied_total"])
    print(f"\n  {len(d):,} week-1 team-seasons with prior-season history and a "
          f"real line.")

    for tgt, carry, league, label in (
            ("real_pass", "carry_pass", "league_pass", "PASS ATTEMPTS"),
            ("real_rush", "carry_rush", "league_rush", "CARRIES")):
        y = d[tgt].to_numpy(float)
        print(f"\n  --- {label} (realized mean {y.mean():.1f}, SD {y.std():.1f}) ---")
        print(f"    league average       MAE {mae(y, d[league]):5.2f}   "
              f"R2 {r2(y, d[league]):+.4f}")
        print(f"    prior-season carry   MAE {mae(y, d[carry]):5.2f}   "
              f"R2 {r2(y, d[carry]):+.4f}")
        X = np.column_stack([np.ones(len(d)), d[carry].to_numpy(float),
                             d["implied_total"].to_numpy(float),
                             d["team_spread"].to_numpy(float)])
        beta, se, t, dof = ols(X, y)
        print(f"    carry + line (in-sample, so an UPPER BOUND -- there is no "
              f"holdout at n={len(d)})")
        print(f"                         MAE {mae(y, X @ beta):5.2f}   "
              f"R2 {r2(y, X @ beta):+.4f}   "
              f"t: carry={t[1]:+.2f} it={t[2]:+.2f} spread={t[3]:+.2f}")

    print("\n  HOW TO READ THIS: the bar is NOT accuracy, it is whether week 1 is")
    print("  BUILDABLE at all -- Session 10.2 already showed a week-1 build from")
    print("  price alone reaching median-pctile 57.2 / max-pctile 99.7, against a")
    print("  week that was previously structurally unbuildable. Carryover beating")
    print("  the league average at all is enough to proceed; the line terms are a")
    print("  bonus and are reported in-sample, so do not quote them as evidence.")


# ---------------------------------------------------------------------------
# PROBE D -- what IS the role-change flag, and which way does it point?
# ---------------------------------------------------------------------------

def probe_d(panel: pd.DataFrame, fit_seasons: list, test_seasons: list):
    print("\n" + "=" * 78)
    print("PROBE D -- price-vs-history divergence as the ROLE-CHANGE FLAG")
    print("=" * 78)
    print("The ROADMAP's Phase 10 design intro says: 'suppress the salary")
    print("anchor's weight when a role change is flagged -- a stale price is")
    print("exactly the value spot we're trying to beat.' That presumes the PRICE")
    print("is stale. On a weekly slate the site reprices every player every week")
    print("with real money behind it, while our usage history is weeks old by")
    print("construction -- so the opposite may be true here, and this measures")
    print("which. A flag built on depth charts or injury reports could not be")
    print("tested at all: this project has no historical archive of either, which")
    print("is why divergence is the only backtestable candidate.")

    # Same curve as probe A, from the same helper -- probe D's divergence is
    # DEFINED against probe A's price_share, so a second independent fit here
    # would be two things that must agree and eventually would not.
    curves, test, ev = fit_and_apply_curves(panel, fit_seasons, test_seasons,
                                           verbose=False)
    if ev is None:
        print("  INSUFFICIENT DATA for the requested split -- skipped.")
        return
    ev = ev.copy()
    ev["divergence"] = ev["price_share"] - ev["hist_share"]
    ev["hist_resid"] = ev["realized_share"] - ev["hist_share"]

    y = ev["hist_resid"].to_numpy(float)
    X = np.column_stack([np.ones(len(ev)), ev["divergence"].to_numpy(float)])
    beta, se, t, dof = ols(X, y)
    print(f"\n  Regressing (realized share - history share) on (price share - "
          f"history share),")
    print(f"  out-of-sample, n={len(ev):,}:")
    print(f"    slope {beta[1]:+.4f}  (SE {se[1]:.4f}, t {t[1]:+.2f})   "
          f"R2 {r2(y, X @ beta):+.4f}")
    print("    A slope near 0 means divergence carries nothing and there is no")
    print("    flag to build. A slope materially ABOVE 0 means price sees role")
    print("    changes history cannot -- and the ROADMAP's instruction is")
    print("    BACKWARDS for this pipeline and must be amended, not followed.")
    print("    A slope near 1.0 would mean price is a complete substitute.")

    print("\n  --- Where the two disagree most (largest |divergence| decile) ---")
    cut = ev["divergence"].abs().quantile(0.9)
    hi = ev[ev["divergence"].abs() >= cut]
    if len(hi) > 30:
        yy = hi["realized_share"].to_numpy(float)
        print(f"    n={len(hi):,}   MAE price {mae(yy, hi['price_share']):.4f} / "
              f"hist {mae(yy, hi['hist_share']):.4f}")
        print("    If price wins HERE by a clear margin, the flag is simply")
        print("    'divergence is large', and its action is to raise the price")
        print("    prior's weight for that player -- the cold-start schedule")
        print("    applied mid-season, not a second mechanism.")

    print("\n  --- Session 10.3a's two catalogued cases ---")
    for season, week, team, name, comp in CATALOGUED_CASES:
        sub = ev[(ev["season"] == season) & (ev["week"] == week)
                 & (ev["component"] == comp)
                 & ev["name"].astype(str).str.contains(name.split()[-1], case=False,
                                                       na=False)]
        if sub.empty:
            print(f"    {season} wk{week} {team} {name}: not in the evaluation "
                  f"window or no realized {comp} row -- cannot check here.")
            continue
        for r in sub.itertuples():
            print(f"    {season} wk{week} {r.team} {r.name} ({comp}): "
                  f"gp={r.games_played} part={r.participation:.2f}  "
                  f"realized {r.realized_share:.3f} | hist {r.hist_share:.3f} | "
                  f"price {r.price_share:.3f}  (salary ${r.salary:.0f})")
    print("    These are the two weeks that ABORTED the first Session 10.3a run.")
    print("    If price lands materially closer to realized than history does on")
    print("    both, that is the direct evidence build item 3 exists to find.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Session 10.3b pre-tests. Measures the card's premises "
                    "before anything is built. Writes nothing.")
    ap.add_argument("--site", choices=["dk", "fd"], default="dk")
    ap.add_argument("--fit-seasons", type=int, nargs="+",
                    default=[2014, 2015, 2016, 2017])
    ap.add_argument("--test-seasons", type=int, nargs="+",
                    default=[2018, 2019, 2020, 2021])
    ap.add_argument("--probes", nargs="+", choices=["A", "B", "C", "D"],
                    default=["A", "B", "C", "D"])
    ap.add_argument("--skip-mirror-check", action="store_true",
                    help="Skip the assertion that this script's cached history "
                         "loader matches statline_model.load_history(). Only "
                         "for debugging -- every history number below depends "
                         "on that equivalence.")
    ap.add_argument("--dump-panel", action="store_true",
                    help="Write the player-week-component panel to "
                         "output/probe_10_3b_panel.csv for inspection. Still "
                         "not an artifact -- nothing loads it.")
    args = ap.parse_args()

    overlap = set(args.fit_seasons) & set(args.test_seasons)
    if overlap:
        print(f"\n  !! WARNING: fit and test seasons overlap on {sorted(overlap)}.")
        print(f"     Session 10.3a measured that fitting on the season then")
        print(f"     measured inflated its effect roughly THREEFOLD. Numbers")
        print(f"     from this run are in-sample and must not be logged as")
        print(f"     evidence.\n")

    seasons = sorted(set(args.fit_seasons) | set(args.test_seasons))
    print("=" * 78)
    print(f"SESSION 10.3b PRE-TESTS -- site={args.site}  "
          f"fit={args.fit_seasons}  test={args.test_seasons}")
    print("=" * 78)

    if not args.skip_mirror_check:
        verify_mirror(seasons[-1], 10)

    panel = None
    if args.dump_panel and not ({"A", "D"} & set(args.probes)):
        print("\n  NOTE: --dump-panel does nothing unless probe A or D is "
              "selected (they are\n  what build the panel). Add --probes A to "
              "get the dump.")

    if "A" in args.probes or "D" in args.probes:
        print("\nBuilding player-week-component panel...")
        panel = build_panel(args.site, seasons)
        print(f"  Panel: {len(panel):,} rows, "
              f"{panel['player_id'].nunique():,} players.")
        if args.dump_panel:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            p = OUTPUT_DIR / "probe_10_3b_panel.csv"
            panel.to_csv(p, index=False)
            print(f"  Panel written to {p}")

    if "A" in args.probes:
        probe_a(panel, args.fit_seasons, args.test_seasons)
    if "B" in args.probes:
        probe_b(args.site, args.fit_seasons, args.test_seasons)
    if "C" in args.probes:
        probe_c(args.site, seasons)
    if "D" in args.probes:
        probe_d(panel, args.fit_seasons, args.test_seasons)

    print("\n" + "=" * 78)
    print("Probes complete. NOTHING was written to data/ -- this script produces")
    print("no artifact the production path could pick up. Paste the output back")
    print("before Session 10.3b's build begins; two of the four build items are")
    print("expected to change shape on these results.")
    print("=" * 78)


if __name__ == "__main__":
    main()
