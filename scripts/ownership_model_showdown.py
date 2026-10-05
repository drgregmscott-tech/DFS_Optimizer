"""
ownership_model_showdown.py
============================

Showdown (Captain Mode) counterpart to ownership_model.py -- DK only.

WHY: on the two real DK showdown slates logged so far (wk1 DEN@KC, wk2 IND@KC)
the heuristic under-estimated the chalk badly: wk2 Walker CPT 12% est vs 42%
real, Butker FLEX 6% vs 31%, Warren 12% vs 41%. Optimizer-implied exposure
(how often a noisy showdown ILP rosters the player, computed SEPARATELY for the
CPT row and the FLEX row) tracks the real field far better, especially at CPT
(wk2 CPT corr 0.81 -> 0.96, chalk MAE 16.3 -> 3.3, leave-one-slate-out).

MODEL (deliberately tiny: two slates of data): per role (CPT, FLEX), ridge
regression on the logit scale of real ownership with 4 standardized features:
  l_exp  logit of mean exposure over 3 noise levels (15/30/50%) of 60 lineups
  isK    kicker flag  (the optimizer over-rosters kickers vs the field)
  isD    DST flag
  isMin  FLEX-equivalent price <= $1,000 (bench-filler punts: heuristic gave 5-12%, real 0-2%)
then water-filled to the role budget (CPT 100%, FLEX 500%) with a cap
(CPT 60%, FLEX 75%). Any failure or a missing artifact returns the heuristic
unchanged. Refit: python scripts/ownership_model_showdown.py fit [--validate]

LIMITS: two slates, one game each. Coefficients are a first calibration, not a
settled truth; expect FLEX misses on narrative/cheap pass-catchers (wk1 Waddle
39% real vs ~0 exposure, wk2 Warren 41% vs 5%) that no salary/projection
feature explains.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
ARTIFACT = DATA_DIR / "ownership_model_showdown_dk.json"

NOISES = (15.0, 30.0, 50.0)
N_LINEUPS = 60
SEED = 7
CAP = {"CPT": 60.0, "FLEX": 75.0}
BUDGET = {"CPT": 100.0, "FLEX": 500.0}
FEATURES = ["l_exp", "isK", "isD", "isMin"]
MIN_PRICE_FLEX = 1000  # players at/below this FLEX price are ~never rostered (real wk1/wk2: 0-2%)
LAMBDA = 5.0
FLOOR = 0.003

# FLEX kicker field prior (WK4 postmortem item 8, 2026-10-05; analysis/wk4_postmortem/sd_item8/).
# The field rosters the top kicker of each team at a near-constant FLEX rate (FC history 2023-25, 97 kickers:
# mean 20.3%, favorite's K 23.8%, underdog's K 16.8%), while noisy-ILP exposure barely tracks it (corr .11-.14)
# and swings with 0.1-pt projection differences (Wk4: Bates 8.5% modeled vs 19.7% real). For the top-projected
# live FLEX K per team the pre-waterfill raw score is replaced by K_PRIOR_BASE + K_PRIOR_FAV * fav (fav = team
# implied total > opponent's; 0.5 if unknown). Backup kickers keep the exposure score. Held out: FLEX MAE
# improves in all 3 history seasons (LOSeason) and on the 6 real 2026 slates (3.90 -> 3.72; K MAE 7.85 -> 4.79).
# Switch: DFS_SD_K_PRIOR=0 restores the pure exposure model. Fail-safe: missing columns -> no-op.
K_PRIOR_BASE = 16.8
K_PRIOR_FAV = 7.0


def _k_prior_on() -> bool:
    import os
    return os.environ.get("DFS_SD_K_PRIOR", "1").strip().lower() not in ("0", "false", "off", "no")


def _k_prior(pool: pd.DataFrame, role: pd.Series) -> np.ndarray:
    out = np.full(len(pool), np.nan)
    if "team" not in pool.columns:
        return out
    fav = pd.Series(0.5, index=pool.index)
    if "implied_total" in pool.columns:
        it = pd.to_numeric(pool["implied_total"], errors="coerce").groupby(pool["team"]).first().dropna()
        if len(it) == 2:
            hi, lo = it.idxmax(), it.idxmin()
            if it[hi] > it[lo]:
                fav = pool["team"].map({hi: 1.0, lo: 0.0}).fillna(0.5)
    m = (pool["position"].astype(str) == "K") & (role.values == "FLEX") & (pool["final_projection"] > 0)
    top = pool[m].sort_values("final_projection", ascending=False).groupby("team").head(1).index
    pos = pool.index.get_indexer(top)
    out[pos] = K_PRIOR_BASE + K_PRIOR_FAV * fav.loc[top].to_numpy(float)
    return out


def _logit(p, cap):
    x = np.clip(np.asarray(p, float) / cap, FLOOR, 1 - FLOOR)
    return np.log(x / (1 - x))


def _inv(z, cap):
    return cap / (1 + np.exp(-np.asarray(z, float)))


def _exposure(pool: pd.DataFrame, noise: float) -> pd.Series:
    import optimizer
    rng = np.random.default_rng(SEED)
    prev, cnt = [], {}
    for _ in range(N_LINEUPS):
        opt = optimizer.randomize_showdown_projections(pool, noise, rng)
        sel = optimizer.solve_showdown_lineup(pool, "dk", previous_player_sets=prev, uniqueness=1,
                                              optimization_projection=opt,
                                              exclude_skill_vs_opp_dst=False)
        prev.append(set(sel["player_id"]))
        for k in sel[optimizer.ROW_KEY_COL]:
            cnt[k] = cnt.get(k, 0) + 1
    return pd.Series(cnt, dtype=float) / N_LINEUPS * 100.0


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Rows aligned to df.index. Needs player_id, roster_role, team, position,
    salary, final_projection (+ optional sigma)."""
    import optimizer
    pool = df.copy()
    for c in ("final_projection", "salary", "sigma"):
        pool[c] = pd.to_numeric(pool[c], errors="coerce") if c in pool.columns else 0.0
    pool["sigma"] = pool["sigma"].fillna(0.0)
    pool["final_projection"] = pool["final_projection"].fillna(0.0)
    pool["player_id"] = pool["player_id"].astype(str)
    pool[optimizer.ROW_KEY_COL] = pool["player_id"] + "::" + pool["roster_role"].astype(str)
    live = pool[pool["final_projection"] > 0].copy()
    exp = sum(_exposure(live, nz) for nz in NOISES).reindex(pool[optimizer.ROW_KEY_COL]).fillna(0.0) / len(NOISES)
    role = pool["roster_role"].map({"CPT": "CPT", "MVP": "CPT", "FLEX": "FLEX"})
    f = pd.DataFrame(index=df.index)
    f["role"] = role.values
    f["l_exp"] = [float(_logit(e, CAP[r])) for e, r in zip(exp.values, role.values)]
    f["isK"] = (pool["position"].astype(str) == "K").astype(float).values
    f["isD"] = (pool["position"].astype(str).isin(["DST", "D", "DEF"])).astype(float).values
    sal_flex = pool["salary"].to_numpy(float) / np.where(role.to_numpy() == "CPT", 1.5, 1.0)
    f["isMin"] = (sal_flex <= MIN_PRICE_FLEX).astype(float)
    f["live"] = (pool["final_projection"] > 0).values
    try:
        f["k_prior"] = _k_prior(pool, role)
    except Exception:  # noqa: BLE001 -- prior is optional; exposure model stands alone
        f["k_prior"] = np.nan
    return f


def _waterfill(r, b, cap):
    out = np.zeros(len(r))
    free = r > 0
    rem = b
    for _ in range(20):
        t = r[free].sum()
        if t <= 0 or rem <= 0:
            break
        tr = np.where(free, r / t * rem, 0.0)
        over = free & (tr > cap)
        if not over.any():
            out = np.where(free, tr, out)
            break
        out = np.where(over, cap, out)
        rem -= cap * over.sum()
        free &= ~over
    return out


def predict(feats: pd.DataFrame, artifact: dict) -> pd.Series:
    out = pd.Series(0.0, index=feats.index)
    for role in ("CPT", "FLEX"):
        m = artifact["roles"][role]
        idx = feats.index[feats["role"] == role]
        X = (feats.loc[idx, FEATURES] - pd.Series(m["mu"])) / pd.Series(m["sd"])
        z = m["intercept"] + X.to_numpy() @ np.array([m["coefs"][k] for k in FEATURES])
        raw = np.where(feats.loc[idx, "live"].to_numpy(), _inv(z, CAP[role]), 0.0)
        if role == "FLEX" and "k_prior" in feats.columns and _k_prior_on():
            kp = feats.loc[idx, "k_prior"].to_numpy(float)
            raw = np.where(np.isfinite(kp) & feats.loc[idx, "live"].to_numpy(), kp, raw)
        out.loc[idx] = _waterfill(raw, BUDGET[role], CAP[role])
    return out


def refine_showdown_ownership(df: pd.DataFrame, site: str) -> pd.DataFrame:
    """Replace estimated_ownership_pct with the fitted model (DK only); the
    heuristic is kept as estimated_ownership_pct_heuristic. Fail-safe."""
    if site != "dk" or not ARTIFACT.exists():
        return df
    try:
        art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        feats = build_features(df)
        new = predict(feats, art)
        out = df.copy()
        # Idempotent: keep the ORIGINAL heuristic if this frame was already refined.
        if "estimated_ownership_pct_heuristic" not in out.columns:
            out["estimated_ownership_pct_heuristic"] = df["estimated_ownership_pct"]
        out["estimated_ownership_pct"] = new.values
        out["sd_k_prior_applied"] = (feats["k_prior"].notna().values & _k_prior_on()
                                     if "k_prior" in feats.columns else False)
        return out
    except Exception as exc:  # noqa: BLE001 -- ownership must never break a build
        print(f"WARNING: showdown ownership model failed ({type(exc).__name__}: {exc}); "
              f"keeping the heuristic estimate.", file=sys.stderr)
        return df


# ---------------------------------------------------------------- fitting
def _training_frame() -> pd.DataFrame:
    """One row per (slate, player, role) for every regular-season DK showdown
    slate in ownership_actual_log.csv that has a final_projections file."""
    log = pd.read_csv(DATA_DIR / "ownership_actual_log.csv")
    log = log[(log.slate_format == "showdown") & (log.slate_type == "regular_season") & (log.site == "dk")]
    frames = []
    for sid in sorted(log.slate_id.unique()):
        path = REPO_ROOT / "output" / f"final_projections_dk_{sid}.csv"
        if not path.exists():
            print(f"skip {sid}: no projections file", file=sys.stderr)
            continue
        pool = pd.read_csv(path, dtype={"player_id": str})
        # If this pool was already built with the model wired in, estimated_ownership_pct
        # IS the model's own prior-fit output, not the true heuristic -- use the preserved
        # raw heuristic column instead so validate's "heuristic" baseline stays honest.
        if "estimated_ownership_pct_heuristic" in pool.columns:
            pool = pool.assign(estimated_ownership_pct=pool["estimated_ownership_pct_heuristic"])
        f = build_features(pool)
        a = log[log.slate_id == sid][["player_id", "roster_role", "actual_ownership_pct"]].copy()
        a["player_id"] = a["player_id"].astype(str)
        m = pd.concat([pool[["player_id", "roster_role", "player_name", "position",
                             "estimated_ownership_pct"]], f.drop(columns="role")], axis=1)
        m["role"] = f["role"].values
        m = m.merge(a, on=["player_id", "roster_role"], how="left")
        m["own"] = m["actual_ownership_pct"].fillna(0.02)  # export truncates at ~0.02%
        m["slate"] = sid
        frames.append(m)
    return pd.concat(frames, ignore_index=True)


def _fit_role(tr: pd.DataFrame, role: str) -> dict:
    t = tr[(tr.role == role) & tr.live]
    X = t[FEATURES]
    mu, sd = X.mean(), X.std().replace(0, 1.0)
    A = np.c_[np.ones(len(t)), ((X - mu) / sd).to_numpy()]
    P = np.eye(A.shape[1]) * LAMBDA
    P[0, 0] = 0
    w = np.linalg.solve(A.T @ A + P, A.T @ _logit(t.own, CAP[role]))
    return {"intercept": float(w[0]), "coefs": dict(zip(FEATURES, map(float, w[1:]))),
            "mu": mu.astype(float).to_dict(), "sd": sd.astype(float).to_dict()}


def _score(a, p, role):
    th = 20 if role == "FLEX" else 8
    ch = a >= th
    return dict(corr=round(float(np.corrcoef(a, p)[0, 1]), 2), mae=round(float(np.abs(a - p).mean()), 2),
                chalk_n=int(ch.sum()), chalk_bias=round(float((p - a)[ch].mean()), 1),
                chalk_mae=round(float(np.abs(p - a)[ch].mean()), 1))


def fit(validate: bool):
    df = _training_frame()
    slates = df.slate.unique().tolist()
    if validate:
        for te in slates:
            tr = df[df.slate != te]
            held = df[df.slate == te]
            art = {"roles": {r: _fit_role(tr, r) for r in ("CPT", "FLEX")}}
            pred = predict(held, art)
            for role in ("CPT", "FLEX"):
                ts = held[(held.role == role) & held.live].copy()
                ts["pred"] = pred.loc[ts.index]
                print(role, te, "heuristic", _score(ts.own.values, ts.estimated_ownership_pct.values, role))
                print(role, te, "model    ", _score(ts.own.values, ts.pred.values, role))
    art = {"roles": {r: _fit_role(df, r) for r in ("CPT", "FLEX")}, "features": FEATURES, "lambda": LAMBDA,
           "trained_on": slates, "cap": CAP, "budget": BUDGET, "noises": list(NOISES), "n_lineups": N_LINEUPS}
    ARTIFACT.write_text(json.dumps(art, indent=2), encoding="utf-8")
    print("wrote", ARTIFACT)
    print(json.dumps({r: art["roles"][r]["coefs"] for r in art["roles"]}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "fit":
        fit("--validate" in sys.argv)
    else:
        print(__doc__)
