"""Feasibility dry run: ONE past week (DK 2019 wk10), leak-free build, in-process.

Writes ONLY under analysis/backtest_feasibility/out/. Nothing in data/ or output/
is written: every module-level OUTPUT_DIR is monkeypatched, the vegas file is
derived from data/nflverse_games.csv (read-only) into the out dir, and the
matchup_factors file is COPIED (read-only source) into the out dir.

Two arms:
  prod   = production flags (--volume-prior --sigma-recalibration, stack on,
           distributional DST, props off) but with the 2026 depth-chart snapshot
           and output/player_status_{week}_* files LEFT IN (shows the leak).
  clean  = same, with load_depth_chart / load_injury_status stubbed to empty.
"""
import shutil, sys
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

SITE, SEASON, WEEK = "dk", 2019, 6
SLATE = f"rotoguru_{SEASON}_wk{WEEK}"

import build_projections as bp
import build_projections_statline as bps
import backtest_harness as bh
import statline_model as sm

for m in (bp, bps, bh):
    m.OUTPUT_DIR = OUT
games = pd.read_csv(REPO / "data" / "nflverse_games.csv")
bh.build_vegas_file(games, SITE, SEASON, WEEK)                   # -> OUT/vegas_implied_totals_10.csv
shutil.copy(REPO / "output" / f"matchup_factors_{SITE}_{SEASON}_{WEEK}.csv", OUT)

real_depth, real_inj = sm.load_depth_chart, sm.load_injury_status


def run(label, stub):
    sm.load_depth_chart = (lambda: pd.DataFrame(columns=["player_id", "team", "position", "depth_rank"])) if stub else real_depth
    sm.load_injury_status = (lambda week: pd.DataFrame(columns=["player_id", "team", "position", "status"])) if stub else real_inj
    df = bps.build_statline_projections(
        SITE, SEASON, WEEK, SLATE, vegas_slate_id=str(WEEK),
        dst_model_mode="distributional", use_volume_prior=True, sigma_recal=True,
        ignore_played_week=True, props_weight=0.0, use_stack=True)
    df.to_csv(OUT / f"proj_{label}_{SLATE}.csv", index=False)
    return df


prod = run("prod_leaky", stub=False)
clean = run("clean", stub=True)

# actuals: nflverse weekly stats -> DK points (PPR + DK bonuses)
ws = pd.read_parquet(REPO / "data" / f"weekly_stats_{SEASON}.parquet")
ws = ws[(ws.season_type == "REG") & (ws.week == WEEK)].copy()
f = lambda c: ws[c].fillna(0) if c in ws else 0
ws["dk_actual"] = (f("fantasy_points_ppr") + 3 * (f("passing_yards") >= 300)
                   + 3 * (f("rushing_yards") >= 100) + 3 * (f("receiving_yards") >= 100))
act = ws[["player_id", "dk_actual"]]

lines = []
for label, d in (("prod_leaky", prod), ("clean", clean)):
    s = d[d.position.isin(["QB", "RB", "WR", "TE"])].merge(act, on="player_id", how="left")
    s["dk_actual"] = s["dk_actual"].fillna(0.0)
    s = s[s.final_projection > 0]
    e = s.final_projection - s.dk_actual
    lines.append(f"{label}: n={len(s)} bias={e.mean():+.2f} MAE={e.abs().mean():.2f} "
                 f"pearson={s.final_projection.corr(s.dk_actual):.3f} "
                 f"spearman={s.final_projection.corr(s.dk_actual, method='spearman'):.3f}")
m = prod[["player_id", "final_projection"]].merge(
    clean[["player_id", "final_projection"]], on="player_id", suffixes=("_prod", "_clean"))
diff = (m.final_projection_prod - m.final_projection_clean).abs()
lines.append(f"players whose projection differs prod vs clean (>0.05): {(diff > 0.05).sum()} of {len(m)}; "
             f"max abs diff {diff.max():.2f}")
(OUT / "dry_run_summary.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
