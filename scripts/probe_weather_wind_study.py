import pandas as pd, numpy as np, glob, re
D="data/"
yrs=[2013,2014,2015,2016,2017,2018,2019,2020,2021,2024,2025]
W=[];S=[]
for y in yrs:
    w=pd.read_parquet(f"{D}weekly_stats_{y}.parquet"); w=w[w.season_type=="REG"]; W.append(w)
    s=pd.read_parquet(f"{D}schedules_{y}.parquet"); s=s[s.game_type=="REG"]; S.append(s)
W=pd.concat(W); S=pd.concat(S)
S=S[S.roof.isin(["outdoors","open"])&S.wind.notna()&S.temp.notna()].copy()
S["wbin"]=pd.cut(S.wind,[-1,4,9,14,19,100],labels=["0-4","5-9","10-14","15-19","20+"])
print("outdoor games with wind:",len(S)); print(S.wbin.value_counts().sort_index().to_dict())
# --- market check: total points vs total_line
S["tot"]=S.home_score+S.away_score
S["res"]=S.tot-S.total_line
print("\n== Actual total - Vegas total by wind bin (negative = market under-adjusts)")
print(S.groupby("wbin",observed=True).agg(n=("res","size"),avg_line=("total_line","mean"),avg_tot=("tot","mean"),res=("res","mean")).round(2))
# rain proxy not available; temp bins
S["tbin"]=pd.cut(S.temp,[-50,25,40,55,85,150],labels=["<25","25-40","40-55","55-85",">85"])
print(S.groupby("tbin",observed=True).agg(n=("res","size"),avg_line=("total_line","mean"),avg_tot=("tot","mean"),res=("res","mean")).round(2))
# --- team-game aggregates
tg=W.groupby(["game_id","team"]).agg(att=("attempts","sum"),pyd=("passing_yards","sum"),comp=("completions","sum"),
   car=("carries","sum"),ryd=("rushing_yards","sum"),ptd=("passing_tds","sum"),ints=("passing_interceptions","sum"),
   sacks=("sacks_suffered","sum"),season=("season","first")).reset_index()
tg["ypa"]=tg.pyd/tg.att.replace(0,np.nan); tg["cmp"]=tg.comp/tg.att.replace(0,np.nan); tg["ypc"]=tg.ryd/tg.car.replace(0,np.nan)
tg["prate"]=tg.att/(tg.att+tg.car)
tg=tg.merge(S[["game_id","wind","temp","wbin","tbin"]],on="game_id")
# normalize each metric by that team-season's mean over ALL its games (incl. these)
for m in ["att","pyd","cmp","ypa","car","ryd","ypc","prate","ptd","ints"]:
    tg[m+"_rel"]=tg[m]/tg.groupby(["team","season"])[m].transform("mean")
print("\n== Team-level, relative to team-season mean (1.00 = normal), by wind bin (outdoor games)")
g=tg.groupby("wbin",observed=True)[[c for c in tg if c.endswith("_rel")]].mean().round(3); g.insert(0,"n",tg.groupby("wbin",observed=True).size()); print(g.T)
# --- player level by position
p=W[W.position.isin(["QB","RB","WR","TE","K"])].copy()
p=p.merge(S[["game_id","wind","temp","wbin"]],on="game_id")
p["pts"]=p.fantasy_points_ppr
if True:
    pass
allp=W[W.position.isin(["QB","RB","WR","TE","K"])].copy()
allp["pts"]=allp.fantasy_points_ppr
base=allp.groupby(["player_id","season"]).agg(mu=("pts","mean"),g=("pts","size")).reset_index()
p=p.merge(base,on=["player_id","season"]); p=p[(p.g>=8)&(p.mu>=(5))]
p["rel"]=p.pts/p.mu
print("\n== Player fantasy pts (PPR proxy) relative to own season mean, by position x wind bin")
t=p.pivot_table(index="position",columns="wbin",values="rel",aggfunc="mean",observed=True).round(3); n=p.pivot_table(index="position",columns="wbin",values="rel",aggfunc="size",observed=True); print(t); print(n)
# component stats for WR/TE/RB rushing
for pos,cols in [("WR",["receiving_yards","targets","receptions"]),("TE",["receiving_yards","targets"]),("RB",["rushing_yards","carries","receiving_yards"]),("QB",["passing_yards","rushing_yards"])]:
    q=W[W.position==pos].merge(S[["game_id","wbin"]],on="game_id").merge(base,on=["player_id","season"])
    q=q[(q.g>=8)]
    for c in cols:
        m=q.groupby(["player_id","season"])[c].transform("mean"); q=q[m>1]; q["r_"+c]=q[c]/q.groupby(["player_id","season"])[c].transform("mean")
    print(pos, q.groupby("wbin",observed=True)[["r_"+c for c in cols]].mean().round(3).to_string())
# kickers
k=W[(W.position=="K")].merge(S[["game_id","wbin"]],on="game_id")
k=k[k.fg_att>0]
print("\n== Kicker FG% by wind bin"); print(k.groupby("wbin",observed=True).agg(n=("fg_att","size"),att=("fg_att","sum"),made=("fg_made","sum")).assign(pct=lambda d:(d.made/d.att).round(3)))
# temperature effect on team passing
print("\n== Team-level by temp bin"); g=tg.groupby("tbin",observed=True)[["ypa_rel","cmp_rel","att_rel","prate_rel","car_rel"]].mean().round(3); g.insert(0,"n",tg.groupby("tbin",observed=True).size()); print(g)
