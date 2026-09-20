"""Run from repo root. Step 1: python scripts/probe_weather_rain_study.py fetch  (downloads ~30 stadiums of hourly precipitation from Open-Meteo archive to data/_precip_cache.json, ~15 min). Step 2: python scripts/probe_weather_rain_study.py  (analysis). See WEATHER_RESEARCH.md."""
import sys
if len(sys.argv)>1 and sys.argv[1]=='fetch':
    import pandas as pd, requests, sys, time, json, os
    sys.path.insert(0,"scripts")
    from weather import STADIUMS
    D="data/"; yrs=[2013,2014,2015,2016,2017,2018,2019,2020,2021,2024,2025]
    S=pd.concat([pd.read_parquet(f"{D}schedules_{y}.parquet") for y in yrs]); S=S[(S.game_type=="REG")&S.roof.isin(["outdoors","open"])]
    out={}
    cache="data/_precip_cache.json"
    if os.path.exists(cache): out=json.load(open(cache))
    for team,g in S.groupby("home_team"):
        if team in out or team not in STADIUMS: continue
        la,lo=STADIUMS[team]; rows={}
        for y in yrs:
            for attempt in range(8):
                try:
                    r=requests.get("https://archive-api.open-meteo.com/v1/archive",params=dict(latitude=la,longitude=lo,start_date=f"{y}-09-01",end_date=f"{y+1}-01-08",hourly="precipitation",timezone="UTC"),timeout=60)
                    if r.status_code==200: break
                    if r.status_code==429: time.sleep(30)
                except requests.RequestException:
                    pass
                time.sleep(5)
            else:
                print("fail",team,y); continue
            h=r.json()["hourly"]; rows.update(dict(zip(h["time"],h["precipitation"])))
            time.sleep(0.3)
        out[team]=rows; json.dump(out,open(cache,"w")); print("ok",team,len(rows),flush=True)
else:
    import pandas as pd, numpy as np, json
    from zoneinfo import ZoneInfo
    from datetime import timezone, timedelta, datetime
    D="data/"; SP="data/"
    yrs=[2013,2014,2015,2016,2017,2018,2019,2020,2021,2024,2025]
    P=json.load(open(SP+"_precip_cache.json"))
    S=pd.concat([pd.read_parquet(f"{D}schedules_{y}.parquet") for y in yrs]); S=S[(S.game_type=="REG")&S.roof.isin(["outdoors","open"])&S.wind.notna()&S.temp.notna()].copy()
    W=pd.concat([pd.read_parquet(f"{D}weekly_stats_{y}.parquet") for y in yrs]); W=W[W.season_type=="REG"]
    def precip(r):
        if r.home_team not in P or not isinstance(r.gametime,str): return np.nan
        k=datetime.strptime(f"{r.gameday} {r.gametime}","%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
        tot=0.0
        for h in range(3):
            t=(k+timedelta(hours=h)).strftime("%Y-%m-%dT%H:00"); v=P[r.home_team].get(t)
            if v is None: return np.nan
            tot+=v
        return tot
    S["rain"]=S.apply(precip,axis=1); S=S[S.rain.notna()]
    S["rbin"]=pd.cut(S.rain,[-1,0.05,1.0,3.0,100],labels=["dry","<=1mm/3h","1-3mm/3h",">3mm/3h"])
    print("games:",len(S)); print(S.rbin.value_counts().sort_index().to_dict())
    S["tot"]=S.home_score+S.away_score; S["res"]=S.tot-S.total_line
    tg=W.groupby(["game_id","team"]).agg(att=("attempts","sum"),pyd=("passing_yards","sum"),comp=("completions","sum"),car=("carries","sum"),ryd=("rushing_yards","sum"),
        fl=("fumbles_lost_total","sum"),season=("season","first")).reset_index()
    tg["ypa"]=tg.pyd/tg.att.replace(0,np.nan); tg["cmp"]=tg.comp/tg.att.replace(0,np.nan); tg["prate"]=tg.att/(tg.att+tg.car)
    tg=tg.merge(S[["game_id","wind","temp","rbin","rain"]],on="game_id")
    for m in ["att","pyd","cmp","ypa","car","ryd","prate","fl"]:
        tg[m+"_rel"]=tg[m]/tg.groupby(["team","season"])[m].transform("mean")
    cols=[c for c in tg if c.endswith("_rel")]
    def show(df,title):
        g=df.groupby("rbin",observed=True)[cols].mean().round(3); g.insert(0,"n",df.groupby("rbin",observed=True).size()); print("\n==",title); print(g.T)
    show(tg,"ALL outdoor team-games by rain bin")
    show(tg[(tg.wind<10)&(tg.temp>45)],"CALM (wind<10) & WARM (>45F): isolates rain")
    show(tg[(tg.wind>=10)&(tg.temp>45)],"Windy (>=10) & warm")
    print("\n== market: actual - vegas total by rain bin (calm/warm)"); c=S[(S.wind<10)&(S.temp>45)]; print(c.groupby("rbin",observed=True).agg(n=("res","size"),res=("res","mean"),tot=("tot","mean"),line=("total_line","mean")).round(2))
    # player level
    allp=W[W.position.isin(["QB","RB","WR","TE"])].copy(); allp["pts"]=allp.fantasy_points_ppr
    base=allp.groupby(["player_id","season"]).agg(mu=("pts","mean"),g=("pts","size")).reset_index()
    p=allp.merge(base,on=["player_id","season"]).merge(S[["game_id","wind","temp","rbin"]],on="game_id"); p=p[(p.g>=8)&(p.mu>=5)&(p.wind<10)&(p.temp>45)]; p["rel"]=p.pts/p.mu
    print("\n== Player pts rel. to own mean, calm/warm, by rain bin"); print(p.pivot_table(index="position",columns="rbin",values="rel",aggfunc="mean",observed=True).round(3)); print(p.pivot_table(index="position",columns="rbin",values="rel",aggfunc="size",observed=True))
