"""Empirical leak test: rebuild (season, week) with every data frame the build
reads truncated to information available before kickoff, then diff against
the normal harness build of the same week.

Embargo applied at pandas.read_parquet / read_csv (in-process only):
  * any frame with season+week columns: drop rows with (season == S and
    week > W) and (season > S).
  * rows for week W itself: dropped for stats-like frames; for schedule /
    games frames (need the target week's fixtures) the result columns
    (scores, result, total, overtime) are blanked instead.
If the projection for week W is unchanged, nothing from week >= W's outcomes
reaches it. (Known pre-kickoff-ish fields that are kept: schedule starter QB
ids, roof/wind, closing lines -- see REPORT.md.)

  python analysis/backtest_multi/leak_embargo_test.py 2019 10
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_backtest as rb  # noqa: E402

S, W = int(sys.argv[1]), int(sys.argv[2])
RESULT_COLS = ["home_score", "away_score", "result", "total", "overtime"]
FIXTURE_HINT = {"home_team", "away_team"}
_rp, _rc = pd.read_parquet, pd.read_csv
hits = {}


def embargo(df, src):
    if not isinstance(df, pd.DataFrame) or not {"season", "week"}.issubset(df.columns):
        return df
    se = pd.to_numeric(df["season"], errors="coerce")
    wk = pd.to_numeric(df["week"], errors="coerce")
    future = (se > S) | ((se == S) & (wk > W))
    cur = (se == S) & (wk == W)
    n0 = len(df)
    if FIXTURE_HINT.issubset(df.columns):
        df = df[~future].copy()
        for c in RESULT_COLS:
            if c in df.columns:
                df.loc[(pd.to_numeric(df["season"]) == S) & (pd.to_numeric(df["week"]) == W), c] = np.nan
    else:
        df = df[~(future | cur)]
    hits[str(src)[-60:]] = n0 - len(df)
    return df


pd.read_parquet = lambda p, *a, **k: embargo(_rp(p, *a, **k), p)
pd.read_csv = lambda p, *a, **k: embargo(_rc(p, *a, **k), p)
# the harness writes/reads its own vegas + matchup files; those have no season/week cols.

rb.OUT = HERE / "out" / "embargo"
opts = {"restore_matchup": True, "stack": True, "sigma_recal": True, "volume_prior": True,
        "role_change": True, "dst_model": "distributional"}
rb.run_season(("embargo", S, [W], opts, True))
rb.OUT = HERE / "out"
pd.read_parquet, pd.read_csv = _rp, _rc
a = _rc(HERE / "out" / "embargo" / "proj" / "embargo" / f"proj_embargo_dk_{S}_wk{W}.csv")
ref_arm = "matchup_restored"
b = _rc(HERE / "out" / "proj" / ref_arm / f"proj_{ref_arm}_dk_{S}_wk{W}.csv")
m = a.merge(b, on=["player_id", "position", "team"], suffixes=("_emb", "_ref"))
d = (m.final_projection_emb - m.final_projection_ref).abs()
print("rows truncated per file:", {k: v for k, v in hits.items() if v})
print(f"{S} wk{W}: matched {len(m)}/{len(a)}; max |diff| {d.max():.6f}; n diff>1e-6: {(d > 1e-6).sum()}")
if (d > 1e-6).any():
    print(m.loc[d > 1e-6, ["player_name_emb", "position", "team", "final_projection_emb",
                           "final_projection_ref"]].head(20).to_string())
