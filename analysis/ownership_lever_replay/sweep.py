"""Ownership-source x own-penalty sweep on the real optimizer CLI. DO NOT COMMIT builds/ (FC/contest-derived).
Same projections in every arm; only estimated_ownership_pct differs (pools/<src>__final_projections_dk_<sid>.csv).
usage: python sweep.py <nproc> <mode>   mode = step1 | se | mme"""
import sys, subprocess, tempfile, shutil
from pathlib import Path
from multiprocessing import Pool
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "analysis" / "lambda_reverify"))
from sweep import RUNNER, S26, HIST  # noqa
OUT = HERE / "builds"; PP = HERE / "pools"
KS = [-0.05, 0.02, 0.05, 0.1, 0.2]
SRCS = ["old", "v2", "v2novac", "v2tp", "oracle"]


def job(a):
    sid, src, preset, k, seed, default = a
    tag = f"{preset}_{src}_k{k:+.3f}_s{seed}" + ("_def" if default else "")
    f = OUT / f"O_{sid}__{tag}.csv"
    if f.exists():
        return
    src_f = PP / f"{src}__final_projections_dk_{sid}.csv"
    if not src_f.exists():
        return
    d = Path(tempfile.mkdtemp(prefix="olr_"))
    shutil.copy(src_f, d / f"final_projections_dk_{sid}.csv")
    cmd = [sys.executable, "-c", RUNNER, str(REPO / "scripts"), str(d), "--site", "dk", "--preset", preset,
           "--slate-id", sid, "--format", "classic", "--seed", str(seed), "--client-id", "x"]
    if not default:
        cmd += ["--own-penalty", str(k)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    lf = [p for p in d.glob("*.csv") if "lineup" in p.name and not p.name.startswith("final_projections")]
    if r.returncode != 0 or not lf:
        (OUT / f"ERR_{sid}__{tag}.txt").write_text(r.stdout[-3000:] + "\n" + r.stderr[-3000:])
    else:
        shutil.copy(lf[0], f)
    shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    mode = sys.argv[2]
    if mode == "step1":
        jobs = [(s, src, p, 0.0, 1, True) for s in S26 for src in ("old", "v2", "v2tp") for p in ("cash", "se_gpp", "se3max_pool", "mme_gpp")]
    elif mode == "se":
        sl = S26
        jobs = [(s, "v2", "se_gpp", 0.0, sd, False) for s in sl for sd in (1, 2)]
        jobs += [(s, src, "se_gpp", k, sd, False) for k in KS for s in sl for src in SRCS for sd in (1, 2)]
    else:
        jobs = [(s, "v2", "mme_gpp", 0.0, 1, False) for s in S26]
        jobs += [(s, src, "mme_gpp", k, 1, False) for k in (0.05, 0.2) for s in S26 for src in ("v2", "oracle")]
    with Pool(int(sys.argv[1])) as p:
        for i, _ in enumerate(p.imap_unordered(job, jobs)):
            if i % 50 == 0:
                print(i, len(jobs), flush=True)
