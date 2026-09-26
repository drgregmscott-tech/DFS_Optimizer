"""Step 4: diagnostics + refit of the DK showdown ownership model on REPLAYED (our-projection) features.
Inputs (gitignored): own_feats_ourproj[_<tag>].parquet (sd_features.py), own_feats_real4.parquet.
Writes candidate artifact to data/fc_history/derived/showdown/ownership_model_showdown_dk.candidate.json (never the
production artifact) and prints aggregate tables only.
    python analysis/showdown_history/refit_ourproj.py [--tag qb] [--section abcd] [--write]"""
import argparse, json, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
R = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(R / "scripts"))
import ownership_model_showdown as oms
SD = R / "data/fc_history/derived/showdown"
CAP, BUD = oms.CAP, oms.BUDGET
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)


def load(tag):
    H = pd.read_parquet(SD / ("own_feats_ourproj.parquet" if tag == "qb" else f"own_feats_ourproj_{tag}.parquet"))
    H["src"] = "hist"; H["year"] = H.season
    RL = pd.read_parquet(SD / "own_feats_real4.parquet"); RL["src"] = "real"; RL["year"] = 2026
    extra = []
    for s in RL.slate.unique():
        p = pd.read_csv(R / "output" / f"final_projections_dk_{s}.csv", dtype={"player_id": str})
        extra.append(p[["player_id", "roster_role", "team", "salary", "final_projection"]].assign(slate=s))
    RL = RL.merge(pd.concat(extra), on=["slate", "player_id", "roster_role"], how="left")
    cols = ["slate", "year", "src", "player_id", "position", "team", "salary", "final_projection", "role", "live", "own",
            "l_exp", "isK", "isD", "isMin"]
    D = pd.concat([H[cols], RL[cols]], ignore_index=True)
    D["position"] = D.position.astype(str).replace({"D": "DST", "DEF": "DST"})
    D["sal_flex"] = D.salary / np.where(D.role == "CPT", 1.5, 1.0)
    for p in ("QB", "RB", "TE"):
        D["is" + p] = (D.position == p).astype(float)
    D["lsal"] = np.log(D.sal_flex.clip(lower=200) / 1000.0)
    D["fp"] = D.final_projection / np.where(D.role == "CPT", 1.5, 1.0)
    D["pshare"] = D.fp / D.groupby(["slate", "role"]).fp.transform(lambda x: x.nlargest(6).sum())
    D["lrank"] = np.log(D.groupby(["slate", "role"]).fp.rank(ascending=False, method="first"))
    return D


KD_REAL_ONLY = False  # --kd-real-only: drop HISTORY K/DST rows from training (replay K/DST l_exp is not faithful)


def fit_role(tr, role, F, lam=5.0, w_real=3.0, w25=2.0):
    t = tr[(tr.role == role) & tr.live]
    if KD_REAL_ONLY:
        t = t[~((t.src == "hist") & t.position.isin(["K", "DST"]))]
    w = np.where(t.year == 2025, w25, 1.0) * np.where(t.src == "real", w_real, 1.0)
    X = t[F]; mu = X.mean(); sd = X.std().replace(0, 1.0).fillna(1.0)
    A = np.c_[np.ones(len(t)), ((X - mu) / sd).to_numpy()]
    P = np.eye(A.shape[1]) * lam; P[0, 0] = 0
    Aw = A * w[:, None]
    wt = np.linalg.solve(Aw.T @ A + P, Aw.T @ oms._logit(t.own, CAP[role]))
    return {"intercept": float(wt[0]), "coefs": dict(zip(F, map(float, wt[1:]))),
            "mu": mu.astype(float).to_dict(), "sd": sd.astype(float).to_dict()}


def predict(g, art, F, floor=0.0):
    """oms.predict generalised to feature list F + optional additive raw floor (pct pts, live rows) before waterfill."""
    out = pd.Series(0.0, index=g.index)
    for (s, role), gs in g.groupby(["slate", "role"]):
        m = art["roles"][role]
        X = (gs[F] - pd.Series(m["mu"])) / pd.Series(m["sd"])
        z = m["intercept"] + X.to_numpy() @ np.array([m["coefs"][k] for k in F])
        fl = floor[role] if isinstance(floor, dict) else floor
        raw = np.where(gs.live.to_numpy(), oms._inv(z, CAP[role]) + fl, 0.0)
        out.loc[gs.index] = oms._waterfill(raw, BUD[role], CAP[role])
    return out


def metrics(g, pred, label):
    rows = []
    for role in ("CPT", "FLEX"):
        m = (g.role == role) & g.live
        a, p = g.own[m].to_numpy(), pred[m].to_numpy()
        th = 20 if role == "FLEX" else 8; ch = a >= th
        r = dict(set=label, role=role, n=int(m.sum()), corr=round(np.corrcoef(a, p)[0, 1], 3),
                 mae=round(np.abs(a - p).mean(), 2), chalk_mae=round(np.abs(a - p)[ch].mean(), 1),
                 chalk_bias=round((p - a)[ch].mean(), 1))
        gg = g[m].assign(p=pred[m])
        r["top1"] = round(float(np.mean([gs.own.idxmax() == gs.p.idxmax() for _, gs in gg.groupby("slate")])), 2)
        for pos in ("QB", "RB", "WR", "TE", "K", "DST"):
            mp = m & (g.position == pos)
            r["b_" + pos] = round(float((pred[mp] - g.own[mp]).mean()), 1)
        mt = m & (g.sal_flex > 1000) & (g.sal_flex <= 3000)
        r["b_1-3k"] = round(float((pred[mt] - g.own[mt]).mean()), 1)
        lo, hi = (2, 10) if role == "FLEX" else (1, 5)
        r["tail_pred"] = int(((p >= lo) & (p < hi)).sum()); r["tail_act"] = int(((a >= lo) & (a < hi)).sum())
        rows.append(r)
    return rows


def loso(D, F, floor=0.0, **kw):
    pr = pd.Series(np.nan, index=D.index)
    for s in D.slate.unique():
        art = {"roles": {r: fit_role(D[D.slate != s], r, F, **kw) for r in ("CPT", "FLEX")}}
        gs = D[D.slate == s]; pr.loc[gs.index] = predict(gs, art, F, floor)
    return pr


SETS = {
    "base4": oms.FEATURES,
    "+pos(QB,RB,TE)": oms.FEATURES + ["isQB", "isRB", "isTE"],
    "+lsal": oms.FEATURES + ["lsal"],
    "+pos+lsal": oms.FEATURES + ["isQB", "isRB", "isTE", "lsal"],
    "+pshare": oms.FEATURES + ["pshare"],
    "+pos+lsal+pshare": oms.FEATURES + ["isQB", "isRB", "isTE", "lsal", "pshare"],
    "+pos+lsal+lrank": oms.FEATURES + ["isQB", "isRB", "isTE", "lsal", "lrank"],
}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", default="qb"); ap.add_argument("--write", action="store_true")
    ap.add_argument("--section", default="abcd"); ap.add_argument("--cand", default="base4")
    ap.add_argument("--cand-floor", type=float, default=0.0)
    ap.add_argument("--kd-real-only", action="store_true")
    a = ap.parse_args()
    global KD_REAL_ONLY
    KD_REAL_ONLY = a.kd_real_only
    D = load(a.tag); H = D.src == "hist"; RLm = D.src == "real"; Y25 = H & (D.year == 2025)
    F0 = oms.FEATURES
    cur = json.loads(oms.ARTIFACT.read_text())
    g0 = D[D.slate == D[RLm].slate.iloc[0]]
    assert np.allclose(predict(g0, cur, F0).values, oms.predict(g0, cur).values, atol=1e-6)

    if "a" in a.section:
        print("\n=== 4(a) replay faithfulness: mean l_exp / realized own / projection, live rows ===")
        L = D[D.live].copy(); L["grp"] = np.where(L.src == "real", "real4", "h" + L.year.astype(str))
        t = L.groupby(["role", "position", "grp"]).agg(l_exp=("l_exp", "mean"), own=("own", "mean"),
                                                      fp=("fp", "mean")).round(2).unstack("grp")
        print(t.to_string())
        n = L.groupby(["grp", "position"]).size().unstack() / L.groupby("grp").slate.nunique().values[:, None] / 2
        print("\nlive players per slate:\n", n.round(1).to_string())
        tp = D[D.role == "FLEX"].sort_values("fp", ascending=False).groupby("slate").head(1)
        print("\n#1 projected player position share:", tp.groupby("src").position.value_counts(normalize=True).round(2).to_dict())
        # QB share of top-6 projection, and top-6 projection level
        t6 = D[D.role == "FLEX"].sort_values("fp", ascending=False).groupby("slate").head(6)
        print("top-6 mean fp:", t6.groupby("src").fp.mean().round(2).to_dict(),
              "| QB fp / mean top-6 non-QB fp:", t6.groupby("src").apply(lambda x: x[x.position == "QB"].fp.mean() / x[x.position != "QB"].fp.mean()).round(2).to_dict())
        print("frac live FLEX rows never rostered by ILP (l_exp at floor):",
              L[L.role == "FLEX"].groupby("grp").l_exp.apply(lambda x: (x < -5.7).mean()).round(2).to_dict())
        print("frac live CPT rows never rostered:", L[L.role == "CPT"].groupby("grp").l_exp.apply(lambda x: (x < -5.7).mean()).round(2).to_dict())

    res = []
    if "b" in a.section:
        pc = pd.concat([predict(D[D.slate == s], cur, F0) for s in D.slate.unique()]).reindex(D.index)
        D["pred_cur"] = pc
        res += metrics(D[H], pc[H], "hist49 | CURRENT artifact")
        res += metrics(D[Y25], pc[Y25], "hist2025 | CURRENT artifact")
        res += metrics(D[H & (D.year < 2025)], pc[H & (D.year < 2025)], "hist2023-24 | CURRENT artifact")
        res += metrics(D[RLm], pc[RLm], "real4 | CURRENT artifact (in-sample)")
    if "c" in a.section or "d" in a.section:
        sets = SETS if "d" in a.section else {"base4": F0}
        floors = [0.0, {"CPT": 0.0, "FLEX": 1.0}, {"CPT": 0.0, "FLEX": 2.0}] if "d" in a.section else [0.0]
        for nm, F in sets.items():
            for fl in floors:
                if fl != 0.0 and nm not in ("base4", "+pos+lsal"):
                    continue
                lab = nm + ("" if fl == 0.0 else f" floorFLEX{fl['FLEX']}")
                pl = loso(D, F, fl)
                res += metrics(D[H], pl[H], f"hist49 LOSO | {lab}")
                res += metrics(D[Y25], pl[Y25], f"hist2025 LOSO | {lab}")
                res += metrics(D[RLm], pl[RLm], f"real4 LOSO | {lab}")
                art_h = {"roles": {r: fit_role(D[H], r, F) for r in ("CPT", "FLEX")}}
                res += metrics(D[RLm], predict(D[RLm], art_h, F, fl), f"real4 HELD-OUT fit-hist-only | {lab}")
                if fl == 0.0:
                    D["pred_loso_" + nm] = pl
        pr = pd.Series(np.nan, index=D.index)
        for s in D[RLm].slate.unique():
            art = {"roles": {r: fit_role(D[RLm & (D.slate != s)], r, F0, w_real=1.0) for r in ("CPT", "FLEX")}}
            gs = D[D.slate == s]; pr.loc[gs.index] = predict(gs, art, F0)
        res += metrics(D[RLm], pr[RLm], "real4 LOSO | real-only 4-feat (production recipe)")
    if res:
        T = pd.DataFrame(res); print("\n=== metrics (bias = pred - actual; tail = count FLEX 2-10% / CPT 1-5%) ===")
        print(T.to_string(index=False)); T.to_csv(SD / f"refit_metrics_{a.tag}_{a.section}{'_kdreal' if KD_REAL_ONLY else ''}.csv", index=False)
    Fc = SETS[a.cand]
    final = {"roles": {r: fit_role(D, r, Fc) for r in ("CPT", "FLEX")}}
    D["pred_cand"] = pd.concat([predict(D[D.slate == s], final, Fc, {"CPT": 0.0, "FLEX": a.cand_floor})
                                for s in D.slate.unique()]).reindex(D.index)
    for r in ("CPT", "FLEX"):
        print(f"\n{r} candidate [{a.cand}] intercept {final['roles'][r]['intercept']:.3f} coefs",
              {k: round(v, 3) for k, v in final["roles"][r]["coefs"].items()})
        print(f"{r} current   intercept {cur['roles'][r]['intercept']:.3f} coefs",
              {k: round(v, 3) for k, v in cur["roles"][r]["coefs"].items()})
        print(f"{r} candidate mu", {k: round(v, 3) for k, v in final["roles"][r]["mu"].items()},
              "sd", {k: round(v, 3) for k, v in final["roles"][r]["sd"].items()})
        print(f"{r} current   mu", {k: round(v, 3) for k, v in cur["roles"][r]["mu"].items()},
              "sd", {k: round(v, 3) for k, v in cur["roles"][r]["sd"].items()})
    D.to_parquet(SD / f"refit_frame_{a.tag}.parquet")
    if a.write:
        art = {"roles": final["roles"], "features": Fc, "lambda": 5.0,
               "trained_on": sorted(D[RLm].slate.unique()) + [f"fc_history_showdown_{D[H].slate.nunique()}_slates_2023-2025_ourproj_replay_{a.tag}"],
               "weights": "2025 x2; real 2026 slates x3", "cap": CAP, "budget": BUD,
               "noises": list(oms.NOISES), "n_lineups": oms.N_LINEUPS}
        if a.cand_floor:
            art["raw_floor"] = {"CPT": 0.0, "FLEX": a.cand_floor}
        art["kd_real_only"] = KD_REAL_ONLY
        p = SD / "ownership_model_showdown_dk.candidate.json"; p.write_text(json.dumps(art, indent=2)); print("wrote", p)


if __name__ == "__main__":
    main()
