"""Re-run analysis/proj_sigma/capture_draws.py (production-faithful QB1-guard history build, 88 DK main slates)
with a DIFFERENT statline_variance artifact, into a private dir. Research only; no FC data in this file.
Output (FC-derived, git-ignored): data/fc_history/derived/proj_variance/<tag>/{proj,draws}/
    python analysis/proj_variance/capture_variant.py --tag vol2021 --artifact data/fc_history/derived/proj_variance/sv_volume_2021.json
"""
import argparse, sys, multiprocessing as mp
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "analysis/proj_sigma"))
DER = REPO / "data/fc_history/derived/proj_variance"


def job(a):
    tag, art, j = a
    sys.path.insert(0, str(REPO / "scripts"))
    import capture_draws as cd, statline_model as sm
    cd.OUT = DER / tag
    if art:
        sm.ARTIFACT_PATH = Path(art)
    return cd.run_season(j)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", required=True); ap.add_argument("--artifact", default="")
    ap.add_argument("--workers", type=int, default=7); a = ap.parse_args()
    have = []
    for p in (REPO / "data/fc_history/derived/salaries_ourproj").glob("salaries_dk_fcmain_*_wk*.csv"):
        s, w = int(p.stem.split("_")[3]), int(p.stem.split("_wk")[1])
        if 2021 <= s <= 2026: have.append((s, w))
    jobs = [(a.tag, str(Path(a.artifact).resolve()) if a.artifact else "", (s, [w], False)) for s, w in sorted(have)]
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for _ in pool.imap_unordered(job, jobs): pass
    print("done", len(jobs))


if __name__ == "__main__":
    main()
