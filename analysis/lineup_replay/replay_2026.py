"""Part A: OLD vs NEW inputs through the full optimizer on 2026 DK classic wk1-3 (9 slates).

OLD = DFS_OWNERSHIP_V2=0 --no-qb-recal --no-early-blend; NEW = defaults. Pools from build_arms.sh (leak-free rebuilds).
wk1/2: pre-lock OUT/DOUBTFUL zeroed from the last committed pre-lock production file (same as ownership_refit_wk3).
Each (slate, arm, seed) -> SE3Max Pool (100) preset batch -> graded vs the real SE3max contest (cash = top 25%).
Same seeds for both arms, so pool differences come only from inputs.

usage: python analysis/lineup_replay/replay_2026.py [n_seeds]
"""
import io
import subprocess
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

REPO = C.REPO
CR = REPO / "data" / "contest_results"
SLATES = {
    "wk1_main_13Sep2026": "dk_classic_wk1_main_13Sep2026_full.csv",
    "wk1_early_13Sep2026": "dk_classic_wk1_early_13Sep2026_full.csv",
    "wk1_afternoon_13Sep2026": "dk_classic_wk1_afternoon_13Sep2026_full.csv",
    "wk2_main_20Sep2026": "dk_classic_wk2_main_20Sep2026_se3max_full.csv",
    "wk2_early_20Sep2026": "dk_classic_wk2_early_20Sep2026_se3max_full.csv",
    "wk2_afternoon_20Sep2026": "dk_classic_wk2_afternoon_20Sep2026_se3max_full.csv",
    "wk3_main_27Sep2026": "dk_classic_wk3_main_27Sep2026_se3max_full.csv",
    "wk3_early_27Sep2026": "dk_classic_wk3_early_27Sep2026_se3max_full.csv",
    "wk3_afternoon_27Sep2026": "dk_classic_wk3_afternoon_27Sep2026_se3max_full.csv",
}
PRELOCK = {"wk1_main_13Sep2026": "cefc761", "wk1_early_13Sep2026": "439ac11", "wk1_afternoon_13Sep2026": "33a3b1c",
           "wk2_main_20Sep2026": "7e57cfe", "wk2_early_20Sep2026": "c1b3099", "wk2_afternoon_20Sep2026": "614702c"}
CASH_PCT = 0.25


def prelock_out(slate):
    """OUT/DOUBTFUL ids from all three same-week pre-lock committed files (union)."""
    wk = slate[:3]
    ids = set()
    for s, c in PRELOCK.items():
        if not s.startswith(wk):
            continue
        raw = subprocess.check_output(["git", "show", f"{c}:output/final_projections_dk_dk_classic_{s}.csv"], cwd=REPO)
        d = pd.read_csv(io.StringIO(raw.decode()), dtype={"player_id": str})
        if "injury_status" in d:
            ids |= set(d.loc[d["injury_status"].isin(["OUT", "DOUBTFUL"]), "player_id"])
    return ids


def load_pool(arm, slate):
    p = pd.read_csv(HERE / "pools" / f"{arm}_{slate}.csv", dtype={"player_id": str, "site_player_id": str})
    if arm == "new" and slate.startswith("wk1"):
        # wk1 build uses the week-23 sentinel, where the blend no-ops; apply the week-1 weights here
        import build_projections_statline as B
        if "no_real_game_this_week" not in p:
            p["no_real_game_this_week"] = False
        p = B._apply_early_season_blend(p, 1)
    if slate in PRELOCK:
        out = prelock_out(slate)
        p.loc[p.player_id.isin(out), "final_projection"] = 0.0
    p.loc[p.get("injury_status", pd.Series("", index=p.index)).isin(["OUT", "DOUBTFUL"]) & slate.startswith("wk3"),
          "final_projection"] = 0.0
    return p


def load_real(slate):
    df = pd.read_csv(CR / SLATES[slate], encoding="utf-8-sig", low_memory=False)
    tab = df[["Player", "%Drafted", "FPTS"]].dropna(subset=["Player"]).copy()
    tab["k"] = tab.Player.map(C.norm)
    tab["own"] = tab["%Drafted"].astype(str).str.rstrip("%").astype(float)
    own = tab.groupby("k").own.sum().to_dict()
    fpts = tab.drop_duplicates("k").set_index("k").FPTS.to_dict()
    pts = df.Points.dropna().to_numpy(float)
    return fpts, own, np.sort(pts)


def grade(keys, fpts, pts_sorted):
    s = sum(fpts.get(k, 0.0) for k in keys)
    N = len(pts_sorted)
    beat = N - np.searchsorted(pts_sorted, s, side="right")  # entries strictly above
    pct = 1 - beat / N
    return s, pct


def job(args):
    slate, arm, seed = args
    pool = load_pool(arm, slate)
    L, n = C.build_pool(pool, seed, f"{arm}_{slate}_{seed}")
    T = C.lineup_table(L, pool)
    fpts, _, pts = load_real(slate)
    name = pool.drop_duplicates("player_id").set_index("player_id").player_name.map(C.norm)
    res = []
    for r in T.itertuples():
        s, pct = grade([name[p] for p in r.pids], fpts, pts)
        res.append((s, pct))
    T["actual"] = [x[0] for x in res]
    T["pct"] = [x[1] for x in res]
    T["cash"] = T.pct >= 1 - CASH_PCT
    T["slate"], T["arm"], T["seed"] = slate, arm, seed
    return T


def main():
    nseed = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    jobs = [(s, a, 7 + 101 * i) for s in SLATES for a in ("old", "new") for i in range(nseed)]
    with Pool(6) as pp:
        frames = pp.map(job, jobs, chunksize=1)
    A = pd.concat(frames, ignore_index=True)
    A.drop(columns=["pids"]).to_csv(HERE / "replay_2026_lineups.csv", index=False)
    rows = []
    for (slate, arm, seed), T in A.groupby(["slate", "arm", "seed"]):
        r = dict(slate=slate, arm=arm, seed=seed, n=len(T), pool_cash=T.cash.mean(), pool_mean_pct=T.pct.mean(),
                 best_pct=T.pct.max(), mean_proj=T.proj.mean(), mean_actual=T.actual.mean())
        for rule in C.RULES:
            x = C.pick(T, rule)
            r[f"{rule}_pct"], r[f"{rule}_cash"] = x.pct, bool(x.cash)
        rows.append(r)
    S = pd.DataFrame(rows)
    S.to_csv(HERE / "replay_2026_summary.csv", index=False)
    pd.set_option("display.width", 250)
    print(S.groupby(["slate", "arm"]).mean(numeric_only=True).round(3).to_string())
    print("\n== by arm (all slates x seeds) ==")
    print(S.groupby("arm").mean(numeric_only=True).round(3).T.to_string())
    print("\n== by arm x week ==")
    S["wk"] = S.slate.str[:3]
    print(S.groupby(["wk", "arm"]).mean(numeric_only=True).round(3).T.to_string())


if __name__ == "__main__":
    main()
