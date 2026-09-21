"""Validate the simulated showdown field against the real lineup score distribution."""
import re, sys
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "scripts"))
import showdown_field as sf

D = "C:/Users/gmsco/Downloads/"
SL = {
    "wk1 DEN@KC": ("dk_showdown_wk1_Den_KC_14Sep2026", D + "dk_showdown_wk1_Den_KC_14Sep2026_results.csv"),
    "wk2 IND@KC": ("dk_showdown_wk2_Ind_KC_20Sep2026", D + "results_se3max_dk_showdown_wk2_Ind_KC_20Sep2026.csv"),
}
QS = [0.5, 0.75, 0.9, 0.95, 0.99, 0.999]
tok = re.compile(r"\b(CPT|FLEX)\s+")


def parse(s):
    p = tok.split(" " + s.strip())
    return [(p[i], p[i + 1].strip()) for i in range(1, len(p) - 1, 2)]


def load(label, split_mode):
    sid, f = SL[label]
    pool = pd.read_csv(R / f"output/final_projections_dk_{sid}.csv", dtype={"player_id": str})
    fl = pool[pool.roster_role == "FLEX"].reset_index(drop=True)
    df = pd.read_csv(f, encoding="utf-8-sig")
    tab = df[["Player", "Roster Position", "%Drafted", "FPTS"]].dropna(subset=["Player"]).copy()
    tab["Player"] = tab.Player.str.strip()
    tab["own"] = tab["%Drafted"].str.rstrip("%").astype(float)
    name = fl.player_name.str.strip()
    cown = name.map(tab[tab["Roster Position"] == "CPT"].set_index("Player").own).fillna(0.02).values
    fown = name.map(tab[tab["Roster Position"] == "FLEX"].set_index("Player").own).fillna(0.02).values
    pts = name.map(tab[tab["Roster Position"] == "FLEX"].set_index("Player").FPTS).fillna(0.0).values
    e = df.iloc[:, :6].dropna(subset=["Lineup"])
    idx = {n: i for i, n in enumerate(name)}
    rc, rf = [], []
    for s in e.Lineup:
        L = parse(s)
        rc.append(idx[[n for r, n in L if r == "CPT"][0]])
        rf.append([idx[n] for r, n in L if r == "FLEX"])
    return fl, cown, fown, pts, e.Points.values.astype(float), np.array(rc), np.array(rf)


def split_dist(cpt, flex, tid):
    k = (tid[flex] == tid[cpt][:, None]).sum(axis=1) + 1
    return np.bincount(np.clip(k, 1, 5), minlength=6)[1:6] / len(k)


if __name__ == "__main__":
    real_splits = {}
    for lab in SL:
        fl, cown, fown, pts, rpts, rc, rf = load(lab, None)
        tid = pd.factorize(fl.team)[0]
        real_splits[lab] = split_dist(rc, rf, tid)
    for lab in SL:
        fl, cown, fown, pts, rpts, rc, rf = load(lab, None)
        tid = pd.factorize(fl.team)[0]
        other = [v for k, v in real_splits.items() if k != lab][0]
        print(f"\n===== {lab}: real lineups {len(rpts)}")
        print("real quantiles :", np.round(np.quantile(rpts, QS), 1))
        print("real CPT-team split (1..5):", np.round(real_splits[lab], 3))
        for mode, ms in [("no min salary", 0), ("min 47.5k", 47500), ("min 48.5k", 48500)]:
            c, f = sf.simulate_field(fl.salary.values, fl.team.values, cown, fown, n=50000, seed=1, min_salary=ms)
            sp = sf.score_lineups(c, f, pts)
            mc, mf = sf.marginals(c, f, len(fl))
            print(f"[{mode}] sim quantiles:", np.round(np.quantile(sp, QS), 1),
                  "| split", np.round(split_dist(c, f, tid), 3),
                  "| CPT own MAE", round(np.abs(mc - cown).mean(), 2), "FLEX own MAE", round(np.abs(mf - fown).mean(), 2))
        # real salary use
        sal = fl.salary.values
        rs = 1.5 * sal[rc] + sal[rf].sum(axis=1)
        ss = 1.5 * sal[c] + sal[f].sum(axis=1)
        print("salary used real q10/50/90:", np.round(np.quantile(rs, [.1, .5, .9])), "sim:", np.round(np.quantile(ss, [.1, .5, .9])))
        kick = fl.position.isin(["K"]).values
        print("lineups w/ >=1 K  real", round(kick[rf].any(axis=1).mean() + 0, 2), "(FLEX) sim", round(kick[f].any(axis=1).mean(), 2))
