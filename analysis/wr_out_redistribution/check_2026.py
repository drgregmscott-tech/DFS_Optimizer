"""2026 wk1-3 second check: apply apply_wr_replacement (shipped params) post hoc to the live main-slate
final_projections with status pinned to the Friday Out/Doubtful report (injuries_2026), score vs actuals.
Note: wk1-3 live CSVs are the as-shipped live projections (not current-code rebuilds)."""
import io, contextlib, sys
from pathlib import Path
import numpy as np, pandas as pd
D = Path(__file__).resolve().parent; CODE = D.parents[1]; DATA = Path(r"C:\Users\gmsco\Desktop\DFS_Optimizer")
sys.path.insert(0, str(CODE / "scripts"))
import statline_model as sm
inj = pd.read_parquet(DATA / "analysis/inactives/raw/injuries_2026.parquet")
S = pd.read_parquet(CODE / "data/weekly_stats_2026.parquet").fillna(0)
S["dk"] = S.fantasy_points_ppr + 3 * (S.rushing_yards >= 100) + 3 * (S.receiving_yards >= 100) + 3 * (S.passing_yards >= 300)
act = S.set_index(["week", "player_id"]).dk
rows = []
for w, f in ((1, "13Sep2026"), (2, "20Sep2026"), (3, "27Sep2026")):
    pool = pd.read_csv(CODE / f"output/final_projections_dk_dk_classic_wk{w}_main_{f}.csv", dtype={"player_id": str})
    pool = pool[pool.position.isin(["RB", "WR", "TE"])]
    o = inj[(inj.week == w) & inj.report_status.isin(["Out", "Doubtful"])]
    stat = pd.DataFrame({"player_id": o.gsis_id.astype(str), "team": o.team, "position": o.position, "status": "OUT"})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = sm.apply_wr_replacement(pool, 2026, w, stat)
    print(buf.getvalue().strip() or f"wk{w}: no fire")
    x = r[(r.wrw_wr_delta_pts > 0) & (r.sigma > 0) & (r.final_projection > 0)].copy(); x["week"] = w
    rows.append(x)
X = pd.concat(rows)
X["act"] = [act.get((w, p), np.nan) for w, p in zip(X.week, X.player_id)]
played = X.act.notna(); X["act"] = X.act.fillna(0)
for nm, g in (("played", X[played]), ("all incl DNP as 0", X)):
    e0 = g.act - g.final_projection; e1 = g.act - g.final_projection - g.wrw_wr_delta_pts
    print(f"{nm}: n={len(g)} off bias {e0.mean():+.2f} MAE {e0.abs().mean():.2f} RMSE {np.sqrt((e0**2).mean()):.2f} | "
          f"on bias {e1.mean():+.2f} MAE {e1.abs().mean():.2f} RMSE {np.sqrt((e1**2).mean()):.2f}")
print(X[["week", "team", "player_name", "salary", "final_projection", "wrw_wr_delta_pts", "act"]].round(1).to_string(index=False))
