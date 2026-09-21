"""
projection_stack.py
====================

Calibrated "stack" layer on top of the stat-line engine (DK classic only).

WHY (Week 2 2026 post-mortem, WK2_POSTMORTEM.md). Rebuilt 32 historical weeks
(2020-21, pre-game information only) and found: at skill positions the engine
alone is roughly tied with salary in out-of-sample R2, but the two are
complementary, and the engine's volume layer is no better than a simple
last-4-games average or salary for WR/TE targets. A per-position linear stack

    points ~ a + b1*salary($K) + b2*engine_points + b3..b9*(last-4-game usage)

fit on 2020-21 improved out-of-sample R2 by +0.016 to +0.054 at RB/WR/TE in
BOTH leave-one-season-out directions, widened the value spread (top vs bottom
fifth of players by engine-minus-salary gap: 4.2 -> 5.3 points), and held on 2026
data the fit never saw (forecast R2 wk2 0.374 -> 0.420, wk1 0.331 -> 0.426;
wk2 studs >= $5.8k: engine 13.3, stack 15.2, actual 15.3). It also removes most of
the stud under-projection that the two-week sample showed.

USAGE FEATURES are last-4-game means (min 1 game, rolling across seasons) of
targets, carries, pass attempts, target share, air-yards share, WOPR and
receiving air yards, using only games BEFORE the slate's week.

HOW IT IS APPLIED (build_projections_statline.py): with the engine-only points E
and the stack S, delta = S - E, clamped so S stays within [STACK_LO, STACK_HI]
of E. Players with no player-prop market get final = E + delta. Players whose
stat means were blended toward the market get final = E_props + PROPS_DELTA_SHARE
* delta (the market already carries part of the recent-usage information the
stack adds, so only half the correction is layered on top -- an assumption to
re-test with real props data). DK classic only: Showdown salaries are on a
different scale and FD has no fit, so both are left untouched.

The fit lives in data/projection_stack_dk.json, made by fit_projection_stack.py
from data/projection_stack_training_dk.csv. Refit as clean training weeks are
added. Any failure returns the engine points unchanged.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

USAGE_STATS = ["targets", "carries", "attempts", "target_share", "air_yards_share",
               "wopr", "receiving_air_yards"]
USAGE_COLS = ["u_" + c for c in USAGE_STATS]
FEATURES = ["sal", "proj"] + USAGE_COLS
STACK_LO, STACK_HI = 0.5, 1.8
PROPS_DELTA_SHARE = 0.5
POSITIONS = ("QB", "RB", "WR", "TE")


def artifact_path(site: str) -> Path:
    return DATA_DIR / f"projection_stack_{site}.json"


def load_artifact(site: str):
    p = artifact_path(site)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def usage_features(season: int, week: int) -> pd.DataFrame:
    """One row per player_id: last-4-game usage means using games strictly before
    (season, week). `week` may be the 23 sentinel (real Week 1 / preseason), which
    means "everything in `season`"."""
    frames = []
    for s in (season - 1, season):
        p = DATA_DIR / f"weekly_stats_{s}.parquet"
        if p.exists():
            d = pd.read_parquet(p)
            col = "season_type" if "season_type" in d.columns else "game_type"
            d = d[d[col] == "REG"]
            if s == season:
                d = d[d["week"] < week]
            frames.append(d)
    if not frames:
        return pd.DataFrame(columns=["player_id"] + USAGE_COLS)
    d = pd.concat(frames, ignore_index=True).sort_values(["player_id", "season", "week"])
    for c in USAGE_STATS:
        if c not in d.columns:
            d[c] = 0.0
    g = d.groupby("player_id")
    out = pd.DataFrame({"player_id": list(g.groups.keys())})
    for c in USAGE_STATS:
        out["u_" + c] = g[c].apply(lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0.0).tail(4).mean())).values
    return out


def apply_stack(df: pd.DataFrame, engine_col: str, site: str, season: int, week: int,
                artifact: dict = None) -> pd.Series:
    """Return the stacked points S (index-aligned to df) for QB/RB/WR/TE rows with a
    positive engine projection; NaN elsewhere. `df` needs player_id, position,
    salary and `engine_col`."""
    artifact = artifact or load_artifact(site)
    out = pd.Series(np.nan, index=df.index, dtype=float)
    if artifact is None:
        return out
    uf = usage_features(season, week).set_index("player_id")
    fill = artifact.get("usage_fill", {})
    for pos in POSITIONS:
        b = artifact["positions"].get(pos)
        if not b:
            continue
        m = (df["position"] == pos) & (pd.to_numeric(df[engine_col], errors="coerce") > 0)
        if not m.any():
            continue
        sub = df.loc[m]
        X = [np.ones(len(sub)),
             pd.to_numeric(sub["salary"], errors="coerce").fillna(0).to_numpy(float) / 1000.0,
             pd.to_numeric(sub[engine_col], errors="coerce").fillna(0).to_numpy(float)]
        for c in USAGE_COLS:
            vals = sub["player_id"].map(uf[c]) if c in uf.columns else pd.Series(np.nan, index=sub.index)
            X.append(vals.fillna(fill.get(c, 0.0)).to_numpy(float))
        coef = np.array([b["intercept"]] + [b["coefs"][f] for f in FEATURES], dtype=float)
        out.loc[m] = np.column_stack(X) @ coef
    return out


def combine(engine_pts: pd.Series, engine_with_props_pts: pd.Series, stacked: pd.Series,
            props_matched: pd.Series) -> pd.Series:
    """final = E + delta for unmatched; E_props + share*delta for matched, with the
    stacked value kept within [STACK_LO, STACK_HI] x engine."""
    e = engine_pts.astype(float)
    s = stacked.copy()
    ok = s.notna() & (e > 0)
    s = s.where(~ok, s.clip(lower=STACK_LO * e, upper=STACK_HI * e))
    delta = (s - e).where(ok, 0.0)
    ep = engine_with_props_pts.astype(float)
    return (ep + np.where(props_matched, PROPS_DELTA_SHARE, 1.0) * delta).clip(lower=0.0)
