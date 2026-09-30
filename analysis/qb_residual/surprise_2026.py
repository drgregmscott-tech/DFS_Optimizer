"""2026 wk1-3 production files: QBs who scored >=8 DK but were projected <8 (surprise starters we missed)."""
import io, os, subprocess, pandas as pd
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FILES = [(1, "main", "cefc761", "13Sep2026"), (2, "main", "7e57cfe", "20Sep2026"), (3, "main", "84fbb02", "27Sep2026"),
         (3, "early", "0dba72d", "27Sep2026"), (3, "afternoon", "2c01488", "27Sep2026")]
for wk, sub, sha, dt in FILES:
    o = pd.read_csv(io.StringIO(subprocess.run(["git", "-C", R, "show", f"{sha}:output/final_projections_dk_dk_classic_wk{wk}_{sub}_{dt}.csv"], capture_output=True, text=True, encoding="utf-8").stdout))
    o = o[o.position == "QB"]
    a = pd.read_csv(os.path.join(R, f"data/results_raw_dk_2026_wk{wk}" + ("" if (wk < 3 and sub == "main") else "_" + sub) + ".csv")); a["player_name"] = a.player_name.str.strip()
    o = o.merge(a[["player_name", "actual_fpts"]], on="player_name", how="left")
    m = o[(o.actual_fpts >= 8) & (o.final_projection < 8)]
    print(wk, sub, "starters(act>=8):", (o.actual_fpts >= 8).sum(), " missed:", m[["player_name", "salary", "final_projection", "actual_fpts"]].values.tolist())
