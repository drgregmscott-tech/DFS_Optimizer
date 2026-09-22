"""
replay_validation.py -- 3-arm replay test for the classic cash-line diagnostic
(WK2_POSTMORTEM.md, 2026-09-22). Long-flagged TODO (ROADMAP.md's Post-Week-2
Improvement Track item 3), finally committed as a real script.

Tests, on each of the 6 real classic SE3max slates played so far, whether the
diagnostic's settings recommendation (stack=2, bring-back, TE-in-FLEX, an
ownership floor) actually improves the REAL outcome, separated into arms so a
win can be attributed to a specific lever rather than a tangle of several:

  Arm 1 (as-is)        -- the lineup actually submitted (gmscott81). Known
                          already; included here for a single side-by-side
                          table, not recomputed.
  Arm 2 (idealized)     -- new settings, ownership floor set against REAL
                          post-lock ownership swapped into the pool before
                          solving. Tests "does chasing chalk help, given
                          perfect ownership knowledge" -- isolates the
                          MECHANISM from our ownership model's own accuracy.
  Arm 2b (realistic)    -- same settings and floor VALUE, but solved against
                          the pool's actual pre-lock estimated_ownership_pct
                          (our model's real output, imperfect). The gap
                          between Arm 2 and Arm 2b is a direct, quantified
                          answer to "how much does our ownership model's
                          inaccuracy cost us."
  Arm 3 (candidate pool + scenario scoring) -- NOT run by this script; use
                          analysis/classic_diag/best_lineup_classic.py
                          separately (materially slower: candidate generation
                          + Monte Carlo scoring per slate). Arm 3's own
                          candidate-generation selection must stay blind to
                          real results (only pre-game info), graded after the
                          fact the same way Arms 1/2/2b are graded here.

CAVEAT: this replay uses each slate's CURRENT `output/final_projections_*.csv`
as a stand-in for "as it stood near lock" -- classic wk1/wk2 slates are long
past lock and the automated refresh loop skips locked slates, so this should
be close, but it has not been cross-checked against a git-history snapshot
from the actual lock time. Flagged, not fixed, in this version.

usage: python scripts/replay_validation.py
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import optimizer

D = "C:/Users/gmsco/Downloads/"
SLATES = {
    "wk1_main": (D + "dk_classic_wk1_main_final_results_13Sep2026.csv", "dk_classic_wk1_main_13Sep2026"),
    "wk1_early": (D + "dk_classic_wk1_early_final_results_13Sep2026.csv", "dk_classic_wk1_early_13Sep2026"),
    "wk1_afternoon": (D + "dk_classic_wk1_afternoon_final_results_13Sep2026.csv", "dk_classic_wk1_afternoon_13Sep2026"),
    "wk2_main": (D + "results_se3max_dk_classic_wk2_main_20Sep2026.csv", "dk_classic_wk2_main_20Sep2026"),
    "wk2_early": (D + "results_se3max_dk_classic_wk2_early_20Sep2026.csv", "dk_classic_wk2_early_20Sep2026"),
    "wk2_afternoon": (D + "results_se3max_dk_classic_wk2_afternoon_20Sep2026.csv", "dk_classic_wk2_afternoon_20Sep2026"),
}
CASH_PCT = 0.25
TOK = re.compile(r"\b(QB|RB|WR|TE|FLEX|DST)\s+")


def parse(s):
    p = TOK.split(" " + s.strip())
    return [(p[i], p[i + 1].strip()) for i in range(1, len(p) - 1, 2)]


def norm(s):
    s = str(s).lower()
    s = re.sub(r"[.'\u2019]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(s.split())


def load_real(f):
    df = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    tab = df[["Player", "Roster Position", "%Drafted", "FPTS"]].dropna(subset=["Player"]).copy()
    tab["k"] = tab.Player.map(norm)
    tab["own"] = tab["%Drafted"].astype(str).str.rstrip("%").astype(float)
    tab = tab.drop_duplicates("k")
    fpts_map = tab.set_index("k")["FPTS"].to_dict()
    own_map = tab.set_index("k")["own"].to_dict()
    e = df.iloc[:, :6].dropna(subset=["Lineup"]).copy()
    real_points = e.Points.dropna().to_numpy(float)
    mine = e[e.EntryName.astype(str).str.contains("gmscott81", na=False)]
    mine_row = None
    if len(mine):
        r = mine.iloc[0]
        N = len(e)
        L = [(slot, norm(nm)) for slot, nm in parse(r.Lineup)]
        pts = sum(fpts_map.get(k, 0.0) for _, k in L)
        rank = int(r.Rank)
        mine_row = dict(pts=pts, rank=rank, pct=1 - (rank - 1) / N, cash=(1 - (rank - 1) / N) >= (1 - CASH_PCT))
    return fpts_map, own_map, real_points, mine_row


def grade(player_ks, fpts_map, real_points):
    N = len(real_points)
    pts = sum(fpts_map.get(k, 0.0) for k in player_ks)
    rank = int((real_points > pts).sum()) + 1  # count of real entries that beat this score, +1
    pct = 1 - (rank - 1) / N
    return dict(pts=pts, rank=rank, pct=pct, cash=pct >= (1 - CASH_PCT))


def solve_arm(pool, min_total_ownership):
    """Mirrors build_single_lineup's own stack-team auto-selection (Session
    3.3): resolve_stack_candidates() picks the best available team to pin
    for stack_mode='qb', since solve_lineup itself requires an explicit
    target_team and won't pick one on its own."""
    fixed_counts, flex_count = optimizer.parse_roster_requirements(optimizer.SITE_CONFIGS["dk"]["roster_slots"])
    stack_positions = {"WR", "TE"}
    candidates, _, _ = optimizer.resolve_stack_candidates(
        pool, "qb", stack_positions, None, None, None,
        optimizer.DEFAULT_STACK_CANDIDATE_POOL, diversify_requested="off", bring_back=True,
    )
    target_team = candidates[0]["target_team"]
    sel = optimizer.solve_lineup(
        pool, optimizer.SITE_CONFIGS["dk"]["salary_cap"], fixed_counts, flex_count,
        stack_mode="qb", stack_size=2, stack_positions=stack_positions, bring_back=True,
        target_team=target_team,
        flex_positions={"RB", "WR", "TE"}, min_total_ownership=min_total_ownership,
    )
    return sel


# Found 2026-09-22: an unconstrained (stack+bring-back, no floor) solve
# already lands at the ~94th percentile of the pool's own achievable
# ownership-sum distribution -- our own model already prefers high-
# ownership players just by maximizing points, so a floor at or below
# that level is non-binding and silently does nothing (this is what
# happened with the first 60th-percentile floor: Arm 2 and Arm 2b came
# out byte-identical). A floor has to sit ABOVE the natural optimum to
# test anything real. Per-slate 90th-percentile floors, real vs. our own
# model's distribution (both computed the same way as the 60th-percentile
# ones this replaced):
FLOOR_REAL_P90 = {
    "wk1_main": 158.5, "wk1_early": 167.5, "wk1_afternoon": 322.7,
    "wk2_main": 146.9, "wk2_early": 201.8, "wk2_afternoon": 237.8,
}
FLOOR_EST_P90 = {
    "wk1_main": 95.1, "wk1_early": 142.7, "wk1_afternoon": 240.4,
    "wk2_main": 69.2, "wk2_early": 109.3, "wk2_afternoon": 158.5,
}


def main():
    rows = []
    for lab, (f, sid) in SLATES.items():
        fpts_map, real_own_map, real_points, mine = load_real(f)
        pool = optimizer.load_final_projections("dk", sid)
        pool = pool[pool.position.isin(["QB", "RB", "WR", "TE", "DST"])].copy()
        pool["k"] = pool.player_name.map(norm)

        result = dict(slate=lab)
        if mine:
            result.update({f"arm1_{k}": v for k, v in mine.items()})
        else:
            print(f"{lab}: no gmscott81 entry found for Arm 1", file=sys.stderr)

        # Arm B: structural settings ONLY (stack=2, bring-back, TE-flex),
        # no ownership floor at all -- isolates the structural effect from
        # any ownership-chasing, since (unlike the floor) these settings
        # are NOT already something pure point-maximization does on its
        # own (DEFAULT_STACK_MODE is "none" -- no stacking happens unless
        # explicitly requested).
        try:
            selB = solve_arm(pool, 0.0)
            gB = grade(selB.player_name.map(norm), fpts_map, real_points)
            result.update({f"armB_{k}": v for k, v in gB.items()})
        except Exception as exc:
            print(f"{lab}: Arm B failed ({type(exc).__name__}: {exc})", file=sys.stderr)

        # Arm C-real: structural settings + a GENUINELY binding ownership
        # floor (90th percentile), idealized with real post-lock ownership
        # swapped in -- tests "does pushing ownership past what a good
        # projection already implies help, given perfect knowledge."
        pool2 = pool.copy()
        pool2["estimated_ownership_pct"] = pool2["k"].map(real_own_map).fillna(0.0)
        try:
            selCr = solve_arm(pool2, FLOOR_REAL_P90[lab])
            gCr = grade(selCr.player_name.map(norm), fpts_map, real_points)
            result.update({f"armCreal_{k}": v for k, v in gCr.items()})
        except Exception as exc:
            print(f"{lab}: Arm C-real failed ({type(exc).__name__}: {exc})", file=sys.stderr)

        # Arm C-est: same binding floor, but on our OWN model's ownership
        # scale and using our own (imperfect) estimate to solve -- the
        # realistic version of the same test.
        try:
            selCe = solve_arm(pool, FLOOR_EST_P90[lab])
            gCe = grade(selCe.player_name.map(norm), fpts_map, real_points)
            result.update({f"armCest_{k}": v for k, v in gCe.items()})
        except Exception as exc:
            print(f"{lab}: Arm C-est failed ({type(exc).__name__}: {exc})", file=sys.stderr)

        rows.append(result)

    out = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    cols = ["slate"] + [c for c in out.columns if c != "slate"]
    print(out[cols].to_string(index=False))
    print(f"\nCash count -- Arm1 (as-is): {out.get('arm1_cash', pd.Series(dtype=bool)).sum()}/6, "
          f"Arm B (structure only, no floor): {out.get('armB_cash', pd.Series(dtype=bool)).sum()}/6, "
          f"Arm C-real (structure + binding real-ownership floor): {out.get('armCreal_cash', pd.Series(dtype=bool)).sum()}/6, "
          f"Arm C-est (structure + binding own-model floor): {out.get('armCest_cash', pd.Series(dtype=bool)).sum()}/6")
    out.to_csv("analysis/classic_diag/replay_arms.csv", index=False)


if __name__ == "__main__":
    main()
