"""
kicker_model.py
=================

Session 13.1 -- the kicker projection engine. Consumes `data/kicker_model.json`
(written by `fit_kicker_model.py`) and produces a per-kicker mean AND sigma
by Monte Carlo simulation. Deliberately separate from the fitter, same split
as dst_model.py / fit_dst_model.py.

See fit_kicker_model.py's module docstring for the full set of numbered
decisions this consumes (volume has no team/Vegas signal -> league-average
rates; player accuracy is real but nearly irrelevant to total points ->
shrunk accuracy shipped for correctness, not for backtest improvement;
sigma needs no DST-style latent correlation factor -> independent draws
measured well-calibrated on their own).

Usage (mirrors dst_model.py's calling convention):

    from kicker_model import load_model, project_kickers
    model = load_model()
    projections = project_kickers(kicker_pool, model, site="dk")

`kicker_pool` needs one row per kicker in the current slate's player pool:
player_id, team (at minimum). Player-specific career accuracy is looked up
from the model artifact by player_id; a kicker with no career row (rookie,
first pipeline-tracked appearance) gets pure league-average accuracy
(decision #6 in the fitter).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scoring_rules  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MODEL_PATH = DATA_DIR / "kicker_model.json"

SUPPORTED_SCHEMA = 1
DEFAULT_SIMS = 20000
DEFAULT_SEED = 20131  # 20-1-3-1, follows dst_model.py's DEFAULT_SEED=20104 (20-1-0-4) naming convention


def load_model(path: Path = MODEL_PATH) -> dict:
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Fit it first:\n"
            f"  python3 scripts/fit_kicker_model.py\n"
            f"(Session 13.1. Not shipped pre-fitted, same reasoning as "
            f"dst_model.py's load_model().)"
        )
    model = json.loads(path.read_text())
    version = model.get("schema_version")
    if version != SUPPORTED_SCHEMA:
        raise SystemExit(
            f"{path.name} has schema_version {version}, this code supports "
            f"{SUPPORTED_SCHEMA}. Refit with the current fit_kicker_model.py "
            f"rather than reading a stale artifact."
        )
    return model


def _shrunk_accuracy(model: dict, player_id: str) -> dict:
    """Decision #4/#6 (fit_kicker_model.py). Returns {bucket: shrunk_rate}
    for one player, falling back to pure league-average when the player has
    no career row (rookie / not seen in the fit window)."""
    k = model["shrink_k"]
    league = model["league_make_rate"]
    career = model.get("_career_by_id")
    if career is None:
        # index once, cached on the model dict for repeated lookups
        career = {row["player_id"]: row for row in model["career_accuracy"]}
        model["_career_by_id"] = career

    row = career.get(player_id)
    if row is None:
        return dict(league)

    out = {}
    for bucket in ("0_39", "40_49", "50p"):
        made = row[f"made_{bucket}"]
        att = row[f"att_{bucket}"]
        out[bucket] = (made + league[bucket] * k) / (att + k)
    return out


def project_kickers(pool: pd.DataFrame, model: dict, site: str = "dk",
                     n_sims: int = DEFAULT_SIMS, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    """One row per kicker in `pool` -> final_projection, sigma, p10, p90.

    `pool` needs: player_id, team (used only for output pass-through --
    volume/accuracy do not condition on team, decision #2/#7).
    """
    rng = np.random.default_rng(seed)
    mu_fga = model["mu_fga"]
    mu_pat = model["mu_pat"]
    shares = model["distance_shares"]
    pat_mr = model["league_pat_make_rate"]

    n = len(pool)
    out = {
        "player_id": pool["player_id"].to_numpy(),
        "team": pool["team"].to_numpy() if "team" in pool.columns else np.full(n, None),
        "final_projection": np.zeros(n),
        "sigma": np.zeros(n),
        "p10": np.zeros(n),
        "p90": np.zeros(n),
        "proj_fg_0_39": np.zeros(n),
        "proj_fg_40_49": np.zeros(n),
        "proj_fg_50p": np.zeros(n),
        "proj_pat": np.zeros(n),
    }

    for i, row in enumerate(pool.itertuples(index=False)):
        pid = getattr(row, "player_id")
        acc = _shrunk_accuracy(model, pid)

        # Decision #5 (fit_kicker_model.py): independent Poisson-thinned
        # attempt draws per bucket (valid decomposition of a single Poisson
        # total, see dst_model.py's simulate() for the analogous pattern),
        # independent Binomial makes at the SHRUNK per-player rate,
        # independent Poisson PAT draw. No latent correlation factor --
        # measured unnecessary (fitter decision #5).
        att_39 = rng.poisson(mu_fga * shares["att_0_39"], n_sims)
        att_49 = rng.poisson(mu_fga * shares["att_40_49"], n_sims)
        att_50 = rng.poisson(mu_fga * shares["att_50p"], n_sims)
        made_39 = rng.binomial(att_39, acc["0_39"])
        made_49 = rng.binomial(att_49, acc["40_49"])
        made_50 = rng.binomial(att_50, acc["50p"])
        pat_att = rng.poisson(mu_pat, n_sims)
        pat_made = rng.binomial(pat_att, pat_mr)

        comp = {
            "made_0_39": made_39, "made_40_49": made_49,
            "made_50p": made_50, "pat_made": pat_made,
        }
        pts = scoring_rules.score_kicker(comp, site)

        out["final_projection"][i] = pts.mean()
        out["sigma"][i] = pts.std(ddof=1)
        out["p10"][i], out["p90"][i] = np.percentile(pts, [10, 90])
        out["proj_fg_0_39"][i] = made_39.mean()
        out["proj_fg_40_49"][i] = made_49.mean()
        out["proj_fg_50p"][i] = made_50.mean()
        out["proj_pat"][i] = pat_made.mean()

    return pd.DataFrame(out)


if __name__ == "__main__":
    # Smoke test -- a tiny synthetic pool, no career history (pure
    # league-average path), just to confirm the module runs end to end.
    model = load_model()
    demo_pool = pd.DataFrame({"player_id": ["demo_k_1", "demo_k_2"], "team": ["AAA", "BBB"]})
    for site in ("dk", "fd"):
        res = project_kickers(demo_pool, model, site=site, n_sims=5000)
        print(f"--- {site} ---")
        print(res[["player_id", "final_projection", "sigma", "p10", "p90"]])
