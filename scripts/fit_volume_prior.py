"""
fit_volume_prior.py
===================

Session 10.3b -- price-as-a-volume-prior, team volume, and the role-change
slope (the FITTER).

Writes `data/volume_prior_{site}.json`, read by `volume_prior.py`. Deliberately
separate from the consumer so the production path never imports fitting
machinery -- the same split as Session 10.2's salary_anchor / fit_salary_anchor
and Session 10.4's dst_model / fit_dst_model.

Three things are fit here:

  1. E[share | salary] per (position, component), isotonic on binned means.
     Reuses fit_salary_anchor.py's OWN PAVA, top-endpoint extension and knot
     evaluation rather than a second copy -- Session 10.3b's card asked for
     exactly that ("reusing fit_salary_anchor.py's isotonic machinery on the
     share rather than on points") and it is the one part of the card that
     survived the pre-tests unchanged.

  2. Team volume per component, two specifications: `with_history` (the
     normal path) and `no_history` (week 1). Both always carry BOTH Vegas
     terms -- see volume_prior.py decision #7 for why one without the other
     is a specification error rather than a simplification.

  3. The role-change slope: the coefficient of (price share - history share)
     in a regression of (realized share - history share). This is the ONE
     constant that drives volume_prior.py's participation override, and it
     is fitted here precisely so it is not hand-tuned against the three
     catalogued cases.

Numbered decisions:

  1. FIT SOURCE IS THE MATCHED SALARY FILES JOINED TO weekly_stats, NOT the
     rotoguru actuals files that fit_salary_anchor.py uses. Stated because it
     is a real deviation from "reuse fit_salary_anchor's machinery": the
     actuals files carry (position, salary, actual_points) and no volume
     columns at all, so a SHARE cannot be fit from them. The machinery is
     reusable; the load path is not.

  2. THE HISTORY SIDE IS COMPUTED WITH statline_model.py'S OWN PRIMITIVES
     (RECENCY_WEIGHTS, _recency_weighted, _participation, team_weeks_played).
     The fitted role slope is only meaningful if `hist_share` here is the
     same quantity the engine will actually compute at run time. A
     reimplementation would fit a slope against a straw man.

  3. HOLDOUT BY DEFAULT (fit 2014-17). Session 10.3a's transferable lesson
     was that fitting `statline_variance.json` on the season then measured
     inflated its effect roughly threefold and would have gone into the log
     as a finding. `--fit-seasons` defaults to the holdout window and the
     script WARNS LOUDLY when a fit includes measurement-window seasons --
     the same guard fit_dst_model.py prints, for the same reason.

     Production is refit on all eight seasons afterwards, exactly as Session
     10.4 did, and that refit is in-sample for any 2018-21 measurement and
     must be recorded as the configuration's numbers rather than as evidence.

  4. A PAIR THAT CANNOT BE FIT IS OMITTED AND REPORTED, NOT FAKED. Unlike
     fit_salary_anchor.py's decision #9 -- where a thin curve is a hard error
     because the anchor must reach the expensive players who decide lineups
     -- a thin (position, component) share pair is a legitimate outcome
     (WR/rush is genuinely rare). It is left out of the artifact, listed at
     the end of the run, and volume_prior.share_from_salary() returns 0.0 for
     it. The failure mode being avoided is a SILENT omission: the pre-test
     probe dropped TE/recv without a word on its first run and every pooled
     number silently excluded a position.

  5. THE ROLE SLOPE IS FIT OUT-OF-SAMPLE AND REPORTED WITH ITS t. If it ever
     comes back near zero, the role-change flag has nothing behind it and
     volume_prior.py decision #3 should be reconsidered rather than shipped
     on a stale artifact. The number is printed, not buried.

  6. SESSION 15.2B -- RUSH's with_history SPEC GAINS A FOURTH TERM,
     opp_rush_allowed (the upcoming opponent's own recency-weighted
     carries-allowed), BECAUSE THE TEAM'S OWN HISTORY TERM WAS MEASURED
     GENUINELY WEAK (Session 15.2's Diagnostic #4: shipped coefficient
     0.237, fresh-data-independent refit 0.306, R2 stuck at 0.05-0.08 no
     matter which of the original three inputs get used) AND A REAL
     BACKTEST SHOWED THIS NEW TERM HELPS WITHOUT FIXING THAT WEAKNESS.
     Probed on real, held-out 2022-2024 data across three rotated holdout
     splits (t = 2.34 to 3.71, coefficient 0.12-0.19 every time, max
     correlation with the existing three terms 0.30) and confirmed again
     on this file's own production convention (train 2014-17, test
     2018-21: t = 3.48, R2_oos 0.0677 -> 0.0728). hist_rush's own
     coefficient barely moves with the new term present (0.194 -> 0.199 on
     that same split) -- confirming this is a genuine ADDITIVE signal, not
     a collinearity artifact that happened to be suppressing hist_rush.

     PASS and RECV do not get an equivalent term. Nobody has probed
     whether "opponent pass-defense strength" or "opponent coverage
     strength" would do the same thing for those components, and this
     project's standing rule is not to ship a change nothing has measured
     -- see decision #4's own "omitted, never faked" rule for the same
     principle applied to a different case. If either component's own
     history coefficient is ever found similarly weak, that is a new,
     separate probe, not an assumed extension of this one.

Usage:
    # measurement fit (holdout -- this is the default)
    python3 scripts/fit_volume_prior.py --site dk

    # production refit, all eight seasons
    python3 scripts/fit_volume_prior.py --site dk \\
        --fit-seasons 2014 2015 2016 2017 2018 2019 2020 2021

Output:
    data/volume_prior_{site}.json   (read by scripts/volume_prior.py)
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import statline_model  # noqa: E402
import volume_prior  # noqa: E402
from fit_salary_anchor import (  # noqa: E402
    _add_top_endpoint_knot,
    interp_knots,
    isotonic_pava,
)
from fit_statline_variance import COMPONENTS  # noqa: E402
from ingest_salaries import normalize_team  # noqa: E402

GAMES_CACHE = DATA_DIR / "nflverse_games.csv"

VOLUME_COL = {"pass": "attempts", "rush": "carries", "recv": "targets"}
for _pos, _comps in COMPONENTS.items():
    for _name, _vol, _yd, _td in _comps:
        assert VOLUME_COL[_name] == _vol, (
            f"VOLUME_COL[{_name}] disagrees with COMPONENTS ({VOLUME_COL[_name]} "
            f"vs {_vol}) -- the fit would be on a different quantity than the "
            f"engine uses.")

# Binning for the share curves. ARBITRARY starting values, flagged, not fit.
# Lower row floor than fit_salary_anchor's 200 because a share exists for
# every player-week while points-above-baseline is a noisier target.
SHARE_N_BINS = 20
SHARE_MIN_BIN_ROWS = 150

# Decision #3 -- the holdout window, matching Session 10.3a's split exactly.
DEFAULT_FIT_SEASONS = [2014, 2015, 2016, 2017]
MEASUREMENT_SEASONS = [2018, 2019, 2020, 2021]

# Validation: the three cases Session 10.3a catalogued (two aborted its first
# run; the third is the limitation statline_model.py decision #9 names).
CATALOGUED_CASES = [(2021, 13, "Wilson", "NYJ"), (2021, 13, "Wilson", "SEA"),
                    (2021, 15, "Newton", "CAR")]

_HIST_CACHE = {}


# ---------------------------------------------------------------------------
# Panel construction (decisions #1, #2)
# ---------------------------------------------------------------------------

def season_history(season: int) -> pd.DataFrame:
    if season in _HIST_CACHE:
        return _HIST_CACHE[season]
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Run ingest_historical.py --season {season} "
            f"(Session 1.2). Not skipping it silently -- a missing season "
            f"would quietly change what this artifact claims to be fit on.")
    df = pd.read_parquet(path)
    col = "season_type" if "season_type" in df.columns else "game_type"
    df = df[df[col] == "REG"].copy()
    num = df.select_dtypes(include=[np.number]).columns
    df[num] = df[num].fillna(0.0)
    _HIST_CACHE[season] = df
    return df


def available_weeks(site: str, season: int) -> list:
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
            f"output schema changed -- not guessing at column names.")
    df = df[df["player_id"].notna()].copy()
    df["salary"] = pd.to_numeric(df["salary"], errors="coerce")
    # Same rule as fit_salary_anchor decision #2: an unpurchasable price
    # carries no market information, which is the only thing being fit.
    df = df[df["salary"].notna() & (df["salary"] > 0)]
    return df.rename(columns={"name": "player_name"})[
        ["player_id", "player_name", "salary", "normalized_team", "position_upper"]]


def team_totals(week_stats: pd.DataFrame) -> pd.DataFrame:
    g = week_stats.groupby("team")[["attempts", "carries", "targets"]].sum()
    return g.rename(columns={"attempts": "team_pass", "carries": "team_rush",
                             "targets": "team_recv"})


def _team_rush_and_opponent(stats: pd.DataFrame) -> pd.DataFrame:
    """Session 15.2b. One row per (week, team) for a SINGLE season's raw
    weekly stats: that team's own real rush volume, its real opponent that
    week, and -- via a self-join of the same table against itself -- how
    many rushes ITS OPPONENT had, i.e. how many rushes this team allowed
    on defense that week.

    `opponent_team` comes straight through from nflverse's own weekly-stats
    release (nflverse_fetch.py pulls the full parquet, no column
    filtering), so no new data source is needed. A team's opponent is the
    mode of every one of its players' `opponent_team` values that week --
    every real player row for a team in a game names the same opponent, so
    this is exact, not a heuristic; a row with no opponent (bye, or a
    non-active-roster row nflverse still lists) is dropped before the mode
    rather than allowed to win a tie.
    """
    off = stats.groupby(["week", "team"], as_index=False)["carries"].sum()
    off = off.rename(columns={"carries": "team_rush"})
    opp = stats.dropna(subset=["opponent_team"]).groupby(
        ["week", "team"])["opponent_team"].agg(
        lambda s: s.value_counts().idxmax()).reset_index()
    out = off.merge(opp, on=["week", "team"], how="left")
    allowed = off.rename(columns={"team": "opponent_team",
                                  "team_rush": "carries_allowed"})
    out = out.merge(allowed, on=["week", "opponent_team"], how="left")
    return out


def build_player_panel(site: str, seasons: list) -> pd.DataFrame:
    """One row per (season, week, player, component), carrying the realized
    share, the share statline_model's own volume model implies, and the
    games-played / participation axes the cold start and the role flag use."""
    rows = []
    for season in seasons:
        weeks = available_weeks(site, season)
        if not weeks:
            print(f"  {season}: no matched salary files -- skipped.")
            continue
        season_stats = season_history(season)
        for week in weeks:
            wk_stats = season_stats[season_stats["week"] == week]
            if wk_stats.empty:
                continue
            tt = team_totals(wk_stats)
            hist = season_stats[season_stats["week"] < week]
            team_wks = statline_model.team_weeks_played(hist)
            lookback = len(statline_model.RECENCY_WEIGHTS)

            # Team per-game volume, computed EXACTLY as
            # statline_model.team_volume_history() computes it: group to
            # per-week team totals, then recency-weight. The pre-test probe
            # used a simple mean of the last five weeks instead, which is a
            # slightly different quantity -- and since `hist_share` is the
            # denominator of the role-change slope, a mismatch here would fit
            # that coefficient against a number the engine never computes.
            # This is decision #2 taken literally.
            #
            # Precomputed once per week: the probe's first version did this
            # inside the per-player body, ~190,000 full boolean scans of the
            # history frame on the eight-season panel.
            recent_pg = {}
            if not hist.empty:
                _pw = hist.groupby(["team", "week"])[
                    ["attempts", "carries", "targets"]].sum()
                for _t, _g in _pw.groupby(level=0):
                    _g = _g.droplevel(0).sort_index()
                    for _c, _vs in VOLUME_COL.items():
                        recent_pg[(_t, _c)] = statline_model._recency_weighted(
                            _g[_vs].to_numpy())

            sal = load_salary_week(site, season, week)
            realized = wk_stats.set_index("player_id")
            hist_by_pid = {pid: g.sort_values("week")
                           for pid, g in hist.groupby("player_id")}

            for r in sal.itertuples(index=False):
                pid, pos = r.player_id, str(r.position_upper).upper()
                if pos not in COMPONENTS or pid not in realized.index:
                    continue
                rr = realized.loc[pid]
                if isinstance(rr, pd.DataFrame):
                    rr = rr.iloc[0]
                real_team = str(rr["team"])
                if real_team not in tt.index:
                    continue

                g = hist_by_pid.get(pid)
                gp = 0 if g is None else int(len(g))
                hist_team = str(g["team"].iloc[-1]) if g is not None else ""
                part = (statline_model._participation(
                            g["week"].tolist(), team_wks.get(hist_team, []),
                            lookback)
                        if g is not None else 0.0)

                for name, vol_stat, _yd, _td in COMPONENTS[pos]:
                    team_tot = float(tt.at[real_team, f"team_{name}"])
                    if team_tot <= 0:
                        continue
                    if g is None:
                        hist_share = np.nan
                    else:
                        mu = statline_model._recency_weighted(
                            g[vol_stat].to_numpy()) * part
                        tpg = recent_pg.get((hist_team, name), 0.0)
                        hist_share = mu / tpg if tpg > 1e-9 else np.nan
                    rows.append({
                        "season": season, "week": week, "player_id": pid,
                        "player_name": r.player_name, "position": pos,
                        "component": name, "team": real_team,
                        "salary": float(r.salary),
                        "realized_share": float(rr[vol_stat]) / team_tot,
                        "hist_share": hist_share,
                        "games_played": gp, "participation": part,
                    })
        print(f"  {season}: {len(weeks)} week(s) panelled.")
    panel = pd.DataFrame(rows)
    if panel.empty:
        raise SystemExit(
            "Player panel is empty. Check data/salaries_{site}_rotoguru_*.csv "
            "and data/weekly_stats_*.parquet exist (Sessions 10.0 and 1.2).")
    return panel


def load_lines(site: str) -> pd.DataFrame:
    if not GAMES_CACHE.exists():
        raise SystemExit(
            f"{GAMES_CACHE} not found. Run the backtest harness once (it "
            f"downloads nflverse games.csv) before fitting -- the team-volume "
            f"specification needs real historical lines.")
    g = pd.read_csv(GAMES_CACHE)
    g = g[g["total_line"].notna() & g["spread_line"].notna()]
    rows = []
    for r in g.itertuples():
        total, spread = float(r.total_line), float(r.spread_line)
        rows.append({"season": int(r.season), "week": int(r.week),
                     "team_norm": normalize_team(r.home_team, site),
                     "team_spread": -spread, "over_under": total,
                     "implied_total": total / 2 + spread / 2})
        rows.append({"season": int(r.season), "week": int(r.week),
                     "team_norm": normalize_team(r.away_team, site),
                     "team_spread": spread, "over_under": total,
                     "implied_total": total / 2 - spread / 2})
    return pd.DataFrame(rows)


def build_team_panel(site: str, seasons: list) -> pd.DataFrame:
    lines = load_lines(site)
    rows = []
    for season in seasons:
        stats = season_history(season)

        # Session 15.2b -- opp_rush_allowed: the upcoming opponent's own
        # recency-weighted carries-allowed, built the identical way
        # hist_rush is built below, just pointed at the opponent's
        # defensive side instead of this team's own offense. Probed and
        # validated on real, held-out data (2022-2024, then re-checked on
        # this exact 2014-17/2018-21 production split) before shipping --
        # see SESSION_LOG.md Session 15.2b for both runs' numbers.
        #
        # Built once per season (dict of each team's own week-indexed
        # rush-defense history), not inside the per-team-per-week loop
        # below -- the loop already re-slices `hist` on every iteration
        # for the existing hist_pass/hist_rush/hist_recv computation, and
        # doing the same for a second team (the opponent) inside that
        # loop would be the same quadratic-rebuild mistake
        # build_player_panel()'s own comment already flags a few
        # functions up.
        rush_def = _team_rush_and_opponent(stats)
        rush_def_by_team = {t: g.set_index("week").sort_index()
                            for t, g in rush_def.groupby("team")}

        for week in sorted(stats["week"].unique().tolist()):
            hist = stats[stats["week"] < week]
            tt = team_totals(stats[stats["week"] == week])
            for team in tt.index:
                th = hist[hist["team"] == team]
                rec = {"season": season, "week": week,
                       "team_norm": normalize_team(team, site),
                       "real_pass": float(tt.at[team, "team_pass"]),
                       "real_rush": float(tt.at[team, "team_rush"]),
                       "real_recv": float(tt.at[team, "team_recv"])}
                if th.empty:
                    rec.update(hist_pass=np.nan, hist_rush=np.nan, hist_recv=np.nan)
                else:
                    pw = th.groupby("week")[["attempts", "carries", "targets"]] \
                           .sum().sort_index()
                    rec.update(
                        hist_pass=statline_model._recency_weighted(
                            pw["attempts"].to_numpy()),
                        hist_rush=statline_model._recency_weighted(
                            pw["carries"].to_numpy()),
                        hist_recv=statline_model._recency_weighted(
                            pw["targets"].to_numpy()))

                team_row = rush_def_by_team.get(team)
                opp = (team_row.at[week, "opponent_team"]
                       if team_row is not None and week in team_row.index
                       else None)
                opp_row = rush_def_by_team.get(opp) if opp is not None else None
                if opp_row is None:
                    rec["opp_rush_allowed"] = np.nan
                else:
                    prior_allowed = opp_row.loc[opp_row.index < week,
                                                "carries_allowed"].dropna().to_numpy()
                    rec["opp_rush_allowed"] = statline_model._recency_weighted(
                        prior_allowed) if len(prior_allowed) else np.nan

                rows.append(rec)
    tp = pd.DataFrame(rows)
    merged = tp.merge(lines, on=["season", "week", "team_norm"], how="left")
    # Session 10.4's bug #1 was a merge that lost 13% of its panel SILENTLY,
    # because an inner join treats a team-code mismatch as an absence rather
    # than an error. Same guard, same 2% threshold.
    lost = float(merged["implied_total"].isna().mean())
    if lost > 0.02:
        raise SystemExit(
            f"Team/line merge lost {lost:.1%} of rows (limit 2%) -- the "
            f"Session 10.4 bug #1 signature (era team codes in games.csv vs "
            f"current codes in weekly_stats). Fix normalization before fitting.")
    return merged.dropna(subset=["implied_total"])


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------

def ols(X, y):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = max(X.shape[0] - X.shape[1], 1)
    s2 = float(resid @ resid) / dof
    se = np.sqrt(np.clip(np.diag(np.linalg.pinv(X.T @ X)) * s2, 0.0, None))
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, beta / se, 0.0)
    return beta, se, t


def r2(y, yhat):
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - float(((y - yhat) ** 2).sum()) / ss_tot if ss_tot > 0 else float("nan")


def fit_share_curve(df: pd.DataFrame, n_bins=SHARE_N_BINS,
                    min_rows=SHARE_MIN_BIN_ROWS):
    """Bin -> weighted bin means -> isotonic -> piecewise-linear knots.
    Same construction as fit_salary_anchor.fit_position(), on `share`."""
    d = df.sort_values("salary").reset_index(drop=True)
    n = len(d)
    if n < min_rows * 2:
        return None
    try:
        d["_bin"] = pd.qcut(d["salary"], q=max(min(n_bins, n // min_rows), 2),
                            duplicates="drop", labels=False)
    except ValueError:
        d["_bin"] = 0
    grp = d.groupby("_bin").agg(salary_mean=("salary", "mean"),
                                share_mean=("realized_share", "mean"),
                                rows=("realized_share", "size")) \
           .sort_values("salary_mean").reset_index(drop=True)
    if len(grp) < 3:
        return None
    xs = grp["salary_mean"].to_numpy(float)
    ys = isotonic_pava(grp["share_mean"].to_numpy(float),
                       grp["rows"].to_numpy(float))
    xs, ys, _ = _add_top_endpoint_knot(xs, ys, float(d["salary"].max()))
    if not all(ys[i] <= ys[i + 1] + 1e-9 for i in range(len(ys) - 1)):
        raise SystemExit(
            "Isotonic share fit came out non-monotone -- that is a bug in "
            "isotonic_pava(), not a data property. Not shipping this curve.")
    return {"n": int(n),
            "salary_min": float(d["salary"].min()),
            "salary_max": float(d["salary"].max()),
            "share_mean": round(float(d["realized_share"].mean()), 5),
            "knots": [[round(float(x), 1), round(float(y), 5)]
                      for x, y in zip(xs, ys)]}


def fit_team_volume(tp: pd.DataFrame, component: str, test: pd.DataFrame) -> dict:
    """Both specifications for one component. Decision #7 of volume_prior.py:
    total and spread are always fit together, never one alone.

    Session 15.2b: RUSH's with_history spec additionally carries
    opp_rush_allowed (the upcoming opponent's own recency-weighted
    carries-allowed) -- probed on real, held-out data and confirmed
    non-redundant with the existing three terms (max correlation 0.30)
    before shipping; see SESSION_LOG.md Session 15.2b for the full probe.
    PASS and RECV are deliberately unchanged: an equivalent opponent-
    strength term was never probed for those components, and this
    project's standing rule is not to ship an unprobed change even when
    the mechanism looks like it should generalize.
    """
    real, histc = f"real_{component}", f"hist_{component}"
    out = {"league_mean": round(float(tp[real].mean()), 4)}
    extra = ["opp_rush_allowed"] if component == "rush" else []

    with_h = tp.dropna(subset=[histc] + extra)
    Xf_cols = [np.ones(len(with_h)), with_h[histc].to_numpy(float),
              with_h["implied_total"].to_numpy(float),
              with_h["team_spread"].to_numpy(float)]
    Xf_cols += [with_h[c].to_numpy(float) for c in extra]
    Xf = np.column_stack(Xf_cols)
    beta, se, t = ols(Xf, with_h[real].to_numpy(float))
    th = test.dropna(subset=[histc] + extra)
    Xt_cols = [np.ones(len(th)), th[histc].to_numpy(float),
              th["implied_total"].to_numpy(float),
              th["team_spread"].to_numpy(float)]
    Xt_cols += [th[c].to_numpy(float) for c in extra]
    Xt = np.column_stack(Xt_cols)
    out["with_history"] = {
        "terms": ["const", "hist", "implied_total", "spread"] + extra,
        "beta": [round(float(b), 6) for b in beta],
        "t": [round(float(x), 3) for x in t],
        "n": int(len(with_h)),
        "r2_oos": round(r2(th[real].to_numpy(float), Xt @ beta), 5) if len(th) else None,
    }

    Xf2 = np.column_stack([np.ones(len(tp)), tp["implied_total"].to_numpy(float),
                           tp["team_spread"].to_numpy(float)])
    beta2, se2, t2 = ols(Xf2, tp[real].to_numpy(float))
    Xt2 = np.column_stack([np.ones(len(test)), test["implied_total"].to_numpy(float),
                           test["team_spread"].to_numpy(float)])
    out["no_history"] = {
        "terms": ["const", "implied_total", "spread"],
        "beta": [round(float(b), 6) for b in beta2],
        "t": [round(float(x), 3) for x in t2],
        "n": int(len(tp)),
        "r2_oos": round(r2(test[real].to_numpy(float), Xt2 @ beta2), 5) if len(test) else None,
    }
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Fit the Session 10.3b volume prior (share curves, team "
                    "volume, role-change slope).")
    ap.add_argument("--site", choices=["dk", "fd"], default="dk")
    ap.add_argument("--fit-seasons", type=int, nargs="+",
                    default=DEFAULT_FIT_SEASONS)
    ap.add_argument("--test-seasons", type=int, nargs="+",
                    default=MEASUREMENT_SEASONS,
                    help="Used ONLY to report out-of-sample diagnostics; "
                         "nothing from these seasons enters the artifact.")
    ap.add_argument("--n-bins", type=int, default=SHARE_N_BINS)
    ap.add_argument("--min-bin-rows", type=int, default=SHARE_MIN_BIN_ROWS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    # Decision #3 -- the same warning fit_dst_model.py prints, for the same
    # reason. Session 10.3a's threefold in-sample inflation is the precedent.
    overlap = sorted(set(args.fit_seasons) & set(MEASUREMENT_SEASONS))
    if overlap:
        print("\n  !! FIT INCLUDES MEASUREMENT-WINDOW SEASONS "
              f"{overlap}.\n"
              "     This is correct for a PRODUCTION refit and wrong for a\n"
              "     measurement. Any 2018-21 number produced against this\n"
              "     artifact is IN-SAMPLE and must be logged as the shipped\n"
              "     configuration's numbers, not as evidence. (Session 10.3a\n"
              "     measured a threefold inflation from exactly this.)\n")

    seasons = sorted(set(args.fit_seasons) | set(args.test_seasons))
    print("=" * 78)
    print(f"SESSION 10.3b VOLUME PRIOR -- site={args.site}  "
          f"fit={args.fit_seasons}")
    print("=" * 78)

    print("\nBuilding player panel...")
    panel = build_player_panel(args.site, seasons)
    fit_p = panel[panel["season"].isin(args.fit_seasons)]
    test_p = panel[panel["season"].isin(args.test_seasons)].copy()
    _ov = sorted(set(args.fit_seasons) & set(args.test_seasons))
    print(f"  Panel: {len(panel):,} rows "
          f"({len(fit_p):,} fit / {len(test_p):,} diagnostic"
          f"{'; THESE OVERLAP on ' + str(_ov) if _ov else ''}).")

    # --- 1. share curves --------------------------------------------------
    wanted = sorted({(p, c) for p, cs in COMPONENTS.items()
                     for c, _v, _y, _t in cs})
    curves, unfitted = {}, []
    for pos, comp in wanted:
        sub = fit_p[(fit_p["position"] == pos) & (fit_p["component"] == comp)]
        k = fit_share_curve(sub, args.n_bins, args.min_bin_rows) if len(sub) else None
        if k is None:
            unfitted.append((pos, comp, len(sub)))
        else:
            curves[f"{pos}|{comp}"] = k

    print(f"\n--- Share curves: {len(curves)}/{len(wanted)} fitted ---")
    for key, c in sorted(curves.items()):
        kx = [k[0] for k in c["knots"]]
        ky = [k[1] for k in c["knots"]]
        print(f"  {key:<9} n={c['n']:>6}  knots={len(kx):>2}  "
              f"${kx[0]:>6.0f}->{ky[0]:.3f} .. ${kx[-1]:>6.0f}->{ky[-1]:.3f}")
    if unfitted:
        # Decision #4: omitted, never faked, and never silent.
        print(f"\n  NOT FITTED (thin data; share_from_salary returns 0.0 for "
              f"these):")
        for pos, comp, n in unfitted:
            print(f"    {pos}/{comp}  n={n:,}")

    # --- 2. team volume ---------------------------------------------------
    print("\nBuilding team panel...")
    tpanel = build_team_panel(args.site, seasons)
    fit_t = tpanel[tpanel["season"].isin(args.fit_seasons)]
    test_t = tpanel[tpanel["season"].isin(args.test_seasons)]
    print(f"  Team panel: {len(fit_t):,} fit / {len(test_t):,} diagnostic "
          f"team-weeks.")

    team_volume = {}
    print("\n--- Team volume (out-of-sample R2; both Vegas terms always) ---")
    for comp in ("pass", "rush", "recv"):
        team_volume[comp] = fit_team_volume(fit_t, comp, test_t)
        wh, nh = team_volume[comp]["with_history"], team_volume[comp]["no_history"]
        print(f"  {comp:<5} league mean {team_volume[comp]['league_mean']:6.2f}")
        # Session 15.2b: printed generically off each spec's own `terms`
        # list (skipping the const at index 0) rather than a hardcoded
        # hist/it/spread triple -- rush's with_history spec now carries a
        # 4th term (opp_rush_allowed) and a hardcoded print would have
        # silently hidden its t-stat from every future fit run's output.
        wh_t = "  ".join(f"{name}={tt:+.2f}"
                         for name, tt in zip(wh["terms"][1:], wh["t"][1:]))
        print(f"        with history  R2 {wh['r2_oos']}  t: {wh_t}")
        nh_t = "  ".join(f"{name}={tt:+.2f}"
                         for name, tt in zip(nh["terms"][1:], nh["t"][1:]))
        print(f"        no history    R2 {nh['r2_oos']}  t: {nh_t}   "
              f"<- week 1 path")

    # --- 3. role-change slope --------------------------------------------
    # Decision #6 -- CROSS-FIT INSIDE THE FIT WINDOW, never on the
    # measurement seasons. FOUND BY REVIEWING THE FIRST REAL BACKTEST.
    #
    # The first version of this script fit the slope on `--test-seasons`,
    # reasoning that price_share is out-of-sample there with respect to the
    # share curves. It is -- but the slope then goes into the artifact and
    # gets MEASURED on those same seasons, which is precisely the error
    # Session 10.3a caught in itself and measured at a threefold inflation.
    # Any 2018-21 backtest run against such an artifact is partly in-sample
    # and cannot be quoted as evidence.
    #
    # Fixed by splitting the FIT window: curves are fit on its earlier half,
    # applied to its later half, and the slope is fit there. Every input to
    # the shipped artifact then predates the measurement window entirely.
    # The curves that actually ship are still fit on the whole fit window --
    # only the slope needs the internal split.
    fs = sorted(args.fit_seasons)
    if len(fs) >= 2:
        cut = max(1, len(fs) // 2)
        slope_fit_seasons, slope_eval_seasons = fs[:cut], fs[cut:]
    else:
        slope_fit_seasons = slope_eval_seasons = fs
        print("\n  !! Only one fit season: the role slope cannot be cross-fit "
              "and will be\n     IN-SAMPLE. Treat any measurement against it "
              "with suspicion.")

    inner_curves = {}
    inner_fit = panel[panel["season"].isin(slope_fit_seasons)]
    for pos, comp in wanted:
        sub = inner_fit[(inner_fit["position"] == pos)
                        & (inner_fit["component"] == comp)]
        k = fit_share_curve(sub, args.n_bins, args.min_bin_rows) if len(sub) else None
        if k is not None:
            inner_curves[f"{pos}|{comp}"] = k

    slope_p = panel[panel["season"].isin(slope_eval_seasons)].copy()
    slope_p["price_share"] = np.nan
    for key, c in inner_curves.items():
        pos, comp = key.split("|")
        m = (slope_p["position"] == pos) & (slope_p["component"] == comp)
        if m.any():
            slope_p.loc[m, "price_share"] = interp_knots(
                c["knots"], slope_p.loc[m, "salary"].to_numpy(float))
    ev = slope_p.dropna(subset=["price_share", "hist_share", "realized_share"])
    # The claim below has to be CHECKED, not asserted. On a production refit
    # (--fit-seasons = all eight) the split puts the slope's eval half ON the
    # measurement seasons, at which point the old unconditional "nothing from
    # the measurement window enters the artifact" line was simply false -- a
    # message that lies is worse than no message, and this project's whole
    # fail-loud convention exists to stop exactly that.
    slope_overlap = sorted(set(slope_eval_seasons) & set(MEASUREMENT_SEASONS))
    print(f"\n  Role slope cross-fit: curves on {slope_fit_seasons} -> slope "
          f"fit on {slope_eval_seasons} ({len(ev):,} rows).")
    if slope_overlap:
        print(f"  !! The slope's eval half OVERLAPS the measurement window on "
              f"{slope_overlap}.\n     Correct for a PRODUCTION refit, and "
              f"DISQUALIFYING for a measurement: any\n     backtest over those "
              f"seasons against this artifact is partly in-sample.")
    else:
        print(f"     No measurement-window season ({MEASUREMENT_SEASONS}) "
              f"contributes to the artifact.")

    # The catalogued-case validation still needs price_share on the
    # DIAGNOSTIC seasons, using the SHIPPED curves. Reported only.
    for key, c in curves.items():
        pos, comp = key.split("|")
        m = (test_p["position"] == pos) & (test_p["component"] == comp)
        if m.any():
            test_p.loc[m, "price_share"] = interp_knots(
                c["knots"], test_p.loc[m, "salary"].to_numpy(float))
    if "price_share" not in test_p.columns:
        test_p["price_share"] = np.nan
    diag = test_p.dropna(subset=["price_share", "hist_share", "realized_share"])
    if len(ev) < 500:
        raise SystemExit(
            f"Only {len(ev)} rows available to fit the role-change slope. "
            f"That coefficient drives volume_prior.py's participation "
            f"override -- refusing to ship a slope fit on this little.")
    div = (ev["price_share"] - ev["hist_share"]).to_numpy(float)
    resid = (ev["realized_share"] - ev["hist_share"]).to_numpy(float)
    X = np.column_stack([np.ones(len(ev)), div])
    beta, se, t = ols(X, resid)
    role = {"slope": round(float(beta[1]), 6),
            "intercept": round(float(beta[0]), 6),
            "se": round(float(se[1]), 6), "t": round(float(t[1]), 3),
            "n": int(len(ev)), "r2": round(r2(resid, X @ beta), 5),
            "cross_fit_curves_on": slope_fit_seasons,
            "cross_fit_slope_on": slope_eval_seasons,
            "fit_on": ("cross-fit INSIDE the fit window (decision #6) -- no "
                       "measurement-window season contributes")}
    print(f"\n--- Role-change slope (volume_prior.py decision #4) ---")
    print(f"  slope {role['slope']:+.4f}  (SE {role['se']:.4f}, "
          f"t {role['t']:+.2f})  R2 {role['r2']:+.4f}  n={role['n']:,}")
    if abs(role["t"]) < 4.0:
        print("  !! WARNING: this slope is weak. volume_prior.py decision #3's "
              "participation\n     override rests entirely on it -- reconsider "
              "shipping the flag rather than\n     shipping it against a "
              "coefficient this uncertain.")

    # --- write ------------------------------------------------------------
    artifact = {
        "schema_version": volume_prior.SCHEMA_VERSION,
        "site": args.site,
        "fitted_on": date.today().isoformat(),
        "fit_seasons": sorted(int(s) for s in args.fit_seasons),
        "diagnostic_seasons": sorted(int(s) for s in args.test_seasons),
        "fit_source": ("salaries_{site}_rotoguru_*.csv joined to "
                       "weekly_stats_*.parquet (decision #1)"),
        "share_curves": curves,
        "unfitted_pairs": [f"{p}|{c}" for p, c, _n in unfitted],
        "team_volume": team_volume,
        "role_change": role,
        "params": {"n_bins": args.n_bins, "min_bin_rows": args.min_bin_rows},
        "caveats": [
            "BOOTSTRAP DATA: RotoGuru tops out at 2021 while this project's "
            "current-state weekly_stats is 2025. Fit on a real but OLDER "
            "market -- refit from live exports once real weeks accumulate.",
            "Prior-season team-volume carryover is deliberately NOT used: it "
            "measured worse than the league mean (volume_prior.py decision "
            "#6). This does NOT apply to dst_model.py's decision #15.",
            "Share curves are fit on players who recorded a stat line that "
            "week, so a listed-but-inactive player is absent from the fit. "
            "Availability is handled separately by status_check.py, same "
            "split as fit_salary_anchor.py decision #4.",
        ],
    }
    out_path = Path(args.out) if args.out else volume_prior.prior_path(args.site)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2))
    print(f"\nWrote {out_path}")

    # --- validation: the three catalogued cases --------------------------
    print("\n--- Session 10.3a's catalogued role-change cases ---")
    print("    (participation BEFORE -> AFTER the decision #3 override)")
    art = json.loads(out_path.read_text())
    found = 0
    for season, week, surname, team in CATALOGUED_CASES:
        sub = diag[(diag["season"] == season) & (diag["week"] == week)
                 & (diag["team"] == team) & (diag["component"] == "pass")
                 & diag["player_name"].astype(str).str.contains(
                     surname, case=False, na=False)]
        for r in sub.itertuples():
            part_eff, flag = volume_prior.role_change_participation(
                art, [r.participation], [r.hist_share], [r.price_share])
            found += 1
            print(f"    {season} wk{week} {r.team} {r.player_name}: "
                  f"realized {r.realized_share:.3f} | hist {r.hist_share:.3f} "
                  f"| price {r.price_share:.3f}   "
                  f"part {r.participation:.2f} -> {part_eff[0]:.2f}"
                  f"{'  [FLAGGED]' if flag[0] else '  [not flagged]'}")
    if not found:
        print("    None matched. Expected ONLY if 2021 is outside "
              "--test-seasons; otherwise\n    the name/team join has broken "
              "and this validation is not actually running.")

    print("\nNext: measure it, holdout first.")
    print(f"  python3 scripts/backtest_harness.py --site {args.site} "
          f"--season 2018 2019 2020 2021 --all-weeks --num-lineups 20 \\")
    print(f"      --engine statline --volume-prior --dst-model distributional")
    print("Then refit on all eight seasons for production before going live.")


if __name__ == "__main__":
    main()
