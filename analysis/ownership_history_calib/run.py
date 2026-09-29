"""Ownership shape/calibration answers from FC history (2021-25), held-out check on 2026 wk1-3.

Base predictions
  history : live base artifact data/ownership_model_dk.json applied to OUR regenerated projections
            (fc_own_features_ourproj.parquet), pub_val=0 (DK AvgPPG not in history). Robustness: a
            history-LOSO refit of the same recipe (BASE feats).
  2026    : analysis/ownership_refit_wk3/frame.parquet -- (a) live artifacts (FFC variant where >=25 listed;
            wk1-2 in-sample for them, wk3 out-of-sample) and (b) FFC-recipe LOWO refit (all 3 weeks OOS).
Every calibration / residual layer is fit on history only (LOSO over seasons for history numbers; all
2021-25 for the 2026 check), so all 9 2026 slates are held out for the layer.
FC-derived data: reads data/fc_history/derived (gitignored). Writes only into this folder.
"""
import json
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "analysis/ownership_fc_refit"))
import ownership_model as om  # noqa: E402
from evaluate import BASE, fit, predict, linpred  # noqa: E402

DER = REPO / "data/fc_history/derived"
CHEAP = {"WR": 4500, "TE": 3500, "RB": 5000, "QB": 5500, "DST": 2800}


# ---------------------------------------------------------------- data
def rank_feats(df):
    df = df.copy()
    df["position_group"] = np.where(df.position.isin(list(om.DEFENSE_LABELS)), "DST", df.position)
    df["position"] = df["position_group"]
    live = df.final_projection > 0
    g = [df.slate_id, df.position]
    df["val"] = df.final_projection / (df.salary / 1000)
    df["l_valrank"] = np.log(df.val.where(live).groupby(g).rank(ascending=False, method="min").fillna(99))
    df["l_projrank"] = np.log(df.final_projection.where(live).groupby(g).rank(ascending=False, method="min").fillna(99))
    mn = df.salary.where(live & (df.position == "DST")).groupby(df.slate_id).transform("min")
    df["min_dst"] = ((df.position == "DST") & (df.salary == mn)).astype(float)
    cw = ((df.position == "WR") & (df.salary < 4500)) | ((df.position == "TE") & (df.salary < 3500))
    df["cheap_wrte_val"] = np.where(cw, df.val, 0.0)
    df["cheap"] = df.salary < df.position.map(CHEAP)
    return df


def load_hist():
    h = pd.read_parquet(DER / "fc_own_features_ourproj.parquet")
    h = h[h.season <= 2025].copy()
    h["pub_val"] = 0.0
    m = pd.read_csv(DER / "fc_master_mapped.csv", dtype={"player_id": str}, low_memory=False,
                    usecols=["source_file", "player_id", "score", "contest", "slate_kind"])
    m = m[(m.contest == "single_entry") & (m.slate_kind == "classic")].drop_duplicates(["source_file", "player_id"])
    h = h.merge(m[["source_file", "player_id", "score"]].rename(columns={"source_file": "slate_id", "score": "fpts"}),
                on=["slate_id", "player_id"], how="left")
    return rank_feats(h)


def load_2026():
    f = pd.read_parquet(REPO / "analysis/ownership_refit_wk3/frame.parquet")
    f["season"] = 2026
    f["ffc_listed"] = f["ffc_listed"].fillna(0)
    e = pd.read_csv(REPO / "data/projection_error_log.csv", dtype={"player_id": str})
    e = e[e.site == "dk"].drop_duplicates(["slate_id", "player_id"])
    f = f.merge(e[["slate_id", "player_id", "actual_fpts"]].rename(columns={"actual_fpts": "fpts"}),
                on=["slate_id", "player_id"], how="left")
    return rank_feats(f)


def hasf(df):
    return df.groupby("slate_id")["ffc_listed"].transform("sum") >= om.MIN_FFC_LISTED


# ---------------------------------------------------------------- calibration layer
def waterfill(r, b, cap):
    out, free, rem = np.zeros(len(r)), r > 0, b
    for _ in range(20):
        tot = r[free].sum()
        if tot <= 0 or rem <= 0:
            break
        trial = np.where(free, r / tot * rem, 0.0)
        over = free & (trial > cap)
        if not over.any():
            return np.where(free, trial, out)
        out = np.where(over, cap, out)
        rem -= cap * over.sum()
        free &= ~over
    return out


def calib(df, p, mid=1.0, temp=1.0, cap=75.0, dst_t=1.0, lo=5500, hi=6999):
    """Total-preserving per slate x position group: power `temp` (non-DST; <1 flatter), x`mid` on
    salary lo..hi (non-DST), power `dst_t` on DST (>1 sharper), then water-filled cap."""
    if mid == 1 and temp == 1 and cap >= 75 and dst_t == 1:
        return p
    out = p.copy()
    pv, sal, isd = p.to_numpy(float), df.salary.to_numpy(float), (df.position == "DST").to_numpy()
    key = df.slate_id.astype(str) + "|" + df.position
    for _, idx in pd.Series(np.arange(len(df))).groupby(key.to_numpy()).groups.items():
        idx = np.asarray(idx)
        x = pv[idx]
        b = x.sum()
        if b <= 0:
            continue
        if isd[idx[0]]:
            r = np.where(x > 0, x ** dst_t, 0.0)
        else:
            r = np.where(x > 0, x ** temp, 0.0) * np.where((sal[idx] >= lo) & (sal[idx] <= hi), mid, 1.0)
        out.iloc[idx] = waterfill(r, b, cap)
    return out


# ---------------------------------------------------------------- metrics
def metrics(df, p):
    cut = (df.final_projection > 8) | (df.position == "DST")
    y, q = df.own[cut].to_numpy(float), p[cut].to_numpy(float)
    r = {"corr": np.corrcoef(q, y)[0, 1], "mae": np.abs(q - y).mean()}
    ch = y >= 20
    r["chalk_bias"] = (q - y)[ch].mean()
    r["chalk_mae"] = np.abs(q - y)[ch].mean()
    r["sub10_mae"] = np.abs(q - y)[y < 10].mean()
    t = (y >= 10) & (y < 20)
    r["t1020_bias"] = (q - y)[t].mean()
    g = df.assign(p=p, y=df.own)
    per = g.groupby("slate_id")
    r["top10"] = per.apply(lambda x: len(set(x.nlargest(10, "p").index) & set(x.nlargest(10, "y").index))).mean()
    r["n1020_pred"] = per.p.apply(lambda x: ((x >= 10) & (x < 20)).sum()).mean()
    r["n1020_real"] = per.y.apply(lambda x: ((x >= 10) & (x < 20)).sum()).mean()
    r["top_pred"], r["top_real"] = per.p.max().mean(), per.y.max().mean()
    nd = g[g.position != "DST"]
    tiers = pd.cut(nd.salary, [0, 5499, 6999, 99999], labels=["lo", "mid", "hi"])
    ts = nd.groupby([nd.slate_id, tiers], observed=False)[["p", "y"]].sum()
    tsm = ts.groupby(level=1, observed=False).mean()
    for k in ("lo", "mid", "hi"):
        r[f"tier_{k}"] = tsm.loc[k, "p"] - tsm.loc[k, "y"]  # pred - real tier total, per slate
    r["tier_abs"] = (ts.p - ts.y).abs().groupby(level=0).sum().mean()
    cb = g[g.cheap & ((g.y >= 2) | (g.p >= 2))]
    r["cheap_corr"] = np.corrcoef(cb.p, cb.y)[0, 1]
    r["cheap_mae"] = (cb.p - cb.y).abs().mean()
    cw = cb[cb.position.isin(["WR", "TE"]) & (cb.y >= 2) & cb.fpts.notna()]
    r["cheapWRTE_gapFP"] = np.corrcoef(cw.p - cw.y, cw.fpts)[0, 1] if len(cw) > 5 else np.nan
    d = g[g.position == "DST"]
    r["dst_top_bias"] = per_top(d)
    dc = d[d.y >= 15]
    r["dst_chalk_bias"] = (dc.p - dc.y).mean() if len(dc) else np.nan
    r["dst_top1_hit"] = d.groupby("slate_id").apply(lambda x: x.p.idxmax() == x.y.idxmax()).mean()
    return r


def per_top(d):
    return d.groupby("slate_id").apply(lambda x: x.loc[x.y.idxmax(), "p"] - x.y.max()).mean()


COLS = ["corr", "mae", "chalk_bias", "chalk_mae", "sub10_mae", "t1020_bias", "top10", "n1020_pred", "n1020_real",
        "top_pred", "top_real", "tier_lo", "tier_mid", "tier_hi", "tier_abs", "cheap_corr", "cheap_mae",
        "cheapWRTE_gapFP", "dst_top_bias", "dst_chalk_bias", "dst_top1_hit"]


def row(label, fold, df, p):
    r = metrics(df, p)
    r.update(model=label, fold=fold)
    return r


# ---------------------------------------------------------------- history fits
def fit_offset(train, feats, off, ridge=1.0):
    X = train[feats].to_numpy(float)
    y = om._logit(train["own"].to_numpy(float)) - off
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    A = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    pen = np.eye(A.shape[1]) * ridge
    pen[0, 0] = 0
    b = np.linalg.solve(A.T @ A + pen, A.T @ y)
    co = b[1:] / sd
    return {"intercept": float(b[0] - np.sum(co * mu)), **{n: float(c) for n, c in zip(feats, co)}}


def with_residual(art, res):
    co = dict(art["coefs"])
    co["intercept"] += res["intercept"]
    feats = list(art["features"])
    for k, v in res.items():
        if k != "intercept":
            co[k] = co.get(k, 0.0) + v
            if k not in feats:
                feats.append(k)
    return {"coefs": co, "cap": art.get("cap", om.OWNERSHIP_CAP_PCT), "features": feats}


def grid_fit(df, p, grid, obj="mae"):
    best, bk = None, None
    for kw in grid:
        v = fast_obj(df, calib(df, p, **kw), obj)
        if best is None or v < best:
            best, bk = v, kw
    return bk


def fast_obj(df, p, obj):
    cut = ((df.final_projection > 8) | (df.position == "DST")).to_numpy()
    y, q = df.own.to_numpy(float), p.to_numpy(float)
    mae = np.abs(q - y)[cut].mean()
    if obj == "mae":
        return mae
    ch = cut & (y >= 20)
    cb = (q - y)[ch].mean()
    nd = (df.position != "DST").to_numpy()
    tier = np.digitize(df.salary.to_numpy(float), [5500, 7000])
    k = pd.Series((q - y)[nd]).groupby([df.slate_id.to_numpy()[nd], tier[nd]]).sum().abs()
    tabs = k.sum() / df.slate_id.nunique()
    return mae + 0.02 * tabs + 0.05 * abs(cb)


RANKS = ["l_valrank", "l_projrank", "min_dst", "cheap_wrte_val"]
CANDS = {  # fixed-value candidates (from the handoff) + single-lever variants
    "none": {},
    "cap60": {"cap": 60},
    "cap65": {"cap": 65},
    "mid1.3": {"mid": 1.3},
    "mid1.45": {"mid": 1.45},
    "mid1.3+cap65": {"mid": 1.3, "cap": 65},
    "mid1.45+cap60": {"mid": 1.45, "cap": 60},
    "temp0.9": {"temp": 0.9},
    "temp0.8": {"temp": 0.8},
    "dst1.25": {"dst_t": 1.25},
    "dst1.5": {"dst_t": 1.5},
    "dst1.75": {"dst_t": 1.75},
}
GRID = [dict(mid=m, temp=t, cap=c, dst_t=d) for m, t, c, d in
        product([1.0, 1.15, 1.3, 1.45], [0.8, 0.9, 1.0, 1.1], [60, 65, 75], [1.0, 1.25, 1.5, 1.75])]
DGRID = [dict(dst_t=d) for d in (0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5)]


def main():
    h = load_hist()
    r26 = load_2026()
    live_b, live_f = om.load_artifact("dk"), om.load_artifact("dk", "_ffc")
    print(f"history {h.slate_id.nunique()} slates {len(h)} rows, fpts matched {h.fpts.notna().mean():.3f}; "
          f"2026 {r26.slate_id.nunique()} slates, fpts matched {r26.fpts.notna().mean():.3f}")
    rows, notes = [], {}
    seasons = sorted(h.season.unique())

    # base predictions on history
    p_live = predict(h, live_b)
    p_refit = pd.Series(0.0, index=h.index)
    for s in seasons:
        te = h.season == s
        p_refit[te] = predict(h[te], fit(h[~te], BASE))
    bases = {"liveBase": p_live, "histRefit": p_refit}

    # Q1/Q3 fixed candidates, per season
    for bn, bp in bases.items():
        for cn, kw in CANDS.items():
            pc = calib(h, bp, **kw)
            for s in seasons:
                m = h.season == s
                rows.append(row(f"{bn}|{cn}", str(s), h[m], pc[m]))
            rows.append(row(f"{bn}|{cn}", "ALL", h, pc))
        # LOSO-fit calibration (joint grid, objective combo) and DST-only (objective dst mae via mae)
        for tag, grid in (("loso_joint", GRID), ("loso_dst", DGRID)):
            pc = pd.Series(0.0, index=h.index)
            picks = {}
            for s in seasons:
                te = h.season == s
                kw = grid_fit(h[~te], bp[~te], grid, obj="combo" if tag == "loso_joint" else "mae")
                picks[int(s)] = kw
                pc[te] = calib(h[te], bp[te], **kw)
                rows.append(row(f"{bn}|{tag}", str(s), h[te], pc[te]))
            rows.append(row(f"{bn}|{tag}", "ALL", h, pc))
            notes[f"{bn}|{tag}_picks"] = picks
            print(bn, tag, picks, flush=True)

    # Q2 rank features: (a) residual layer on live base; (b) refit base recipe + ranks
    for tag, feats in (("resid_ranks", RANKS), ("resid_minDST", ["min_dst"]), ("resid_cheapWRTE", ["cheap_wrte_val"])):
        pc = pd.Series(0.0, index=h.index)
        cos = {}
        for s in seasons:
            te = h.season == s
            res = fit_offset(h[~te], feats, linpred(h[~te], live_b))
            cos[int(s)] = {k: round(v, 3) for k, v in res.items()}
            pc[te] = predict(h[te], with_residual(live_b, res))
            rows.append(row(f"liveBase|{tag}", str(s), h[te], pc[te]))
        rows.append(row(f"liveBase|{tag}", "ALL", h, pc))
        notes[f"{tag}_coefs"] = cos
        print(tag, cos, flush=True)
    pc = pd.Series(0.0, index=h.index)
    for s in seasons:
        te = h.season == s
        pc[te] = predict(h[te], fit(h[~te], BASE + RANKS))
        rows.append(row("histRefit|+ranks", str(s), h[te], pc[te]))
    rows.append(row("histRefit|+ranks", "ALL", h, pc))

    # ---------------- 2026 held-out: layers fit on all of 2021-25
    full_joint = grid_fit(h, p_live, GRID, obj="combo")
    full_dst = grid_fit(h, p_live, DGRID)
    res_full = {t: fit_offset(h, f, linpred(h, live_b)) for t, f in
                (("resid_ranks", RANKS), ("resid_minDST", ["min_dst"]), ("resid_cheapWRTE", ["cheap_wrte_val"]))}
    notes["full_joint"], notes["full_dst"] = full_joint, full_dst
    notes["res_full"] = {k: {a: round(b, 3) for a, b in v.items()} for k, v in res_full.items()}
    print("2021-25 fit: joint", full_joint, "dst", full_dst, flush=True)

    f = hasf(r26)

    def route(df, b, fa):
        p = predict(df, b)
        m = hasf(df)
        if m.any():
            p[m] = predict(df[m], fa)
        return p
    b26 = {"live": (live_b, live_f)}
    lowo = {}
    for w in (1, 2, 3):
        tr = (r26.week != w)
        lowo[w] = (fit(r26[tr], om.FEATURES), fit(r26[tr & f], om.FEATURES + om.FFC_FEATURES))
    p26 = {"live": route(r26, live_b, live_f), "lowoRefit": pd.Series(0.0, index=r26.index)}
    for w in (1, 2, 3):
        te = r26.week == w
        p26["lowoRefit"][te] = route(r26[te], *lowo[w])
    for bn, bp in p26.items():
        variants = {cn: calib(r26, bp, **kw) for cn, kw in CANDS.items()}
        variants["hist_joint"] = calib(r26, bp, **full_joint)
        variants["hist_dst"] = calib(r26, bp, **full_dst)
        for t, res in res_full.items():
            if bn == "live":
                variants[t] = route(r26, with_residual(live_b, res), with_residual(live_f, res))
            else:
                v = pd.Series(0.0, index=r26.index)
                for w in (1, 2, 3):
                    te = r26.week == w
                    v[te] = route(r26[te], with_residual(lowo[w][0], res), with_residual(lowo[w][1], res))
                variants[t] = v
        for cn, pc in variants.items():
            for w in (1, 2, 3):
                m = r26.week == w
                rows.append(row(f"2026-{bn}|{cn}", f"wk{w}", r26[m], pc[m]))
            rows.append(row(f"2026-{bn}|{cn}", "ALL", r26, pc))

    # ---------------- raw diagnostics: DST and cheap band on history (real vs live base)
    d = h.assign(p=p_live)
    dd = d[d.position == "DST"].copy()
    dd["price_rank"] = dd.groupby("slate_id").salary.rank(method="first")
    dd["own_rank"] = dd.groupby("slate_id").own.rank(ascending=False, method="first")
    diag = {
        "hist_dst_by_real_rank": dd.groupby(dd.own_rank.clip(upper=6)).agg(real=("own", "mean"), pred=("p", "mean"), n=("own", "size")).round(1).to_dict(),
        "hist_dst_by_price_q": dd.groupby(pd.qcut(dd.salary, 4).astype(str)).agg(real=("own", "mean"), pred=("p", "mean")).round(2).to_dict(),
        "hist_min_dst": dd[dd.min_dst == 1].agg({"own": "mean", "p": "mean"}).round(2).to_dict(),
        "hist_dst_real_top_share": dd.groupby("slate_id").own.max().mean(),
        "hist_dst_pred_top_share": dd.groupby("slate_id").p.max().mean(),
    }
    cw = d[d.cheap & d.position.isin(["WR", "TE"]) & (d.own >= 2) & d.fpts.notna()]
    diag["hist_cheapWRTE_gapFP_by_season"] = cw.groupby("season").apply(lambda x: round(np.corrcoef(x.p - x.own, x.fpts)[0, 1], 3)).to_dict()
    diag["hist_cheapWRTE_realown_FP_corr"] = round(np.corrcoef(cw.own, cw.fpts)[0, 1], 3)
    diag["hist_cheapWRTE_predown_FP_corr"] = round(np.corrcoef(cw.p, cw.fpts)[0, 1], 3)
    notes["diag"] = diag

    R = pd.DataFrame(rows)[["model", "fold"] + COLS]
    R.to_csv(OUT / "results.csv", index=False)
    json.dump(notes, open(OUT / "notes.json", "w"), indent=1, default=str)
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 500)
    print(R[R.fold == "ALL"].round(3).to_string(index=False))
    print(json.dumps(diag, indent=1, default=str))


if __name__ == "__main__":
    main()
