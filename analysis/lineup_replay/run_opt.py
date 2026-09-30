"""Run scripts/optimizer.py's own CLI (unchanged logic, --preset) against a replay build, in-process with
OUTPUT_DIR pointed at analysis/lineup_replay/builds/<arm> (in-memory substitution; tracked file untouched).

usage: python analysis/lineup_replay/run_opt.py <arm> <slate_id> <preset> <seed>
writes builds/<arm>/lineups_multi_dk_<slate_id>_<preset>_s<seed>.csv
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCRIPTS = REPO / "scripts"

arm, sid, preset, seed = sys.argv[1:5]
outdir = HERE / "builds" / arm
sys.path.insert(0, str(SCRIPTS))
src_path = SCRIPTS / "optimizer.py"
src = src_path.read_text(encoding="utf-8")
a = 'OUTPUT_DIR = REPO_ROOT / "output"'
assert src.count(a) == 1
src = src.replace(a, f'OUTPUT_DIR = Path(r"{outdir}")')
sys.argv = [str(src_path), "--site", "dk", "--preset", preset, "--slate-id", sid, "--format", "classic",
            "--seed", seed, "--client-id", f"{preset}_s{seed}"]
g = {"__name__": "__main__", "__file__": str(src_path)}
try:
    exec(compile(src, str(src_path), "exec"), g)
except SystemExit as e:
    if e.code not in (0, None):
        raise
