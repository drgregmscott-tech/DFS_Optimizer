"""
B2/B3 + live-model check. Leave-one-week-out (LOWO) on wk1-3 DK classic (frame.parquet from build_frame.py).

Candidates (all refit per fold on the other two weeks, scripts/fit_ownership_model.fit, ridge 1):
  base        om.FEATURES                       (-> data/ownership_model_dk.json)
  ffc         om.FEATURES + om.FFC_FEATURES     (-> data/ownership_model_dk_ffc.json)
  ffc+rank    ffc + within-position value/projection rank + cheapest-DST flag + cheap-WR/TE value
              (targets the Phase-1 findings: chalk_score ranking, cheap DST, cheap band)
  live_*      the live artifacts as they stand (fit on wk1-2 PRE-guard projections) applied to the
              rebuilt features: wk3 fold is true out-of-sample; wk1/2 folds are in-sample (labelled).
  asbuilt     wk3 only: estimated_ownership_pct in the pre-lock production file (what we actually used).
  +floor(a)   B3: FFC-listed >= 30% -> est = max(model, a*ffc); a picked by LOWO on the train weeks
              (grid .5-1.0, objective = train-week MAE on the meaningful cut). Reported raw and with
              position budgets restored (non-floored players scaled down).

Metrics on the held-out week. Meaningful cut = final_projection > 8 (plus DST, which rarely clears 8).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import fit_ownership_model as fom  # noqa: E402
import ownership_model as om  # noqa: E402
import ownership_heuristic as oh  # noqa: E402

BUDGETS = oh.compute_position_slot_budgets("dk")
LOW_BAND = {"WR": 4500, "TE": 3500, "RB": 5000, "QB": 5500, "DST": 2800}  # Step 5 'low' band (<)
EXTRA = ["l_vrank", "l_prank", "dst_min", "cheap_val"]
# FFC-cliff candidates: unlisted players get l_ffc from the heuristic estimate instead of a flat 1%
SOFT = ["l_est", "l_exp", "sal", "top1sal", "cv", "dart", "lo_proj", "pub_val", "l_ffc_soft", "ffc_listed"]
NOLIST = ["l_est", "l_exp", "sal", "top1sal", "cv", "dart", "lo_proj", "pub_val", "l_ffc_soft"]


def add_extra(df):
    df = df.copy()
    pos = df["position_group"]
    val = df["final_projection"] / (df["salary"] / 1000.0)
    g = [df["slate_id"], pos]
    df["l_vrank"] = -np.log(val.groupby(g).rank(ascending=False, method="min"))
    df["l_prank"] = -np.log(df["final_projection"].groupby(g).rank(ascending=False, method="min"))
    dmin = df[pos == "DST"].groupby("slate_id")["salary"].min()
    df["dst_min"] = ((pos == "DST") & (df["salary"] <= df["slate_id"].map(dmin) + 200)).astype(float)
    df["cheap_val"] = (((pos == "WR") & (df["salary"] < 4500)) | ((pos == "TE") & (df["salary"] < 3500))).astype(float) * val.clip(upper=5)
    ffc = pd.to_numeric(df["ffc_own_pct"], errors="coerce")
    df["l_ffc_soft"] = om._logit(ffc.fillna(df["estimated_ownership_pct"].clip(upper=30)))
    return df


def load():
    df = pd.read_parquet(HERE / "frame.parquet")
    df = add_extra(df)
    pe = pd.read_csv(REPO / "data/projection_error_log.csv", dtype={"player_id": str})
    pe = pe[pe["slate_format"] == "classic"].drop_duplicates(["slate_id", "player_id"])
    df = df.merge(pe[["slate_id", "player_id", "actual_fpts"]], on=["slate_id", "player_id"], how="left")
    df["cut"] = (df["final_projection"] > 8) | (df["position_group"] == "DST")
    df["low_band"] = df["salary"] < df["position_group"].map(LOW_BAND)
    return df


def floor(df, pred, a, renorm):
    ffc = pd.to_numeric(df["ffc_own_pct"], errors="coerce")
    hit = (ffc >= 30) & (a * ffc > pred)
    out = pred.where(~hit, a * ffc)
    if renorm:
        for (_, grp), idx in df.groupby(["slate_id", "position_group"]).groups.items():
            h = hit.loc[idx]
            if not h.any():
                continue
            b = BUDGETS[grp]
            rest = b - out.loc[idx][h].sum()
            free = out.loc[idx][~h]
            if free.sum() > 0 and rest > 0:
                out.loc[free.index] = free * rest / free.sum()
    return out


def metrics(d, p):
    """d = eval frame (one week), p = prediction aligned to d.index."""
    c = d["cut"]
    y, q = d["own"], p
    e = q - y
    ch = c & (y >= 20)
    sub = c & (y < 10)
    top = []
    for _, g in d.groupby("slate_id"):
        top.append(len(set(q.loc[g.index].nlargest(10).index) & set(y.loc[g.index].nlargest(10).index)))
    # cheap band: Step-5 fixed 'low' salary band, NO proj>8 cut (the cut removes most of it);
    # rows the field or the model cared about (real or predicted >= 2%)
    lb = d["low_band"] & ((y >= 2) | (q >= 2))
    wt = lb & d["position_group"].isin(["WR", "TE"])
    fld = d["low_band"] & d["position_group"].isin(["WR", "TE"]) & (y >= 2) & d["actual_fpts"].notna()
    unl = c & (y >= 10) & d["ffc_own_pct"].isna() & (d["position_group"] != "DST")
    return dict(
        corr=np.corrcoef(q[c], y[c])[0, 1], mae=e[c].abs().mean(),
        chalk_n=int(ch.sum()), chalk_bias=e[ch].mean(), chalk_mae=e[ch].abs().mean(),
        sub10_bias=e[sub].mean(), sub10_mae=e[sub].abs().mean(),
        top10=np.mean(top),
        cheap_corr=np.corrcoef(q[lb], y[lb])[0, 1], cheap_mae=e[lb].abs().mean(), cheap_bias5=e[lb & (y >= 5)].mean(),
        cheapWRTE_corr=np.corrcoef(q[wt], y[wt])[0, 1],
        cheapWRTE_gapFP=np.corrcoef(e[fld], d.loc[fld, "actual_fpts"])[0, 1] if fld.sum() > 5 else np.nan,
        unlisted_chalk_bias=e[unl].mean(), unlisted_n=int(unl.sum()),
    )


def fit_pred(train, test, feats):
    art = fom.fit(train, feats=feats)
    return fom.predict_slates(test, art, BUDGETS), art


def pick_a(train, feats):
    ptr, _ = fit_pred(train, train, feats)
    best = None
    for a in np.arange(0.0, 1.01, 0.05):
        m = (floor(train, ptr, a, True) - train["own"])[train["cut"]].abs().mean()
        if best is None or m < best[1]:
            best = (round(a, 2), m)
    return best[0]


FEATS_ALL = {"base": om.FEATURES, "ffc": om.FEATURES + om.FFC_FEATURES,
             "ffc+rank": om.FEATURES + om.FFC_FEATURES + EXTRA,
             "ffc_soft": SOFT, "ffc_soft_nolisted": NOLIST,
             "ffc+dst_min": om.FEATURES + om.FFC_FEATURES + ["dst_min"]}


def main():
    df = load()
    weeks = [1, 2, 3]
    FEATS = FEATS_ALL
    live = {"live_base": om.load_artifact("dk"), "live_ffc": om.load_artifact("dk", "_ffc")}
    rows = []
    preds = {}
    for w in weeks:
        te, tr = df[df.week == w], df[df.week != w]
        P = {}
        for name, f in FEATS.items():
            P[name], _ = fit_pred(tr, te, f)
        for name, art in live.items():
            P[name + (" (OOS)" if w == 3 else " (in-sample)")] = fom.predict_slates(te, art, BUDGETS)
        if w == 3:
            P["asbuilt (live file, OOS)"] = te["est_live"].fillna(0.0)
        a = pick_a(tr, FEATS["ffc"])
        P[f"ffc+floor a={a} raw"] = floor(te, P["ffc"], a, False)
        P[f"ffc+floor a={a} renorm"] = floor(te, P["ffc"], a, True)
        P["ffc+floor a=0.7 renorm"] = floor(te, P["ffc"], 0.7, True)
        if w == 3:
            P[f"asbuilt+floor a={a} renorm"] = floor(te, P["asbuilt (live file, OOS)"], a, True)
        for name, p in P.items():
            r = metrics(te, p)
            r.update(week=w, model=name)
            rows.append(r)
            preds[(w, name.split(" a=")[0])] = p
    res = pd.DataFrame(rows).set_index(["week", "model"]).round(3)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(res.to_string())
    res.to_csv(HERE / "lowo_results.csv")

    # all-rows corr (no cut) for comparability with the .764 baseline (fit_ownership_model scores all rows)
    print("\nAll-rows (no cut) corr / chalk bias, held-out week:")
    for w in weeks:
        te = df[df.week == w]
        for name in ["base", "ffc", "ffc+rank"]:
            p = preds[(w, name)]
            print(f"  wk{w} {name:9s}", fom.score(te, p, name))

    # final full-data fits -> NEW files (never overwrite live artifacts)
    import json
    for name, var in [("base", ""), ("ffc", "_ffc")]:
        art = fom.fit(df, feats=FEATS[name])
        art.update(site="dk", variant=var.strip("_") or "base", weeks=weeks, n_rows=int(len(df)), ridge=fom.RIDGE,
                   exposure_lineups=om.EXPOSURE_LINEUPS, exposure_randomization_pct=om.EXPOSURE_RANDOMIZATION_PCT,
                   slates=sorted(df.slate_id.unique()), fit_at="2026-09-29",
                   note="wk1-2 leak-free rebuilds (current code, pre-lock status applied) + wk3 pre-lock production. NOT LIVE.")
        with open(HERE / f"ownership_model_dk{var}.refit-2026-09-29.json", "w") as f:
            json.dump(art, f, indent=2)
        print(f"\n{name} full-fit coefs:", {k: round(v, 3) for k, v in art["coefs"].items()})
    # coefficient stability across folds
    print("\nFold coefficient stability (ffc):")
    for w in weeks:
        art = fom.fit(df[df.week != w], feats=FEATS["ffc"])
        print(f"  drop wk{w}:", {k: round(v, 2) for k, v in art["coefs"].items()})
    print("\nFold coefficient stability (ffc+rank extras):")
    for w in weeks:
        art = fom.fit(df[df.week != w], feats=FEATS["ffc+rank"])
        print(f"  drop wk{w}:", {k: round(art['coefs'][k], 2) for k in EXTRA + ['l_est', 'l_ffc', 'ffc_listed']})


if __name__ == "__main__":
    main()
