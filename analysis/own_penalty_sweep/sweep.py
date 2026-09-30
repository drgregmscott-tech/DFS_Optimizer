"""own-penalty sweep (copied from lambda_reverify): builds with --own-penalty K; lambda = preset value.
WK3 postmortem S4 step C: lambda re-verify on the full optimizer CLI (2026-09-30). DO NOT COMMIT builds/ (FC-derived).

Pools = analysis/pool_randomization/builds/pools (current production inputs: 2026 wk1-2 old+blend-off, wk3 new
with QB recal + v2; history = hist old + production QB recal, FC-zero proxy). Runs scripts/optimizer.py's own
main() (--preset P --lambda L) in a subprocess with OUTPUT_DIR swapped to a temp dir (tracked file untouched).
usage: python sweep.py <nproc>
"""
import sys, subprocess, tempfile, shutil
from pathlib import Path
from multiprocessing import Pool
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
POOLS = REPO / "analysis" / "pool_randomization" / "builds" / "pools"
OUT = HERE / "builds"
LAMS = [float(x) for x in __import__("os").environ.get("OWNP","-0.05,-0.02,0,0.02,0.05,0.1").split(",")]
PRESETS = {"mme_gpp": [1], "se3max_pool": [1], "se_gpp": [1, 2, 3]}
S26 = sorted(p.name[len("final_projections_dk_"):-4] for p in POOLS.glob("final_projections_dk_dk_*.csv"))
HIST = sorted(p.name[len("final_projections_dk_"):-4] for p in POOLS.glob("final_projections_dk_hist_*.csv"))

RUNNER = r'''
import sys
from pathlib import Path
scripts, outdir, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
sys.path.insert(0, scripts)
p = Path(scripts) / "optimizer.py"
src = p.read_text(encoding="utf-8")
a = 'OUTPUT_DIR = REPO_ROOT / "output"'
assert src.count(a) == 1
src = src.replace(a, "OUTPUT_DIR = Path(r'" + outdir + "')")
sys.argv = [str(p)] + rest
try:
    exec(compile(src, str(p), "exec"), {"__name__": "__main__", "__file__": str(p)})
except SystemExit as e:
    if e.code not in (0, None):
        raise
'''


def job(a):
    sid, preset, lam, seed, arm = a
    tag = f"{preset}_l{lam:+.3f}_s{seed}__{arm}"
    f = OUT / f"L_{sid}__{tag}.csv"
    if f.exists():
        return
    d = Path(tempfile.mkdtemp(prefix="own_"))
    shutil.copy(HERE / f"pools_{arm}" / f"final_projections_dk_{sid}.csv", d)  # history ownership already on the 900% footing
    cmd = [sys.executable, "-c", RUNNER, str(REPO / "scripts"), str(d), "--site", "dk", "--preset", preset,
           "--slate-id", sid, "--format", "classic", "--seed", str(seed), "--own-penalty", str(lam), "--client-id", "x"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    outs = [p for p in d.glob("*.csv") if not p.name.startswith("final_projections")]
    lf = [p for p in outs if "lineup" in p.name]
    if r.returncode != 0 or not lf:
        (OUT / f"ERR_{sid}__{tag}.txt").write_text(r.stdout[-3000:] + "\n" + r.stderr[-3000:])
    else:
        shutil.copy(lf[0], f)
    shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    slates = S26 + HIST
    if len(sys.argv) > 2 and sys.argv[2] == "smoke":
        slates = [S26[0]]
    HW = lambda ws: [h for h in HIST if int(h[-2:]) in ws]
    MME8 = [h for h in HIST if h[-7:] in ("h2022w04", "h2022w13", "h2023w06", "h2023w15", "h2024w08", "h2024w16", "h2025w05", "h2025w14")]
    sl = {"se_gpp": HIST, "se3max_pool": HW((6, 12, 18)), "mme_gpp": MME8}
    jobs = [(s, p, l, sd, arm) for p, seeds in PRESETS.items() for s in sl[p] for l in LAMS for sd in seeds for arm in ("v2", "oracle") if not (arm == "oracle" and l == 0)]
    jobs += [(s, p, l, sd, "v2") for p, seeds in PRESETS.items() for s in S26 for l in LAMS for sd in seeds]
    order = {"se_gpp": 0, "se3max_pool": 1, "mme_gpp": 2}
    jobs.sort(key=lambda j: order[j[1]])
    with Pool(int(sys.argv[1])) as p:
        for i, _ in enumerate(p.imap_unordered(job, jobs)):
            if i % 25 == 0:
                print(i, len(jobs), flush=True)
