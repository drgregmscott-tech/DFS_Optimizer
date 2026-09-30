"""Step 1: is the chalk-size miss a SHAPE problem (v2 mis-calibrated given its own ranking) or an INFORMATION problem
(v2 ranks the chalk player too low)? Plus per-miss feature ranks. No FC data written here except local prints."""
import sys; from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
H = pd.read_parquet(R/"data/fc_history/derived/ownership_v2/hist.parquet").reset_index(drop=True)
L = pd.read_parquet(R/"data/fc_history/derived/cheap_wrte/v2_loso.parquet")
H = H.merge(L, on=["slate_id","player_id"], how="left")
P = H[H.in_pool & (H.proj>0) & (H.pos!="DST")].copy()
key=["slate_id","grp"]
P["v2_rk"]=P.groupby(key).v2.rank(ascending=False,method="first")
P["real_rk"]=P.groupby(key).own.rank(ascending=False,method="first")
P["fc_rk"]=P.groupby(key).fc_own.rank(ascending=False,method="first")
P["fcval"]=P.fc_proj/P.salk; P["fcval_rk"]=P.groupby(key).fcval.rank(ascending=False,method="min")
print("== calibration by v2 rank within slate x position (all WR/TE) ==")
w=P[P.pos.isin(["WR","TE"])]
print(w.groupby([w.pos, w.v2_rk.clip(upper=11)]).agg(n=("own","size"),real=("own","mean"),v2=("v2","mean"),fc=("fc_own","mean")).round(1).unstack(0).head(11).to_string())
print("== by REAL rank: who is chalk #1..#3, where does v2 rank them ==")
for pos in ["WR","TE","RB"]:
    x=P[(P.pos==pos)&(P.real_rk<=3)]
    print(pos, x.groupby("real_rk").agg(real=("own","mean"),v2=("v2","mean"),v2rk_med=("v2_rk","median"),v2top3=("v2_rk",lambda s:(s<=3).mean()),fc=("fc_own","mean"),fcrk_med=("fc_rk","median"),valrk_med=("val_rk","median"),fcvalrk_med=("fcval_rk","median"),pubvrk_med=("pubv_rk","median")).round(2).to_string())
# chalk misses: real>=20, v2 under by 8+
M=P[P.pos.isin(["WR","TE"])&(P.own>=20)]
M=M.assign(miss=M.own-M.v2)
big=M[M.miss>=8]
print("\nWR/TE 20%+ n",len(M),"under by 8+:",len(big))
def share(c,thr): return (big[c]<=thr).mean()
for c in ["val_rk","proj_rk","pubv_rk","fcval_rk","salk_rk"]:
    print(f"{c}: median {big[c].median():.0f}; top3 {share(c,3):.2f}; top5 {share(c,5):.2f}")
print("sal_chg<0 share",(big.sal_chg<0).mean().round(2),"| vacated>.1",(big.vacated>.1).mean().round(2),"| lag_own>=10",(big.lag_own>=10).mean().round(2),"| last_dk>=15",(big.last_dk>=15).mean().round(2))
print("our proj vs fc proj for misses: mean proj %.1f fc_proj %.1f actual %.1f"%(big.proj.mean(),big.fc_proj.mean(),big.act.mean()))
print("same for all WR/TE: proj-fcproj mean %.2f"%(P[P.pos.isin(['WR','TE'])].eval('proj-fc_proj').mean()))
# how many misses have our proj LOW relative to fc_proj
big=big.assign(pgap=big.fc_proj-big.proj)
print("misses where FC proj exceeds ours by 3+:",(big.pgap>=3).mean().round(2), " all WRTE:",((P.fc_proj-P.proj)>=3)[P.pos.isin(['WR','TE'])].mean().round(2))
print(big.sort_values("miss",ascending=False)[["season","week","player","pos","salary","own","v2","fc_own","proj","fc_proj","val_rk","fcval_rk","pubv_rk","sal_chg","vacated","lag_own"]].head(40).round(1).to_string())
P.to_parquet(R/"data/fc_history/derived/cheap_wrte/wrte_chalk_P.parquet")
