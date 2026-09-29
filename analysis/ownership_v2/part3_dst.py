"""Part 3: DST-only ownership allocation (softmax within DST, budget 100).
History: 86 FC SE main slates 2021-25, target = realized own, leave-one-season-out (5 folds).
2026: 9 slates, trained on all history. Baselines: live artifact (history base), FC Own (2021-23), live 2026.
Output: data/fc_history/derived/ownership_v2/part3_out.txt"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import Model, allocate  # noqa: E402
from build import OUT  # noqa: E402


def dst_feats(D):
    D = D[D.pos == "DST"].copy()
    D["in_pool"] = D.in_pool & (D.proj > 0)
    g = D.groupby("slate_id")
    D["opp_rk"] = g.opp_total.rank(pct=True)                 # low = weak opponent offense
    D["fav"] = (D.spread > 0).astype(float)
    D["proj_rk"] = g.proj.rank(ascending=False, pct=True)
    D["pres_rk"] = g.pressure.rank(pct=True)
    D["viable"] = (((D.opp_rk <= .4) & (D.fav > 0)) | (D.proj_rk <= .25)) & (D.pres_rk > 1 / 3)
    D["viable_f"] = D.viable.astype(float)
    D["vsal_rk"] = D.salary.where(D.viable).groupby(D.slate_id).rank(method="min")
    D["cheapest_viable"] = (D.vsal_rk == 1).astype(float)
    D["vsal_lrk"] = np.log(D.vsal_rk.fillna(20))
    D["proj_gap1"] = g.proj.transform("max") - D.proj
    D["opp_gap"] = D.opp_total - g.opp_total.transform("min")
    return D


F_DST = ["opp_total", "opp_rk", "opp_gap", "spread", "fav", "proj", "proj_rk", "proj_gap1", "pressure", "pres_rk",
         "salk", "salk_lrk", "viable_f", "cheapest_viable", "vsal_lrk", "l_lag_own", "game_total"]
F_DST_OPT = F_DST + ["l_exp", "l_est"]


def dmetrics(D, p, tgt="own"):
    y = D[tgt].fillna(0).to_numpy(); p = np.asarray(p)
    o = {}
    top_hit, top_bias, mtop_bias, top2 = [], [], [], []
    for ix in D.groupby("slate_id").indices.values():
        rt, pt = ix[np.argmax(y[ix])], ix[np.argmax(p[ix])]
        top_hit.append(rt == pt); top_bias.append(p[rt] - y[rt]); mtop_bias.append(p[pt] - y[pt])
        top2.append(rt in ix[np.argsort(-p[ix])[:3]])
    o["top_is_top"] = np.mean(top_hit); o["real_top_in_model_top3"] = np.mean(top2)
    o["bias_real_top"] = np.mean(top_bias); o["bias_model_top"] = np.mean(mtop_bias)
    o["mae"] = np.abs(p - y).mean(); o["corr"] = np.corrcoef(p, y)[0, 1]
    cv = D.cheapest_viable.to_numpy() > 0
    o["cheapviable_pred"] = p[cv].mean(); o["cheapviable_real"] = y[cv].mean()
    o["pred_max"] = pd.Series(p).groupby(D.slate_id.to_numpy()).max().mean()
    o["real_max"] = pd.Series(y).groupby(D.slate_id.to_numpy()).max().mean()
    return o


def main():
    log = []
    pr = lambda *a: (print(*a), log.append(" ".join(str(x) for x in a)))  # noqa: E731
    H = dst_feats(pd.read_parquet(OUT / "hist.parquet"))
    Y = dst_feats(pd.read_parquet(OUT / "y2026.parquet"))
    pr(f"history DST rows {len(H)} slates {H.slate_id.nunique()}, viable/slate {H.viable.sum() / H.slate_id.nunique():.1f}")
    res, preds = {}, {}
    for name, feats, l2, trees in [("lin", F_DST, 3.0, 0), ("lin+opt", F_DST_OPT, 3.0, 0),
                                   ("boost", F_DST_OPT, 3.0, 60)]:
        p = np.zeros(len(H))
        for s in sorted(H.season.unique()):
            m = Model(feats, l2=l2, trees=trees, depth=2, lr=.1, min_h=3, pos_inter=False).fit(H[H.season != s], "own")
            p[(H.season == s).to_numpy()] = m.predict(H[H.season == s], budgets={"DST": 100.0})
        preds[name] = p
        res[name + " (LOSO)"] = dmetrics(H, p)
    live = H.ours_own_model.fillna(0).to_numpy()
    live = live / pd.Series(live).groupby(H.slate_id.to_numpy()).transform("sum").to_numpy() * 100
    res["live artifact (hist base)"] = dmetrics(H, live)
    res["live x power1.25 (parked cand.)"] = dmetrics(H, allocate(H, np.log(np.maximum(live, 1e-3)) * 1.25, {"DST": 100.0}))
    h3 = H[H.season <= 2023]
    fc = h3.fc_own.fillna(0).to_numpy(); fc = fc / pd.Series(fc).groupby(h3.slate_id.to_numpy()).transform("sum").to_numpy() * 100
    res["FC Own 2021-23 only"] = dmetrics(h3, fc)
    res["lin (LOSO) 2021-23 only"] = dmetrics(h3, preds["lin"][(H.season <= 2023).to_numpy()])
    pr("\n=== DST history, target realized own (per-slate DST sums to 100) ===")
    pr(pd.DataFrame(res).T.round(3).to_string())
    per = {}
    for s in sorted(H.season.unique()):
        m = (H.season == s).to_numpy()
        a, b = dmetrics(H[m], preds["lin"][m]), dmetrics(H[m], live[m])
        per[s] = {"top_hit lin/live": f"{a['top_is_top']:.2f}/{b['top_is_top']:.2f}",
                  "bias_real_top lin/live": f"{a['bias_real_top']:+.1f}/{b['bias_real_top']:+.1f}",
                  "mae lin/live": f"{a['mae']:.2f}/{b['mae']:.2f}",
                  "cheapviable pred lin/live/real": f"{a['cheapviable_pred']:.1f}/{b['cheapviable_pred']:.1f}/{a['cheapviable_real']:.1f}"}
    pr("\nper season:"); pr(pd.DataFrame(per).T.to_string())
    # final fit on all history -> coefficients + 2026 check
    m = Model(F_DST, l2=3.0, pos_inter=False).fit(H, "own")
    coef = pd.Series(m.b / m.sd, index=F_DST)
    pr("\nlin coefficients (per raw unit, all-history fit):"); pr(coef.round(3).to_string())
    mo = Model(F_DST_OPT, l2=3.0, pos_inter=False).fit(H, "own")
    y26 = {}
    L = pd.read_parquet(OUT / "y2026_preds.parquet").set_index(["slate_id", "player_id"]) if (OUT / "y2026_preds.parquet").exists() else None
    p_new = m.predict(Y, budgets={"DST": 100.0})
    p_newo = mo.predict(Y, budgets={"DST": 100.0})
    y26["new DST lin"] = dmetrics(Y, p_new)
    y26["new DST lin+opt"] = dmetrics(Y, p_newo)
    if L is not None:
        lv = np.array([L.live_ffc.get((a, b), 0.0) for a, b in zip(Y.slate_id, Y.player_id)])
        y26["live FFC artifact"] = dmetrics(Y, lv)
        # blend live and new within DST (log space 50/50)
        bl = allocate(Y, .5 * np.log(np.maximum(lv, .05)) + .5 * np.log(np.maximum(p_new, .05)), {"DST": 100.0})
        y26["50/50 log blend live+new"] = dmetrics(Y, bl)
    pr("\n=== 2026 wk1-3 (9 slates) held out ===")
    pr(pd.DataFrame(y26).T.round(3).to_string())
    json.dump({"features": F_DST, "mu": m.mu.tolist(), "sd": m.sd.tolist(), "b": m.b.tolist()},
              open(OUT / "dst_model_fit.json", "w"), indent=1)
    Y.assign(dst_new=p_new)[["slate_id", "player", "salary", "opp_total", "proj", "own", "dst_new"]].to_csv(OUT / "part3_2026_dst.csv", index=False)
    (OUT / "part3_out.txt").write_text("\n".join(log))


if __name__ == "__main__":
    main()
