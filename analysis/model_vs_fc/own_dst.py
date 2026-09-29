"""C. Ownership head-to-head (OUR production ownership artifact vs FC's pre-lock projected 'Own' vs realized SE
ownership) and D. 'cheapest viable DST' test. No FC data in this file.
Input: data/fc_history/derived/model_vs_fc/frame.parquet. Output: data/fc_history/derived/model_vs_fc/own_dst_out.txt
"""
from pathlib import Path
import numpy as np, pandas as pd

R = Path(__file__).resolve().parents[2]
OUT = R / "data/fc_history/derived/model_vs_fc"
LOG = open(OUT / "own_dst_out.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n")
rng = np.random.default_rng(5)
J = pd.read_parquet(OUT / "frame.parquet")

# ---------------- C. ownership ----------------
H = J[(J.season <= 2023) & J.ours_own.notna() & J.own.notna()].copy()
H["fc_own"] = H.fc_own_proj.fillna(0)
H["real_tier"] = pd.cut(H.own, [-1, 5, 10, 20, 101], labels=["<5", "5-10", "10-20", "20+"])
P(f"== C. OWNERSHIP 2021-23 (FC 'Own' projection exists only in 2021-23 exports). rows {len(H)}, slates {H.slate.nunique()}")
P("   OURS = current production ownership artifact on our regenerated projection (pub_val=0, no FFC, no news) -> handicapped")
P(f"   per-slate totals: real {H.groupby('slate').own.sum().mean():.0f}, FC {H.groupby('slate').fc_own.sum().mean():.0f}, ours {H.groupby('slate').ours_own.sum().mean():.0f}")


def om(d, c):
    e = d[c] - d.own
    sp = d.groupby("slate").apply(lambda g: g[c].rank().corr(g.own.rank())).mean()
    hot = d.own >= 20
    return dict(n=len(d), bias=e.mean(), MAE=e.abs().mean(), RMSE=np.sqrt((e ** 2).mean()), corr=d[c].corr(d.own), spear_slate=sp,
                catch20=(d.loc[hot, c] >= 15).mean() if hot.any() else np.nan,
                prec20=(d.loc[d[c] >= 20, "own"] >= 15).mean() if (d[c] >= 20).any() else np.nan)


def tab(d, by, title):
    rows = []
    for k, g in (d.groupby(by, observed=True) if by else [("all", d)]):
        for c, lab in [("fc_own", "FC"), ("ours_own", "OURS")]:
            m = om(g, c); m.update(slice=k, model=lab); rows.append(m)
    P(f"\n-- {title}"); P(pd.DataFrame(rows).set_index(["slice", "model"]).round(3).to_string())


tab(H, None, "all")
tab(H, "pos", "by position")
tab(H, "tier", "by salary band")
tab(H[H.pos.isin(["WR", "TE"])], "tier", "WR+TE by salary band")
tab(H, "real_tier", "by REAL ownership tier (bias = under/over at each tier)")
# slate bootstrap of deltas
per = {s: g for s, g in H.groupby("slate")}; sl = list(per); bs = []
for _ in range(300):
    g = pd.concat([per[s].assign(slate=i) for i, s in enumerate(rng.choice(sl, len(sl)))])
    a, b = om(g, "fc_own"), om(g, "ours_own"); bs.append([a["MAE"] - b["MAE"], a["corr"] - b["corr"], a["spear_slate"] - b["spear_slate"]])
bs = np.percentile(np.array(bs), [2.5, 97.5], axis=0); a, b = om(H, "fc_own"), om(H, "ours_own")
P(f"\n   FC minus OURS (slate bootstrap 95%): MAE {a['MAE'] - b['MAE']:+.2f} [{bs[0,0]:+.2f},{bs[1,0]:+.2f}]  corr {a['corr'] - b['corr']:+.3f} "
  f"[{bs[0,1]:+.3f},{bs[1,1]:+.3f}]  spear {a['spear_slate'] - b['spear_slate']:+.3f} [{bs[0,2]:+.3f},{bs[1,2]:+.3f}]")
# where each misses: biggest under-calls
for c in ["fc_own", "ours_own"]:
    x = H.assign(e=H[c] - H.own)
    u = x[x.e <= -10]
    P(f"   {c}: under-calls by >=10pt: {len(u)} ({len(u)/H.slate.nunique():.1f}/slate); by pos {u.pos.value_counts().to_dict()}; by band {u.tier.value_counts().to_dict()}; "
      f"over-calls >=10pt: {(x.e >= 10).sum()}")
# 2026: ours live only
L = J[(J.regime == "prod2026") & J.live_est.notna()].copy()
L["own"] = L.live_real.fillna(L.own)
P(f"\n-- 2026 wk1-2 main: ours LIVE pre-lock vs realized (FC has no projected ownership in 2024+ exports -> no FC head-to-head)")
P("   " + str({k: round(v, 3) for k, v in om(L.assign(ours_own=L.live_est), "ours_own").items()}))

# ---------------- D. cheapest viable DST ----------------
D = J[(J.pos == "DST") & (J.regime == "hist")].copy()
D["opp_imp"] = D.vegas_pts  # FC DST row uses opponent implied total (verified convention)
D["own_imp"] = D.implied_total  # our file: own team implied
D["spread_fav"] = D.own_imp - D.opp_imp
# sack proxy: team def sacks per game, prior weeks this season (fallback prior season)
ts = pd.concat([pd.read_parquet(R / f"data/team_stats_{s}.parquet")[["season", "week", "team", "opponent_team", "def_sacks", "sacks_suffered"]]
                for s in range(2020, 2026)])
ts = ts.sort_values(["team", "season", "week"])
ts["sack_rate"] = ts.groupby("team").def_sacks.transform(lambda x: x.shift(1).rolling(8, min_periods=3).mean())
ts["allowed"] = ts.groupby("team").sacks_suffered.transform(lambda x: x.shift(1).rolling(8, min_periods=3).mean())
D["team"] = D.player_id.str.replace("DST_", "")
D = D.merge(ts[["season", "week", "team", "opponent_team", "sack_rate"]], on=["season", "week", "team"], how="left")
D = D.merge(ts[["season", "week", "team", "allowed"]].rename(columns={"team": "opponent_team"}), on=["season", "week", "opponent_team"], how="left")
D["press"] = D.sack_rate + D.allowed
g = D.groupby("slate")
D["opp_rank"] = g.opp_imp.rank(); D["proj_rank"] = g.ours.rank(ascending=False); D["n"] = g.slate.transform("size")
D["press_rank"] = g.press.rank(ascending=False)
# viable = low opponent total (bottom 40% of slate) AND favored, OR our DST projection top quarter; plus pressure not bottom third
D["viable"] = (((D.opp_rank <= 0.4 * D.n) & (D.spread_fav > 0)) | (D.proj_rank <= 0.25 * D.n)) & ~(D.press_rank > 0.67 * D.n)
D["model_own"] = D.ours_own
out = []
for s, x in D.groupby("slate"):
    v = x[x.viable]
    if v.empty: continue
    cv = v.nsmallest(1, "salary").iloc[0]; cmin = x.nsmallest(1, "salary").iloc[0]
    out.append(dict(slate=s, n_viable=len(v), cv_sal=cv.salary, cv_act=cv.act, cv_own=cv.own, cv_model=cv.model_own, cv_fcown=cv.fc_own_proj,
                    viable_mean_act=v.act.mean(), all_mean_act=x.act.mean(), cv_ptsk=cv.act / cv.salary * 1000,
                    viable_ptsk=(v.act / v.salary * 1000).mean(), all_ptsk=(x.act / x.salary * 1000).mean(),
                    cv_is_min=cv.salary == cmin.salary, min_act=cmin.act, min_own=cmin.own,
                    cv_top3_own=int((x.own.rank(ascending=False) <= 3)[x.index == cv.name].any()) if False else int(cv.own >= x.own.nlargest(3).min()),
                    rho_own_price_viable=v.own.corr(-v.salary, method="spearman") if len(v) >= 3 else np.nan,
                    rho_own_price_all=x.own.corr(-x.salary, method="spearman")))
O = pd.DataFrame(out)
O.to_csv(OUT / "dst_cheapest_viable.csv", index=False)
P(f"\n== D. CHEAPEST-VIABLE DST (history 2021-25, {len(O)} slates; viable = opp implied bottom-40% & favored, or our DST proj top-25%, and pressure not bottom third)")
P(f"   viable per slate {O.n_viable.mean():.1f}; cheapest-viable is also min-price DST on {O.cv_is_min.mean():.0%} of slates; mean salary {O.cv_sal.mean():.0f}")
P(f"   POINTS: cheapest-viable {O.cv_act.mean():.2f} vs viable avg {O.viable_mean_act.mean():.2f} vs all-DST avg {O.all_mean_act.mean():.2f} vs min-price DST {O.min_act.mean():.2f}")
P(f"   PTS/$1k: cheapest-viable {O.cv_ptsk.mean():.2f} vs viable {O.viable_ptsk.mean():.2f} vs all {O.all_ptsk.mean():.2f}")
d1 = O.cv_ptsk - O.all_ptsk; bb = [rng.choice(d1, len(d1)).mean() for _ in range(2000)]
P(f"   cheapest-viable minus slate avg pts/$1k: {d1.mean():+.2f} [{np.percentile(bb,2.5):+.2f},{np.percentile(bb,97.5):+.2f}]; beats slate avg on {(d1 > 0).mean():.0%} of slates")
d2 = O.cv_act - O.viable_mean_act; bb = [rng.choice(d2, len(d2)).mean() for _ in range(2000)]
P(f"   cheapest-viable minus viable avg (raw pts): {d2.mean():+.2f} [{np.percentile(bb,2.5):+.2f},{np.percentile(bb,97.5):+.2f}]")
P(f"   OWNERSHIP: real {O.cv_own.mean():.1f}% vs our model {O.cv_model.mean():.1f}% (n with model {O.cv_model.notna().sum()}); FC proj (21-23) {O.cv_fcown.mean():.1f}%; "
  f"real top-3 owned DST on {O.cv_top3_own.mean():.0%} of slates; avg DST own {100/ D.groupby('slate').size().mean():.1f}% baseline")
m = O.dropna(subset=["cv_model"]); dd = m.cv_own - m.cv_model; bb = [rng.choice(dd, len(dd)).mean() for _ in range(2000)]
P(f"   real minus model on cheapest-viable: {dd.mean():+.2f} [{np.percentile(bb,2.5):+.2f},{np.percentile(bb,97.5):+.2f}] (positive = field owns MORE than our model)")
P(f"   field DST own vs price-cheapness: spearman among viable {O.rho_own_price_viable.mean():+.3f}, among all DSTs {O.rho_own_price_all.mean():+.3f}")
# what the field DOES track among DSTs
P(f"   within-slate spearman(real DST own, x): opp implied (low) {D.groupby('slate').apply(lambda x: x.own.corr(-x.opp_imp, method='spearman')).mean():+.3f}, "
  f"favored margin {D.groupby('slate').apply(lambda x: x.own.corr(x.spread_fav, method='spearman')).mean():+.3f}, "
  f"our DST proj {D.groupby('slate').apply(lambda x: x.own.corr(x.ours, method='spearman')).mean():+.3f}, "
  f"pressure {D.groupby('slate').apply(lambda x: x.own.corr(x.press, method='spearman')).mean():+.3f}, cheapness {D.groupby('slate').apply(lambda x: x.own.corr(-x.salary, method='spearman')).mean():+.3f}")
P(f"   by season cheapest-viable pts/$1k minus slate avg: {O.assign(s=O.slate // 100).groupby('s').apply(lambda x: round((x.cv_ptsk - x.all_ptsk).mean(), 2)).to_dict()}")
P(f"   by season real-minus-model own on cheapest viable: {m.assign(s=m.slate // 100).groupby('s').apply(lambda x: round((x.cv_own - x.cv_model).mean(), 2)).to_dict()}")
LOG.close()
