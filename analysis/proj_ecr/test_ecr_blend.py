"""Unit checks for scripts/ecr_blend.py (synthetic data, no network). Run: python analysis/proj_ecr/test_ecr_blend.py"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import ecr_blend  # noqa: E402

ecr_blend.AUDIT_DIR = ROOT / "analysis" / "proj_ecr" / "_test_audit"  # never touch data/ in tests

NOW = datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc)
FUT = int(datetime(2026, 9, 27, 17, 0, tzinfo=timezone.utc).timestamp())
PAST = int(datetime(2026, 9, 24, 23, 0, tzinfo=timezone.utc).timestamp())
NEXTWK = int(datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc).timestamp()) + 86400 * 3

pts_map = pd.DataFrame({"position": ["RB"] * 3 + ["TE"] * 2, "ecr": [1.0, 10.0, 20.0, 1.0, 10.0],
                        "exp_pts": [24.0, 12.0, 6.0, 20.0, 8.0]})
xwalk = pd.DataFrame({"fantasypros_id": [str(i) for i in range(1, 9)],
                      "gsis_id": [f"00-000000{i}" for i in range(1, 9)]})


def mk_df():
    return pd.DataFrame({
        "player_id": [f"00-000000{i}" for i in range(1, 10)],
        "player_name": [f"P{i}" for i in range(1, 10)],
        "position": ["RB", "RB", "RB", "RB", "RB", "RB", "TE", "QB", "RB"],
        "team": ["A"] * 9, "opponent": ["B"] * 9,
        "final_projection": [10.0, 20.0, 0.0, 8.0, 15.0, 9.0, 8.0, 18.0, 12.0],
        "statline_p10": [2.0, 1.0, 0.0, 0.5, 3.0, 2.0, 1.0, 5.0, 3.0],
        "statline_p90": [20.0, 30.0, 0.0, 15.0, 25.0, 18.0, 14.0, 30.0, 20.0]})


def mk_ecr(scrape="2026-09-25"):
    return pd.DataFrame({
        "page": ["ppr-rb"] * 5 + ["ppr-te"],
        "fantasypros_id": [1, 2, 3, 4, 5, 7],
        "ecr": [10.0, 1.0, 1.0, 20.0, 10.0, 10.0],
        "player_game_kickoff_ts": [FUT, FUT, FUT, FUT, PAST, FUT],
        "player_opponent": ["vs. B", "at B", "vs. B", "vs. B", "vs. B", "vs. B"],
        "scrape_date": [scrape] * 6})


def run(df, w, ecr, **kw):
    return ecr_blend.apply_blend(df, w, "test", now=NOW, ecr_df=ecr, crosswalk=xwalk, pts_map=pts_map, **kw)


# 1. weights zero -> untouched
d0 = mk_df()
out, s = run(d0, {"RB": 0.0, "TE": 0.0}, mk_ecr())
assert out.equals(d0) and s["status"] == "not_run"

# 2. stale ECR file -> untouched
out, s = run(mk_df(), {"RB": 0.5}, mk_ecr("2026-09-20"))
assert out.equals(mk_df()) and s["status"] == "skipped_stale_ecr"

# 3. basic blend RB w=0.5
out, s = run(mk_df(), {"RB": 0.5}, mk_ecr())
assert s["status"] == "applied" and s["RB_blended"] == 3, s  # P1, P2, P4 (P3 has final 0, P5 kicked off, P6/P9 not in ECR)
assert s["RB_skipped"] == {"no_ecr": 2, "kickoff_passed": 1}, s
# P1: ecr 10 -> 12.0 pts: (10+12)/2 = 11 ; P2: ecr 1 -> 24: (20+24)/2 = 22
assert abs(out.loc[0, "final_projection"] - 11.0) < 1e-9
assert abs(out.loc[1, "final_projection"] - 22.0) < 1e-9
# P3 final 0 stays 0 even though ECR has him
assert out.loc[2, "final_projection"] == 0.0
# P4 (ecr 20, kickoff future): (8+6)/2 = 7 ... but window check: FUT is within 8 days, so blended
assert abs(out.loc[3, "final_projection"] - 7.0) < 1e-9
# P5 kickoff already passed -> unchanged
assert out.loc[4, "final_projection"] == 15.0
# P6 not in ECR -> unchanged
assert out.loc[5, "final_projection"] == 9.0
# TE (weight 0 / not requested) and QB never touched
assert out.loc[6, "final_projection"] == 8.0 and out.loc[7, "final_projection"] == 18.0
# 4. p10/p90 shift by the same delta and clip at 0
assert abs(out.loc[0, "statline_p10"] - 3.0) < 1e-9 and abs(out.loc[0, "statline_p90"] - 21.0) < 1e-9
assert abs(out.loc[3, "statline_p10"] - 0.0) < 1e-9  # 0.5 - 1.0 clipped to 0
assert out.loc[2, "statline_p10"] == 0.0 and out.loc[2, "statline_p90"] == 0.0

# 5. week window: kickoff far beyond the scrape week is skipped
e = mk_ecr(); e.loc[0, "player_game_kickoff_ts"] = NEXTWK + 86400 * 10
out, s = run(mk_df(), {"RB": 0.5}, e)
assert out.loc[0, "final_projection"] == 10.0 and s["RB_skipped"].get("outside_week") == 1

# 6. TE blend only when asked
out, s = run(mk_df(), {"RB": 0.0, "TE": 0.3}, mk_ecr())
assert abs(out.loc[6, "final_projection"] - (0.7 * 8.0 + 0.3 * 8.0)) < 1e-9  # ecr 10 -> 8.0 pts
assert out.loc[0, "final_projection"] == 10.0

# 7. input frame not mutated
d1 = mk_df(); before = d1.copy(); run(d1, {"RB": 0.5}, mk_ecr()); assert d1.equals(before)
print("all ECR blend checks passed")
