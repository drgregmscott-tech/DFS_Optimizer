"""Part 2: teacher (FC Own) vs realized target, held-out; then the 2026 wk1-3 check.
Output: data/fc_history/derived/ownership_v2/part2_out.txt, y2026_preds.parquet"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import ALL, FAM, R, Model, allocate, metrics, mtable  # noqa: E402
from build import OUT  # noqa: E402

sys.path.insert(0, str(R / "scripts"))
import ownership_model as om  # noqa: E402
import ownership_heuristic as oh  # noqa: E402

TREES = 150
H = pd.read_parquet(OUT / "hist.parquet")
Y = pd.read_parquet(OUT / "y2026.parquet")
NOLAG = [c for c in ALL if c not in FAM["lag_own"]]


def live_2026():
    f = pd.read_parquet(R / "analysis/ownership_refit_wk3/frame.parquet")
    B = oh.compute_position_slot_budgets("dk")
    ffc, base = om.load_artifact("dk", "_ffc"), om.load_artifact("dk")
    out = []
    for sid, g in f.groupby("slate_id"):
        out.append(pd.DataFrame({"slate_id": sid, "player_id": g.player_id,
                                 "live_ffc": om.predict(g, g, ffc, B).values,
                                 "live_base": om.predict(g, g, base, B).values}))
    return pd.concat(out).drop_duplicates(["slate_id", "player_id"]).set_index(["slate_id", "player_id"])


def cut(df):
    return ((df.proj > 8) | (df.pos == "DST")).to_numpy()


def main():
    log = []
    pr = lambda *a: (print(*a), log.append(" ".join(str(x) for x in a)))  # noqa: E731
    # ---------------- history: realized-target LOSO vs FC-teacher
    seasons = sorted(H.season.unique())
    p_real = np.zeros(len(H)); p_teach = np.zeros(len(H)); p_real_lin = np.zeros(len(H))
    for s in seasons:
        te = (H.season == s).to_numpy()
        tr = H[~te]
        p_real[te] = Model(ALL, trees=TREES).fit(tr, "own").predict(H[te])
        p_real_lin[te] = Model(ALL).fit(tr, "own").predict(H[te])
        trf = tr[tr.season <= 2023]  # teacher only exists 2021-23
        p_teach[te] = Model(ALL, trees=TREES).fit(trf, "fc_own").predict(H[te])
    rows = {}
    for s in seasons:
        m = (H.season == s).to_numpy()
        rows[f"{s} realized-trained boost"] = metrics(H[m], p_real[m], "own")
        rows[f"{s} FC-teacher boost"] = metrics(H[m], p_teach[m], "own")
        rows[f"{s} live artifact"] = metrics(H[m], H.ours_own_model.fillna(0)[m], "own")
        if s <= 2023:
            rows[f"{s} FC Own"] = metrics(H[m], H.fc_own.fillna(0)[m], "own")
    rows["ALL realized-trained boost"] = metrics(H, p_real, "own")
    rows["ALL realized-trained linear"] = metrics(H, p_real_lin, "own")
    rows["ALL FC-teacher boost"] = metrics(H, p_teach, "own")
    rows["ALL live artifact"] = metrics(H, H.ours_own_model.fillna(0), "own")
    m3 = (H.season <= 2023).to_numpy()
    rows["2021-23 FC Own"] = metrics(H[m3], H.fc_own.fillna(0)[m3], "own")
    rows["2021-23 realized-trained boost"] = metrics(H[m3], p_real[m3], "own")
    pr("=== History, target = REALIZED SE ownership, leave-one-season-out, all FC rows ===")
    pr("(FC-teacher on 2021-23 folds trained on the other two FC seasons; 2024-25 trained on all 2021-23)")
    pr(mtable(rows).to_string())
    H.assign(p2_real=p_real, p2_teach=p_teach)[["slate_id", "player_id", "player", "pos", "salary", "proj", "own", "fc_own",
                                                "p2_real", "p2_teach", "ours_own_model", "in_pool", "grp"]].to_parquet(OUT / "part2_hist_preds.parquet")

    # ---------------- 2026 held out (all history as training)
    L = live_2026()
    Y["live_ffc"] = [L.live_ffc.get(k, 0.0) for k in zip(Y.slate_id, Y.player_id)]
    Y["live_base"] = [L.live_base.get(k, 0.0) for k in zip(Y.slate_id, Y.player_id)]
    M_real = Model(ALL, trees=TREES).fit(H, "own")
    M_real_nolag = Model(NOLAG, trees=TREES).fit(H, "own")
    M_teach = Model(ALL, trees=TREES).fit(H[H.season <= 2023], "fc_own")
    M_lin = Model(ALL).fit(H, "own")
    budgets = M_real.budgets
    F_real = M_real.score(Y)
    P = {"new realized boost": M_real.predict(Y, budgets, F_real),
         "new realized boost, no lag_own": M_real_nolag.predict(Y, budgets),
         "new FC-teacher boost": M_teach.predict(Y, budgets),
         "new realized linear": M_lin.predict(Y, budgets),
         "live FFC artifact (wk1-2 in-sample)": Y.live_ffc.to_numpy(),
         "live base artifact (wk1-2 in-sample)": Y.live_base.to_numpy(),
         "as-built pre-lock (log wk1-2 / file wk3)": Y.est_live.fillna(Y.live_log).fillna(0).to_numpy()}
    # + pub_val / FFC: (a) log-blend with live FFC, alpha by leave-one-week-out; (b) stacked softmax on new score
    lf = np.log(np.maximum(Y.live_ffc.to_numpy(), .05))
    blend = np.zeros(len(Y)); stack = np.zeros(len(Y)); stack_nf = np.zeros(len(Y)); alphas = []
    Y["F_new"] = F_real
    for wk in [1, 2, 3]:
        te = (Y.week == wk).to_numpy(); tr = ~te
        best = None
        for a in np.linspace(0, 1, 11):
            pp = allocate(Y[tr], a * F_real[tr] + (1 - a) * lf[tr], budgets)
            e = np.abs(pp - Y.own.fillna(0).to_numpy()[tr]).mean() - np.corrcoef(pp, Y.own.fillna(0)[tr])[0, 1]
            best = (e, a) if best is None or e < best[0] else best
        alphas.append(best[1])
        blend[te] = allocate(Y[te], best[1] * F_real[te] + (1 - best[1]) * lf[te], budgets)
        for feats, dst in [(["F_new", "pub_val", "l_ffc", "ffc_listed"], "ffc"), (["F_new", "pub_val"], "nf")]:
            ms = Model(feats, l2=1.0, pos_inter=False).fit(Y[tr], "own")
            (stack if dst == "ffc" else stack_nf)[te] = ms.predict(Y[te], budgets)
    P[f"new + live-FFC log blend (LOWO alpha {alphas})"] = blend
    P["new + pub_val + FFC stacked (LOWO)"] = stack
    P["new + pub_val stacked (LOWO, no FFC)"] = stack_nf
    for scope, msk in [("ALL ROWS", np.ones(len(Y), bool)), ("CUT proj>8 + DST", cut(Y))]:
        rows = {}
        for k, v in P.items():
            rows[k] = metrics(Y[msk], np.asarray(v)[msk], "own")
        pr(f"\n=== 2026 wk1-3, 9 slates, {scope} ===")
        pr(mtable(rows).to_string())
    for wk in [1, 2, 3]:
        rows = {}
        m = (Y.week == wk).to_numpy()
        for k in ["new realized boost", "new FC-teacher boost", "live FFC artifact (wk1-2 in-sample)",
                  "as-built pre-lock (log wk1-2 / file wk3)", "new + pub_val + FFC stacked (LOWO)"]:
            rows[k] = metrics(Y[m], np.asarray(P[k])[m], "own")
        pr(f"\n2026 wk{wk} (all rows):"); pr(mtable(rows)[["corr", "sp_slate", "mae", "catch20", "bias20", "corr_cheapWRTE", "top10pct"]].to_string())
    pr("\nbooster gain importance, realized-trained (all history):"); pr(M_real.importance().head(20).round(3).to_string())
    pr("\nbooster gain importance, FC-teacher (2021-23):"); pr(M_teach.importance().head(20).round(3).to_string())
    out = Y[["slate_id", "player_id", "player", "pos", "salary", "proj", "own", "live_ffc", "live_base", "est_live", "live_log"]].copy()
    for k, v in P.items():
        out["p_" + k.split(" (")[0].replace(" ", "_").replace(",", "").replace("+", "p")] = np.asarray(v)
    out.to_parquet(OUT / "y2026_preds.parquet")
    (OUT / "part2_out.txt").write_text("\n".join(log))


if __name__ == "__main__":
    main()
