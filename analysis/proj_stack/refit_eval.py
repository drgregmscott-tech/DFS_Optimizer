"""Refit the projection stack on guarded history and compare old / refit / no-stack / QB-recal.
Research only; no FC data here. Reads data/fc_history/derived/proj_stack/train.csv (build_train.py).
Writes data/fc_history/derived/proj_stack/{preds.csv, eval.txt, lineups.csv, lineups.txt}
and (with --write-artifact) data/projection_stack_dk_refit_2026-09-26.json (fit 2021-2025, all rows).
    python analysis/proj_stack/refit_eval.py [--write-artifact] [--no-lineups]
"""
import argparse, json, os, sys, multiprocessing as mp
from datetime import datetime, timezone
import numpy as np, pandas as pd
from scipy.stats import spearmanr

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(R, "scripts"))
sys.path.insert(0, os.path.join(R, "analysis/proj_lineup_level"))
import projection_stack as ps  # noqa: E402
import fit_projection_stack as fps  # noqa: E402
import lineup_eval as le  # noqa: E402

OUT = os.path.join(R, "data/fc_history/derived/proj_stack")
ART_NEW = os.path.join(R, "data/projection_stack_dk_refit_2026-09-26.json")
FIT_SEASONS = [2021, 2022, 2023, 2024, 2025]


def fit_art(T, seasons):
    tr = T[T.season.isin(seasons) & T.covd]
    fill = {c: float(tr[c].mean()) for c in ps.USAGE_COLS}
    art = {"version": 1, "site": "dk", "fit_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_rows": int(len(tr)), "seasons": [int(s) for s in seasons], "features": ps.FEATURES,
           "usage_fill": fill, "positions": {},
           "note": "Refit 2026-09-26 on guarded (QB1-from-salary) production-faithful rebuild, DK main slates, "
                   "actual = DK pts with DNP=0 (same convention as the 2020-21 fit). analysis/proj_stack/."}
    for pos in ps.POSITIONS:
        d = tr[tr.position == pos].copy()
        for c in ps.USAGE_COLS:
            d[c] = d[c].fillna(fill[c])
        b = fps.ridge_solve(fps.design(d, pos), d["act"].to_numpy(float))
        names = ["sal", "proj"] + fps.POS_USAGE[pos]
        coefs = {f: 0.0 for f in ps.FEATURES}
        coefs.update({f: float(v) for f, v in zip(names, b[1:])})
        art["positions"][pos] = {"intercept": float(b[0]), "coefs": coefs, "n": int(len(d))}
    return art


def apply_art(T, art):
    """Runtime-equivalent: S = X@coef with usage NaN -> artifact usage_fill; clamp [0.5E,1.8E]; >=0."""
    out = T.final_projection.copy().astype(float)
    for pos in ps.POSITIONS:
        m = T.covd & (T.position == pos)
        b = art["positions"][pos]
        X = [np.ones(m.sum()), T.loc[m, "salary"].to_numpy(float) / 1000, T.loc[m, "engine_projection"].to_numpy(float)]
        X += [T.loc[m, c].fillna(art["usage_fill"][c]).to_numpy(float) for c in ps.USAGE_COLS]
        S = np.column_stack(X) @ np.array([b["intercept"]] + [b["coefs"][f] for f in ps.FEATURES])
        e = T.loc[m, "engine_projection"].to_numpy(float)
        out.loc[m] = np.clip(np.clip(S, 0.5 * e, 1.8 * e), 0, None)
    return out


def wb(w):
    return np.select([w <= 1, w <= 4, w <= 9], [0, 1, 2], 3)


def metrics(d, col):
    y, p = d.act.to_numpy(float), d[col].to_numpy(float)
    sl = np.polyfit(p, y, 1)[0] if len(d) > 10 else np.nan
    sp = d.groupby("slate").apply(lambda g: spearmanr(g[col], g.act)[0] if len(g) > 3 else np.nan).mean()
    return dict(n=len(d), bias=np.mean(p - y), slope=sl, mae=np.mean(np.abs(p - y)), rmse=np.sqrt(np.mean((p - y) ** 2)), sp=sp)


TOPN = {"QB": 5, "RB": 10, "WR": 15, "TE": 5}


def topn(d, col, pos):
    return d.groupby("slate").apply(lambda g: g.nlargest(TOPN[pos], col).act.mean()).mean()


def job(a):
    s, sal, pos, act, pids, objs, k = a
    best = le.solve_k(sal, pos, act, 1)[0]
    rows = []
    for v, obj in objs.items():
        for r, L in enumerate(le.solve_k(sal, pos, obj, k)):
            rows.append(dict(slate=s, var=v, rank=r, score=act[L].sum(), best=act[best].sum(),
                             qb=pids[[i for i in L if pos[i] == "QB"][0]], players="|".join(pids[L])))
    return rows


def boot(d, n=4000, seed=1):
    rng = np.random.default_rng(seed)
    d = np.asarray(d); idx = rng.integers(0, len(d), (n, len(d)))
    m = d[idx].mean(1)
    return d.mean(), np.percentile(m, 2.5), np.percentile(m, 97.5), d.std(ddof=1) / np.sqrt(len(d))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--write-artifact", action="store_true"); ap.add_argument("--no-lineups", action="store_true")
    a = ap.parse_args()
    T = pd.read_csv(os.path.join(OUT, "train.csv"), dtype={"player_id": str})
    T = T[T.salary > 0].reset_index(drop=True)
    T["slate"] = T.season * 100 + T.week
    T["covd"] = T.position.isin(ps.POSITIONS) & (T.engine_projection > 0)
    T["old"] = T.final_projection
    T["none"] = np.where(T.covd, T.engine_projection, T.final_projection)
    # refit LOSO (2021-25 held out one at a time; 2026 = full 2021-25 fit) and forward (fit 2021-23)
    T["refit"] = np.nan
    arts = {}
    for s in FIT_SEASONS:
        arts[s] = fit_art(T, [x for x in FIT_SEASONS if x != s])
        m = T.season == s; T.loc[m, "refit"] = apply_art(T[m], arts[s])
    full = fit_art(T, FIT_SEASONS)
    m = T.season == 2026; T.loc[m, "refit"] = apply_art(T[m], full)
    fwd = fit_art(T, [2021, 2022, 2023])
    T["fwd"] = apply_art(T, fwd)
    # QB linear recal on old final (QB1 rows by salary, week bucket, LOSO; 2026 = 2021-25), QBs with q>5 only
    T["wb"] = wb(T.week)
    isq = T.position == "QB"
    T["qb1"] = isq & (T[isq].groupby(["slate", "team"]).salary.rank(ascending=False, method="first") == 1).reindex(T.index, fill_value=False)
    T["qcal"] = T.old
    for s in T.season.unique():
        for b in range(4):
            fr = T[T.qb1 & (T.season != s) & (T.season <= 2025) & (T.wb == b)]
            mm = isq & (T.season == s) & (T.wb == b) & (T.old > 5)
            if len(fr) >= 50 and mm.any():
                sl, ic = np.polyfit(fr.old, fr.act, 1)
                T.loc[mm, "qcal"] = ic + sl * T.loc[mm, "old"]
    VARS = ["old", "none", "refit", "fwd", "qcal"]
    for v in VARS:
        T[v] = T[v].fillna(0).clip(lower=0)
    T.to_csv(os.path.join(OUT, "preds.csv"), index=False)

    out = []
    for name, art in [("OLD 2020-21", ps.load_artifact("dk")), ("REFIT 2021-25", full), ("FWD 2021-23", fwd)]:
        out.append(f"{name}: " + " | ".join(f"{p} ic{art['positions'][p]['intercept']:+.2f} sal{art['positions'][p]['coefs']['sal']:+.2f} "
                                             f"proj{art['positions'][p]['coefs']['proj']:+.3f}" for p in ps.POSITIONS))
    C = T[T.covd]
    out.append("\n== per position x season (stack-covered rows, engine>0; act DNP=0). cells: bias/slope/mae/rmse/sp/topN ==")
    for pos in ps.POSITIONS:
        for seas in [2021, 2022, 2023, 2024, 2025, 2026, "2023+", "ALL"]:
            d = C[C.position == pos]
            d = d[d.season >= 2023] if seas == "2023+" else (d if seas == "ALL" else d[d.season == seas])
            vs = VARS if pos == "QB" else ["old", "none", "refit", "fwd"]
            cells = []
            for v in vs:
                mt = metrics(d, v)
                cells.append(f"{v}:{mt['bias']:+.2f}/{mt['slope']:.2f}/{mt['mae']:.2f}/{mt['rmse']:.2f}/{mt['sp']:.3f}/{topn(d, v, pos):.2f}")
            out.append(f"{pos} {seas} n{len(d)} | " + " | ".join(cells))
    out.append("\n== tier: top-12 by old proj within slate/pos (QB top-8), 2023+ : bias old/none/refit/qcal ==")
    for pos in ps.POSITIONS:
        d = C[(C.position == pos) & (C.season >= 2023)].copy()
        k = 8 if pos == "QB" else 12
        d = d[d.groupby("slate").old.rank(ascending=False, method="first") <= k]
        out.append(f"{pos} n{len(d)} act{d.act.mean():.2f} " + " ".join(f"{v}:{(d[v]-d.act).mean():+.2f}" for v in ["old", "none", "refit", "fwd", "qcal"]))
    out.append("\n== mean shift vs old, QB top-5 by old per slate, by season (refit-old, qcal-old) ==")
    d = C[(C.position == "QB")].copy(); d = d[d.groupby("slate").old.rank(ascending=False, method="first") <= 5]
    out.append(" ".join(f"{s}:{(g.refit-g.old).mean():+.2f}/{(g.qcal-g.old).mean():+.2f}" for s, g in d.groupby("season")))
    txt = "\n".join(out); print(txt)
    open(os.path.join(OUT, "eval.txt"), "w").write(txt)

    if a.write_artifact:
        with open(ART_NEW, "w", encoding="utf-8") as f:
            json.dump(full, f, indent=2)
        print("wrote", ART_NEW)
    if a.no_lineups:
        return
    LV = ["old", "none", "refit", "qcal", "fwd"]
    jobs = [(s, g.salary.values.astype(float), g.pos.values, g.act.values,
             g.player_id.values, {v: g[v].values for v in LV}, 5) for s, g in T[T.pos.isin(le.POS)].groupby("slate")]
    with mp.get_context("spawn").Pool(12) as p:
        res = p.map(job, jobs, chunksize=1)
    L = pd.DataFrame([r for rr in res for r in rr]); L["season"] = L.slate // 100
    L["cash"] = L.score >= le.CASH * L.best
    L.to_csv(os.path.join(OUT, "lineups.csv"), index=False)
    o = [f"slates {L.slate.nunique()}"]
    for sub, name in [(L[L["rank"] == 0], "top-1"), (L, "top-5 avg")]:
        piv = sub.groupby(["slate", "var"]).agg(score=("score", "mean"), cash=("cash", "mean")).unstack("var")
        seas = piv.index // 100
        o.append(f"\n== {name} ==  ALL " + " ".join(f"{v}:{piv['score'][v].mean():.1f}/{piv['cash'][v].mean():.2f}" for v in LV))
        for v in ["none", "refit", "qcal", "fwd"]:
            d = piv["score"][v] - piv["score"]["old"]
            mm, lo, hi, se = boot(d)
            rec = d[seas >= 2023]; r2 = boot(rec)
            o.append(f"{v}-old {mm:+.2f} [{lo:+.2f},{hi:+.2f}] MDE80%={2.8*se:.2f} | 2023+ {r2[0]:+.2f} [{r2[1]:+.2f},{r2[2]:+.2f}] n{len(rec)} | "
                     + " ".join(f"{s}:{d[seas == s].mean():+.1f}" for s in sorted(set(seas))) + f" | cash {(piv['cash'][v]-piv['cash']['old']).mean():+.3f}")
    t = L[L["rank"] == 0].pivot(index="slate", columns="var", values="qb")
    pl = L[L["rank"] == 0].pivot(index="slate", columns="var", values="players")
    o.append("\nflips vs old (top-1) QB: " + " ".join(f"{v}:{(t[v] != t['old']).mean():.2f}" for v in LV)
             + " | lineup: " + " ".join(f"{v}:{(pl[v] != pl['old']).mean():.2f}" for v in LV))
    txt = "\n".join(o); print(txt)
    open(os.path.join(OUT, "lineups.txt"), "w").write(txt)


if __name__ == "__main__":
    main()
