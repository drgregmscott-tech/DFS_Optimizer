"""Who-replaces-whom frame. Every (team, week) 2016-2026 where an RB/WR/TE with real usage (played the team's previous
game, trailing carry share >= .20 or target share >= .12) is OUT. Rows = each active RB/WR/TE teammate x the event.
Status known pre-game: FRI = Out/Doubtful/IR designation or RES; T90 = official game-day inactive (also pre-lock).
Only pre-game info goes into features (trailing window = the player's last <=4 appearances within the team's last 8 games)."""
from pathlib import Path; import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]; OUT = Path(__file__).parent
S = []
for y in range(2015, 2027):
    s = pd.read_parquet(R/f"data/weekly_stats_{y}.parquet")
    s = s[s.season_type == "REG"]
    S.append(s[["player_id","player_display_name","position","season","week","team","carries","targets","rushing_yards",
                "receiving_yards","passing_yards","fantasy_points_ppr"]])
S = pd.concat(S, ignore_index=True).fillna(0)
S["dk"] = S.fantasy_points_ppr + 3*(S.rushing_yards>=100) + 3*(S.receiving_yards>=100) + 3*(S.passing_yards>=300)
tv = S.groupby(["season","week","team"])[["carries","targets"]].sum().rename(columns={"carries":"tcar","targets":"ttgt"}).reset_index()
tv = tv.sort_values(["team","season","week"]); tv["g"] = tv.groupby("team").cumcount()
S = S.merge(tv, on=["season","week","team"])
S = S[S.position.isin(["RB","WR","TE"])].copy()
gi = tv.set_index(["season","week","team"]).g

# ---- status: 2016-25 panel; 2026 built the same way from rosters + injury reports
P = pd.read_csv(R/"analysis/inactives/status_panel_2016_2025.csv")
P = P[P.position.isin(["RB","WR","TE"])]
P["fri"] = P.desig.isin(["Out","Doubtful","IR/Reserve(no desig)"]) | (P.status == "RES")
P = P.rename(columns={"gsis_id":"player_id"})[["season","week","team","player_id","position","inactive","fri"]]
r = pd.read_parquet(R/"data/weekly_rosters_2026.parquet"); r = r[r.position.isin(["RB","WR","TE"])&(r.week<=3)]
inj = pd.read_parquet(R/"analysis/inactives/raw/injuries_2026.parquet")
od = set(map(tuple, inj[inj.report_status.isin(["Out","Doubtful"])][["week","gsis_id"]].values))
r = r.assign(inactive=r.status!="ACT", fri=[(w,g) in od or st=="RES" for w,g,st in zip(r.week,r.gsis_id,r.status)])
P = pd.concat([P, r.rename(columns={"gsis_id":"player_id"})[["season","week","team","player_id","position","inactive","fri"]]])
P = P.dropna(subset=["player_id"]).drop_duplicates(["season","week","player_id"])

# ---- trailing usage per player at each team-game
S = S.sort_values(["player_id","team","g"])
def trailing(team, season, week, pids):
    pass
key = S.set_index(["player_id","team"]).sort_index()
rows = []
evs = 0
tvi = tv.set_index(["season","week","team"])
for (season, week, team), grp in P.groupby(["season","week","team"]):
    if (season, week, team) not in tvi.index: continue  # bye / no game
    g = tvi.loc[(season, week, team)].g
    past = S[(S.team == team) & (S.g < g) & (S.g >= g-8)]
    if past.empty: continue
    past = past.sort_values("g").groupby("player_id").tail(4)
    ag = past.groupby("player_id").agg(car=("carries","sum"), tgt=("targets","sum"), tcar=("tcar","sum"), ttgt=("ttgt","sum"),
                                       ppg=("dk","mean"), n=("dk","size"), last_g=("g","max"), pos=("position","last"))
    ag["sh_car"] = ag.car/ag.tcar.clip(lower=1); ag["sh_tgt"] = ag.tgt/ag.ttgt.clip(lower=1)
    tp = tv[(tv.team==team)&(tv.g<g)&(tv.g>=g-4)]; vcar, vtgt = tp.tcar.mean(), tp.ttgt.mean()
    st = grp.set_index("player_id")
    for flag in ("fri", "inactive"):
        outs = [p for p in st.index[st[flag]] if p in ag.index and ag.loc[p,"last_g"] == g-1
                and (ag.loc[p,"sh_car"] >= .20 or ag.loc[p,"sh_tgt"] >= .12)]
        if not outs: continue
        O = ag.loc[outs]
        Vc, Vt = O.sh_car.sum(), O.sh_tgt.sum()
        mc = O.sh_car.idxmax(); mt = O.sh_tgt.idxmax()
        act = st.index[~st.inactive & ~st.fri]
        cand = [p for p in act if p in ag.index]
        if not cand: continue
        C = ag.loc[cand].copy()
        cur = S[(S.team==team)&(S.g==g)].set_index("player_id")
        tcar_real = float(tvi.loc[(season,week,team)].tcar); ttgt_real = float(tvi.loc[(season,week,team)].ttgt)
        for ch, V, m in (("car", Vc, mc), ("tgt", Vt, mt)):
            C[f"V_{ch}"] = V; C[f"outpos_{ch}"] = ag.loc[m,"pos"]
            C[f"rk_{ch}"] = C.groupby("pos")[f"sh_{ch}"].rank(ascending=False, method="first")
        C["real_car"] = [cur.carries.get(p, 0) for p in C.index]; C["real_tgt"] = [cur.targets.get(p, 0) for p in C.index]
        C["act"] = [cur.dk.get(p, 0.0) for p in C.index]
        C["rs_car"] = C.real_car/max(tcar_real,1); C["rs_tgt"] = C.real_tgt/max(ttgt_real,1)
        C["vcar"], C["vtgt"] = vcar, vtgt
        C = C.reset_index().assign(season=season, week=week, team=team, flag=flag, n_out=len(outs),
                                   out_ids="|".join(outs))
        rows.append(C)
F = pd.concat(rows, ignore_index=True)
F.to_parquet(OUT/"frame.parquet")
print(F.groupby(["flag","season"]).size().unstack(0), "\nevents:", F.groupby(["flag"]).apply(lambda d: d[["season","week","team"]].drop_duplicates().shape[0]))
