"""
ownership_model.py
===================

Week 2 (2026) post-mortem -- layered ownership model, DK classic only.

WHY THIS EXISTS
---------------
ownership_heuristic.py scores players on value-per-dollar percentiles and a
U-shaped salary tier. It never asks "what would our own projections push
people toward", so it contradicted the optimizer built on the same
projections: on the real wk2 main slate the heuristic gave Bijan Robinson 4%
ownership while the optimizer put him in 67-93% of lineups, and the field
actually had him at 43% (Jeanty 5% vs 45%, Achane wk1 5% vs 58%). Measured
on two weeks of real DK contest ownership (data/ownership_actual_log.csv),
trained on one week and tested on the other, both directions:

    heuristic alone                       corr 0.71 / 0.68   chalk bias -13.6 / -14.8
    + optimizer-implied exposure          corr 0.79 / 0.74   chalk bias  -8.9 /  -6.9
    + salary + reliability layer (this)   corr 0.83 / 0.79   chalk bias  -5.9 /  -8.2

WHAT IT DOES
------------
For every player with a positive projection it builds these features, fits a
logistic-scale linear model to real ownership (fit_ownership_model.py), and
renormalizes to the same per-position roster-slot budgets the heuristic uses
(so the total stays 900% for a classic slate):

  l_est      logit of the heuristic's estimated_ownership_pct
  l_exp      logit of the player's exposure across EXPOSURE_LINEUPS optimizer
             lineups built with EXPOSURE_RANDOMIZATION_PCT noise on the
             projections (a proxy for "the part of the field that
             optimizes off consensus-style projections"); 25% noise matched
             real ownership better than 10% because the real field is far
             from a single tight optimizer
  sal        salary in $K
  top1sal    1 if the player has the highest salary at his position on the slate
  cv         sigma / projection (projection uncertainty)
  dart       1 for RB/WR/TE priced <= $4,500 (the field owns darts less than an
             optimizer would)
  lo_proj    1 for RB/WR projected < 8

WHAT IT DOES NOT DO
-------------------
- Contest type (cash vs SE vs MME) is not modeled; the field differs slightly
  by contest, the target was avoiding 4%-vs-40% misses, not that.
- FanDuel and Showdown are untouched (no real ownership data to fit; FD
  contests do not publish results). They keep the heuristic.
- Only two weeks of data behind the coefficients. The fit uses a small ridge
  penalty and a handful of features on purpose; refit each week with
  `python scripts/fit_ownership_model.py` as data accumulates.

Any failure here falls back to the heuristic's numbers with a printed
warning -- ownership must never take down a projection build.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

EXPOSURE_LINEUPS = 60
EXPOSURE_RANDOMIZATION_PCT = 25.0
EXPOSURE_SEED = 7

# Logistic scale ceiling: no player is predicted above this share of lineups.
# Real max in wk1-2 was 67.5%.
OWNERSHIP_CAP_PCT = 75.0
LOGIT_FLOOR = 0.003

FEATURES = ["l_est", "l_exp", "sal", "top1sal", "cv", "dart", "lo_proj", "pub_val"]
DEFENSE_LABELS = {"DST", "D", "DEF"}


def artifact_path(site: str) -> Path:
    return DATA_DIR / f"ownership_model_{site}.json"


def load_artifact(site: str):
    path = artifact_path(site)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _logit(pct, cap=OWNERSHIP_CAP_PCT):
    x = np.clip(np.asarray(pct, dtype=float) / cap, LOGIT_FLOOR, 1.0 - LOGIT_FLOOR)
    return np.log(x / (1.0 - x))


def _inv_logit(z, cap=OWNERSHIP_CAP_PCT):
    return cap / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def optimizer_exposure(df: pd.DataFrame, site: str, n_lineups: int = EXPOSURE_LINEUPS,
                       randomization_pct: float = EXPOSURE_RANDOMIZATION_PCT,
                       seed: int = EXPOSURE_SEED) -> pd.Series:
    """% of `n_lineups` unstacked, uniqueness-1 optimizer lineups each
    player appears in, using the project's own solve_lineup(). Index =
    player_id. Players with no positive projection are absent (exposure 0)."""
    import optimizer
    from ingest_salaries import SITE_CONFIGS

    cfg = SITE_CONFIGS[site]
    fixed_counts, flex_count = optimizer.parse_roster_requirements(cfg["roster_slots"])
    players = df.copy()
    # Inside a projection build these columns can arrive as object dtype
    # (skill/DST/kicker frames concatenated); the optimizer needs floats.
    for col in ("final_projection", "salary", "sigma"):
        if col in players.columns:
            players[col] = pd.to_numeric(players[col], errors="coerce")
    if "sigma" not in players.columns:
        players["sigma"] = 0.0
    players["sigma"] = players["sigma"].fillna(0.0)
    players["final_projection"] = players["final_projection"].fillna(0.0)
    players = players[players["final_projection"] > 0].copy()
    rng = np.random.default_rng(seed)
    counts = {}
    previous = []
    made = 0
    for _ in range(n_lineups):
        opt = optimizer.randomize_projections(players, randomization_pct, rng)
        sel = optimizer.solve_lineup(
            players, cfg["salary_cap"], fixed_counts, flex_count,
            previous_lineups=previous, uniqueness=1, optimization_projection=opt,
            stack_mode="none")
        ids = set(sel["player_id"])
        previous.append(ids)
        for pid in ids:
            counts[pid] = counts.get(pid, 0) + 1
        made += 1
    if made == 0:
        raise RuntimeError("no lineups generated")
    return pd.Series(counts, dtype=float) / made * 100.0


def build_features(df: pd.DataFrame, exposure: pd.Series) -> pd.DataFrame:
    """Feature frame aligned to df.index. Requires final_projection, salary,
    position, sigma and the heuristic's estimated_ownership_pct."""
    out = pd.DataFrame(index=df.index)
    est = pd.to_numeric(df["estimated_ownership_pct"], errors="coerce").fillna(0.0)
    exp = df["player_id"].map(exposure).fillna(0.0)
    proj = pd.to_numeric(df["final_projection"], errors="coerce").fillna(0.0)
    sal = pd.to_numeric(df["salary"], errors="coerce").fillna(0.0)
    sigma = pd.to_numeric(df["sigma"], errors="coerce").fillna(0.0) if "sigma" in df.columns \
        else pd.Series(0.0, index=df.index)
    pos = df["position"].astype(str)
    out["l_est"] = _logit(est)
    out["l_exp"] = _logit(exp)
    out["sal"] = sal / 1000.0
    rank = sal.where(proj > 0).groupby(pos).rank(ascending=False, method="min")
    out["top1sal"] = (rank <= 1).astype(float)
    out["cv"] = (sigma / proj.clip(lower=0.5)).clip(upper=5.0)
    out["dart"] = ((sal <= 4500) & pos.isin(["RB", "WR", "TE"])).astype(float)
    out["lo_proj"] = ((proj < 8) & pos.isin(["RB", "WR"])).astype(float)
    # pub_val: DK's own displayed AvgPointsPerGame per $K -- the value the field
    # sees in the lobby (2026-09-23 ownership review: only pre-lock signal that
    # explained the residual in BOTH weeks; corr 0.16/0.28 with model error).
    # Missing/zero (no DK average, e.g. rookies/FD/old files) -> 0.
    avg = (pd.to_numeric(df["dk_avg_ppg"], errors="coerce") if "dk_avg_ppg" in df.columns
           else pd.Series(np.nan, index=df.index))
    out["pub_val"] = (avg / (sal / 1000.0).clip(lower=1.0)).fillna(0.0).clip(upper=15.0)
    return out


def predict(df: pd.DataFrame, features: pd.DataFrame, artifact: dict, budgets: dict,
            group_col: str = "position_group") -> pd.Series:
    """Model prediction, renormalized within each position group to `budgets`
    (same roster-slot budgets the heuristic uses). Zero-projection players get 0."""
    coefs = artifact["coefs"]
    z = np.full(len(df), float(coefs["intercept"]))
    for name in artifact.get("features", FEATURES):
        z = z + float(coefs[name]) * features[name].to_numpy(float)
    raw = pd.Series(_inv_logit(z, artifact.get("cap", OWNERSHIP_CAP_PCT)), index=df.index)
    raw = raw.where(pd.to_numeric(df["final_projection"], errors="coerce").fillna(0.0) > 0, 0.0)
    cap = float(artifact.get("cap", OWNERSHIP_CAP_PCT))
    budget = df[group_col].map(budgets)
    # Renormalize to the position budget WITH the cap enforced: on a small
    # slate the budget is large relative to the pool, and a plain rescale
    # pushed a handful of players to 96-100% (real max wk1-2: 67.5%). Water-
    # fill instead: anything that would exceed the cap is held at the cap and
    # the remainder is redistributed pro rata over the uncapped players.
    scaled = pd.Series(0.0, index=df.index)
    for _, idx in df.groupby(group_col).groups.items():
        r = raw.loc[idx].to_numpy(float)
        b = float(budget.loc[idx].iloc[0]) if not pd.isna(budget.loc[idx].iloc[0]) else 0.0
        out = np.zeros(len(r))
        free = r > 0
        remaining = b
        for _ in range(10):
            tot = r[free].sum()
            if tot <= 0 or remaining <= 0:
                break
            trial = np.where(free, r / tot * remaining, 0.0)
            over = free & (trial > cap)
            if not over.any():
                out = np.where(free, trial, out)
                break
            out = np.where(over, cap, out)
            remaining -= cap * over.sum()
            free = free & ~over
        scaled.loc[idx] = out
    return scaled.clip(lower=0.0, upper=cap)


def refine_ownership(scored: pd.DataFrame, site: str, budgets: dict) -> pd.DataFrame:
    """Called from build_projections.add_ownership_columns() after the
    heuristic has produced chalk_score / estimated_ownership_pct on `scored`
    (columns: player_id, position, position_group, salary, final_projection,
    sigma, ...). Returns `scored` with estimated_ownership_pct replaced by
    the layered model and the heuristic kept as estimated_ownership_pct_heuristic.
    DK classic only; anything else, a missing artifact, or any error returns
    the heuristic unchanged."""
    artifact = load_artifact(site)
    if artifact is None or site != "dk":
        return scored
    try:
        heuristic = scored["estimated_ownership_pct"].copy()
        exposure = optimizer_exposure(scored, site)
        feats = build_features(scored, exposure)
        new = predict(scored, feats, artifact, budgets)
        out = scored.copy()
        out["estimated_ownership_pct_heuristic"] = heuristic
        out["estimated_ownership_pct"] = new
        return out
    except Exception as exc:  # noqa: BLE001 -- ownership must never break a build
        print(f"WARNING: layered ownership model failed ({type(exc).__name__}: {exc}); "
              f"keeping the heuristic estimate.", file=sys.stderr)
        return scored
