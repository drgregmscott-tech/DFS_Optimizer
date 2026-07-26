"""
measure_dst.py
===============

Session 10.4 -- measures the DST projection at the DST SLOT specifically,
which is what that card's second validation line asks for and what the
lineup-level harness cannot isolate.

Why a separate script
---------------------
`backtest_harness.py` grades whole lineups. A DST fills 1 of 9 slots and
contributes roughly 6.5 of ~120 lineup points, so a real improvement in DST
projection is diluted to near-invisibility in a lineup percentile. Session
10.1's own note applies: 17 weeks against a ~16-point week-to-week SD cannot
detect an effect smaller than about 9 percentile points, and no DST change
will ever be that large.

So the two validations answer different questions and BOTH are required:

  * this script  -- is the DST projection itself better? (accuracy, ordering,
                    calibration, measured against real graded DST actuals)
  * the harness  -- does that translate into better lineups, or at least not
                    worse? (`--dst-model distributional`)

Numbered decisions (continuing dst_model.py's numbering):

 19. GRADED AGAINST REAL ROTOGURU DST ACTUALS, NOT AGAINST A RECONSTRUCTION.
     `rotoguru_actuals_{site}_{season}.csv` carries real DK/FD graded DST
     scores -- 544 rows a season, 8 seasons for DK. That is the same target
     the harness scores lineups against, so a gain here is denominated in the
     same units as a gain there.

 20. THE LEGACY ARM USES THE REAL SALARY FILE'S `AvgPointsPerGame` WHEN IT
     EXISTS. That column IS the legacy model's only real input
     (`build_projections.py` decision #5a), so reading it from the real
     `salaries_{site}_rotoguru_{season}_wk{week}.csv` reproduces the legacy
     arm exactly rather than approximately.

     When a salary file is absent the arm falls back to a season-to-date mean
     of the real graded actuals -- which is what DK's AvgPointsPerGame is --
     and says so LOUDLY in the output. A silent fallback here would let a
     reconstruction masquerade as the real baseline, which is precisely the
     failure mode this project keeps hitting.

 21. FOUR METRICS, BECAUSE MAE ALONE IS THE WRONG SCOREBOARD -- the same
     argument Phase 10's design intro makes at the lineup level:

       MAE / RMSE   accuracy
       Spearman     ORDERING, which is what actually drives selection: the
                    optimizer picks the best DST it can afford, so being
                    right about the ranking matters more than being right
                    about the level
       calibration  mean projected vs mean realized (a model biased high on
                    every defense re-ranks nothing but corrupts the
                    lineup-level objective in Session 10.5)
       chosen-DST   the realized points of the defense each arm would
                    actually have STARTED. This is the one that maps to
                    money, and it is reported per week so its noise is
                    visible rather than hidden in an average.

 22. SIGMA IS CHECKED FOR CALIBRATION, NOT JUST PRODUCED. Session 10.5's
     objective subtracts `lambda * sigma`, so a sigma that is systematically
     too small makes every defense look falsely safe. Reported as the ratio
     of realized RMSE to mean projected sigma; 1.0 is calibrated, below 1.0
     means the model is over-stating its own uncertainty.

Usage:
  python3 scripts/measure_dst.py --site dk --seasons 2018 2019 2020 2021
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dst_model  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"


def load_games() -> pd.DataFrame:
    path = DATA_DIR / "games.parquet"
    if not path.exists():
        raise SystemExit(f"{path} not found -- run ingest_historical.py first.")
    return pd.read_parquet(path)


def week_vegas(games: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    wk = games[(games["season"] == season) & (games["week"] == week)
               & (games["game_type"] == "REG")]
    rows = []
    for g in wk.itertuples():
        if pd.isna(g.total_line) or pd.isna(g.spread_line):
            continue
        for me, opp, spread in ((g.home_team, g.away_team, -g.spread_line),
                                (g.away_team, g.home_team, g.spread_line)):
            rows.append({"team": me, "opponent": opp,
                         "implied_total": round(g.total_line / 2 - spread / 2, 2),
                         "over_under": float(g.total_line)})
    return pd.DataFrame(rows)


def legacy_avg_points(site: str, season: int, week: int,
                      actuals: pd.DataFrame) -> tuple:
    """Decision #20. Returns (series indexed by team, source_label)."""
    path = DATA_DIR / f"salaries_{site}_rotoguru_{season}_wk{week}.csv"
    if path.exists():
        sal = pd.read_csv(path)
        pos = sal.get("position_upper", sal.get("Position"))
        dst = sal[pos.astype(str).str.upper().isin(["DST", "DEF", "D"])]
        if not dst.empty and "AvgPointsPerGame" in dst.columns:
            team_col = "normalized_team" if "normalized_team" in dst.columns else "TeamAbbrev"
            s = pd.to_numeric(dst["AvgPointsPerGame"], errors="coerce")
            return (pd.Series(s.to_numpy(), index=dst[team_col].to_numpy())
                    .groupby(level=0).mean(), "real_salary_file")
    prior = actuals[(actuals["season"] == season) & (actuals["week"] < week)]
    if prior.empty:
        return pd.Series(dtype=float), "no_prior_data"
    return prior.groupby("team")["actual_points"].mean(), "RECONSTRUCTED_from_actuals"


def load_dst_actuals(site: str, seasons) -> pd.DataFrame:
    frames = []
    for season in seasons:
        path = DATA_DIR / f"rotoguru_actuals_{site}_{season}.csv"
        if not path.exists():
            raise SystemExit(
                f"{path.name} not found -- run "
                f"ingest_rotoguru.py --site {site} --season {season}.")
        a = pd.read_csv(path)
        a = a[a["rotoguru_position"].astype(str).str.upper().isin(["DEF", "DST", "D"])].copy()
        # Decision #12 -- RotoGuru spells relocated teams the era-correct way.
        a["team"] = dst_model.canonical_team(a["team"]).to_numpy()
        frames.append(a[["season", "week", "team", "actual_points"]])
    return pd.concat(frames, ignore_index=True)


def run(site: str, seasons, sims: int, seed: int, min_week: int) -> pd.DataFrame:
    games = load_games()
    model = dst_model.load_model()
    actuals = load_dst_actuals(site, seasons)

    sources, rows = set(), []
    for season in seasons:
        for week in sorted(actuals[actuals["season"] == season]["week"].unique()):
            if week < min_week:
                continue
            vegas = week_vegas(games, season, int(week))
            if vegas.empty:
                continue
            act = actuals[(actuals["season"] == season) & (actuals["week"] == week)]
            teams = sorted(set(vegas["team"]) & set(act["team"]))
            if len(teams) < 8:
                continue

            feat = dst_model.build_features(season, int(week), teams, vegas,
                                            model, games=games)
            sim = dst_model.simulate(feat, site, model, n_sims=sims, seed=seed + int(week))

            avg, src = legacy_avg_points(site, season, int(week), actuals)
            sources.add(src)
            league_avg_implied = float(vegas["implied_total"].mean())
            opp_imp = (vegas.drop_duplicates("team").set_index("team")["opponent"]
                       .map(vegas.drop_duplicates("team").set_index("team")["implied_total"]))

            df = sim[["team", "final_projection", "sigma"]].rename(
                columns={"final_projection": "new_proj", "sigma": "new_sigma"})
            df["legacy_proj"] = (df["team"].map(avg).astype(float)
                                 * (league_avg_implied / df["team"].map(opp_imp).astype(float)))
            df = df.merge(act[["team", "actual_points"]], on="team", how="inner")
            df["season"], df["week"] = season, int(week)
            rows.append(df)

    if not rows:
        raise SystemExit("measure_dst: no weeks produced a comparison.")
    out = pd.concat(rows, ignore_index=True).dropna(subset=["legacy_proj", "new_proj"])
    out.attrs["legacy_source"] = sorted(sources)
    return out


def report(df: pd.DataFrame, site: str) -> None:
    src = df.attrs.get("legacy_source", [])
    print(f"\n{'='*74}\nSession 10.4 -- DST slot measurement ({site.upper()})")
    print(f"{len(df):,} defense-weeks over "
          f"{df.groupby(['season','week']).ngroups} weeks, seasons "
          f"{sorted(df.season.unique())}")
    if any("RECONSTRUCTED" in s for s in src):
        print("  !! LEGACY ARM IS RECONSTRUCTED (decision #20): no real salary "
              "files found,\n     AvgPointsPerGame derived from graded actuals. "
              "Re-run where\n     data/salaries_*_rotoguru_*.csv exist for the "
              "real legacy baseline.")
    else:
        print("  legacy arm read from the real salary files' AvgPointsPerGame.")
    print("=" * 74)

    a = df["actual_points"].to_numpy(float)
    print(f"\n{'metric':<26}{'legacy':>12}{'distributional':>16}{'delta':>10}")
    print("-" * 74)
    res = {}
    for name, col in (("legacy", "legacy_proj"), ("new", "new_proj")):
        p = df[col].to_numpy(float)
        res[name] = {
            "MAE": float(np.abs(p - a).mean()),
            "RMSE": float(np.sqrt(((p - a) ** 2).mean())),
            "Spearman": float(stats.spearmanr(p, a).statistic),
            "Pearson": float(np.corrcoef(p, a)[0, 1]),
            "mean_proj": float(p.mean()),
        }
    for m in ("MAE", "RMSE", "Spearman", "Pearson", "mean_proj"):
        d = res["new"][m] - res["legacy"][m]
        print(f"{m:<26}{res['legacy'][m]:>12.4f}{res['new'][m]:>16.4f}{d:>+10.4f}")
    print(f"{'mean ACTUAL':<26}{a.mean():>12.4f}{a.mean():>16.4f}")

    # Decision #21 -- the chosen-DST comparison, paired by week.
    print(f"\n{'-'*74}\nChosen-DST (each arm starts its own top-projected defense)")
    per_week = []
    for (s, w), g in df.groupby(["season", "week"]):
        per_week.append({
            "season": s, "week": w,
            "legacy": float(g.loc[g["legacy_proj"].idxmax(), "actual_points"]),
            "new": float(g.loc[g["new_proj"].idxmax(), "actual_points"]),
        })
    pw = pd.DataFrame(per_week)
    diff = pw["new"] - pw["legacy"]
    t = stats.ttest_rel(pw["new"], pw["legacy"])
    wins = int((diff > 0).sum())
    ties = int((diff == 0).sum())
    print(f"  legacy mean {pw['legacy'].mean():.3f} | "
          f"distributional mean {pw['new'].mean():.3f} | "
          f"delta {diff.mean():+.3f}")
    print(f"  paired t = {t.statistic:+.2f} (p = {t.pvalue:.3f}) over {len(pw)} weeks")
    print(f"  weeks better/worse/tied: {wins} / {len(pw)-wins-ties} / {ties}")

    # Decision #22 -- sigma calibration.
    print(f"\n{'-'*74}\nSigma calibration (Session 10.5 depends on this)")
    rmse = float(np.sqrt(((df['new_proj'] - a) ** 2).mean()))
    ms = float(df["new_sigma"].mean())
    print(f"  realized RMSE {rmse:.3f} / mean projected sigma {ms:.3f} = "
          f"{rmse/ms:.3f}   (1.00 = calibrated)")
    print(f"  sigma range {df['new_sigma'].min():.2f} - {df['new_sigma'].max():.2f} "
          f"(the 10.3a placeholder was a function of the projection alone)")
    print("=" * 74)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="dk", choices=["dk", "fd"])
    ap.add_argument("--seasons", type=int, nargs="+", default=[2018, 2019, 2020, 2021])
    ap.add_argument("--sims", type=int, default=dst_model.DEFAULT_SIMS)
    ap.add_argument("--seed", type=int, default=dst_model.DEFAULT_SEED)
    ap.add_argument("--min-week", type=int, default=1,
                    help="Skip weeks below this (default 1 -- the model is "
                         "designed to handle week 1 via prior-season carryover).")
    ap.add_argument("--save", type=Path, default=None)
    args = ap.parse_args()

    df = run(args.site, args.seasons, args.sims, args.seed, args.min_week)
    report(df, args.site)
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.save, index=False)
        print(f"\nPer-defense rows written to {args.save}")


if __name__ == "__main__":
    main()
