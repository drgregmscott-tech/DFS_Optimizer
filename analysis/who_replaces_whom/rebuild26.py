"""Leak-free OLD vs NEW rebuild of one DK classic 2026 slate, without editing tracked scripts or touching output/.

OLD = DFS_OWNERSHIP_V2=0, --no-early-blend, --no-qb-recal.  NEW = all three on (defaults).
Runs build_projections_statline.py's own __main__ in-process from an in-memory copy of its source with two
in-memory substitutions: OUTPUT_DIR -> analysis/lineup_replay/builds/<arm>, and (wk1 only) the early blend is
fed week 1 (the wk1 rebuild must use --season 2025 --week 23 for data, which would otherwise skip the blend).
The injury-status pull the build reads is pinned to the pre-lock file (statline_model.load_injury_status patched).
Then status_check apply (zero OUT/DOUBTFUL + ownership refresh) with the same pre-lock status file, as production does.

usage: python analysis/lineup_replay/rebuild.py <old|new> <wk1_main|...>
DO NOT COMMIT the builds/ folder.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "rebuild26"
REPO = HERE.parents[2]
SCRIPTS = REPO / "scripts"

# label: (slate_id, season, week, blend_week, status file (pre-lock), vegas slate id)
S = "output/player_status_"
SLATES = {
    "wk1_main": ("dk_classic_wk1_main_13Sep2026", 2025, 23, 1, S + "23_20260910_185633.csv", None),
    "wk1_early": ("dk_classic_wk1_early_13Sep2026", 2025, 23, 1, S + "23_20260910_185633.csv", None),
    "wk1_afternoon": ("dk_classic_wk1_afternoon_13Sep2026", 2025, 23, 1, S + "23_20260910_185633.csv", None),
    "wk2_main": ("dk_classic_wk2_main_20Sep2026", 2026, 2, 2, S + "2_20260920_163047.csv", None),
    "wk2_early": ("dk_classic_wk2_early_20Sep2026", 2026, 2, 2, S + "2_20260920_163047.csv", None),
    "wk2_afternoon": ("dk_classic_wk2_afternoon_20Sep2026", 2026, 2, 2, S + "2_20260920_193048.csv", None),
    "wk3_main": ("dk_classic_wk3_main_27Sep2026", 2026, 3, 3, S + "3_20260927_163048.csv", "dk_classic_wk3_main_27Sep2026"),
    "wk3_early": ("dk_classic_wk3_early_27Sep2026", 2026, 3, 3, S + "3_20260927_163048.csv", "dk_classic_wk3_main_27Sep2026"),
    "wk3_afternoon": ("dk_classic_wk3_afternoon_27Sep2026", 2026, 3, 3, S + "3_20260927_194535.csv", "dk_classic_wk3_main_27Sep2026"),
}


def build(arm, lab):
    sid, season, week, bweek, status, vegas = SLATES[lab]
    outdir = HERE / "builds" / arm
    outdir.mkdir(parents=True, exist_ok=True)
    os.environ["DFS_WRW_RB"] = "1" if arm == "on" else "0"
    sys.path.insert(0, str(SCRIPTS))
    import pandas as pd
    import statline_model

    def _pinned(wk):
        latest = pd.read_csv(REPO / status)
        latest = statline_model._apply_manual_status_to_pull(latest, wk)
        return latest[["player_id", "team", "position", "status"]]
    statline_model.load_injury_status = _pinned

    src_path = SCRIPTS / "build_projections_statline.py"
    src = src_path.read_text(encoding="utf-8")
    a = 'if __name__ == "__main__":'
    assert src.count(a) == 1
    src = src.replace(a, f'OUTPUT_DIR = Path(r"{outdir}")\n' + a)
    b = "df = _apply_early_season_blend(df, week, "
    assert src.count(b) == 1, "blend call site moved"
    src = src.replace(b, f"df = _replay_blend(df, {bweek}, ")
    # wk1 only: the data week is 23 (2025), so QB recal must be off (real week 1 < min_week 3), and the blend must
    # leave zero-sigma (no-history) rows alone -- otherwise sigma recal fails loud on "positive projection, sigma 0".
    # NOTE: that failure would also hit a real week-1 production build (see RESULTS.md, flagged not fixed).
    helper = """
def _replay_blend(df, wk, cfg):
    keep = df['statline_sigma'].fillna(0) <= 0
    saved = df.loc[keep, ['final_projection', 'statline_p10', 'statline_p90']].copy()
    df = _apply_early_season_blend(df, wk, cfg)
    df.loc[keep, ['final_projection', 'statline_p10', 'statline_p90']] = saved
    df.loc[keep, 'early_blend_delta'] = 0.0
    return df


"""
    anchor = "def build_statline_projections("
    assert src.count(anchor) == 1
    src = src.replace(anchor, helper + anchor)
    argv = [str(src_path), "--site", "dk", "--season", str(season), "--week", str(week), "--slate-id", sid,
            "--volume-prior", "--sigma-recalibration", "--dst-model", "distributional", "--backtest-no-leak",
            "--early-blend-config", str(REPO / "data" / "early_season_blend_config.json"),
            "--qb-recal-config", str(REPO / "data" / "qb_recal_config.json")]
    if vegas:
        argv += ["--vegas-slate-id", vegas]
    if False:
        argv += ["--no-early-blend", "--no-qb-recal"]
    elif lab.startswith("wk1"):
        argv += ["--no-qb-recal"]
    sys.argv = argv
    g = {"__name__": "__main__", "__file__": str(src_path)}
    exec(compile(src, str(src_path), "exec"), g)
    built = outdir / f"final_projections_dk_{sid}.csv"
    raw = outdir / f"buildtime_{sid}.csv"
    shutil.copy(built, raw)
    env = dict(os.environ)
    r = subprocess.run([sys.executable, str(SCRIPTS / "status_check.py"), "apply", "--site", "dk", "--week", str(week),
                        "--status-file", str(REPO / status), "--projections-file", str(raw), "--out", str(built)],
                       cwd=REPO, env=env, capture_output=True, text=True)
    print(r.stdout[-1500:], r.stderr[-1500:])


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
