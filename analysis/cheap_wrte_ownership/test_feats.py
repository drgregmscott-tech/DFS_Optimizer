"""Step 2: LOSO test of candidate cheap-WR/TE features added to v2 linear. Target = realized ownership.
Every candidate is computable pre-lock from columns v2 already builds. No FC data here."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ownership_v2"))
from common import ALL, R, Model, metrics, mtable  # noqa

def add(df):
    d = df.copy()
    ch = ((d.salary < 5500) & d.pos.isin(["WR", "TE"])).astype(float)
    d["cw"] = ch
    # role / vacated
    d["benef"] = d.vacated * d.my_share                     # top remaining target earner on a team with vacated usage
    d["cw_vac"] = ch * d.vacated
    d["cw_share"] = ch * d.my_share
    d["cw_benef"] = ch * d.benef
    d["share_x"] = d.my_share / (1 - d.vacated).clip(lower=.2)  # share re-normalised over teammates still present
    d["cw_sharex"] = ch * d.share_x
    # vegas
    d["cw_tt"] = ch * d.team_total
    d["cw_gt"] = ch * d.game_total
    # value / concentration inside the cheap band
    d["cw_val"] = ch * d.val
    d["cw_proj"] = ch * d.proj
    d["cw_val2"] = ch * d.val ** 2
    # price lag: recent production vs salary
    d["p3v"] = (d.p3_dk.fillna(0) / d.salk.clip(lower=1)).clip(-2, 10)
    d["cw_p3v"] = ch * d.p3v
    d["cw_lastv"] = ch * d.last_val
    d["cw_lag"] = ch * d.l_lag_own
    d["cw_tgt"] = ch * d.p3_tgt.fillna(0)
    return d

SETS = {
    "v2 (baseline)": [],
    "+role (vac, share, benef, share_x)": ["benef", "cw_vac", "cw_share", "cw_benef", "share_x", "cw_sharex"],
    "+vegas cheap (tt, gt)": ["cw_tt", "cw_gt"],
    "+value shape cheap (val, proj, val^2)": ["cw_val", "cw_proj", "cw_val2"],
    "+price lag (p3v, last_val, lag_own, tgt)": ["p3v", "cw_p3v", "cw_lastv", "cw_lag", "cw_tgt"],
}
SETS["+role +vegas"] = SETS["+role (vac, share, benef, share_x)"] + SETS["+vegas cheap (tt, gt)"]
SETS["all candidates"] = sorted({c for v in SETS.values() for c in v})

if __name__ == "__main__":
    H = add(pd.read_parquet(R / "data/fc_history/derived/ownership_v2/hist.parquet").reset_index(drop=True))
    Y = add(pd.read_parquet(R / "data/fc_history/derived/ownership_v2/y2026.parquet").reset_index(drop=True))
    seasons = sorted(H.season.unique())
    rows, preds = {}, {}
    for name, extra in SETS.items():
        f = ALL + extra
        p = np.zeros(len(H))
        for s in seasons:
            te = (H.season == s).to_numpy()
            p[te] = Model(f).fit(H[~te], "own").predict(H[te])
        preds[name] = p
        m = metrics(H, p, "own")
        per = [metrics(H[H.season == s], p[(H.season == s).to_numpy()], "own")["corr_cheapWRTE"] for s in seasons]
        m.update({f"cw{s}": v for s, v in zip(seasons, per)})
        M = Model(f).fit(H, "own"); py = M.predict(Y)
        m26 = metrics(Y, py, "own")
        m.update({"26corr": m26["corr"], "26mae": m26["mae"], "26cw": m26["corr_cheapWRTE"],
                  "26cw_wk3": metrics(Y[Y.week == 3], py[(Y.week == 3).to_numpy()], "own")["corr_cheapWRTE"]})
        rows[name] = m
        print(name, "done", flush=True)
    t = pd.DataFrame(rows).T
    cols = ["corr", "mae", "catch20", "corr_cheapWRTE"] + [f"cw{s}" for s in seasons] + ["26corr", "26mae", "26cw", "26cw_wk3"]
    print(t[cols].astype(float).round(3).to_string())
    m3 = (H.season <= 2023).to_numpy()
    print("FC Own 2021-23 cheap corr:", round(metrics(H[m3], H.fc_own.fillna(0)[m3], "own")["corr_cheapWRTE"], 3))
    pd.DataFrame(preds).assign(slate_id=H.slate_id, player_id=H.player_id).to_parquet(R / "data/fc_history/derived/cheap_wrte/feat_preds.parquet")
