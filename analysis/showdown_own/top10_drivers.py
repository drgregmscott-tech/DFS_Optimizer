"""What predicts a top-10% finish in real Showdown fields? (wk1 DEN@KC + wk2 IND@KC, 13.5k lineups)
Lift = P(top10% | feature) / 10%. Also a pooled logistic regression on a few structure features."""
import re
import numpy as np, pandas as pd
tok = re.compile(r"\b(CPT|FLEX)\s+")
D = "C:/Users/gmsco/Downloads/"
S = {"wk1": (D + "dk_showdown_wk1_Den_KC_14Sep2026_results.csv", "dk_showdown_wk1_Den_KC_14Sep2026"),
     "wk2": (D + "results_se3max_dk_showdown_wk2_Ind_KC_20Sep2026.csv", "dk_showdown_wk2_Ind_KC_20Sep2026")}


def parse(s):
    p = tok.split(" " + s.strip())
    return [(p[i], p[i + 1].strip()) for i in range(1, len(p) - 1, 2)]


frames = []
for lab, (f, sid) in S.items():
    P = pd.read_csv(f"output/final_projections_dk_{sid}.csv")
    fl = P[P.roster_role == "FLEX"].copy(); fl["k"] = fl.player_name.str.strip()
    info = fl.set_index("k")[["team", "position", "salary", "final_projection"]].to_dict("index")
    df = pd.read_csv(f, encoding="utf-8-sig")
    tab = df[["Player", "Roster Position", "%Drafted"]].dropna(subset=["Player"]).copy()
    tab["k"] = tab.Player.str.strip(); tab["own"] = tab["%Drafted"].str.rstrip("%").astype(float)
    own = {(r.k, r["Roster Position"]): r.own for _, r in tab.iterrows()}
    e = df.iloc[:, :6].dropna(subset=["Lineup"]).copy(); N = len(e)
    rows = []
    for r in e.itertuples():
        L = parse(r.Lineup)
        cpt = [n for ro, n in L if ro == "CPT"][0]
        pl = [(ro, n) for ro, n in L]
        tms = [info[n]["team"] for _, n in pl]
        pos = [info[n]["position"] for _, n in pl]
        c = pd.Series(tms).value_counts()
        fav = "KC"
        n_fav = sum(t == fav for t in tms)
        sal = 1.5 * info[cpt]["salary"] + sum(info[n]["salary"] for ro, n in pl if ro == "FLEX")
        rows.append(dict(slate=lab, top10=r.Rank <= N * .10, top1=r.Rank <= N * .01, pct=1 - (r.Rank - 1) / N,
                         cpt_pos=info[cpt]["position"], cpt_own=own.get((cpt, "CPT"), 0.0), n_fav=n_fav,
                         split=f"{c.max()}-{6-c.max()}", nK=pos.count("K"), nD=pos.count("DST"),
                         nQB=pos.count("QB"), sal=sal,
                         own_sum=sum(own.get((n, ro), 0.0) for ro, n in pl),
                         proj=1.5 * info[cpt]["final_projection"] + sum(info[n]["final_projection"] for ro, n in pl if ro == "FLEX")))
    frames.append(pd.DataFrame(rows))
A = pd.concat(frames, ignore_index=True)
A["split_fav"] = A.n_fav.astype(str) + "KC"          # players from the favorite (KC) -- 6-n_fav from the dog
A["cpt_tier"] = pd.cut(A.cpt_own, [-1, 3, 6, 12, 100], labels=["<3%", "3-6%", "6-12%", ">12%"])
A["own_q"] = A.groupby("slate").own_sum.transform(lambda x: pd.qcut(x, 4, labels=["Q1 low", "Q2", "Q3", "Q4 chalk"]))
A["proj_q"] = A.groupby("slate").proj.transform(lambda x: pd.qcut(x, 4, labels=["Q1 low", "Q2", "Q3", "Q4 high"]))
A["sal_bin"] = pd.cut(A.sal, [0, 47500, 49000, 49800, 50001], labels=["<47.5k", "47.5-49k", "49-49.8k", ">49.8k"])
for col in ["cpt_pos", "cpt_tier", "split", "n_fav", "nK", "nD", "nQB", "own_q", "proj_q", "sal_bin"]:
    g = A.groupby(["slate", col], observed=True).agg(n=("top10", "size"), top10=("top10", "mean")).reset_index()
    g["lift"] = (g.top10 / 0.10).round(2)
    w = g.pivot(index=col, columns="slate", values=["n", "lift"])
    print(f"\n--- {col} ---"); print(w.to_string())

# pooled logistic (statsmodels-free): IRLS with a few structure dummies, standardized within slate
X = pd.DataFrame({
    "cpt_QB": (A.cpt_pos == "QB") * 1.0, "cpt_K": (A.cpt_pos == "K") * 1.0, "cpt_DST": (A.cpt_pos == "DST") * 1.0,
    "hasK": (A.nK >= 1) * 1.0, "hasDST": (A.nD >= 1) * 1.0, "split33": (A.split == "3-3") * 1.0, "split51": (A.split == "5-1") * 1.0,
    "proj_z": A.groupby("slate").proj.transform(lambda x: (x - x.mean()) / x.std()),
    "own_z": A.groupby("slate").own_sum.transform(lambda x: (x - x.mean()) / x.std()),
    "sal_z": A.groupby("slate").sal.transform(lambda x: (x - x.mean()) / x.std()),
})
Xm = np.c_[np.ones(len(X)), X.values]; y = A.top10.values.astype(float); b = np.zeros(Xm.shape[1])
for _ in range(25):
    p = 1 / (1 + np.exp(-Xm @ b)); W = p * (1 - p)
    H = Xm.T @ (Xm * W[:, None]) + 1e-6 * np.eye(len(b)); b = b + np.linalg.solve(H, Xm.T @ (y - p))
se = np.sqrt(np.diag(np.linalg.inv(H)))
print("\n--- pooled logistic for top-10% (log-odds; |z|>2 ~ real) ---")
print(pd.DataFrame({"coef": b, "z": b / se}, index=["const"] + list(X.columns)).round(2).to_string())
