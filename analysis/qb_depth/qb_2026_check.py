"""Apply QB recal candidates to 2026 wk1-3 pre-lock production files (props on for wk3) and compare to DK actuals
(+ FC for wk1-2 main). Research; no FC data inside."""
import io, json, os, subprocess
import numpy as np, pandas as pd
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(R, "data/fc_history/derived")
cand = json.load(open(os.path.join(D, "qb_depth/qb_recal_candidate_2026-09-29.json")))["coef"]
# 'lin' variant full fit for comparison
X = pd.read_parquet(os.path.join(D, "qb_depth/qb_recal_eval.parquet")); TR = X[(X.q >= 8) & X.played & (X.attempts + X.carries >= 5)]
lin = np.polyfit(TR.q, TR.act, 1)
FILES = [(1, "main", "cefc761", "13Sep2026"), (2, "main", "7e57cfe", "20Sep2026"), (3, "main", "84fbb02", "27Sep2026"),
         (3, "early", "0dba72d", "27Sep2026"), (3, "afternoon", "2c01488", "27Sep2026")]
F = pd.read_parquet(os.path.join(D, "model_vs_fc/frame.parquet")); F = F[(F.season == 2026) & (F.pos == "QB")][["week", "player_id", "fc"]]
rows = []
for wk, sub, sha, dt in FILES:
    txt = subprocess.run(["git", "-C", R, "show", f"{sha}:output/final_projections_dk_dk_classic_wk{wk}_{sub}_{dt}.csv"], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    o = pd.read_csv(io.StringIO(txt), dtype={"player_id": str}); o = o[o.position == "QB"]
    a = pd.read_csv(os.path.join(R, f"data/results_raw_dk_2026_wk{wk}" + ("" if (wk < 3 and sub == "main") else "_" + sub) + ".csv")); a["player_name"] = a.player_name.str.strip()
    o = o.merge(a[["player_name", "actual_fpts"]], on="player_name", how="left")
    o["week"], o["sub"] = wk, sub
    rows.append(o)
P = pd.concat(rows).drop_duplicates(["week", "sub", "player_id"]).reset_index(drop=True)
P["act"] = P.actual_fpts
P["spread"] = P.over_under / 2 - P.implied_total
P["rush_pts"] = .1 * P.proj_rush_yd + 6 * P.proj_rush_td
g = P.final_projection >= 8
P["cand"] = np.where(g, cand["a"] + cand["b_proj"] * P.final_projection + cand["c_implied"] * P.implied_total + cand["d_spread"] * P.spread + cand["e_rush_pts"] * P.rush_pts, P.final_projection)
P["lin"] = np.where(g, np.polyval(lin, P.final_projection), P.final_projection)
P = P.merge(F.drop_duplicates(["week", "player_id"]), on=["week", "player_id"], how="left")
g = P.final_projection >= 8
Q = P[g & P.act.notna() & (P.act != 0)]
mae = lambda d, c: (d[c] - d.act).abs().mean()
print("2026 QB proj>=8 with nonzero actual: MAE (bias)  prod | cand | lin | FC(main wk1-2)")
for (wk, sub), d in Q.groupby(["week", "sub"]):
    print(wk, sub, len(d), " | ".join(f"{mae(d,c):.2f}({(d[c]-d.act).mean():+.1f})" for c in ["final_projection", "cand", "lin"]),
          f"| FC {mae(d.dropna(subset=['fc']),'fc'):.2f}" if d.fc.notna().any() else "")
W3 = Q[Q.week == 3].drop_duplicates("player_name")
print("wk3 unique QBs", len(W3), " | ".join(f"{mae(W3,c):.2f}({(W3[c]-W3.act).mean():+.1f})" for c in ["final_projection", "cand", "lin"]))
print("wk3 corr prod/cand/lin", " / ".join(f"{W3[c].corr(W3.act):.3f}" for c in ["final_projection", "cand", "lin"]))
# bootstrap wk3 unique
rng = np.random.default_rng(1); e0 = (W3.final_projection - W3.act).abs().values; e1 = (W3.cand - W3.act).abs().values
bs = [np.mean((e0 - e1)[i]) for i in (rng.integers(0, len(W3), len(W3)) for _ in range(4000))]
print("wk3 gain cand vs prod %.2f [%.2f, %.2f]" % (np.mean(e0 - e1), *np.percentile(bs, [2.5, 97.5])))
print(W3.sort_values("final_projection", ascending=False)[["player_name", "salary", "final_projection", "cand", "lin", "act", "implied_total", "spread", "rush_pts"]].round(1).to_string(index=False))
