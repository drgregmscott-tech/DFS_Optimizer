"""Projection accuracy recheck: OLD (committed pre-fix output/) vs FIXED no-stack (engine) vs FIXED (+stack).

FIXED sources (scratchpad, leak-free): wk1 = fin/ (== new/), wk2 = rb_nolk/ (decision #4b zeroing disabled).
FIX_NS = the same files' engine_projection column (== final - stack_delta; props snapshots absent for all
6 slates so props step is inert; verified wk1 == nostack/ build exactly; nostack/ wk2 is the LEAKY build, not used).
Pool forced to OLD lock-time pool (dead/OUT in OLD -> excluded), same as pivot_rerun prep().
Actuals: data/projection_error_log.csv (DK contest export points). "Meaningful" = max(OLD,FIX)>8.
Dedup per player-week: prefer main > early > afternoon row.
usage: python analysis/proj_recheck/accuracy.py
"""
import subprocess, io, sys
from pathlib import Path
import numpy as np, pandas as pd
def spearmanr(a, b):
    class R: pass
    r = R(); r.statistic = pd.Series(np.asarray(a)).rank().corr(pd.Series(np.asarray(b)).rank()); return r

REPO = Path(__file__).resolve().parents[2]
S = Path(r"C:\Users\gmsco\AppData\Local\Temp\claude\C--Users-gmsco-Desktop-DFS-Optimizer\36a97c4a-433e-4ff9-b857-c9a23bb65822\scratchpad")
OUT = Path(__file__).resolve().parent
SL = [f"dk_classic_wk{w}_{s}_{d}" for w, d in ((1, "13Sep2026"), (2, "20Sep2026")) for s in ("main", "early", "afternoon")]
PRI = {"main": 0, "early": 1, "afternoon": 2}
V = ["OLD", "FIX_NS", "FIX"]


def git(p):
    return subprocess.run(["git", "show", f"HEAD:{p}"], cwd=REPO, capture_output=True, text=True, check=True, encoding="utf-8").stdout


def frame():
    L = pd.read_csv(REPO / "data/projection_error_log.csv", dtype={"player_id": str})
    rows = []
    for sid in SL:
        name = f"final_projections_dk_{sid}.csv"
        o = pd.read_csv(io.StringIO(git(f"output/{name}")), dtype={"player_id": str})
        f = pd.read_csv(S / ("fin" if "wk1" in sid else "rb_nolk") / name, dtype={"player_id": str})
        dead = set(o.loc[o.final_projection <= 0, "player_id"]) | set(o.loc[o.get("injury_status", pd.Series(dtype=str)) == "OUT", "player_id"])
        m = o[~o.player_id.isin(dead)][["player_id", "player_name", "position", "team", "salary", "final_projection"]].rename(columns={"final_projection": "OLD"})
        m = m.merge(f[["player_id", "engine_projection", "final_projection", "stack_delta", "proj_pass_att"]]
                    .rename(columns={"engine_projection": "FIX_NS", "final_projection": "FIX"}), on="player_id", how="inner")
        a = L[L.slate_id == sid].drop_duplicates("player_id").set_index("player_id").actual_fpts
        m["act"] = m.player_id.map(a)
        m = m.dropna(subset=["act"])
        m["slate_id"], m["week"], m["sub"] = sid, int(sid.split("_wk")[1][0]), sid.split("_")[3]
        rows.append(m)
    return pd.concat(rows, ignore_index=True)


def tier(s):
    return pd.cut(s, [0, 4500, 6000, 7500, 20000], labels=["<4.5k", "4.5-6k", "6-7.5k", "7.5k+"])


def acc(d):
    r = {"n": len(d)}
    for v in V:
        e = d[v] - d.act
        r[f"{v}_bias"], r[f"{v}_mae"], r[f"{v}_rmse"] = e.mean(), e.abs().mean(), np.sqrt((e ** 2).mean())
    return r


def rankq(D):
    """within slate x position (non-deduped: ranking is a per-slate decision)."""
    out = []
    N = {"QB": 3, "RB": 5, "WR": 8, "TE": 3}
    for (sid, pos), g in D.groupby(["slate_id", "position"]):
        if pos not in N or len(g) < 6:
            continue
        r = {"slate_id": sid, "position": pos, "n": len(g)}
        n = N[pos]
        top_act = set(g.nlargest(n, "act").player_id)
        for v in V:
            r[f"{v}_sp"] = spearmanr(g[v], g.act).statistic
            r[f"{v}_valsp"] = spearmanr(g[v] / g.salary, g.act / g.salary).statistic   # relative value
            r[f"{v}_top"] = len(set(g.nlargest(n, v).player_id) & top_act) / n
            r[f"{v}_topact"] = g.nlargest(n, v).act.mean()   # mean actual of projected top-N
        out.append(r)
    return pd.DataFrame(out)


if __name__ == "__main__":
    D = frame()
    D = D[D[["OLD", "FIX"]].max(axis=1) > 8].copy()
    D.to_csv(OUT / "accuracy_frame.csv", index=False)
    Dd = D.assign(p=D["sub"].map(PRI)).sort_values("p").drop_duplicates(["player_id", "week"])
    pd.set_option("display.width", 250)
    res = []
    for key, grp in [("ALL", Dd.groupby(lambda _: "all")), ("pos", Dd.groupby("position")),
                     ("tier", Dd.groupby(tier(Dd.salary), observed=True)), ("week", Dd.groupby("week"))]:
        for k, g in grp:
            res.append({"by": key, "grp": str(k), **acc(g)})
    A = pd.DataFrame(res).round(2)
    A.to_csv(OUT / "accuracy_summary.csv", index=False)
    print(A.to_string(index=False))
    # paired bootstrap of |e| difference, cluster = player-week
    rng = np.random.default_rng(0)
    for a, b in (("FIX_NS", "OLD"), ("FIX", "OLD"), ("FIX", "FIX_NS")):
        dd = ((Dd[a] - Dd.act).abs() - (Dd[b] - Dd.act).abs()).to_numpy()
        bs = [rng.choice(dd, len(dd)).mean() for _ in range(4000)]
        print(f"MAE {a}-{b}: {dd.mean():+.2f}  95% {np.percentile(bs, 2.5):+.2f}..{np.percentile(bs, 97.5):+.2f}")
    R = rankq(D)
    R.to_csv(OUT / "ranking_by_slate_pos.csv", index=False)
    cols = [f"{v}_{m}" for m in ("sp", "valsp", "top", "topact") for v in V]
    print(R.groupby("position")[cols].mean().round(3).to_string())
    print("ALL", R[cols].mean().round(3).to_dict())
    for a, b in (("FIX_NS", "OLD"), ("FIX", "OLD"), ("FIX", "FIX_NS")):
        for m in ("sp", "valsp", "topact"):
            dd = (R[f"{a}_{m}"] - R[f"{b}_{m}"]).to_numpy()
            bs = [rng.choice(dd, len(dd)).mean() for _ in range(4000)]
            print(f"{m:6s} {a}-{b}: {dd.mean():+.3f} 95% {np.percentile(bs, 2.5):+.3f}..{np.percentile(bs, 97.5):+.3f}  wins {(dd > 0).sum()}/{len(dd)}")
    # the moved-team blow-up: fixed pass attempts implausible
    B = D[(D.proj_pass_att > 50) | ((D.FIX_NS > 1.6 * D.OLD) & (D.FIX_NS > 12))]
    print("\nLarge FIX_NS inflations (proj_pass_att>50 or FIX_NS>1.6xOLD & >12):")
    print(B[["slate_id", "player_name", "position", "team", "salary", "proj_pass_att", "OLD", "FIX_NS", "stack_delta", "FIX", "act"]].round(1).to_string(index=False))
