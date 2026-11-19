"""
projection_stack.py
====================

Calibrated "stack" layer on top of the stat-line engine (DK classic; FD behind DFS_D2_FD_STACK).

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
re-test with real props data). DK classic only (FD only behind the flag above): Showdown salaries are on a
different scale, so they are left untouched.

The DK fit lives in data/projection_stack_dk.json, made by fit_projection_stack.py
from data/projection_stack_training_dk.csv (the current artifact was refit 2026-10-07 on
2021-25; the 2020-21 above is the original WK2 study). Refit as clean training weeks are
added. Any failure returns the engine points unchanged.

FD (D2 item c, analysis/d2_projection_inputs/FD_STACK_DESIGN.md): off unless
DFS_D2_FD_STACK=1 ("nosal" = salary-free block only). data/projection_stack_fd.json has
`positions` (salary term = the same-week DK price, since FD price history 2022-25 does not
exist) and `positions_nosal` (engine + usage only). A row without a DK price uses the
no-salary block. Missing artifact or any failure = engine points unchanged.
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


# ---------------------------------------------------------------- FD (D2 item c; DFS_D2_FD_STACK)
def dk_salary_for_fd(df: pd.DataFrame, season: int, week: int, slate_id: str = None) -> pd.Series:
    """Same-week DK salary for each FD row (index-aligned, NaN = no DK price). Looks for the DK twin of
    the FD slate file (fd_ -> dk_ in the slate id), else the DK main-slate file of that week. The DK
    price stands in for the FD price in the FD stack's salary term (no FD price history exists 2022-25)."""
    import glob
    cand = []
    if slate_id:
        # FD file salaries_fd_fd_classic_wk10_main_15Nov2026 -> DK twin salaries_dk_dk_classic_wk10_main_15Nov2026
        cand.append(DATA_DIR / ("salaries_dk_" + str(slate_id).replace("fd_", "dk_", 1) + ".csv"))
    # Same-week DK main slate of the SAME season (file names end in the year; never borrow another season's prices).
    cand += [Path(p) for p in sorted(glob.glob(str(DATA_DIR / f"salaries_dk_dk_classic_wk{int(week)}_main_*{int(season)}.csv")))]
    sal = None
    for p in cand:
        if p.exists():
            d = pd.read_csv(p, dtype={"player_id": str}, usecols=["player_id", "salary"])
            d = d[d["player_id"].notna()].drop_duplicates("player_id")
            s = pd.to_numeric(d.set_index("player_id")["salary"], errors="coerce")
            sal = s if sal is None else sal.combine_first(s)   # twin first, main slate fills players not on it
    if sal is None:
        raise FileNotFoundError(f"no DK salary file for FD slate {slate_id!r} week {week}")
    return df["player_id"].map(sal).astype(float)


def apply_stack_fd(df: pd.DataFrame, engine_col: str, season: int, week: int, artifact: dict,
                   dk_salary: pd.Series = None):
    """FD stacked points S and the block used per row ('dksal' / 'nosal' / '' for rows not stacked).
    dksal block = artifact['positions'] with the DK price as `salary`; rows with no DK price (or dk_salary
    None) use artifact['positions_nosal']. NaN S where the engine is not positive (same as apply_stack)."""
    nosal_art = {"usage_fill": artifact.get("usage_fill", {}), "positions": artifact.get("positions_nosal", {})}
    S_no = apply_stack(df, engine_col, "fd", season, week, nosal_art)
    block = pd.Series(np.where(S_no.notna(), "nosal", ""), index=df.index, dtype=object)
    S = S_no.copy()
    if dk_salary is not None and artifact.get("positions"):
        d2 = df.copy()
        d2["salary"] = pd.to_numeric(dk_salary, errors="coerce")
        has = d2["salary"].notna() & (d2["salary"] > 0)
        if has.any():
            S_dk = apply_stack(d2.loc[has], engine_col, "fd", season, week,
                               {"usage_fill": artifact.get("usage_fill", {}), "positions": artifact["positions"]})
            ok = S_dk.notna()
            S.loc[S_dk.index[ok]] = S_dk[ok]
            block.loc[S_dk.index[ok]] = "dksal"
    return S, block
