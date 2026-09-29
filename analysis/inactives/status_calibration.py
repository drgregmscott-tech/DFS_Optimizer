"""Inactives / availability measurement (research only; writes analysis/inactives/*.csv + calib_report.txt).

Q1: what does each final injury-report designation (nflverse injuries: Out/Doubtful/Questionable/none) imply
    for P(inactive at kickoff) and P(near-zero DK points), by position, game weekday, final practice status?
Q2: on OUR projection universe (regenerated 2021-25 ourproj, injuries stubbed; proj>8), how many were inactive,
    and how much of that was knowable from the Friday report vs only on game day (no designation / Questionable)?
Q3: 2026 wk1-3: last pre-lock production status file vs actual inactive.
Outcome definitions: inactive = nflverse weekly roster status != ACT for that week OR no stat row in weekly_stats;
  near-zero = actual DK points < 2 (FC score when available, else nflverse PPR as proxy).
"""
import glob, os, re
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
H = os.path.join(R, "analysis", "inactives")
OUT = open(os.path.join(H, "calib_report.txt"), "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.write(s + "\n")
SK = ["QB", "RB", "WR", "TE"]

def rosters(s):
    p = os.path.join(R, "data", f"weekly_rosters_{s}.parquet")
    if not os.path.exists(p): p = os.path.join(H, "raw", f"weekly_rosters_{s}.parquet")
    r = pd.read_parquet(p, columns=["season", "week", "gsis_id", "status", "game_type"])
    return r[r.game_type == "REG"].drop_duplicates(["week", "gsis_id"])

games = pd.read_csv(os.path.join(R, "data", "nflverse_games.csv"))
games = games[games.game_type == "REG"]
gd = pd.concat([games[["season", "week", "home_team", "weekday", "gametime"]].rename(columns={"home_team": "team"}),
                games[["season", "week", "away_team", "weekday", "gametime"]].rename(columns={"away_team": "team"})])
TEAMFIX = {"LAR": "LA", "JAC": "JAX", "OAK": "LV", "SD": "LAC", "STL": "LA", "WSH": "WAS"}

rows = []
for s in range(2016, 2026):
    inj = pd.read_parquet(os.path.join(H, "raw", f"injuries_{s}.parquet"))
    inj = inj[(inj.game_type == "REG") & inj.position.isin(SK)]
    inj = inj.drop_duplicates(["week", "gsis_id"], keep="last")
    st = pd.read_parquet(os.path.join(R, "data", f"weekly_stats_{s}.parquet"),
                         columns=["player_id", "week", "season_type", "fantasy_points_ppr", "position"])
    st = st[st.season_type == "REG"]
    ro = rosters(s)
    ro = ro.merge(pd.read_parquet(os.path.join(R, "data", f"weekly_rosters_{s}.parquet") if os.path.exists(os.path.join(R, "data", f"weekly_rosters_{s}.parquet")) else os.path.join(H, "raw", f"weekly_rosters_{s}.parquet"),
                                  columns=["week", "gsis_id", "position", "team", "game_type"]).query("game_type=='REG'").drop_duplicates(["week", "gsis_id"])[["week", "gsis_id", "position", "team"]],
                  on=["week", "gsis_id"])
    ro = ro[ro.position.isin(SK) & ro.status.isin(["ACT", "INA", "RES"])]  # on a 53/IR during week
    # prior-3-played-game avg ppr as relevance (no lookahead)
    st = st.sort_values("week")
    st["trail"] = st.groupby("player_id").fantasy_points_ppr.transform(lambda x: x.shift().rolling(3, min_periods=1).mean())
    trail = st[["player_id", "week", "trail"]]
    # carry forward last trail value for weeks the player missed
    d = ro.merge(inj[["week", "gsis_id", "report_status", "practice_status"]], on=["week", "gsis_id"], how="left")
    d = d.merge(st[["player_id", "week", "fantasy_points_ppr"]].rename(columns={"player_id": "gsis_id"}), on=["week", "gsis_id"], how="left")
    last = st[["player_id", "week", "fantasy_points_ppr"]].rename(columns={"player_id": "gsis_id"})
    d = d.sort_values("week")
    d["pts_hist"] = d.fantasy_points_ppr
    d["trail"] = d.groupby("gsis_id").pts_hist.transform(lambda x: x.shift().rolling(3, min_periods=1).mean())
    d["trail"] = d.groupby("gsis_id").trail.ffill()
    d["season"] = s
    rows.append(d)
d = pd.concat(rows)
d["team"] = d.team.replace(TEAMFIX)
d = d.merge(gd, on=["season", "week", "team"], how="left")
d["inactive"] = (d.status != "ACT") | d.fantasy_points_ppr.isna()
d["nearzero"] = d.fantasy_points_ppr.fillna(0) < 2
d["desig"] = d.report_status.fillna("None").replace({"Note": "None"})
d.loc[(d.status == "RES") & (d.desig == "None"), "desig"] = "IR/Reserve(no desig)"
d["prac"] = d.practice_status.fillna("-").str.replace(" Participation in Practice", "").str.replace("Did Not Participate In Practice", "DNP")
d["rel"] = d.trail >= 8
d.to_csv(os.path.join(H, "status_panel_2016_2025.csv"), index=False)

def tab(x, by):
    g = x.groupby(by).agg(n=("inactive", "size"), p_inactive=("inactive", "mean"), p_nearzero=("nearzero", "mean"),
                          mean_pts=("fantasy_points_ppr", lambda v: v.fillna(0).mean()))
    return g.round(3)

P("== Q1 designation calibration, 2016-2025 REG, skill players on 53/IR, relevant = trailing-3 PPR >= 8")
rel = d[d.rel]
P(tab(rel, "desig").to_string()); P()
P("-- Questionable/Doubtful by final practice status (relevant)")
P(tab(rel[rel.desig.isin(["Questionable", "Doubtful"])], ["desig", "prac"]).to_string()); P()
P("-- Questionable by position (relevant)")
P(tab(rel[rel.desig == "Questionable"], ["position"]).to_string()); P()
P("-- Questionable by game weekday (relevant)")
P(tab(rel[rel.desig == "Questionable"], ["weekday"]).to_string()); P()
P("-- Questionable by era (relevant)")
rel = rel.assign(era=np.where(rel.season >= 2021, "2021-25", "2016-20"))
P(tab(rel[rel.desig == "Questionable"], ["era"]).to_string()); P()
P("-- Questionable & ACTIVE: points vs trailing (does Q lower output when they play?)")
qa = rel[(rel.desig == "Questionable") & ~rel.inactive]; na = rel[(rel.desig == "None") & ~rel.inactive]
P(f"Q active: n={len(qa)} pts/trail={qa.fantasy_points_ppr.sum()/qa.trail.sum():.3f} | None active: n={len(na)} pts/trail={na.fantasy_points_ppr.sum()/na.trail.sum():.3f}")
P()
P("== Where relevant inactives come from (information timing), 2021-2025 relevant")
r2 = rel[(rel.season >= 2021) & rel.inactive]
nwk = rel[rel.season >= 2021][["season", "week"]].drop_duplicates().shape[0]
t = r2.desig.value_counts()
P(pd.DataFrame({"n": t, "per_week": (t / nwk).round(2), "share": (t / t.sum()).round(3)}).to_string())
P("Timing key: Out/Doubtful/IR = known by Fri (Sat for MNF) final report; Questionable = resolved at ~T-90 inactives"
  " (or earlier by reporters); None = no designation -> game-day surprise (illness, healthy scratch, late add) or stale roster")

# ---------- Q2: our projection universe ----------
P(); P("== Q2 ourproj (2021-25 regenerated, injuries stubbed) proj>8 on DK main slates")
op = []
for f in glob.glob(os.path.join(R, "data/fc_history/derived/ourproj/proj_*.csv")):
    x = pd.read_csv(f, usecols=["season", "week", "player_id", "position", "final_projection", "salary"])
    op.append(x)
op = pd.concat(op); op = op[op.position.isin(SK) & (op.season <= 2025)].drop_duplicates(["season", "week", "player_id"])
op = op.merge(d[["season", "week", "gsis_id", "desig", "prac", "inactive", "fantasy_points_ppr", "status"]],
              left_on=["season", "week", "player_id"], right_on=["season", "week", "gsis_id"], how="left")
op["inactive"] = op.inactive.fillna(True)  # not on 53-roster panel (cut/PS) -> treat as out
op["desig"] = op.desig.fillna("NotOnRoster")
op["act"] = op.fantasy_points_ppr.fillna(0)
big = op[op.final_projection > 8]
nsl = big[["season", "week"]].drop_duplicates().shape[0]
P(f"rows {len(big)} over {nsl} slates; inactive {big.inactive.sum()} ({big.inactive.mean():.3f}), per slate {big.inactive.sum()/nsl:.1f}")
g = big.groupby("desig").agg(n=("inactive", "size"), inactive=("inactive", "sum"), p_inact=("inactive", "mean"),
                            mean_proj=("final_projection", "mean"), mean_act=("act", "mean")).round(3)
P(g.to_string())
bi = big[big.inactive]
P(f"inactive proj>8: projected pts wasted {bi.final_projection.sum():.0f} total, {bi.final_projection.sum()/nsl:.1f}/slate, mean proj {bi.final_projection.mean():.1f}")
P("share of inactive proj>8 knowable from Friday report (Out/Doubtful/IR): "
  f"{bi.desig.isin(['Out','Doubtful','IR/Reserve(no desig)']).mean():.3f}; Questionable: {(bi.desig=='Questionable').mean():.3f}; "
  f"no designation: {(bi.desig=='None').mean():.3f}; not on roster: {(bi.desig=='NotOnRoster').mean():.3f}")
big.to_csv(os.path.join(H, "ourproj_gt8_status.csv"), index=False)
bi2 = bi.assign(kind=np.select([bi.desig.isin(["Out","Doubtful","IR/Reserve(no desig)"]), bi.desig=="Questionable", bi.desig=="NotOnRoster",
                                (bi.desig=="None") & (bi.status=="INA"), (bi.desig=="None") & (bi.position=="QB")],
                               ["friday_known","questionable","not_on_roster(cut/PS/trade)","surprise_INA_no_desig","active_backupQB_no_snaps"], "active_nonQB_no_stats"))
P("-- inactive proj>8 by kind (per slate)"); P((bi2.kind.value_counts()/nsl).round(2).to_string())

# ---------- probability-weighted availability backtest ----------
P(); P("== Availability-weighting backtest on ourproj proj>8 2021-25 (player-level, actual PPR proxy)")
# fit on 2016-2020 panel, apply to 2021-25 (out of sample)
fit = d[d.rel & (d.season <= 2020)]
pq = fit[fit.desig == "Questionable"].groupby("prac").inactive.mean().to_dict()
pd_ = fit[fit.desig == "Doubtful"].inactive.mean()
pn = fit[fit.desig == "None"].inactive.mean()
P(f"fit 2016-20: P(inact|Doubtful)={pd_:.3f} P(inact|None)={pn:.3f} P(inact|Q,prac)={ {k: round(v,3) for k,v in pq.items()} }")
def avail(r, mode):
    if r.desig in ("Out", "IR/Reserve(no desig)"): return 0.0
    if mode == "hard_outdoubt" and r.desig == "Doubtful": return 0.0
    if mode == "hard_outdoubt": return 1.0
    if r.desig == "Doubtful": return 1 - pd_
    if r.desig == "Questionable": return 1 - pq.get(r.prac, np.mean(list(pq.values())))
    return 1.0
ev = big[big.desig != "NotOnRoster"].copy()
for m in ["none", "hard_outdoubt", "prob"]:
    a = 1.0 if m == "none" else ev.apply(lambda r: avail(r, m), axis=1)
    ev["p_" + m] = ev.final_projection * a
    e = ev["p_" + m] - ev.act
    P(f"{m:14s} RMSE {np.sqrt((e**2).mean()):.3f} MAE {e.abs().mean():.3f} bias {e.mean():.3f}")
P("(pipeline-equivalent is hard_outdoubt; 'prob' multiplies Q/D projections by fitted availability. "
  "Note: for lineup EV the right use is availability-weighted mean for ranking, not shading Q players who are later confirmed active.)")
OUT.close()
