"""Chalk-temperature candidate: sharpen each position group's ownership shares (share**gamma, re-allocated to the same
group total) -- scripts/ownership_v2.apply_chalk_temp. History 2021-25: v2 LOSO preds (current code, FC-salary rebuild,
cached by the stud study) + vac bump, gamma picked leave-one-season-out. 2026 wk1-3: shipped blend + vac bump, LOWO.
No FC data in this file; FC-derived row outputs go to data/fc_history/derived/chalk_temp/ (git-ignored)."""
import os, sys
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
MAIN = Path(os.environ.get("DFS_MAIN", r"C:\Users\gmsco\Desktop\DFS_Optimizer"))
sys.path.insert(0, str(R / "scripts"))
import ownership_v2 as ov  # noqa
D = MAIN / "data/fc_history/derived"
OUT = D / "chalk_temp"; OUT.mkdir(exist_ok=True)
GAM = [0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0]


def metr(df, p, mask):
    y = df.own.fillna(0).to_numpy(float); p = np.nan_to_num(np.asarray(p, float))
    p, y = p[mask], y[mask]; o = {"n": len(y)}
    pos = y > 0
    o["corr"] = np.corrcoef(p[pos], y[pos])[0, 1]
    o["mae"] = np.abs(p - y).mean()
    for lo, thr, k in ((20, 15, "catch20"), (30, 20, "catch30")):
        h = y >= lo; o[k] = (p[h] >= thr).mean() if h.any() else np.nan
    for lo, hi_, k in ((20, 999, "bias20"), (30, 999, "bias30"), (0, 5, "bias0_5")):
        h = (y >= lo) & (y < hi_); o[k] = (p[h] - y[h]).mean() if h.any() else np.nan
    return o


def bands(df):
    sk = df.pos.isin(["QB", "RB", "WR", "TE"]).to_numpy() & df.in_pool.to_numpy().astype(bool)
    cw = df.pos.isin(["WR", "TE"]).to_numpy() & (df.salary < 5500).to_numpy()
    return {"cheapWRTE": sk & cw,
            "mid": sk & ~cw & (df.salary < 7000).to_numpy(),
            "7k+": sk & (df.salary >= 7000).to_numpy(), "all_skill": sk}


def run(df, base, unit, label):
    cache = {g: ov.apply_chalk_temp(df, base.copy(), gamma=g)[0] for g in GAM}
    u = df[unit].to_numpy(); B = bands(df); sk = B["all_skill"]
    y = df.own.fillna(0).to_numpy()
    held = np.full(len(df), np.nan); chosen = {}
    for s in np.unique(u):  # choose gamma by training-unit skill MAE (neutral objective, not the target tier)
        tr = (u != s) & sk
        g = min(GAM, key=lambda g: np.abs(np.nan_to_num(cache[g][tr]) - y[tr]).mean())
        chosen[s] = g; held[u == s] = cache[g][u == s]
    print(f"\n==== {label}: leave-one-{unit}-out gamma chosen by train skill MAE: {chosen}")
    rows = {}
    for s in list(np.unique(u)) + ["pooled"]:
        um = (u == s) if s != "pooled" else np.ones(len(df), bool)
        for bn, bm in B.items():
            for g in GAM:
                rows[(s, bn, f"g{g}")] = metr(df, cache[g], bm & um)
            rows[(s, bn, "LO-chosen")] = metr(df, held, bm & um)
    T = pd.DataFrame(rows).T.astype(float).round(3)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 3000)
    print(T.to_string())
    return cache, held, T


if __name__ == "__main__":
    H = pd.read_parquet(D / "ownership_v2/hist.parquet").reset_index(drop=True)
    H["v2"] = pd.read_parquet(D / "stud_own/v2_loso_fresh.parquet").v2.values
    hb, _ = ov.apply_vac_bump(H, H.v2.to_numpy(float).copy())
    _, _, HT = run(H, hb, "season", "HISTORY 2021-25 (v2 LOSO + vac bump)")
    HT.to_csv(OUT / "hist_table.csv")
    Y = pd.read_parquet(D / "ownership_v2/y2026.parquet").reset_index(drop=True)
    P = pd.read_parquet(D / "ownership_v2/y2026_preds.parquet").reset_index(drop=True)
    yb, _ = ov.apply_vac_bump(Y, P["p_new_p_live-FFC_log_blend"].to_numpy(float).copy())
    _, _, YT = run(Y, yb, "week", "2026 wk1-3 (shipped blend + vac bump)")
    YT.to_csv(OUT / "y2026_table.csv")
