"""Step 5: lineup-level check of current vs candidate ownership predictions on the 49 history slates.
(i) chalk identification (top-owned CPT/FLEX hit rates, within-slate Spearman), (ii) simulated-field (F1, max-entropy
matching REALIZED ownership) percentile of the max-OUR-projection lineup and leverage lineups
(our proj - lam * ownership sum) where ownership = realized / current-model LOSO-free prediction / candidate LOSO.
Aggregates only. Output: data/fc_history/derived/showdown/lineup_check.parquet
    python analysis/showdown_history/lineup_check.py [workers]"""
import sys, json
from pathlib import Path
from multiprocessing import Pool
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
R = HERE.parents[1]; sys.path.insert(0, str(R / "scripts"))
SD = R / "data/fc_history/derived/showdown"
LAMS = (0.05, 0.1, 0.2)


def build_preds():
    import refit_ourproj as ro, ownership_model_showdown as oms
    ro.KD_REAL_ONLY = True
    D = ro.load("qb"); F = ro.SETS["+lsal"]
    cur = json.loads(oms.ARTIFACT.read_text())
    D["p_cur"] = pd.concat([ro.predict(D[D.slate == s], cur, oms.FEATURES) for s in D.slate.unique()]).reindex(D.index)
    D["p_cand"] = ro.loso(D, F)
    return D[D.src == "hist"]


def run(args):
    import enum_lib as E
    slate, g = args
    L = E.enumerate_game(g); act = L["act"].astype(float)
    ct = g.cpt_own.to_numpy() / g.cpt_own.sum(); ft = g.flex_own.to_numpy() / g.flex_own.sum() * 5
    w, err = E.ipf_field(L, ct, ft, (0.6 * (L["sal"] - 50000) / 1000.0).astype(float))
    o = np.argsort(act); cw = np.cumsum(w[o]); a_s = act[o]; q90 = float(a_s[np.searchsorted(cw, 0.9)])
    def pct(s):
        i = np.searchsorted(a_s, s, "left"); j = np.searchsorted(a_s, s, "right")
        lo = cw[i - 1] if i > 0 else 0.0; hi = cw[j - 1] if j > 0 else 0.0
        return lo + 0.5 * (hi - lo)
    P = L["proj"].astype(float)
    rows = []
    def add(name, obj):
        top = np.argpartition(-obj, 20)[:20]; top = top[np.argsort(-obj[top])]
        rows.append(dict(slate=slate, strategy=name, pct1=pct(act[top[0]]), top10_1=act[top[0]] >= q90,
                         pct20=np.mean([pct(act[i]) for i in top]), top10_20=np.mean(act[top] >= q90), err=err))
    add("max_ourproj", P)
    for src in ("real", "cur", "cand"):
        co = g[f"c_{src}"].to_numpy(); fo = g[f"f_{src}"].to_numpy()
        own = co[L["cpt"]] + fo[L["flex"]].sum(1)
        for lam in LAMS:
            add(f"lev{lam}_{src}", P - lam * own)
    return rows


if __name__ == "__main__":
    nw = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    D = build_preds()
    # (i) chalk identification
    out = []
    for (s, role), gs in D[D.live].groupby(["slate", "role"]):
        a = gs.own
        out.append(dict(slate=s, role=role, cur_top1=gs.p_cur.idxmax() == a.idxmax(), cand_top1=gs.p_cand.idxmax() == a.idxmax(),
                        cur_top3=len(set(gs.p_cur.nlargest(3).index) & set(a.nlargest(3).index)),
                        cand_top3=len(set(gs.p_cand.nlargest(3).index) & set(a.nlargest(3).index)),
                        cur_sp=gs.p_cur.corr(a, method="spearman"), cand_sp=gs.p_cand.corr(a, method="spearman"),
                        cur_top1_pos=gs.loc[gs.p_cur.idxmax(), "position"], cand_top1_pos=gs.loc[gs.p_cand.idxmax(), "position"],
                        real_top1_pos=gs.loc[a.idxmax(), "position"]))
    C = pd.DataFrame(out)
    print("=== (i) chalk identification (hist49; candidate = LOSO) ===")
    print(C.groupby("role")[["cur_top1", "cand_top1", "cur_top3", "cand_top3", "cur_sp", "cand_sp"]].mean().round(3).to_string())
    for role in ("CPT", "FLEX"):
        c = C[C.role == role]
        print(role, "top-1 predicted position: real", c.real_top1_pos.value_counts().to_dict(), "| cur", c.cur_top1_pos.value_counts().to_dict(),
              "| cand", c.cand_top1_pos.value_counts().to_dict())
    # (ii) lineup sims: one row per player (FLEX pos, flex salary, OUR flex projection, realized + predicted own)
    M = pd.read_parquet(SD / "sd_id_map.parquet")
    P = pd.read_parquet(SD / "players.parquet")
    M = M.merge(P[["slate", "Player", "Team", "act"]].assign(team=P.Team.replace({"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "LVR": "LV"})).drop(columns="Team"),
                on=["slate", "Player", "team"], how="left")
    piv = D.pivot_table(index=["slate", "player_id"], columns="role", values=["fp", "p_cur", "p_cand"], aggfunc="first")
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]; piv = piv.reset_index()
    G = M.merge(piv, on=["slate", "player_id"], how="left")
    G = G.assign(Team=G.team, sal=G.sal, proj=G.fp_FLEX.fillna(0.0), c_real=G.cpt_own, f_real=G.flex_own,
                 c_cur=G.p_cur_CPT.fillna(0), f_cur=G.p_cur_FLEX.fillna(0), c_cand=G.p_cand_CPT.fillna(0), f_cand=G.p_cand_FLEX.fillna(0))
    G = G[(G.flex_own > 0) | (G.cpt_own > 0) | (G.act > 0) | (G.proj > 0)]
    jobs = [(s, g.reset_index(drop=True)) for s, g in G.groupby("slate")]
    with Pool(nw) as p:
        rows = [r for rr in p.imap_unordered(run, jobs) for r in rr]
    T = pd.DataFrame(rows); T["year"] = T.slate.str[:4].astype(int); T.to_parquet(SD / "lineup_check.parquet")
    base = T[T.strategy == "max_ourproj"].set_index("slate")
    rng = np.random.default_rng(0); res = []
    for st, g in T.groupby("strategy"):
        g = g.set_index("slate")
        for col in ("pct1", "pct20", "top10_20"):
            d = (g[col] - base[col]).astype(float) * 100
            bs = [d.sample(len(d), replace=True, random_state=int(rng.integers(1e9))).mean() for _ in range(2000)]
            d25 = d[g.year == 2025]
            res.append(dict(strategy=st, metric=col, mean=round(float(g[col].astype(float).mean() * 100), 1),
                            diff=round(d.mean(), 1), lo=round(np.percentile(bs, 5), 1), hi=round(np.percentile(bs, 95), 1),
                            diff2025=round(d25.mean(), 1)))
    pd.set_option("display.width", 200)
    print("\n=== (ii) simulated F1 field vs realized ownership; diff vs max-our-proj, pct points, 90% slate-bootstrap CI ===")
    print(pd.DataFrame(res).pivot_table(index="strategy", columns="metric", values=["mean", "diff", "lo", "hi", "diff2025"]).round(1).to_string())
    print("max IPF err:", T.err.max())
