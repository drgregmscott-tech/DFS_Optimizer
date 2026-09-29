"""Part 1: reverse-engineer FC's pre-lock projected ownership ('Own', 2021-23, 54 slates).
Leave-one-season-out (3 folds). Evaluated on ALL FC slate rows (non-pool rows predicted 0), same as model_vs_fc C.
Output: data/fc_history/derived/ownership_v2/part1_out.txt (+ printed)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import ALL, FAM, Model, metrics, mtable  # noqa: E402
from build import OUT  # noqa: E402

H = pd.read_parquet(OUT / "hist.parquet")
H = H[H.season <= 2023].copy()
# FC-projection features (diagnostic only: FC's projection is not available live)
p = H.in_pool & (H.proj > 0)
H["fc_proj"] = H.fc_proj.fillna(0)
H["fc_val"] = np.where(p, H.fc_proj / H.salk.clip(lower=1), 0)
for c in ["fc_proj", "fc_val"]:
    H[c + "_lrk"] = np.log(H[c].where(p).groupby([H.slate_id, H.grp]).rank(ascending=False).fillna(99))
H["pdep"] = pd.to_numeric(H.pdepth.astype(str).str.extract(r"(\d+)")[0], errors="coerce").fillna(4)
FCF = ["fc_proj", "fc_val", "fc_proj_lrk", "fc_val_lrk"]
TGT = "fc_own"


def lodo(feats, trees=0, df=H, tgt=TGT, **kw):
    pred = np.zeros(len(df)); imp = []
    for s in sorted(df.season.unique()):
        tr, te = df[df.season != s], df[df.season == s]
        m = Model(feats, trees=trees, **kw).fit(tr, tgt)
        pred[(df.season == s).to_numpy()] = m.predict(te)
        if trees:
            imp.append(m.importance())
    return pred, (pd.concat(imp, axis=1).mean(1).sort_values(ascending=False) if imp else None)


def main():
    log = []
    pr = lambda *a: (print(*a), log.append(" ".join(str(x) for x in a)))  # noqa: E731
    rows = {}
    rows["FC Own itself vs FC Own"] = metrics(H, H.fc_own, TGT)
    rows["LIVE artifact (hist base)"] = metrics(H, H.ours_own_model.fillna(0), TGT)
    P = {}
    P["lin_all"], _ = lodo(ALL)
    P["boost_all"], imp = lodo(ALL, trees=150)
    P["boost_all+fcproj"], imp_fc = lodo(ALL + FCF, trees=150)
    P["boost_all+fcproj+pdepth"], _ = lodo(ALL + FCF + ["pdep"], trees=150)
    for k, v in P.items():
        rows[k] = metrics(H, v, TGT)
    pr("=== Target FC Own, LOSO 2021-23, all FC rows ===")
    pr(mtable(rows).to_string())
    pr("\nbooster gain importance (reproducible features):\n" + imp.head(25).round(3).to_string())
    pr("\nbooster gain importance (+FC proj):\n" + imp_fc.head(15).round(3).to_string())
    # ablation: drop one family (linear+trees), and single-family (+price) models
    ab = {}
    base = metrics(H, P["boost_all"], TGT)
    for fam, cols in FAM.items():
        keep = [c for c in ALL if c not in cols]
        pp, _ = lodo(keep, trees=150)
        mm = metrics(H, pp, TGT)
        ab["-" + fam] = {k: mm[k] - base[k] for k in ["corr", "sp_slate", "mae", "catch20", "corr_pos", "corr_cheapWRTE", "corr_7k"]}
    pr("\nDrop-one-family deltas vs boost_all (negative corr = family carries unique signal):")
    pr(pd.DataFrame(ab).T.round(3).to_string())
    single = {}
    for fam, cols in FAM.items():
        if fam == "price":
            continue
        pp, _ = lodo(FAM["price"] + cols, trees=150)
        single["price+" + fam] = metrics(H, pp, TGT)
    pp, _ = lodo(FAM["price"], trees=150)
    single["price only"] = metrics(H, pp, TGT)
    pr("\nPrice + one family (booster):")
    pr(mtable(single).to_string())
    # per-season breakdown
    ps = {}
    for s in [2021, 2022, 2023]:
        m = H.season == s
        ps[f"{s} boost_all"] = metrics(H[m], P["boost_all"][m.to_numpy()], TGT)
        ps[f"{s} live"] = metrics(H[m], H.ours_own_model.fillna(0)[m], TGT)
    pr("\nPer season:"); pr(mtable(ps).to_string())
    # residual: what is left of FC Own after the reproducible model? correlate residual with FC-only info
    res = H.fc_own.fillna(0) - P["boost_all"]
    pm = (H.in_pool & (H.proj > 0)).to_numpy()
    pr("\nResidual (FC Own - boost_all) on pool rows: sd %.2f; corr with fc_proj-ours proj %.3f; with pdepth %.3f; "
       "with realized own - boost_all %.3f" % (
           res[pm].std(), np.corrcoef(res[pm], (H.fc_proj - H.proj)[pm])[0, 1],
           np.corrcoef(res[pm], H.pdep[pm])[0, 1], np.corrcoef(res[pm], (H.own - P["boost_all"])[pm])[0, 1]))
    # how does each predict REALIZED on 2021-23?
    rr = {"FC Own -> realized": metrics(H, H.fc_own.fillna(0), "own"),
          "boost_all(FC teacher) -> realized": metrics(H, P["boost_all"], "own"),
          "live -> realized": metrics(H, H.ours_own_model.fillna(0), "own")}
    pr("\nSame predictions scored against REALIZED ownership 2021-23:"); pr(mtable(rr).to_string())
    H.assign(p1_boost=P["boost_all"], p1_lin=P["lin_all"], p1_fc=P["boost_all+fcproj"])[
        ["slate_id", "player_id", "player", "pos", "salary", "fc_own", "own", "p1_boost", "p1_lin", "p1_fc"]
    ].to_parquet(OUT / "part1_preds.parquet")
    (OUT / "part1_out.txt").write_text("\n".join(log))


if __name__ == "__main__":
    main()
