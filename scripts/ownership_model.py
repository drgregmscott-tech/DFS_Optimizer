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
import os
import sys
from datetime import datetime, timezone
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
# Extra features for the variant artifact used when a public projected-ownership
# table (Fantasy Football Calculator, scripts/ingest_public_ownership.py) exists
# for the slate. ffc_own_pct is that table's projected % (top 50 only; players
# it does not list are treated as ~1%, with ffc_listed = 0).
FFC_FEATURES = ["l_ffc", "ffc_listed"]
MIN_FFC_LISTED = 25
DEFENSE_LABELS = {"DST", "D", "DEF"}

# 2026-10-04 FFC sticky-mode fix (Wk3 postmortem showdown-vs-classic session):
# ffc_used previously got re-decided fresh on every refresh purely off whether
# ffc_own_pct's matched count (ingest_public_ownership.py, run by hand, not
# part of the automated pipeline) cleared MIN_FFC_LISTED that run. The FFC
# and pure-v2 artifacts are different fitted models, not a smooth blend of
# each other, so one mid-week flip (confirmed on wk3 main's real history:
# a single False->True flip on 2026-09-24, then stable the rest of the week)
# moved several players 8-15 ownership points simultaneously with no
# projection change behind it. Once a slate has cleared the bar, this keeps
# it on FFC mode for the rest of the week even if a later run's match count
# dips (e.g. a slow scrape), rather than flipping back to a different model.
# A run with ZERO matched players (the table truly absent that run) still
# falls back for that run only -- never force a blend with no data behind
# it. State lives in a small per-slate JSON file, same pattern as
# data/x_injury_feed_state.json. Any failure here is a no-op (falls back to
# the un-stickied decision for that run); switch off with DFS_OWN_FFC_STICKY=0.
FFC_STATE_PATH = DATA_DIR / "ownership_ffc_mode_state.json"


def ffc_sticky_enabled() -> bool:
    return os.environ.get("DFS_OWN_FFC_STICKY", "1").strip().lower() not in ("0", "false", "off", "no")


def _ffc_state_key(site: str, slate_id: str) -> str:
    return f"{site}:{slate_id}"


def _load_ffc_state() -> dict:
    try:
        with open(FFC_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 -- missing/corrupt state = nothing locked yet
        return {}


def _is_ffc_locked(site: str, slate_id: str) -> bool:
    try:
        return bool(_load_ffc_state().get(_ffc_state_key(site, slate_id), {}).get("locked"))
    except Exception:  # noqa: BLE001
        return False


def _mark_ffc_locked(site: str, slate_id: str, matched: int) -> None:
    try:
        key = _ffc_state_key(site, slate_id)
        state = _load_ffc_state()
        if state.get(key, {}).get("locked"):
            return
        state[key] = {
            "locked": True,
            "matched_at_lock": int(matched),
            "locked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        FFC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FFC_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, sort_keys=True)
    except Exception:  # noqa: BLE001 -- state bookkeeping must never break a build
        pass


def artifact_path(site: str, variant: str = "") -> Path:
    return DATA_DIR / f"ownership_model_{site}{variant}.json"


def load_artifact(site: str, variant: str = ""):
    path = artifact_path(site, variant)
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
    ffc = pd.to_numeric(df["ffc_own_pct"], errors="coerce") if "ffc_own_pct" in df.columns         else pd.Series(np.nan, index=df.index)
    out["ffc_listed"] = ffc.notna().astype(float)
    out["l_ffc"] = _logit(ffc.fillna(1.0))
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


# Ownership v2 switch (2026-09-29, scripts/ownership_v2.py). Default ON.
# Off: set env DFS_OWNERSHIP_V2=0 (or this constant to False) -- the previous
# layered path then runs exactly as before, with no extra columns.
OWNERSHIP_V2_ENABLED = True


def ownership_v2_enabled() -> bool:
    env = os.environ.get("DFS_OWNERSHIP_V2")
    if env is not None:
        return env.strip().lower() not in ("0", "false", "off", "no")
    return OWNERSHIP_V2_ENABLED


def _loud(msg):
    """Loud fallback warning (stderr + GitHub ::warning:: annotation); off: DFS_LOUD_FALLBACKS=0."""
    try:
        import ownership_v2
        ownership_v2.loud_warn(msg)
    except Exception:  # noqa: BLE001
        print(f"WARNING: {msg}", file=sys.stderr)


def refine_ownership(scored: pd.DataFrame, site: str, budgets: dict,
                     season: int = None, week: int = None, slate_id: str = None) -> pd.DataFrame:
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
    ffc_used = False
    matched = pd.to_numeric(scored["ffc_own_pct"], errors="coerce").notna().sum() \
        if "ffc_own_pct" in scored.columns else 0
    ffc_eligible = matched >= MIN_FFC_LISTED
    sticky = ffc_sticky_enabled() and slate_id
    if ffc_eligible:
        if sticky:
            _mark_ffc_locked(site, slate_id, matched)
    elif sticky and matched > 0 and _is_ffc_locked(site, slate_id):
        # Thin this run but not empty, and this slate already cleared the
        # bar earlier in the week -- stay on FFC mode rather than flipping
        # back to pure v2 over what's likely just a slow/partial scrape.
        ffc_eligible = True
        print(f"Ownership: FFC table thin this run ({matched} matched, need {MIN_FFC_LISTED}) "
              f"but {slate_id} locked into FFC mode earlier this week -- keeping it.")
    if ffc_eligible:
        ffc_artifact = load_artifact(site, "_ffc")
        if ffc_artifact is not None:
            artifact = ffc_artifact
            ffc_used = True
            print("Ownership: using public-ownership (FFC) variant of the layered model.")
    try:
        heuristic = scored["estimated_ownership_pct"].copy()
        exposure = optimizer_exposure(scored, site)
        feats = build_features(scored, exposure)
        new = predict(scored, feats, artifact, budgets)
        out = scored.copy()
        out["estimated_ownership_pct_heuristic"] = heuristic
        out["estimated_ownership_pct"] = new
    except Exception as exc:  # noqa: BLE001 -- ownership must never break a build
        print(f"WARNING: layered ownership model failed ({type(exc).__name__}: {exc}); "
              f"keeping the heuristic estimate.", file=sys.stderr)
        return scored
    if not ownership_v2_enabled():
        return out
    if week is None:
        _loud("ownership v2 needs the slate week (not passed); keeping the previous layered model.")
        return out
    try:
        import ownership_v2
        final, v2_only = ownership_v2.refine_v2(scored, feats, new, ffc_used, site, season, week)
        out["est_own_live_old"] = new
        out["est_own_v2_only"] = v2_only.fillna(new).round(4)
        out["estimated_ownership_pct"] = final.fillna(new)
        for col, arr in getattr(ownership_v2, "LAST_AUDIT", {}).items():
            if len(arr) == len(out):
                out[col] = np.round(np.asarray(arr, float), 4)
        print(f"Ownership v2: ON ({'log-blend with live FFC model, a=' + str(ownership_v2.FFC_BLEND_ALPHA) if ffc_used else 'no FFC table -> v2 alone'}; "
              f"DST = v2 DST model). Previous model kept as est_own_live_old. "
              f"Switch off with DFS_OWNERSHIP_V2=0.")
        return out
    except Exception as exc:  # noqa: BLE001 -- ownership must never break a build
        _loud(f"ownership v2 failed ({type(exc).__name__}: {exc}); keeping the previous layered model.")
        return out
