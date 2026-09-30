"""WK3 postmortem S4 step C: lambda re-verify on the full optimizer CLI (2026-09-30). DO NOT COMMIT builds/ (FC-derived).

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
LAMS = [-0.01, -0.005, 0.0, 0.03, 0.063]
PRESETS = {"mme_gpp": [1], "se_gpp": [1, 2, 3]}
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
    sid, preset, lam, seed = a
    tag = f"{preset}_l{lam:+.3f}_s{seed}"
    f = OUT / f"L_{sid}__{tag}.csv"
    if f.exists():
        return
    d = Path(tempfile.mkdtemp(prefix="lam_"))
    shutil.copy(POOLS / f"final_projections_dk_{sid}.csv", d)
    cmd = [sys.executable, "-c", RUNNER, str(REPO / "scripts"), str(d), "--site", "dk", "--preset", preset,
           "--slate-id", sid, "--format", "classic", "--seed", str(seed), "--lambda", str(lam), "--client-id", "x"]
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
    jobs = [(s, p, l, sd) for p, seeds in PRESETS.items() for s in (slates if p == "se_gpp" else S26 + HIST[::2]) for l in LAMS for sd in seeds]
    jobs.sort(key=lambda j: j[1] != "mme_gpp")  # long jobs first
    with Pool(int(sys.argv[1])) as p:
        for i, _ in enumerate(p.imap_unordered(job, jobs)):
            if i % 25 == 0:
                print(i, len(jobs), flush=True)
