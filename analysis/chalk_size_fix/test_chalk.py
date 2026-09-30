"""Chalk-size candidate: pull the shipped ownership toward RAW FFC for players raw FFC puts in its slate top-N.
Uses the exact code in scripts/ownership_v2.py (apply_vac_bump, apply_chalk_ffc). 2026 wk1-3 real DK ownership,
9 slates. N and b picked leave-one-week-out (objective: overall MAE on the training weeks). No FC data used.
Env DFS_DATA_ROOT: repo root holding the git-ignored data/fc_history/derived/ (default: this repo)."""
import os
import sys
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
DR = Path(os.environ.get("DFS_DATA_ROOT", R))
sys.path.insert(0, str(R / "scripts"))
import ownership_v2 as ov  # noqa

D = DR / "data/fc_history/derived/ownership_v2"
Y = pd.read_parquet(D / "y2026.parquet").reset_index(drop=True)
P = pd.read_parquet(D / "y2026_preds.parquet").reset_index(drop=True)
assert (Y.player_id.values == P.player_id.values).all()
ffc = Y.ffc_own_pct.to_numpy(float)
blend = P["p_new_p_live-FFC_log_blend"].to_numpy(float)
ship, _ = ov.apply_vac_bump(Y, blend.copy())          # shipped = blend + vac bump (both default ON live)
ship = np.where(Y.pos.isin(ov.GROUPS), ship, np.nan)
y = Y.own.fillna(0).to_numpy(float)
BANDS = {"cheapWRTE": (Y.pos.isin(["WR", "TE"]) & (Y.salary < 5500)).to_numpy(),
         "7k+": ((Y.salary >= 7000) & (Y.pos != "DST")).to_numpy(),
         "all": Y.pos.isin(ov.GROUPS).to_numpy()}


def m(p, mask):
    p = np.nan_to_num(p[mask]); t = y[mask]; o = {}
    pos = t > 0
    o["corr"] = np.corrcoef(p[pos], t[pos])[0, 1] if pos.sum() > 2 else np.nan
    o["mae"] = np.abs(p - t).mean()
    for lo, thr, k in ((20, 15, "catch20"), (15, 10, "catch15")):
        h = t >= lo; o[k] = (p[h] >= thr).mean() if h.any() else np.nan
    for lo, hi_, k in ((20, 999, "bias20"), (30, 999, "bias30"), (10, 30, "bias10_30")):
        h = (t >= lo) & (t < hi_); o[k] = (p[h] - t[h]).mean() if h.any() else np.nan
    return o


def top10(p, mask):
    c = []
    for ix in Y[mask].groupby("slate_id").indices.values():
        ix = np.where(mask)[0][ix]; k = max(1, int(round((y[ix] > 0).sum() / 10)))
        c.append(len(set(ix[np.argsort(-y[ix])[:k]]) & set(ix[np.argsort(-np.nan_to_num(p[ix]))[:k]])) / k)
    return np.mean(c)


NS, BS = [3, 5, 8, 10, 15, 20, 30], [0, .25, .5, .75, 1.0]
cache = {(n, b): ov.apply_chalk_ffc(Y, ship.copy(), ffc, n=n, b=b)[0] for n in NS for b in BS}
wk = Y.week.to_numpy()
if __name__ == "__main__":
    grid = []
    for (n, b), p in cache.items():
        r = {"n": n, "b": b}
        for bn, bm in BANDS.items():
            for k, v in m(p, bm).items():
                r[f"{bn}_{k}"] = v
        grid.append(r)
    G = pd.DataFrame(grid)
    pd.set_option("display.width", 250)
    print("FULL GRID (all 3 weeks pooled, in-sample, for reference)")
    print(G[["n", "b", "all_mae", "all_corr", "all_bias20", "cheapWRTE_corr", "cheapWRTE_mae", "cheapWRTE_bias20",
             "7k+_corr", "7k+_mae", "7k+_bias20", "7k+_bias30", "7k+_bias10_30"]].round(3).to_string())
    chosen, held = {}, np.full(len(Y), np.nan)
    for w in (1, 2, 3):
        tr = (wk != w) & BANDS["all"]
        best = min(cache, key=lambda k: (np.abs(np.nan_to_num(cache[k][tr]) - y[tr]).mean(), k[1]))
        chosen[w] = best; te = wk == w; held[te] = cache[best][te]
    print("\nLOWO chosen (n, b) by training-week MAE:", chosen)
    rows = {}
    for w in (1, 2, 3, "all"):
        wm = (wk == w) if w != "all" else np.ones(len(Y), bool)
        for bn, bm in BANDS.items():
            for name, p in (("shipped", ship), ("chalk LOWO", held), ("raw FFC", np.nan_to_num(ffc))):
                r = m(p, bm & wm)
                if bn == "all":
                    r["top10pct"] = top10(p, bm & wm)
                rows[(w, bn, name)] = r
    T = pd.DataFrame(rows).T.astype(float).round(3)
    print(T.to_string())
    ffc_listed = np.isfinite(ffc) & (ffc > 0)
    print("\nFFC coverage of real 20%+ skill players:", round(ffc_listed[(y >= 20) & BANDS["all"]].mean(), 3))
    pd.DataFrame({"week": wk, "player": Y.player, "pos": Y.pos, "salary": Y.salary, "own": y, "shipped": ship,
                  "chalk": held, "ffc": ffc}).query("own >= 15 or chalk >= 15 or shipped >= 15") \
        .to_csv(DR / "data/fc_history/derived/chalk_size_fix_rows.csv", index=False)
