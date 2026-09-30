"""Ownership lever sweep (WK3 postmortem S4 parking lot, 2026-09-30). DO NOT COMMIT builds/ (FC-derived).
Runs real scripts/optimizer.py CLI (--preset mme_gpp --own-penalty K) on the lambda_reverify pools.
Arms: mod = pool as-is (our modeled ownership, what we'd have live); real = estimated_ownership_pct replaced by
realized contest ownership (upper bound, leaky by construction). usage: python sweep.py <nproc> [smoke]"""
import sys, subprocess, tempfile, shutil
from pathlib import Path
from multiprocessing import Pool
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LAM = REPO / "analysis" / "lambda_reverify"
sys.path.insert(0, str(LAM)); sys.path.insert(0, str(REPO / "analysis" / "lineup_replay"))
import importlib.util as _u
_sp = _u.spec_from_file_location("lam_sweep", LAM / "sweep.py"); _m = _u.module_from_spec(_sp); _sp.loader.exec_module(_m)
RUNNER, POOLS, S26, HIST = _m.RUNNER, _m.POOLS, _m.S26, _m.HIST
OUT = HERE / "builds"
KS = [-0.05, 0.05, 0.15]
PRESET = sys.argv[3] if len(sys.argv) > 3 else "mme_gpp"
SEEDS = [1] if PRESET == "mme_gpp" else [1, 2, 3]


def real_own(sid, df):
    if sid.startswith("hist_"):
        M = np.load(REPO / "analysis" / "lineup_replay" / "hist_meta" / f"{sid[5:]}.npz")
        d = dict(zip(M["fp_ids"], M["own"]))
        return df.player_name.map(lambda n: d.get(int(str(n).split("#")[-1]), 0.0)).astype(float)
    import grade as G
    lab = {v[0]: k for k, v in G.SL.items()}[sid]
    C = G.contest(*G.SL[lab][1]["se"])
    return df.player_name.map(lambda n: C["own"].get(G.norm(n), 0.0)).astype(float)


def job(a):
    sid, arm, k, seed = a
    tag = f"{PRESET}_{arm}_k{k:+.3f}_s{seed}"
    f = OUT / f"O_{sid}__{tag}.csv"
    if f.exists():
        return
    d = Path(tempfile.mkdtemp(prefix="own_"))
    src = POOLS / f"final_projections_dk_{sid}.csv"
    if arm == "real":
        df = pd.read_csv(src, dtype={"player_id": str})
        df["estimated_ownership_pct"] = real_own(sid, df)
        df.to_csv(d / src.name, index=False)
    else:
        shutil.copy(src, d)
    lam = "-0.005" if PRESET == "mme_gpp" else "0"
    cmd = [sys.executable, "-c", RUNNER, str(REPO / "scripts"), str(d), "--site", "dk", "--preset", PRESET,
           "--slate-id", sid, "--format", "classic", "--seed", str(seed), "--lambda", lam, "--own-penalty", str(k),
           "--client-id", "x"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    lf = [p for p in d.glob("*.csv") if "lineup" in p.name and not p.name.startswith("final_projections")]
    if r.returncode != 0 or not lf:
        (OUT / f"ERR_{sid}__{tag}.txt").write_text(r.stdout[-3000:] + "\n" + r.stderr[-3000:])
    else:
        shutil.copy(lf[0], f)
    shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    slates = S26 + (HIST[::4] if PRESET == "mme_gpp" else HIST)
    if len(sys.argv) > 2 and sys.argv[2] == "smoke":
        slates = [S26[0]]
    jobs = [(s, "mod", 0.0, sd) for s in slates for sd in SEEDS]
    jobs += [(s, arm, k, sd) for s in slates for arm in ("mod", "real") for k in KS for sd in SEEDS]
    with Pool(int(sys.argv[1])) as p:
        for i, _ in enumerate(p.imap_unordered(job, jobs)):
            if i % 25 == 0:
                print(i, len(jobs), flush=True)
