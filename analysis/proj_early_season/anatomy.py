"""Player-level anatomy: where FC beats OUR projections, early (wk1-4) vs later (research only; no FC data inside).
Reads git-ignored FC-derived files; writes data/fc_history/derived/proj_early_season/{players.parquet, anatomy.txt}.
    python analysis/proj_early_season/anatomy.py
"""
import os, glob
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DER = os.path.join(R, "data/fc_history/derived")
OUT = os.path.join(DER, "proj_early_season")
LOG = open(os.path.join(OUT, "anatomy.txt"), "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n")
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
SK = ["QB", "RB", "WR", "TE"]

fc = pd.read_csv(os.path.join(DER, "fc_master_mapped.csv"), low_memory=False, dtype={"player_id": str})
fc = fc[(fc.site == "dk") & (fc.slate_kind == "classic") & (fc.slate_raw == "main") & fc.player_id.notna() & fc.pos.isin(SK)]
fc = fc.drop_duplicates(["season", "week", "player_id"])[["season", "week", "player_id", "player", "pos", "team", "salary", "fc_proj", "score", "inj", "pdepth"]]

ws = {s: pd.read_parquet(os.path.join(R, f"data/weekly_stats_{s}.parquet")) for s in range(2013, 2027)}
ws = {s: d[d[("season_type" if "season_type" in d else "game_type")] == "REG"] for s, d in ws.items()}
act = pd.concat([d[d.season >= 2021][["season", "week", "player_id", "attempts", "carries", "targets", "receptions", "team"]] for d in ws.values()])
act = act.rename(columns={"attempts": "a_pass", "carries": "a_rush", "targets": "a_tgt", "receptions": "a_rec", "team": "a_team"})

cols = ["season", "week", "player_id", "final_projection", "proj_pass_att", "proj_rush_att", "proj_targets", "games_played"]
def rd(pat):
    return pd.concat([pd.read_csv(f, dtype={"player_id": str}, usecols=cols) for f in glob.glob(pat)]).drop_duplicates(["season", "week", "player_id"])
base = rd(os.path.join(DER, "ourproj/proj_*.csv"))
X = fc.merge(base, on=["season", "week", "player_id"], how="inner")
for arm in ["prod", "carry"]:
    a = rd(os.path.join(OUT, arm, "proj_*.csv"))[["season", "week", "player_id", "final_projection", "proj_pass_att", "proj_rush_att", "proj_targets"]]
    X = X.merge(a.add_suffix("_" + arm).rename(columns={f"season_{arm}": "season", f"week_{arm}": "week", f"player_id_{arm}": "player_id"}),
                on=["season", "week", "player_id"], how="left")
# prod: wk1 = prod arm, wk2+ = base (production has no carryover after wk1)
for c in ["final_projection", "proj_pass_att", "proj_rush_att", "proj_targets"]:
    X[c + "_prod"] = np.where(X.week == 1, X[c + "_prod"], X[c])
    X[c + "_carry"] = np.where(X.week <= 4, X[c + "_carry"], X[c])
X = X.merge(act, on=["season", "week", "player_id"], how="left")
X["played"] = X.a_pass.notna()
X["act"] = X.score.fillna(0).where(X.played, 0.0)
X["fc"] = X.fc_proj.fillna(0).clip(lower=0)

# ---- player types (from PRIOR-season data only, except 'role_chg' which is ex-post, flagged)
prev_rows, prev_team, prev_opp, ever = {}, {}, {}, {}
seen = set()
for s in range(2013, 2027):
    if s >= 2021:
        p = ws[s - 1]
        g = p.sort_values("week").groupby("player_id")
        prev_team[s] = g.team.last(); prev_rows[s] = g.size()
        prev_opp[s] = (g.carries.sum() + g.targets.sum() + g.attempts.sum()) / g.size()
        ever[s] = set(seen)
    seen |= set(ws[s].player_id)
X["rookie"] = [pid not in ever[s] for s, pid in zip(X.season, X.player_id)]
X["prev_gp"] = [prev_rows[s].get(pid, 0) for s, pid in zip(X.season, X.player_id)]
X["mover"] = [(not r) and (pid in prev_team[s].index) and (prev_team[s][pid] != t) for s, pid, t, r in zip(X.season, X.player_id, X.team.replace({"JAC": "JAX", "LAR": "LA", "WSH": "WAS", "LVR": "LV"}), X.rookie)]
X["opp_act"] = X.a_rush.fillna(0) + X.a_tgt.fillna(0) + X.a_pass.fillna(0)
cur4 = X[X.played & (X.week <= 4)].groupby(["season", "player_id"]).opp_act.mean()
X["cur4_opp"] = [cur4.get((s, p), np.nan) for s, p in zip(X.season, X.player_id)]
X["prev_opp"] = [prev_opp[s].get(p, np.nan) for s, p in zip(X.season, X.player_id)]
r = X.cur4_opp / X.prev_opp
X["ptype"] = np.select([X.rookie, X.mover, (X.prev_gp < 4), (r < 0.67) | (r > 1.5)], ["rookie", "mover", "prev<4gp", "role_chg(ex-post)"], "stable_vet")
X["tier"] = pd.cut(X.salary, [0, 3999, 5499, 6999, 99999], labels=["<4k", "4-5.4k", "5.5-6.9k", "7k+"])
X["wb"] = pd.cut(X.week, [0, 1, 2, 4, 8, 99], labels=["wk1", "wk2", "wk3-4", "wk5-8", "wk9+"])
X["slate"] = X.season * 100 + X.week
X.to_parquet(os.path.join(OUT, "players.parquet"))

# relevant population: played, and at least one projection >=5 (lineup-relevant)
V = X[X.played & ((X.fc >= 5) | (X.final_projection >= 5))].copy()
def stats(g, arms=("final_projection", "final_projection_prod", "final_projection_carry")):
    o = {"n": len(g)}
    o["mae_fc"] = (g.fc - g.act).abs().mean()
    for a in arms:
        k = {"final_projection": "base", "final_projection_prod": "prod", "final_projection_carry": "carry"}[a]
        if g[a].notna().all():
            o[f"mae_{k}"] = (g[a] - g.act).abs().mean(); o[f"bias_{k}"] = (g[a] - g.act).mean()
            o[f"rho_{k}"] = g.groupby("slate").apply(lambda h: h[a].corr(h.act, method="spearman")).mean() if len(g) > 30 else np.nan
    o["bias_fc"] = (g.fc - g.act).mean()
    o["rho_fc"] = g.groupby("slate").apply(lambda h: h.fc.corr(h.act, method="spearman")).mean() if len(g) > 30 else np.nan
    return pd.Series(o)

P("Population: played & (FC>=5 or ours>=5). mae/bias vs actual DK pts; rho = mean within-slate Spearman.")
P("base = regenerated harness; prod = production-faithful (wk1 prior-season lookback; wk2+ == base); carry = candidate fix wk1-4\n")
P("== by week bucket, all seasons"); P(V.groupby("wb", observed=True).apply(stats).round(2).to_string())
P("\n== by week bucket x season (edge = mae_base - mae_fc; edge_prod)")
t = V.groupby(["season", "wb"], observed=True).apply(stats)
t["edge_base"] = t.mae_base - t.mae_fc; t["edge_prod"] = t.mae_prod - t.mae_fc; t["edge_carry"] = t.mae_carry - t.mae_fc
P(t[["n", "mae_fc", "mae_base", "mae_prod", "mae_carry", "edge_base", "edge_prod", "edge_carry", "rho_fc", "rho_base", "rho_prod", "rho_carry"]].round(2).to_string())
E = V[V.week <= 4]; L8 = V[V.week >= 5]
for key in ["pos", "ptype", "tier"]:
    P(f"\n== wk1-4 by {key} (all seasons)"); P(E.groupby(key, observed=True).apply(stats).round(2).to_string())
    P(f"-- wk5+ by {key}"); P(L8.groupby(key, observed=True).apply(stats, arms=("final_projection",)).round(2).to_string())
    tt = E.groupby(["season", key], observed=True).apply(stats)
    P(f"-- wk1-4 edge (mae_prod - mae_fc) by season x {key}"); P((tt.mae_prod - tt.mae_fc).unstack(key).round(2).to_string())
    P(f"-- wk1-4 edge (mae_carry - mae_fc) by season x {key}"); P((tt.mae_carry - tt.mae_fc).unstack(key).round(2).to_string())

# ---- component: volume error (ours only; FC has no components)
V["opp_proj"] = V.proj_rush_att + V.proj_targets + V.proj_pass_att
V["opp_proj_prod"] = V.proj_rush_att_prod + V.proj_targets_prod + V.proj_pass_att_prod
V["opp_proj_carry"] = V.proj_rush_att_carry + V.proj_targets_carry + V.proj_pass_att_carry
for a in ["", "_prod", "_carry"]:
    V["verr" + a] = V["opp_proj" + a] - V.opp_act
    # efficiency: pts per projected opp vs actual pts per actual opp, error in pts holding actual volume
    V["ppo" + a] = V["final_projection" + a] / V["opp_proj" + a].replace(0, np.nan)
    V["eff_err" + a] = (V["ppo" + a] - V.act / V.opp_act.replace(0, np.nan)) * V.opp_act
P("\n== component decomposition (skill, ours): volume = rush_att+targets+pass_att; eff_err = (proj pts/opp - act pts/opp) * act opp")
comp = V.groupby(["wb", "pos"], observed=True).agg(n=("act", "size"), vmae=("verr", lambda s: s.abs().mean()), vbias=("verr", "mean"),
    vmae_prod=("verr_prod", lambda s: s.abs().mean()), vmae_carry=("verr_carry", lambda s: s.abs().mean()),
    emae=("eff_err", lambda s: s.abs().mean()), ebias=("eff_err", "mean"), emae_prod=("eff_err_prod", lambda s: s.abs().mean()),
    emae_carry=("eff_err_carry", lambda s: s.abs().mean()))
P(comp.round(2).to_string())
LOG.close()
