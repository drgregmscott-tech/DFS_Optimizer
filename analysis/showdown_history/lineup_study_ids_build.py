"""Re-parse the FC Lineup Study SHOWDOWN files keeping per-entry PLAYER IDS (the original cache kept only derived features).

Needed by lineup_study_construction_detail.py (partner position, price tiers, split-by-team) and
lineup_study_modeled_own.py (re-score lineups with our modeled ownership).

Input : data/fc_history/lineup_study/*_SHOWDOWN_{SE,big}_*.json.gz            (FC subscription data, gitignored)
Output: data/fc_history/lineup_study/_sd_entries_ids.parquet   per entry: contest, rank, points, payout_c, p0(CPT)..p5
        data/fc_history/lineup_study/_sd_players.parquet       per contest x player: meta, salary, FC proj, FC proj_own,
                                                                solved actual score, realized CPT/FLEX rostership
Both are raw-derived and live in the gitignored raw folder (never commit). Parsing reuses lineup_study_build.py
helpers exactly (same row filter, payout rebuild, score solve, cap-bound salary recovery).
Data root: env DFS_ROOT, else the main checkout (data is gitignored and only exists there).
"""
import glob, os, re, sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd

ROOT = os.environ.get("DFS_ROOT", r"C:\Users\gmsco\Desktop\DFS_Optimizer")
sys.path.insert(0, os.path.join(ROOT, "analysis", "showdown_history"))
import lineup_study_build as LB  # noqa: E402

OUT_E = os.path.join(LB.SRC, "_sd_entries_ids.parquet")
OUT_P = os.path.join(LB.SRC, "_sd_players.parquet")
_G = {}


def _init(gm):
    _G["m"] = gm


def parse(f):
    gmeta = _G["m"]
    d = LB.load(f)
    c, P, R = d["contest"], d["players"], d["rows"]
    m = re.match(r"(\d{4})wk(\d+)b?_SHOWDOWN_(SE|big)_(\d+)", os.path.basename(f))
    season, week, ctype, cid = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    R = [r for r in R if len(r[5]) == 6]
    lineups = [[str(i) for i in r[5]] for r in R]
    pts = np.array([float(r[3]) for r in R])
    ranks = [int(r[0]) for r in R]
    ids = sorted({p for lu in lineups for p in lu})
    sal, meta = {}, {}
    for p in ids:
        q = P.get(p, {}); g = gmeta.get(p, {})
        meta[p] = {"pos": q.get("SitePos") or g.get("pos"), "team": q.get("Team") or g.get("team"),
                   "name": q.get("PlayerName") or g.get("name"), "proj": q.get("FC_proj"), "fc_proj_own": q.get("proj_own")}
        sal[p] = q.get("Salary")
    sal_known = {p: sal[p] is not None for p in ids}
    if any(v is None for v in sal.values()):
        for p, v in LB.cap_bound_salary(lineups, sal).items():
            sal[p] = v
    scores, _, _ = LB.solve_scores(lineups, pts, ids)
    n = len(R)
    cc = Counter(lu[0] for lu in lineups)
    fc = Counter(p for lu in lineups for p in lu[1:])
    cash_c = np.array([float(r[4]) for r in R])
    pay = cash_c if cash_c.sum() > 0 else LB.rebuild_payouts(ranks, d["payouts"], int(c.get("places_paid")))
    fav = next((q["game_fav"] for q in P.values() if q.get("game_fav")), None)
    total = next((q["game_total"] for q in P.values() if q.get("game_total")), None)
    spread = next((q["game_spread"] for q in P.values() if q.get("game_spread") is not None), None)
    arr = np.array([[int(x) for x in lu] for lu in lineups], dtype=np.int64)
    E = pd.DataFrame({"contest": cid, "rank": np.array(ranks, dtype=np.int32), "points": pts.astype(np.float32),
                      "payout_c": pay.astype(np.float64)})
    for j in range(6):
        E[f"p{j}"] = arr[:, j]
    Pl = pd.DataFrame([{"contest": cid, "season": season, "week": week, "ctype": ctype, "pid": int(p),
                        "name": meta[p]["name"], "team": meta[p]["team"], "pos": meta[p]["pos"], "sal": sal[p],
                        "sal_known": sal_known[p], "fc_proj": meta[p]["proj"], "fc_proj_own": meta[p]["fc_proj_own"],
                        "act": scores[p], "cpt_own": 100.0 * cc[p] / n, "flex_own": 100.0 * fc[p] / n,
                        "fav": fav, "game_total": total, "game_spread": spread, "n_entries": n,
                        "cost_c": float(c.get("cost") or 0), "contest_name": c.get("name")} for p in ids])
    return E, Pl


def main():
    files = sorted(glob.glob(os.path.join(LB.SRC, "*_SHOWDOWN_*.json.gz")))
    gm = LB.global_meta(files)
    Es, Ps = [], []
    with ProcessPoolExecutor(8, initializer=_init, initargs=(gm,)) as ex:
        for f, (E, Pl) in zip(files, ex.map(parse, files)):
            Es.append(E); Ps.append(Pl); print(os.path.basename(f), len(E), flush=True)
    E = pd.concat(Es, ignore_index=True); E["contest"] = E["contest"].astype("category")
    E.to_parquet(OUT_E); pd.concat(Ps, ignore_index=True).to_parquet(OUT_P)
    print("entries", len(E), "contests", E["contest"].nunique())


if __name__ == "__main__":
    main()
