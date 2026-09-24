"""Production diff: HEAD scripts vs working-tree scripts on real 2026 slates.

Each version builds in its own subprocess. The HEAD copies of the modules
changed in this session are executed from `git show HEAD:<path>` under their
real file paths, so their data/output paths resolve exactly as in production.
OUTPUT_DIR writes (reconcile report) go to a temp dir; data/ and output/ are
only read. Result frames are pickled to --out (default: a temp dir).

  python analysis/backtest_multi/diff_2026_slate.py                       # default slates
  python analysis/backtest_multi/diff_2026_slate.py --slates dk:2026:3:dk_classic_wk3_main_27Sep2026
  python analysis/backtest_multi/diff_2026_slate.py --new-kw p10_calibration=False   # expect identity
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
CHANGED = ["statline_model.py", "build_projections_statline.py"]
DEFAULT_SLATES = ["dk:2026:3:dk_classic_wk3_main_27Sep2026",
                  "dk:2026:3:dk_showdown_wk3_Atl_GB_24Sep2026"]

CHILD = r'''
import sys, types, subprocess, pickle, json
from pathlib import Path
REPO = Path(sys.argv[1]); version = sys.argv[2]; out = Path(sys.argv[3]); tmp = Path(sys.argv[4])
site, season, week, slate = sys.argv[5].split(":"); extra = json.loads(sys.argv[6])
sys.path.insert(0, str(REPO / "scripts"))
if version == "head":
    for name in %r:
        src = subprocess.run(["git", "show", f"HEAD:scripts/{name}"], cwd=REPO, capture_output=True,
                             text=True, check=True, encoding="utf-8").stdout
        mod = types.ModuleType(name[:-3]); mod.__file__ = str(REPO / "scripts" / name)
        sys.modules[name[:-3]] = mod
        exec(compile(src, mod.__file__, "exec"), mod.__dict__)
import build_projections_statline as bps
bps.OUTPUT_DIR = tmp
kw = dict(dst_model_mode="distributional", use_volume_prior=True, sigma_recal=True,
          vegas_slate_id=slate, props_weight=0.5, use_stack=True)
kw.update(extra)
df = bps.build_statline_projections(site, int(season), int(week), slate, **kw)
df.to_pickle(out)
''' % (CHANGED,)


def run(version, slate, outdir, extra):
    tmp = Path(tempfile.mkdtemp())
    out = outdir / f"{version}_{slate.split(':')[-1]}.pkl"
    r = subprocess.run([sys.executable, "-c", CHILD, str(REPO), version, str(out), str(tmp), slate,
                        json.dumps(extra)], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit(f"{version} {slate} failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return pd.read_pickle(out), r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slates", nargs="+", default=DEFAULT_SLATES)
    ap.add_argument("--new-kw", nargs="*", default=[], help="k=v overrides for the working-tree build")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    extra = {k: eval(v) for k, v in (x.split("=", 1) for x in a.new_kw)}  # noqa: S307 -- local CLI only
    outdir = Path(a.out) if a.out else Path(tempfile.mkdtemp())
    outdir.mkdir(parents=True, exist_ok=True)
    for slate in a.slates:
        h, _ = run("head", slate, outdir, {})
        n, log = run("new", slate, outdir, extra)
        def _sorted(df):
            df = df.assign(_rr=df["roster_role"].fillna("") if "roster_role" in df.columns else "")
            return df.sort_values(["player_id", "_rr", "position", "salary"], kind="stable")                 .drop(columns="_rr").reset_index(drop=True)
        h, n = _sorted(h), _sorted(n)
        print(f"\n=== {slate}  rows head={len(h)} new={len(n)}  cols equal={list(h.columns) == list(n.columns)}  -> {outdir}")
        changed = []
        for c in h.columns:
            if c not in n.columns:
                changed.append(c); continue
            x, y = h[c], n[c]
            if pd.api.types.is_numeric_dtype(x):
                eq = np.isclose(x.astype(float), y.astype(float), equal_nan=True, rtol=0, atol=0)
            else:
                eq = (x.fillna("<NA>").astype(str) == y.fillna("<NA>").astype(str)).to_numpy()
            if not eq.all():
                changed.append(c)
                print(f"  CHANGED {c}: {int((~eq).sum())} rows" + (
                    f", mean {x.mean():.3f} -> {y.mean():.3f}" if pd.api.types.is_numeric_dtype(x) else ""))
        if not changed:
            print("  IDENTICAL (every column, every row)")
        if "statline_p10" in changed:
            sk = n["position"].isin(["QB", "RB", "WR", "TE"]) & (n["final_projection"] >= 5)
            for thr in (1.0, 0.9, 0.5):
                print(f"  dart flags final>=5 (non-DST): p10<{thr}: head {int((h.loc[sk, 'statline_p10'] < thr).sum())}"
                      f" new {int((n.loc[sk, 'statline_p10'] < thr).sum())}")
            k = int((h.loc[sk, "statline_p10"] < 1.0).sum())
            T = float(np.sort(n.loc[sk, "statline_p10"].to_numpy())[k]) if 0 < k < sk.sum() else float("nan")
            print(f"  threshold on new p10 matching head's p10<1.0 count ({k}) among final>=5: {T:.2f}")
            m = h[sk][["player_name", "position", "salary", "final_projection", "statline_p10"]].copy()
            m["p10_new"] = n.loc[sk, "statline_p10"].to_numpy()
            print(m.sort_values("final_projection", ascending=False).head(12).round(2).to_string(index=False))
        for line in log.splitlines():
            if line.startswith(("p10 calibration", "Floor-share")):
                print("  log:", line)


if __name__ == "__main__":
    main()
