"""
B1 frame: 9 DK classic slates (wk1-3) with ownership-model features, real ownership, and extras.

- wk1/wk2: leak-free rebuilds in ./rebuilds (rebuild_wk12.sh, current code, --backtest-no-leak).
  The rebuild has no status info, so we apply the PRE-LOCK status the way production does
  (status_check apply): zero OUT+DOUBTFUL players, using the union of OUT/DOUBTFUL flags in that
  week's pre-lock committed files (commits below, last commit before lock).
- wk3: pre-lock production outputs (copied from output/ into ./rebuilds; committed 16:31Z/16:33Z/19:46Z).
  For wk3 we also keep the file's as-built estimated_ownership_pct = the LIVE model's out-of-sample number.

Writes frame.parquet (features via scripts/fit_ownership_model.load_training_frame logic).
"""
import io
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import fit_ownership_model as fom  # noqa: E402

PRELOCK = {1: ["cefc761:wk1_main_13Sep2026", "439ac11:wk1_early_13Sep2026", "33a3b1c:wk1_afternoon_13Sep2026"],
           2: ["7e57cfe:wk2_main_20Sep2026", "c1b3099:wk2_early_20Sep2026", "614702c:wk2_afternoon_20Sep2026"]}


def prelock_out(week):
    ids = set()
    for spec in PRELOCK[week]:
        c, s = spec.split(":")
        raw = subprocess.check_output(["git", "show", f"{c}:output/final_projections_dk_dk_classic_{s}.csv"], cwd=REPO)
        d = pd.read_csv(io.StringIO(raw.decode()), dtype={"player_id": str})
        if "injury_status" in d:
            ids |= set(d.loc[d["injury_status"].isin(["OUT", "DOUBTFUL"]), "player_id"])
    return ids


def main():
    # stage: status-applied copies in a temp dir that load_training_frame reads as OUTPUT_DIR
    stage = HERE / "stage"
    stage.mkdir(exist_ok=True)
    asbuilt = {}
    for f in sorted((HERE / "rebuilds").glob("final_projections_dk_dk_classic_wk*.csv")):
        d = pd.read_csv(f, dtype={"player_id": str, "site_player_id": str})
        wk = int(f.name.split("_wk")[1][0])
        if wk in PRELOCK:
            out = prelock_out(wk)
            m = d["player_id"].isin(out)
            print(f"{f.name}: zeroing {int((m & (d.final_projection > 0)).sum())} pre-lock OUT/DOUBTFUL")
            d.loc[m, "final_projection"] = 0.0
        else:
            sid = f.stem.replace("final_projections_dk_", "")
            asbuilt[sid] = d.set_index("player_id")["estimated_ownership_pct"]
        d.to_csv(stage / f.name, index=False)
    fom.OUTPUT_DIR = stage
    df = fom.load_training_frame("dk")
    df["est_live"] = np.nan
    for sid, s in asbuilt.items():
        m = df["slate_id"] == sid
        df.loc[m, "est_live"] = df.loc[m, "player_id"].map(s).values
    df.to_parquet(HERE / "frame.parquet")
    print("rows", len(df))


if __name__ == "__main__":
    main()
