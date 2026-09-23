"""replay_showdown.py -- real-data validation for best_single.score()'s selection
rule, mirroring analysis/classic_diag/replay_selection_criteria.py's rigor for
Showdown (2026-09-23, in response to recommend_lineup.py crashing on Showdown --
see that script's docstring).

Classic's replay uses full real contest-results exports (every real entry's
lineup + score) to build the TRUE real field. No equivalent export exists for
these 2 real Showdown slates -- only per-player aggregates are logged
(data/ownership_actual_log.csv: real post-lock ownership by player_id/roster_role;
data/projection_error_log.csv: real actual_fpts by player_id). So the "real field"
here is a PROXY: showdown_field.simulate_field() draws plausible rosters from REAL
ownership (not the model's estimate), then each drawn roster is scored with REAL
actual_fpts (not simulated points) -- same idea as classic's real field, built from
the best real signal actually available rather than the full export this project
doesn't have for Showdown.

Two slates only (dk_showdown_wk1_Den_KC_14Sep2026, dk_showdown_wk2_NYG_LAR_21Sep2026)
have BOTH real ownership AND real logged results -- a real, but much smaller, sample
than classic's 6-slate replay. Flagged, not hidden.

Tests each candidate-selection rule TWICE:
  *_est  -- the REALISTIC arm: score()'s own field is built from the pool's
            estimated_ownership_pct (the model's pre-lock estimate) -- exactly what
            a live run does, since real ownership doesn't exist before lock.
  *_real -- the IDEALIZED arm: score()'s own field is built from REAL post-lock
            ownership instead -- isolates "does the ranking mechanism work at all,
            given perfect ownership knowledge" from "how much does ownership-
            estimate error cost us," same separation classic's replay_validation.py
            made (Arm 2 vs Arm 2b).

usage: python analysis/showdown_own/replay_showdown.py [n_candidates] [n_forced] [field_n] [n_sims]
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import optimizer  # noqa: E402
import showdown_field as sf  # noqa: E402
import best_single as bs  # noqa: E402

N_CAND = int(sys.argv[1]) if len(sys.argv) > 1 else 150
N_FORCED = int(sys.argv[2]) if len(sys.argv) > 2 else 20
FIELD_N = int(sys.argv[3]) if len(sys.argv) > 3 else 8000
N_SIMS = int(sys.argv[4]) if len(sys.argv) > 4 else 600
TOP_PCTS = (0.90, 0.99)  # top10% / top1%, matching best_single.py's own scenario metrics

SLATES = {
    "wk1_Den_KC": "dk_showdown_wk1_Den_KC_14Sep2026",
    "wk2_NYG_LAR": "dk_showdown_wk2_NYG_LAR_21Sep2026",
}


def load_real(slate_id):
    own = pd.read_csv(R / "data" / "ownership_actual_log.csv", dtype={"player_id": str})
    own = own[own.slate_id == slate_id]
    res = pd.read_csv(R / "data" / "projection_error_log.csv", dtype={"player_id": str})
    res = res[res.slate_id == slate_id]
    # A Showdown player is logged TWICE here (once per roster_role, CPT rows
    # carrying the 1.5x-scaled final_projection/actual_fpts) -- keep the FLEX
    # (base, unscaled) row only. grade()/build_real_field() apply the 1.5x
    # captain multiplier themselves, so the map here must be the base value.
    res = res[res.roster_role != "CPT"] if "roster_role" in res.columns else res
    res = res.drop_duplicates("player_id")
    real_fpts = res.set_index("player_id")["actual_fpts"]
    real_cpt_own = own[own.roster_role == "CPT"].set_index("player_id")["actual_ownership_pct"]
    real_flex_own = own[own.roster_role == "FLEX"].set_index("player_id")["actual_ownership_pct"]
    return real_fpts, real_cpt_own, real_flex_own


def build_real_field(fl, real_fpts, real_cpt_own, real_flex_own, field_n, seed):
    """The proxy real field described in the module docstring: rosters drawn from
    REAL ownership, scored with REAL actual points."""
    cpt_own = fl.player_id.map(real_cpt_own).fillna(0.0).values
    flex_own = fl.player_id.map(real_flex_own).fillna(0.0).values
    fc, ff = sf.simulate_field(fl.salary.values, fl.team.values, cpt_own, flex_own,
                               n=field_n, seed=seed)
    pts = fl.player_id.map(real_fpts).fillna(0.0).values
    field_scores = np.sort(sf.score_lineups(fc, ff, pts))
    return field_scores


def grade(cand_rows, real_fpts):
    """cand_rows: the [ROWKEY, player_id, roster_role] frame for one candidate."""
    cpt = cand_rows[cand_rows.roster_role == "CPT"]["player_id"].iloc[0]
    flex = cand_rows[cand_rows.roster_role == "FLEX"]["player_id"].tolist()
    pts = 1.5 * real_fpts.get(cpt, 0.0) + sum(real_fpts.get(p, 0.0) for p in flex)
    return pts


def score_against_real_field(pts, field_scores):
    n = len(field_scores)
    rank = int((field_scores > pts).sum()) + 1
    pct = 1 - (rank - 1) / n
    return dict(pts=pts, pct=pct, top10=pct >= (1 - 0.10), top1=pct >= (1 - 0.01))


def rule_field(P, fl, own_source, real_cpt_own=None, real_flex_own=None, field_n=FIELD_N, seed=1):
    if own_source == "est":
        cpt_by_pid = P[P.roster_role == "CPT"].set_index("player_id")["estimated_ownership_pct"]
        cpt_own = fl.player_id.map(cpt_by_pid).fillna(0.0).values
        flex_own = pd.to_numeric(fl["estimated_ownership_pct"], errors="coerce").fillna(0.0).values
    else:
        cpt_own = fl.player_id.map(real_cpt_own).fillna(0.0).values
        flex_own = fl.player_id.map(real_flex_own).fillna(0.0).values
    return sf.simulate_field(fl.salary.values, fl.team.values, cpt_own, flex_own, n=field_n, seed=seed)


def main():
    rows = []
    for lab, sid in SLATES.items():
        t0 = time.time()
        real_fpts, real_cpt_own, real_flex_own = load_real(sid)

        P = optimizer.load_showdown_pool("dk", sid).reset_index(drop=True)
        P["sigma"] = pd.to_numeric(P.get("sigma", np.nan), errors="coerce")
        P["sigma"] = P["sigma"].fillna(P.final_projection * 0.6)
        P["participation_effective"] = pd.to_numeric(P.get("participation_effective", 1.0), errors="coerce")
        cands = bs.candidates(P, site="dk", n_noise=N_CAND, n_forced=N_FORCED, seed=5)
        fl = P[P.roster_role == "FLEX"].reset_index(drop=True)

        real_field_scores = build_real_field(fl, real_fpts, real_cpt_own, real_flex_own, FIELD_N, seed=1)
        real_pts_per_cand = np.array([grade(c, real_fpts) for c in cands])
        # final_projection is already 1.5x-priced on the CPT row (Session 14.0's
        # apply_captain_multiplier()), so a plain sum over the candidate's rows
        # is the lineup's real total projected points -- no extra weighting needed.
        raw_proj = np.array([
            P.set_index(bs.ROWKEY).loc[c[bs.ROWKEY], "final_projection"].to_numpy().sum()
            for c in cands
        ])

        for arm, own_source in (("est", "est"), ("real", "real")):
            fc, ff = rule_field(P, fl, own_source, real_cpt_own, real_flex_own, seed=1)
            res = bs.evaluate(P, cands, {"f": (fc, ff)}, n_sims=N_SIMS, seed=100)
            names = list(bs.scenarios())
            avg10 = np.mean([res[(s, "f")][0] for s in names], axis=0)
            worst10 = np.min([res[(s, "f")][0] for s in names], axis=0)
            avg1 = np.mean([res[(s, "f")][1] for s in names], axis=0)
            avgpct = np.mean([res[(s, "f")][2] for s in names], axis=0)

            picks = {
                f"avg_top10_{arm}": int(avg10.argmax()),
                f"worst_top10_{arm}": int(worst10.argmax()),
                f"avg_top1_{arm}": int(avg1.argmax()),
                f"avg_pct_{arm}": int(avgpct.argmax()),
                f"raw_proj_{arm}": int(raw_proj.argmax()),
            }
            for rule, idx in picks.items():
                g = score_against_real_field(real_pts_per_cand[idx], real_field_scores)
                rows.append(dict(slate=lab, rule=rule, n_pool=len(cands), **g))

        print(f"{lab}: done in {time.time()-t0:.0f}s ({len(cands)} candidates)")

    out = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("\n" + out.to_string(index=False))

    print("\n--- summary across both slates ---")
    for rule in sorted(out.rule.unique()):
        sub = out[out.rule == rule]
        print(f"{rule:22s}: top10={sub.top10.sum()}/{len(sub)}  top1={sub.top1.sum()}/{len(sub)}  "
              f"mean_pct={sub.pct.mean():.3f}")

    out.to_csv(R / "analysis/showdown_own/replay_showdown_results.csv", index=False)


if __name__ == "__main__":
    main()
