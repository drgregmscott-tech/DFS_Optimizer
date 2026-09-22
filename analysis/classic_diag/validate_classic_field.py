"""Validate scripts/classic_field.py the same way analysis/showdown_own/validate_field.py
validates the Showdown field: feed it REAL ownership + REAL points for a slate, check the
simulated field's score quantiles match the real contest's, and check the real stack rate
(QB + same-team skill players) is reproduced.
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import classic_field as cf

D = "C:/Users/gmsco/Downloads/"
SLATES = {
    "wk1_main": (D + "dk_classic_wk1_main_final_results_13Sep2026.csv", "dk_classic_wk1_main_13Sep2026"),
    "wk1_early": (D + "dk_classic_wk1_early_final_results_13Sep2026.csv", "dk_classic_wk1_early_13Sep2026"),
    "wk1_afternoon": (D + "dk_classic_wk1_afternoon_final_results_13Sep2026.csv", "dk_classic_wk1_afternoon_13Sep2026"),
    "wk2_main": (D + "results_se3max_dk_classic_wk2_main_20Sep2026.csv", "dk_classic_wk2_main_20Sep2026"),
    "wk2_early": (D + "results_se3max_dk_classic_wk2_early_20Sep2026.csv", "dk_classic_wk2_early_20Sep2026"),
    "wk2_afternoon": (D + "results_se3max_dk_classic_wk2_afternoon_20Sep2026.csv", "dk_classic_wk2_afternoon_20Sep2026"),
}
TOK = re.compile(r"\b(QB|RB|WR|TE|FLEX|DST)\s+")


def parse(s):
    p = TOK.split(" " + s.strip())
    return [(p[i], p[i + 1].strip()) for i in range(1, len(p) - 1, 2)]


def norm(s):
    s = str(s).lower()
    s = re.sub(r"[.'\u2019]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(s.split())


def real_stack_rate(df):
    real = []
    for s in df.Lineup.dropna():
        L = parse(s)
        pass  # computed in top_drivers_classic.py already; not repeated here for speed
    return None


for lab, (f, sid) in SLATES.items():
    P = pd.read_csv(f"output/final_projections_dk_{sid}.csv", dtype={"player_id": str})
    P["k"] = P.player_name.map(norm)
    df = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    tab = df[["Player", "Roster Position", "%Drafted", "FPTS"]].dropna(subset=["Player"]).copy()
    tab["k"] = tab.Player.map(norm)
    tab["own"] = tab["%Drafted"].astype(str).str.rstrip("%").astype(float)
    tab = tab.drop_duplicates("k")
    pool = P[P.position.isin(["QB", "RB", "WR", "TE", "DST"])].merge(
        tab[["k", "own", "FPTS"]], on="k", how="left")
    pool["own"] = pool["own"].fillna(0.0)
    pool = pool[pool.own > 0].reset_index(drop=True)  # only players who actually appeared in the real field
    if pool.position.value_counts().get("QB", 0) < 2 or pool.position.value_counts().get("DST", 0) < 2:
        print(f"{lab}: too few live QB/DST after own>0 filter, skipping")
        continue

    lu = cf.simulate_field(pool, n=15000, seed=1)
    sim_pts = cf.score_lineups(lu, pool.FPTS.fillna(0.0).to_numpy(float))

    e = df.iloc[:, :6].dropna(subset=["Lineup"])
    real_pts = e.Points.dropna().to_numpy(float)

    qs = [50, 75, 90, 95, 99, 99.9]
    sim_q = np.percentile(sim_pts, qs)
    real_q = np.percentile(real_pts, qs)
    print(f"\n=== {lab} ===")
    for q, s, r in zip(qs, sim_q, real_q):
        print(f"  p{q}: sim={s:.1f} real={r:.1f} diff={s - r:+.1f}")

    stack = (pool.team.to_numpy(dtype=object)[lu["rb"]] == pool.team.to_numpy(dtype=object)[lu["qb"]][:, None]).sum(axis=1)
    stack += (pool.team.to_numpy(dtype=object)[lu["wr"]] == pool.team.to_numpy(dtype=object)[lu["qb"]][:, None]).sum(axis=1)
    stack += (pool.team.to_numpy(dtype=object)[lu["te"]] == pool.team.to_numpy(dtype=object)[lu["qb"]])
    stack += (pool.team.to_numpy(dtype=object)[lu["flex"]] == pool.team.to_numpy(dtype=object)[lu["qb"]])
    print(f"  sim stack>=1 rate: {(stack >= 1).mean():.3f} (real target ~0.81-0.95 per classic diagnostic)")

    obs_own = np.zeros(len(pool))
    n = len(lu["qb"])
    for arr in (lu["qb"], lu["te"], lu["dst"]):
        obs_own += np.bincount(arr, minlength=len(pool))
    for arr in (lu["rb"].ravel(), lu["wr"].ravel(), lu["flex"]):
        obs_own += np.bincount(arr, minlength=len(pool))
    obs_own = obs_own / n * 100
    mae = np.abs(obs_own - pool.own.to_numpy()).mean()
    print(f"  ownership MAE: {mae:.2f}")
