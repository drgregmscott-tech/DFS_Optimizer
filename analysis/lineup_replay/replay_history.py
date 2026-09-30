"""Part B: lineup-level replay on FC history (2022-25 DK classic main slates, real SE / 3-max fields).

For every main slate with >=1 SE or 3MAX contest in data/fc_history/lineup_study:
  pool   = our production-faithful projection replay (data/fc_history/derived/proj_qb/ourproj_qb1, QB1 guard),
           restricted to the contest's slate teams; players zeroed if the pre-lock injury report says Out/Doubtful
           or the nflverse roster says INA/RES (= the owner's Sunday-morning inactives check).
  arms   = 'ours'   SE3Max Pool (100) preset on our projections
           'fc'     same pool, same status, FC's projection as the objective (lineup-level head-to-head vs FC)
           'ours_cl' our projections + the committed --cl-* soft construction terms (fixed weights, not tuned)
  grade  = each lineup's actual DK points (FC fantasy_points) vs every SE/3MAX contest on the slate: exact rank in the
           real field, cash (paid rank), payout from the contest's prize ranges, return = payout / entry fee.
Selection rules (pre-game info only) are applied inside each pool.

usage: python analysis/lineup_replay/replay_history.py [nproc]
FC data stays local; outputs are aggregate CSVs in analysis/lineup_replay/ (do not commit).
"""
import glob
import gzip
import json
import os
import re
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

REPO = C.REPO
LS = REPO / "data" / "fc_history" / "lineup_study"
PROJ = REPO / "data" / "fc_history" / "derived" / "proj_qb" / "ourproj_qb1"
PANEL = REPO / "analysis" / "inactives" / "status_panel_2016_2025.csv"
FIX = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "LVR": "LV"}
TYPES = ("SE", "3MAX")
CL = dict(dst_band_bonus=1.0, dst_expensive_penalty=1.0, zero_punt_penalty=1.0,
          three_plus_punt_penalty=1.0, flex_rb_bonus=0.5, flex_wr_penalty=0.5)


def nk(s):
    return re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", str(s).lower()))


def contests_by_slate():
    out = {}
    for f in sorted(glob.glob(str(LS / "*.json.gz"))):
        b = os.path.basename(f)
        if "_LIST" in b or "SHOWDOWN" in b.upper():
            continue
        m = re.match(r"(\d{4})wk(\d+)_([A-Za-z0-9]+)", b)
        if not m:
            continue
        s, w, typ = int(m.group(1)), int(m.group(2)), m.group(3)
        if typ not in TYPES:
            continue
        if re.match(r"\d{4}wk\d+b_", b):  # secondary slates
            continue
        out.setdefault((s, w), []).append(f)
    return out


def load_contest(f):
    d = json.load(gzip.open(f))
    c = d["contest"]
    rows = [r for r in d["rows"] if len(r[5]) == 9]
    pts = np.sort(np.array([float(r[3]) for r in rows]))
    n = int(c.get("total_entrants") or len(rows))
    if len(rows) < 1000 or len(rows) < 0.9 * n:  # truncated / tiny
        return None
    rng = sorted((int(k), float(v)) for k, v in d["payouts"]["ranges"].items())
    last = int(d["payouts"].get("last_paid_rank") or c.get("places_paid"))
    return dict(file=os.path.basename(f), type=d["type"], pts=pts, ranges=rng, last=last,
                cost=float(c["cost"]), players=d["players"], teams=set(tfix(t) for t in d["slate"]["Teams"].split(",")))


def tfix(t):
    return FIX.get(t, t)


def payout(rank, K):
    if rank > K["last"]:
        return 0.0
    p = 0.0
    for r0, v in K["ranges"]:
        if rank >= r0:
            p = v
        else:
            break
    return p


def build_slate_pool(s, w, K, panel):
    p = pd.read_csv(PROJ / f"proj_{s}_wk{w}.csv", dtype={"player_id": str, "site_player_id": str})
    p = p.drop_duplicates("player_id")
    p["team"] = p.team.map(tfix)
    p["opponent"] = p.opponent.map(tfix)
    p = p[p.team.isin(K["teams"])].copy()
    st = panel[(panel.season == s) & (panel.week == w)]
    bad = set(st.loc[st.report_status.isin(["Out", "Doubtful"]) | st.status.isin(["INA", "RES"]), "gsis_id"])
    p["status_zero"] = p.player_id.isin(bad)
    p.loc[p.status_zero, "final_projection"] = 0.0
    # map FC players (actual points, FC projection) by name+team, DST by team
    P = K["players"]
    fc = pd.DataFrame([dict(k=nk(q.get("PlayerName")), team=tfix(q.get("Team")), pos=q.get("SitePos"),
                            fp=float(q.get("fantasy_points") or 0), fcp=float(q.get("FC_proj") or 0),
                            sal=float(q.get("Salary") or 0)) for q in P.values()])
    fcd = fc[fc.pos == "DST"].drop_duplicates("team").set_index("team")
    fcs = fc[fc.pos != "DST"].drop_duplicates(["k", "team"]).set_index(["k", "team"])
    fcu = fc[fc.pos != "DST"].drop_duplicates("k", keep=False).set_index("k")
    fp, fcp = [], []
    for r in p.itertuples():
        row = None
        if r.position == "DST":
            row = fcd.loc[r.team] if r.team in fcd.index else None
        else:
            k = nk(r.player_name)
            if (k, r.team) in fcs.index:
                row = fcs.loc[(k, r.team)]
            elif k in fcu.index:
                row = fcu.loc[k]
        fp.append(np.nan if row is None else row.fp)
        fcp.append(np.nan if row is None else row.fcp)
    p["actual"] = fp
    p["fc_proj"] = fcp
    return p


def grade_lineups(T, pool, Ks):
    act = pool.set_index("player_id").actual.fillna(0.0)
    T["actual"] = [float(sum(act.get(x, 0.0) for x in pids)) for pids in T.pids]
    for i, K in enumerate(Ks):
        N = len(K["pts"])
        rank = N - np.searchsorted(K["pts"], T.actual.values, side="right") + 1
        T[f"pct{i}"] = 1 - (rank - 1) / N
        T[f"cash{i}"] = rank <= K["last"]
        T[f"ret{i}"] = [payout(int(r), K) / K["cost"] for r in rank]
    k = len(Ks)
    T["pct"] = T[[f"pct{i}" for i in range(k)]].mean(1)
    T["cash"] = T[[f"cash{i}" for i in range(k)]].mean(1)
    T["ret"] = T[[f"ret{i}" for i in range(k)]].mean(1)
    # capped return: cap each contest payout at 20x fee (limits single-lineup jackpot noise)
    T["ret_cap"] = T[[f"ret{i}" for i in range(k)]].clip(upper=20).mean(1)
    return T


def job(args):
    (s, w), files = args
    try:
        panel = pd.read_csv(PANEL, usecols=["season", "week", "gsis_id", "status", "report_status"])
        Ks = [K for K in (load_contest(f) for f in files) if K is not None]
        if not Ks:
            return None
        pool = build_slate_pool(s, w, Ks[0], panel)
        cov = pool.fc_proj.notna().mean()
        out = []
        for arm in ("ours", "fc", "ours_cl"):
            q = pool.copy()
            kw = {}
            if arm == "fc":
                q["final_projection"] = q.fc_proj.fillna(0.0)
                q.loc[q.status_zero, "final_projection"] = 0.0
            if arm == "ours_cl":
                kw["classic_shape"] = CL
            L, n = C.build_pool(q, 7, f"h{s}_{w}_{arm}", **kw)
            T = C.lineup_table(L, q)
            # our projection of each lineup (for the fc arm too, so rules can be compared on one scale)
            ourp = pool.set_index("player_id").final_projection
            fcp = pool.set_index("player_id").fc_proj.fillna(0.0)
            T["our_proj"] = [float(sum(ourp.get(x, 0) for x in pids)) for pids in T.pids]
            T["fc_proj"] = [float(sum(fcp.get(x, 0) for x in pids)) for pids in T.pids]
            T = grade_lineups(T, pool, Ks)
            T["season"], T["week"], T["arm"], T["n_contests"], T["fc_cov"] = s, w, arm, len(Ks), cov
            T["contest_types"] = ",".join(sorted({K["type"] for K in Ks}))
            out.append(T.drop(columns=["pids"]))
        # field benchmark: mean return per contest is (1-rake); record the real field's cash line per contest
        return pd.concat(out, ignore_index=True)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL {s} wk{w}: {type(e).__name__}: {e}", flush=True)
        return None


def main():
    nproc = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    cs = contests_by_slate()
    jobs = [(k, v) for k, v in sorted(cs.items()) if (PROJ / f"proj_{k[0]}_wk{k[1]}.csv").exists()]
    print(f"{len(jobs)} slates", flush=True)
    with Pool(nproc) as pp:
        frames = [f for f in pp.imap_unordered(job, jobs) if f is not None]
    A = pd.concat(frames, ignore_index=True)
    A.to_csv(HERE / "history_lineups.csv", index=False)
    print("rows", len(A), "slates", A.groupby(["season", "week"]).ngroups)


if __name__ == "__main__":
    main()
