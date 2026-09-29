"""Player-level "who consistently cashes" test on the classic lineup-study fields (framing note, checklist §3).

Not individual winning lineups: for every player in every contest we have realized field rostership, rostership among
cashing lineups, and his actual score. Grouped by role (position x salary tier x ownership tier), we ask:
  1. cash leverage  = own_cash / own_field  (>1: this kind of player is over-represented in cashing lineups)
  2. points vs FC projection by ownership tier within position x salary tier (does the crowd know something FC doesn't?)
  3. hit rate = share of players in the group whose leverage > 1.25 ("consistent cash driver" rate)
Points/projection use one contest per slate (the largest field) so a slate is not counted six times; leverage is per
contest type because the fields differ. 90% bootstrap CIs over slates. Output (aggregate only):
  analysis/classic_history/out/cl_player_roles.csv, cl_player_points_vs_own.csv
"""
import glob, os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DER = os.path.join(ROOT, "data", "fc_history", "derived", "classic")
OUT = os.path.join(ROOT, "analysis", "classic_history", "out")
RS = np.random.RandomState(11)
POS = {0: "QB", 1: "RB", 2: "WR", 3: "TE", 4: "DST"}
SAL = {"QB": [0, 5500, 6500, 7500, 1e9], "RB": [0, 5000, 6500, 8000, 1e9], "WR": [0, 4500, 6000, 7500, 1e9],
       "TE": [0, 3500, 4500, 6000, 1e9], "DST": [0, 2800, 3200, 3600, 1e9]}
TIER = ["low", "mid-low", "mid-high", "high"]


def boot_slate(df, col, B=1000):
    g = df.groupby("slate")[col].mean().values
    if len(g) < 3:
        return np.nan, np.nan
    s = g[RS.randint(0, len(g), (B, len(g)))].mean(1)
    return np.percentile(s, 5), np.percentile(s, 95)


def main():
    Qa = pd.read_csv(os.path.join(OUT, "cl_qa.csv"))
    drop = set(Qa.loc[(Qa["rows_vs_entrants"] < 0.99) | (Qa["rows_used"] < 1000), "file"].str[:-8])
    P = pd.concat([pd.read_parquet(f) for f in glob.glob(os.path.join(DER, "players", "*.parquet"))
                   if os.path.basename(f)[:-8] not in drop], ignore_index=True)
    P["pos_s"] = P["pos"].map(POS)
    P = P[P["pos_s"].notna() & P["sal"].notna()]
    P["sal_t"] = "?"
    for p, e in SAL.items():
        m = P["pos_s"] == p
        P.loc[m, "sal_t"] = pd.cut(P.loc[m, "sal"], e, labels=TIER, right=False).astype(str)
    P["own_t"] = pd.cut(P["own"], [0, 2, 5, 10, 20, 101], labels=["<2", "2-5", "5-10", "10-20", "20+"], right=False).astype(str)
    P["lev"] = P["own_cash"] / P["own"]
    P["resid"] = P["fp"] - P["proj"]
    P["proj_ok"] = P["proj"] > 0

    # 1+3: leverage by role, per contest type, players with >= 2% field ownership (the players the field actually uses)
    U = P[P["own"] >= 2].copy()
    U["driver"] = (U["lev"] > 1.25).astype(float)
    rows = []
    for keys in (["ctype", "pos_s", "own_t"], ["ctype", "pos_s", "sal_t"], ["ctype", "pos_s", "sal_t", "own_t"]):
        for k, g in U.groupby(keys):
            if g["slate"].nunique() < 20:
                continue
            r = dict(zip(keys, k)); r["grouping"] = "+".join(keys[1:])
            r["players"] = len(g); r["slates"] = g["slate"].nunique()
            r["lev"] = g.groupby("slate")["lev"].mean().mean(); r["lev_lo"], r["lev_hi"] = boot_slate(g, "lev")
            r["driver_rate"] = g["driver"].mean()
            by = g.groupby("season")["lev"].mean()
            r["seasons_lev_gt1"] = f"{int((by.reindex([2022, 2023, 2024, 2025]) > 1).sum())}/{int(by.reindex([2022, 2023, 2024, 2025]).notna().sum())}"
            rows.append(r)
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(OUT, "cl_player_roles.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    print(R[R.grouping == "pos_s+own_t"].round(3).to_string(index=False))
    print(R[R.grouping == "pos_s+sal_t"].round(3).to_string(index=False))

    # 2: points vs FC projection by ownership tier, one contest per slate (largest field), players with proj > 0
    big = P.groupby("slate")["n_entries"].transform("max") == P["n_entries"]
    Q = P[big & P["proj_ok"]].drop_duplicates(["slate", "pid"]).copy()
    # within slate x position x salary tier, ownership rank-normalized, so the tier comparison holds price fixed
    rows = []
    for keys in (["pos_s", "own_t"], ["pos_s", "sal_t", "own_t"]):
        for k, g in Q.groupby(keys):
            if g["slate"].nunique() < 20:
                continue
            r = dict(zip(keys, k)); r["grouping"] = "+".join(keys); r["players"] = len(g); r["slates"] = g["slate"].nunique()
            r["proj"] = g["proj"].mean(); r["fp"] = g["fp"].mean(); r["resid"] = g.groupby("slate")["resid"].mean().mean()
            r["resid_lo"], r["resid_hi"] = boot_slate(g, "resid")
            by = g.groupby("season")["resid"].mean()
            r["seasons_resid_pos"] = f"{int((by.reindex([2022, 2023, 2024, 2025]) > 0).sum())}/{int(by.reindex([2022, 2023, 2024, 2025]).notna().sum())}"
            r["pts_per_k"] = (g["fp"] / g["sal"] * 1000).mean()
            rows.append(r)
    Z = pd.DataFrame(rows)
    Z.to_csv(os.path.join(OUT, "cl_player_points_vs_own.csv"), index=False)
    print(Z[Z.grouping == "pos_s+own_t"].round(3).to_string(index=False))
    # per-slate regression: resid ~ z(log own) within position, controlling projection and salary
    rows = []
    for (sl, p), g in Q[Q["own"] > 0].groupby(["slate", "pos_s"]):
        if len(g) < 8:
            continue
        lo = np.log(g["own"].values)
        X = np.column_stack([np.ones(len(g)), (lo - lo.mean()) / (lo.std() or 1), g["proj"], g["sal"] / 1000])
        b = np.linalg.lstsq(X, g["fp"].values, rcond=None)[0]
        rows.append({"slate": sl, "season": int(g["season"].iat[0]), "pos": p, "own_coef": b[1], "n": len(g)})
    C = pd.DataFrame(rows)
    out = []
    for p, g in C.groupby("pos"):
        v = g["own_coef"].values; s = v[RS.randint(0, len(v), (2000, len(v)))].mean(1)
        by = g.groupby("season")["own_coef"].mean()
        out.append({"pos": p, "slates": len(g), "pts_per_sd_logown": v.mean(), "lo": np.percentile(s, 5), "hi": np.percentile(s, 95),
                    "seasons_pos": f"{int((by.reindex([2022, 2023, 2024, 2025]) > 0).sum())}/4"})
    O = pd.DataFrame(out); O.to_csv(os.path.join(OUT, "cl_player_own_coef.csv"), index=False)
    print(O.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
