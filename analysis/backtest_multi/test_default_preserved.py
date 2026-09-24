"""Production-identity test for the opt-in scripts/ change (canonical_teams).

Builds a real 2026 DK classic slate twice in production mode (all real loaders,
depth chart / injury status included, props at the production CLI weight) --
once with scripts/build_projections_statline.py as committed at git HEAD, once
with the working-tree version at its defaults -- and asserts identical output.
Also asserts canonical_teams=True is identical on a 2026 slate (the alias map
is identity on 2020+ codes). OUTPUT_DIR writes (reconcile report) are
redirected to a temp dir; data/ and output/ are only read.

  python analysis/backtest_multi/test_default_preserved.py [slate_id] [season] [week]
"""
import importlib.util, subprocess, sys, tempfile
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
SLATE = sys.argv[1] if len(sys.argv) > 1 else "dk_classic_wk2_main_20Sep2026"
SEASON = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
WEEK = int(sys.argv[3]) if len(sys.argv) > 3 else 2
TMP = Path(tempfile.mkdtemp())

head_src = subprocess.run(["git", "show", "HEAD:scripts/build_projections_statline.py"],
                          cwd=REPO, capture_output=True, text=True, check=True).stdout
head_path = TMP / "bps_head.py"
head_path.write_text(head_src, encoding="utf-8")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


import build_projections as bp  # noqa: E402
bps_head = load("bps_head", head_path)
bps_new = load("bps_new", REPO / "scripts" / "build_projections_statline.py")
for m in (bps_head, bps_new):
    m.OUTPUT_DIR = TMP
# load_* helpers read from bp.OUTPUT_DIR (vegas lives in output/): leave it.

kw = dict(dst_model_mode="distributional", use_volume_prior=True, sigma_recal=True,
          vegas_slate_id=SLATE, props_weight=0.5, use_stack=True)
a = bps_head.build_statline_projections("dk", SEASON, WEEK, SLATE, **kw)
b = bps_new.build_statline_projections("dk", SEASON, WEEK, SLATE, **kw)
c = bps_new.build_statline_projections("dk", SEASON, WEEK, SLATE, canonical_teams=True, **kw)
pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))
pd.testing.assert_frame_equal(a.reset_index(drop=True), c.reset_index(drop=True))
print(f"PASS: {SLATE} ({len(a)} rows, {a.shape[1]} cols) identical HEAD vs working tree "
      f"(default) and vs canonical_teams=True; sum final_projection={a.final_projection.sum():.4f}")
