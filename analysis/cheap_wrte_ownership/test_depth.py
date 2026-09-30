"""Step 4: is depth/role rank the missing cheap WR/TE signal? Compare (a) FC's depth tag (history-only
diagnostic; FC-derived) with (b) a depth rank we can rebuild pre-lock: rank of prior-3-game usage share among
teammates of the same group who are IN this week's pool (i.e. after removing OUT players = next man up).
Target = realized ownership, LOSO 2021-25. No FC data in this file."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ownership_v2"))
from common import ALL, R, Model, metrics  # noqa

def add(d):
    d = d.copy()
    for k in ["WR1", "WR2", "WR3", "TE1", "TE2"]:
        d["fcd_" + k] = (d.get("pdepth", pd.Series(index=d.index, dtype=object)) == k).astype(float)
    pool = d.in_pool & (d.proj > 0)
    sh = d.my_share.where(pool & d.pos.isin(["WR", "TE"]))
    d["rk_rec"] = sh.groupby([d.slate_id, d.team]).rank(ascending=False, method="first")   # WR+TE combined
    d["rk_pos"] = sh.groupby([d.slate_id, d.team, d.pos]).rank(ascending=False, method="first")
    ch = ((d.salary < 5500) & d.pos.isin(["WR", "TE"])).astype(float)
    for k in (1, 2, 3):
        d[f"rec{k}"] = (d.rk_rec == k).astype(float)
    d["pos1"] = (d.rk_pos == 1).astype(float)
    d["cw_rec1"] = ch * d.rec1; d["cw_rec2"] = ch * d.rec2; d["cw_pos1"] = ch * d.pos1
    # promoted: depth rank improved because a higher-share teammate is absent this week
    raw = d.my_share.where(d.pos.isin(["WR", "TE"]))
    d["promoted"] = (d.vacated > 0.15).astype(float) * d.rec1
    d["cw_promoted"] = ch * d.promoted
    return d

SETS = {
    "v2 baseline": [],
    "+rebuilt depth (rec1-3, pos1, cheap x)": ["rec1", "rec2", "rec3", "pos1", "cw_rec1", "cw_rec2", "cw_pos1", "promoted", "cw_promoted"],
    "+FC depth tag (diagnostic)": ["fcd_WR1", "fcd_WR2", "fcd_WR3", "fcd_TE1", "fcd_TE2"],
}
if __name__ == "__main__":
    H = add(pd.read_parquet(R / "data/fc_history/derived/ownership_v2/hist.parquet").reset_index(drop=True))
    Y = add(pd.read_parquet(R / "data/fc_history/derived/ownership_v2/y2026.parquet").reset_index(drop=True))
    rows = {}
    for name, extra in SETS.items():
        f = ALL + extra; p = np.zeros(len(H))
        for s in sorted(H.season.unique()):
            te = (H.season == s).to_numpy(); p[te] = Model(f).fit(H[~te], "own").predict(H[te])
        m = metrics(H, p, "own")
        for s in sorted(H.season.unique()):
            m[f"cw{s}"] = metrics(H[H.season == s], p[(H.season == s).to_numpy()], "own")["corr_cheapWRTE"]
        if not name.startswith("+FC"):
            py = Model(f).fit(H, "own").predict(Y); m26 = metrics(Y, py, "own")
            m.update({"26corr": m26["corr"], "26mae": m26["mae"], "26cw": m26["corr_cheapWRTE"]})
        rows[name] = m; print(name, flush=True)
    t = pd.DataFrame(rows).T
    print(t[["corr", "mae", "catch20", "corr_cheapWRTE", "cw2021", "cw2022", "cw2023", "cw2024", "cw2025", "26corr", "26mae", "26cw"]].astype(float).round(3).to_string())
    # how well does the rebuilt depth agree with FC's tag on cheap WR/TE?
    c = H[(H.salary < 5500) & H.pos.isin(["WR", "TE"]) & (H.own > 0)]
    print(pd.crosstab(c.pdepth.where(c.pdepth.isin(["WR1","WR2","WR3","WR4","TE1","TE2"]), "other"), c.rk_rec.fillna(0).clip(upper=5)))
    print(c.groupby(c.pdepth.where(c.pdepth.isin(["WR1","WR2","WR3","WR4","TE1","TE2"]), "other")).own.agg(["size","mean"]).round(2))
    print(c.groupby(c.rk_rec.fillna(0).clip(upper=5)).own.agg(["size","mean"]).round(2))
