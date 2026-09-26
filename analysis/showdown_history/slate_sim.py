"""Per-slate: exhaustive enumeration, hindsight-optimal features, strategy lineups (chosen on FC Proj +
ownership only), and scoring vs 3 simulated-field variants (IPF max-entropy fields matching FC ownership).
Outputs per-slate pickles in data/fc_history/derived/showdown/slates/. Run: python slate_sim.py [workers]"""
import sys, pickle
from pathlib import Path
from multiprocessing import Pool
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent)); import enum_lib as E
R = Path(__file__).resolve().parents[2]; D = R / "data/fc_history/derived/showdown"; (D / "slates").mkdir(exist_ok=True)
TOPN = 20

def strategies(g, L):
    pos = g.pos.to_numpy(); cp = pos[L["cpt"]]
    allpos = np.c_[L["cpt"], L["flex"]]
    nK = (pos[allpos] == "K").sum(1); nD = (pos[allpos] == "DST").sum(1)
    sal = g.sal.to_numpy(); dst_idx = np.where(pos == "DST")[0]
    cheap_dst = dst_idx[np.argmin(sal[dst_idx])] if len(dst_idx) else -1
    exp_dst = [i for i in dst_idx if i != cheap_dst]
    has_expD = np.isin(allpos, exp_dst).any(1)
    split = np.maximum(L["nteam0"], 6 - L["nteam0"])
    fav = g.fav.to_numpy(); nfav = fav[allpos].sum(1)
    co = g.cpt_own.to_numpy(); fo = g.flex_own.to_numpy()
    cown = co[L["cpt"]]; ownsum = cown + fo[L["flex"]].sum(1)
    chalk_c = int(np.argmax(co))
    rbwr = np.isin(cp, ["RB", "WR"]); P = L["proj"].astype(float)
    S = {
        "A_max_proj": (P, None),
        "B_cpt_RBWR": (P, rbwr),
        "C_maxK1": (P, nK <= 1),
        "D_RBWR_maxK1": (P, rbwr & (nK <= 1)),
        "E_no_cpt_K_DST_TE": (P, ~np.isin(cp, ["K", "DST", "TE"])),
        "F_cpt_QB": (P, cp == "QB"),
        "G_no_DST": (P, nD == 0),
        "H_DST_cheap_only": (P, ~has_expD),
        "I_D_plus_H": (P, rbwr & (nK <= 1) & ~has_expD),
        "J_split_5_1": (P, split == 5),
        "K_split_max4": (P, split <= 4),
        "L_split_3_3": (P, split == 3),
        "M_fav_heavy4": (P, nfav >= 4),
        "N_dog_heavy4": (P, nfav <= 2),
        "O_cpt_own_lt5": (P, cown < 5),
        "P_cpt_own_5_15": (P, (cown >= 5) & (cown < 15)),
        "Q_cpt_own_ge15": (P, cown >= 15),
        "R_fade_chalk_cpt": (P, L["cpt"] != chalk_c),
        "S_chalk_cpt": (P, L["cpt"] == chalk_c),
        "T_zeroK": (P, nK == 0),
        "U_twoK": (P, nK == 2),
        "V_RBWR_maxK1_nochalkcpt": (P, rbwr & (nK <= 1) & (L["cpt"] != chalk_c)),
    }
    for lam in (0.05, 0.1, 0.2):
        S[f"W_lev_{lam}"] = (P - lam * ownsum, None)
        S[f"X_chalk_{lam}"] = (P + lam * ownsum, None)
    return S, dict(cp=cp, nK=nK, nD=nD, split=split, nfav=nfav, cown=cown, ownsum=ownsum, has_expD=has_expD, chalk_c=chalk_c)

def run(slate):
    df = pd.read_parquet(D / "players.parquet")
    g = df[df.slate == slate]
    g = g[(g.flex_own > 0) | (g.cpt_own > 0) | (g.act > 0) | (g.proj > 0)].reset_index(drop=True)
    L = E.enumerate_game(g); act = L["act"].astype(float)
    S, F = strategies(g, L)
    res = dict(slate=slate, n_players=len(g), n_lineups=len(act))
    # hindsight
    order = np.argsort(-act)[:TOPN]
    pos = g.pos.to_numpy(); crank_own = (-g.cpt_own).rank(method="min").to_numpy(); crank_proj = (-g.proj).rank(method="min").to_numpy()
    hs = []
    for r, i in enumerate(order):
        c = L["cpt"][i]
        hs.append(dict(rank=r, act=act[i], proj=L["proj"][i], sal=L["sal"][i], cpt_pos=pos[c], cpt_own=g.cpt_own[c],
                       cpt_own_rank=crank_own[c], cpt_proj_rank=crank_proj[c], cpt_sal=g.sal[c], cpt_fav=g.fav[c],
                       split=F["split"][i], nK=F["nK"][i], nD=F["nD"][i], expD=F["has_expD"][i], nfav=F["nfav"][i],
                       ownsum=F["ownsum"][i], n_min=(g.sal.to_numpy()[L["flex"][i]] <= 1000).sum(),
                       n_proj0=(g.proj.to_numpy()[L["flex"][i]] <= 0).sum()))
    res["hind"] = pd.DataFrame(hs)
    # fields
    ct = g.cpt_own.to_numpy() / g.cpt_own.sum(); ft = g.flex_own.to_numpy() / g.flex_own.sum() * 5
    priors = {"F0_uniform": None, "F1_salary": 0.6 * (L["sal"] - 50000) / 1000.0,
              "F2_sal_proj": 0.6 * (L["sal"] - 50000) / 1000.0 + 0.15 * (L["proj"] - L["proj"].max())}
    fields = {}
    for k, lp in priors.items():
        w, err = E.ipf_field(L, ct, ft, None if lp is None else lp.astype(float))
        o = np.argsort(act); cw = np.cumsum(w[o]); a_s = act[o]
        q = {qq: float(a_s[np.searchsorted(cw, qq)]) for qq in (0.5, 0.9, 0.99, 0.999)}
        fields[k] = dict(err=err, q=q, mean=float((w * act).sum()),
                         cpt_pos=pd.Series(w).groupby(F["cp"]).sum().to_dict(),
                         split=pd.Series(w).groupby(F["split"]).sum().to_dict(),
                         nK=pd.Series(w).groupby(F["nK"]).sum().to_dict(),
                         sal_mean=float((w * L["sal"]).sum()), hind_pct=float(w[act < act[order[0]]].sum()),
                         _o=o, _cw=cw, _as=a_s)
    def pct(s, f):
        i = np.searchsorted(f["_as"], s, "left"); j = np.searchsorted(f["_as"], s, "right")
        lo = f["_cw"][i - 1] if i > 0 else 0.0; hi = f["_cw"][j - 1] if j > 0 else 0.0
        return lo + 0.5 * (hi - lo)
    rows = []
    for name, (obj, mask) in S.items():
        o = obj if mask is None else np.where(mask, obj, -np.inf)
        if not np.isfinite(o.max()):
            continue
        top = np.argpartition(-o, TOPN)[:TOPN]; top = top[np.argsort(-o[top])]; top = top[np.isfinite(o[top])]
        for r, i in enumerate(top):
            d = dict(strategy=name, rank=r, act=act[i], proj=float(L["proj"][i]), cpt_pos=F["cp"][i], cpt_own=F["cown"][i],
                     split=F["split"][i], nK=F["nK"][i], ownsum=F["ownsum"][i])
            for k, f in fields.items():
                p = pct(act[i], f); d[f"{k}_pct"] = p; d[f"{k}_top1"] = act[i] >= f["q"][0.99]; d[f"{k}_top10"] = act[i] >= f["q"][0.9]
                d[f"{k}_top01"] = act[i] >= f["q"][0.999]
            rows.append(d)
    res["strat"] = pd.DataFrame(rows)
    res["fields"] = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in fields.items()}
    pickle.dump(res, open(D / "slates" / f"{slate}.pkl", "wb"))
    return slate, res["fields"]["F1_salary"]["err"]

if __name__ == "__main__":
    nw = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    slates = sorted(pd.read_parquet(D / "players.parquet").slate.unique())
    todo = [s for s in slates if not (D / "slates" / f"{s}.pkl").exists()]
    with Pool(nw) as p:
        for s, e in p.imap_unordered(run, todo):
            print(s, round(e, 4), flush=True)
