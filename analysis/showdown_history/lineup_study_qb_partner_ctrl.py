"""QB-CPT partner position (WR vs RB vs TE, highest-salary same-team FLEX) with projection / salary controls.
Per contest (QB-CPT entries only): OLS of cashed / ret_cap on RB, TE dummies (WR = base) plus
  M1: none; M2: z(lineup FC proj_sum); M3: M2 + z(partner FC proj) + z(salary left); M4: M3 + z(partner salary).
Also a matched view: partner FC projection quintile within contest (pooled over positions), lift by position inside quintile.
Output: derived/showdown/ls_cd_qb_partner_ctrl.csv (aggregate only)."""
import os
import numpy as np
import pandas as pd

ROOT = os.environ.get("DFS_ROOT", r"C:\Users\gmsco\Desktop\DFS_Optimizer")
LS = os.path.join(ROOT, "data", "fc_history", "lineup_study")
OUT = os.path.join(ROOT, "data", "fc_history", "derived", "showdown")
RS = np.random.RandomState(7)


def boot(v, B=2000):
    v = np.asarray(v, float); v = v[np.isfinite(v)]
    s = v[RS.randint(0, len(v), (B, len(v)))].mean(1)
    return np.percentile(s, 5), np.percentile(s, 95)


E = pd.read_parquet(os.path.join(LS, "_sd_entries_ids.parquet")); E["contest"] = E.contest.astype(str)
P = pd.read_parquet(os.path.join(LS, "_sd_players.parquet")); P["contest"] = P.contest.astype(str)
coef, match = [], []
for cid, e in E.groupby("contest", sort=False):
    p = P[P.contest == cid].set_index("pid")
    main2 = p.team.value_counts().index[:2]; p = p.assign(team=p.team.where(p.team.isin(main2)))
    pr = pd.to_numeric(p.fc_proj, errors="coerce")
    ids = [e[f"p{j}"].values for j in range(6)]
    pos0 = p.pos.reindex(ids[0]).values
    q = pos0 == "QB"
    if q.sum() < 1000:
        continue
    ids = [x[q] for x in ids]; eq = e[q]; n = q.sum()
    tm = [p.team.reindex(x).values for x in ids]
    fpos = np.column_stack([p.pos.reindex(x).values for x in ids[1:]])
    fsal = np.column_stack([p.sal.reindex(x).values.astype(float) for x in ids[1:]])
    fpr = np.column_stack([pr.reindex(x).values for x in ids[1:]])
    fown = np.column_stack([p.flex_own.reindex(x).values for x in ids[1:]])
    same = np.column_stack([tm[j] == tm[0] for j in range(1, 6)])
    k = np.where(same, fsal + fown / 1000.0, -1e9).argmax(1); r = np.arange(n)
    d = pd.DataFrame({"ppos": np.where(same.any(1), fpos[r, k], "none"), "ppr": fpr[r, k], "psal": fsal[r, k]})
    d["proj_sum"] = 1.5 * pr.reindex(ids[0]).values + np.nansum(fpr, 1)
    d["left"] = 50000 - (1.5 * p.sal.reindex(ids[0]).values + fsal.sum(1))
    allpay = e.payout_c; cap = allpay.quantile(0.999)
    pc = np.minimum(eq.payout_c.values, cap); d["ret_cap"] = pc / np.minimum(allpay, cap).mean()
    d["cashed"] = (eq.payout_c.values > 0).astype(float)
    d = d[d.ppos.isin(["WR", "RB", "TE"])].dropna()
    if len(d) < 1000 or d.proj_sum.std() < 5 or d.ppr.std() < 1 or (d.ppos == "TE").sum() < 30 or (d.ppos == "RB").sum() < 30:
        continue
    z = lambda s: (s - s.mean()) / s.std()
    base = [np.ones(len(d)), (d.ppos == "RB").astype(float), (d.ppos == "TE").astype(float)]
    specs = {"M1 raw": [], "M2 +lineup proj": [z(d.proj_sum)], "M3 +partner proj +sal left": [z(d.proj_sum), z(d.ppr), z(d.left)],
             "M4 +partner salary": [z(d.proj_sum), z(d.ppr), z(d.left), z(d.psal)]}
    meta = {"contest": cid, "ctype": p.ctype.iat[0], "season": int(p.season.iat[0])}
    for nm, extra in specs.items():
        X = np.column_stack(base + extra)
        for y in ("cashed", "ret_cap"):
            b = np.linalg.lstsq(X, d[y].values, rcond=None)[0]
            coef.append({**meta, "model": nm, "y": y, "RB_vs_WR": b[1], "TE_vs_WR": b[2],
                         "partner_proj": b[4] if len(b) > 4 else np.nan})
    # matched: partner FC-projection quintile within contest, pooled positions
    d["pq"] = pd.qcut(d.ppr.rank(method="first"), 5, labels=False) + 1
    for (pq, pp), g in d.groupby(["pq", "ppos"]):
        match.append({**meta, "pq": pq, "ppos": pp, "n": len(g), "cash": g.cashed.mean(), "ret": g.ret_cap.mean()})
C = pd.DataFrame(coef); M = pd.DataFrame(match)
rows = []
for (ct, m, y), g in C.groupby(["ctype", "model", "y"]):
    for col in ("RB_vs_WR", "TE_vs_WR"):
        lo, hi = boot(g[col]); by = g.groupby("season")[col].mean()
        rows.append({"ctype": ct, "model": m, "y": y, "term": col, "contests": len(g), "est": g[col].mean(), "lo": lo, "hi": hi,
                     "pos": int((g[col] > 0).sum()), **{f"s{k}": v for k, v in by.items()}})
T = pd.DataFrame(rows)
# matched: within each contest x quintile, RB - WR and TE - WR cash difference (both cells need >= 30)
mm = []
for (cid, pq), g in M[M.n >= 30].groupby(["contest", "pq"]):
    s = g.set_index("ppos"); ct = g.ctype.iat[0]
    for pp in ("RB", "TE"):
        if pp in s.index and "WR" in s.index:
            mm.append({"ctype": ct, "contest": cid, "pq": pq, "term": pp + "_vs_WR", "d_cash": 100 * (s.cash[pp] - s.cash["WR"])})
MM = pd.DataFrame(mm)
for (ct, t, pq), g in MM.groupby(["ctype", "term", "pq"]):
    lo, hi = boot(g.d_cash)
    rows.append({"ctype": ct, "model": f"matched partner-proj Q{pq}", "y": "cashed(pts)", "term": t, "contests": g.contest.nunique(),
                 "est": g.d_cash.mean(), "lo": lo, "hi": hi})
for (ct, t), g in MM.groupby(["ctype", "term"]):
    cm = g.groupby("contest").d_cash.mean(); lo, hi = boot(cm)
    rows.append({"ctype": ct, "model": "matched, all quintiles (contest mean)", "y": "cashed(pts)", "term": t, "contests": len(cm),
                 "est": cm.mean(), "lo": lo, "hi": hi})
T = pd.DataFrame(rows)
T.loc[T.y == "cashed", ["est", "lo", "hi"]] *= 100
T.to_csv(os.path.join(OUT, "ls_cd_qb_partner_ctrl.csv"), index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
print(T.round(3).to_string(index=False))
print("partner-proj coef (cash pts/SD, M3):", C[(C.model.str.startswith("M3")) & (C.y == "cashed")].groupby("ctype").partner_proj.mean().mul(100).round(2).to_dict())
