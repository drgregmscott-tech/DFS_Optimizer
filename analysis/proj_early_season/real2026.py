"""2026 wk1-2: PRE-LOCK production projections (git cefc761 / 7e57cfe) vs FC vs actual, largest lineup-relevant
disagreements with cause tags (research only; no FC data inside). Prints; caller copies summary."""
import io, os, subprocess, numpy as np, pandas as pd
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")); OUT = os.path.join(R, "data/fc_history/derived/proj_early_season")
def gshow(c, f):
    return pd.read_csv(io.StringIO(subprocess.run(["git", "show", f"{c}:output/{f}"], cwd=R, capture_output=True, text=True, encoding="utf-8", check=True).stdout), dtype={"player_id": str})
X = pd.read_parquet(os.path.join(OUT, "players.parquet")); X = X[X.season == 2026]
G = pd.read_csv(os.path.join(R, "analysis/proj_recheck/guarded_accuracy_frame.csv"), dtype={"player_id": str})
G = G[G["sub"] == "main"].drop_duplicates(["week", "player_id"])[["week", "player_id", "FIX"]]
out = []
for wk, c, f in [(1, "cefc761", "final_projections_dk_dk_classic_wk1_main_13Sep2026.csv"), (2, "7e57cfe", "final_projections_dk_dk_classic_wk2_main_20Sep2026.csv")]:
    o = gshow(c, f)[["player_id", "final_projection", "games_played", "participation_effective", "proj_pass_att", "proj_targets", "proj_rush_att", "injury_status"]]
    o = o.rename(columns={"final_projection": "PROD", "proj_pass_att": "p_pa", "proj_targets": "p_tgt", "proj_rush_att": "p_ra"})
    m = X[X.week == wk].drop(columns=["games_played"]).merge(o, on="player_id").merge(G[G.week == wk].drop(columns="week"), on="player_id", how="left")
    out.append(m)
M = pd.concat(out, ignore_index=True)
M["gap"] = M.PROD - M.fc; M["err_prod"] = M.PROD - M.act; M["err_fc"] = M.fc - M.act
Rl = M[(M[["PROD", "fc"]].max(axis=1) >= 8)]
print("n", len(Rl), "MAE prod %.2f fc %.2f harness %.2f FIX(guarded) %.2f" % ((Rl.PROD - Rl.act).abs().mean(), (Rl.fc - Rl.act).abs().mean(), (Rl.final_projection - Rl.act).abs().mean(), (Rl.FIX - Rl.act).abs().mean()))
print("bias prod %.2f fc %.2f; by pos:" % ((Rl.PROD - Rl.act).mean(), (Rl.fc - Rl.act).mean()))
print(Rl.groupby(["week", "pos"]).apply(lambda h: pd.Series({"n": len(h), "prod": (h.PROD - h.act).abs().mean(), "fc": (h.fc - h.act).abs().mean(), "fix": (h.FIX - h.act).abs().mean(), "bias_prod": (h.PROD - h.act).mean(), "bias_fc": (h.fc - h.act).mean()})).round(2).to_string())
def cause(r):
    t = []
    if r.pos == "QB" and r.PROD < r.fc - 3: t.append("QB-dilution(pre-guard)")
    if r.injury_status == "OUT" or (r.PROD <= 0.5 and r.fc > 5): t.append("zeroed/OUT")
    if not r.played: t.append("DNP")
    if r.rookie: t.append("rookie")
    if r.mover: t.append("mover")
    if r.week == 1 and r.ptype == "role_chg(ex-post)": t.append("role-chg")
    if r.week == 2 and r.games_played <= 1: t.append("1-game-history")
    return ",".join(t) or "noise/eff"
T = Rl.reindex(Rl.gap.abs().sort_values(ascending=False).index).head(25).copy()
T["cause"] = T.apply(cause, axis=1); T["closer"] = np.where((T.PROD - T.act).abs() < (T.fc - T.act).abs(), "ours", "FC")
print(T[["week", "player", "pos", "salary", "PROD", "FIX", "fc", "act", "games_played", "participation_effective", "p_pa", "p_tgt", "p_ra", "ptype", "cause", "closer"]].round(1).to_string(index=False))
print(T.cause.value_counts().to_string()); print("closer:", T.closer.value_counts().to_dict())
