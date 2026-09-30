"""Check: patched optimizer with default / --own-penalty 0 produces byte-identical lineups to the pre-patch optimizer."""
import sys, subprocess, tempfile, shutil, hashlib
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "analysis" / "lambda_reverify"))
from sweep import RUNNER, POOLS
OLD = 'src = p.read_text(encoding="utf-8")'
assert OLD in RUNNER
sid = "dk_classic_wk3_main_27Sep2026"


def run(optsrc, preset, extra):
    r = RUNNER.replace(OLD, "src = Path(r'" + str(optsrc) + "').read_text(encoding='utf-8')")
    d = Path(tempfile.mkdtemp()); shutil.copy(POOLS / f"final_projections_dk_{sid}.csv", d)
    subprocess.run([sys.executable, "-c", r, str(REPO / "scripts"), str(d), "--site", "dk", "--preset", preset, "--slate-id", sid,
                    "--format", "classic", "--seed", "1", "--client-id", "x"] + extra, check=True, capture_output=True, cwd=str(REPO))
    f = [p for p in d.glob("*.csv") if "lineup" in p.name][0]
    return hashlib.md5(f.read_bytes()).hexdigest()


for preset in ["se_gpp", "cash", "mme_gpp"]:
    a = run(REPO / "analysis/ownership_lever/optimizer_orig.py.bak", preset, [])
    b = run(REPO / "scripts/optimizer.py", preset, [])
    c = run(REPO / "scripts/optimizer.py", preset, ["--own-penalty", "0"])
    print(preset, "IDENTICAL" if a == b == c else "DIFF", a, b, c, flush=True)
