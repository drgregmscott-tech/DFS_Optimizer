"""Tidy FC DK showdown history -> data/fc_history/derived/showdown/players.parquet (gitignored).
No FC data embedded here."""
import glob, re
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
SRC = R / "data/fc_history/Showdowns"; OUT = R / "data/fc_history/derived/showdown"; OUT.mkdir(parents=True, exist_ok=True)
def num(s): return pd.to_numeric(s.astype(str).str.replace('%', '').str.replace('$', '').str.replace(',', ''), errors='coerce')
rows, qa = [], []
for f in sorted(SRC.glob("fc_dk_*.csv")):
    m = re.match(r"fc_dk_(\d{4})_(\w+?)_(\w+)\.csv", f.name); yr = int(m.group(1))
    d = pd.read_csv(f, header=1, low_memory=False)
    d["own"] = num(d["Own%"]).fillna(0)
    teams = d.loc[d.own > 0, "Team"].value_counts()
    teams = list(teams.index[:2])
    g = d[d.Team.isin(teams)].copy()
    g["role"] = np.where(g.Pos == "CPTN", "CPT", "FLEX")
    g["sal"] = num(g.Salary); g["proj"] = num(g["FC Proj"]).fillna(0); g["act"] = num(g["Score"])
    g["vegas"] = num(g["VegasPts"]); g["stdv"] = num(g["STDV"]); g["ceil"] = num(g["Ceiling"]); g["floor"] = num(g["Floor"])
    flex = g[g.role == "FLEX"][["Player", "Team", "Pos", "sal", "proj", "act", "pDepth"]]
    cpt = g[g.role == "CPT"]
    mm = cpt.merge(flex, on=["Player", "Team"], suffixes=("", "_f"), how="left")
    qa.append(dict(file=f.name, year=yr, teams="/".join(teams), n_cpt=len(cpt), n_flex=len(flex),
                   cpt_own=cpt.own.sum(), flex_own=g[g.role == "FLEX"].own.sum(),
                   act_na=g.act.isna().mean(), proj0=(g.proj <= 0).mean(), cpt_unmatched=mm.Pos_f.isna().sum(),
                   sal_ratio_bad=int((~np.isclose(mm.sal, 1.5 * mm.sal_f)).sum()),
                   act_ratio_bad=int((~np.isclose(mm.act, 1.5 * mm.act_f, atol=0.06) & mm.act.notna()).sum()),
                   proj_ratio_bad=int((~np.isclose(mm.proj, 1.5 * mm.proj_f, atol=0.06)).sum()),
                   vegas=g.groupby("Team").vegas.first().to_dict()))
    # one row per player: FLEX pos, flex salary/proj/act, cpt_own, flex_own
    p = flex.rename(columns={"Pos": "pos"}).copy()
    p = p.merge(cpt[["Player", "Team", "own"]].rename(columns={"own": "cpt_own"}), on=["Player", "Team"], how="left")
    p = p.merge(g[g.role == "FLEX"][["Player", "Team", "own", "vegas", "stdv", "ceil", "floor", "Opp"]].rename(columns={"own": "flex_own"}), on=["Player", "Team"], how="left")
    p["cpt_own"] = p.cpt_own.fillna(0); p["slate"] = f.stem.replace("fc_dk_", ""); p["year"] = yr
    rows.append(p)
df = pd.concat(rows, ignore_index=True)
df["pos"] = df.pos.replace({"D": "DST", "DEF": "DST"})
opp_v = df.groupby(["slate", "Team"]).vegas.first().rename("tv").reset_index()
tot = opp_v.groupby("slate").tv.sum().rename("total")
df = df.merge(opp_v, on=["slate", "Team"]).merge(tot, on="slate")
df["fav"] = (df.tv > df.total - df.tv).astype(int)
df["spread"] = df.tv - (df.total - df.tv)
df.to_parquet(OUT / "players.parquet"); q = pd.DataFrame(qa); q.to_csv(OUT / "qa.csv", index=False)
pd.set_option("display.width", 250); print(q.drop(columns="vegas").to_string()); print(df.pos.value_counts()); print(df.describe().T)
