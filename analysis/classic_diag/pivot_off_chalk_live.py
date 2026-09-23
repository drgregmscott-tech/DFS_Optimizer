"""Tests the ONE untested substitution flagged while designing the live Week 3+
lineup system (HANDOFF_week3_lineup_system.md, 2026-09-22 follow-up
conversation): pivot_off_chalk.py's anchor and per-slot pivot-eligibility both
used REAL POST-LOCK ownership (own_map from replay_validation.load_real) --
fine for a historical replay, impossible before a real slate locks. A live
system has to build the anchor and find pivot candidates from
estimated_ownership_pct (the model's OWN pre-lock signal, already baked into
final_projections_{site}_{slate_id}.csv) instead. Greg asked directly whether
the frontend could actually reproduce today's validated numbers, and the
honest answer was "not yet -- this exact substitution has never been tested."
This script tests it, against the same 6 real logged slates, before any
frontend work starts.

Two changes vs. pivot_off_chalk.py, everything else (multi-swap enumeration,
4-scenario Monte Carlo, worst_top25 selection) BYTE-IDENTICAL:

  1. build_live_anchor() replaces anchor_mask(): was
     chalk.most_repeated_lineup(raw_csv) (the real field's actual
     most-duplicated lineup -- can't be known before lock). Now:
     optimizer.solve_lineup() with estimated_ownership_pct substituted in as
     the ILP objective (via its existing `optimization_projection` param,
     Session 3.2-addendum) in place of final_projection. This reuses the
     ALREADY-VALIDATED cap-legal ILP solver every real build already goes
     through -- not new solver logic, just a different objective column --
     and produces a cap-legal, most-owned-possible lineup: the live-usable
     equivalent of "the real field's chalk build." exclude_skill_vs_opp_dst
     stays at its real default (True), matching how a real build would run.

  2. best_alt_per_slot() compares against P["own"] (estimated_ownership_pct,
     already loaded onto P by best_lineup_classic.build_pool_and_field() --
     the same live signal classic_field.py's own field simulation already
     uses) instead of the real post-lock own_map.

Grades the result against the SAME real logged results as every other test in
this campaign, for direct comparison to pivot_off_chalk.py's real-anchor
number (4/6 cash, 0.819 mean pctile) -- the real own_map is loaded ONLY for
fpts_map/real_points/grading purposes here, never for anchor or pivot
construction.

usage: python analysis/classic_diag/pivot_off_chalk_live.py [n_sims] [field_n]
"""
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import optimizer
import replay_validation as rv
import best_lineup_classic as blc

N_SIMS = int(sys.argv[1]) if len(sys.argv) > 1 else 800
FIELD_N = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
SALARY_CAP = 50000
SWAPPABLE_POS = {"RB", "WR", "TE"}


def build_live_anchor(site, P):
    """Cap-legal, QUALITY-first lineup -- the normal points-maximizing ILP
    solve (final_projection objective, no randomization), via the SAME
    solver optimizer.py already uses for every real build.

    REVISED 2026-09-23: the first version of this function maximized
    sum(estimated_ownership_pct) subject to the cap -- a pure ownership-max
    build with NO regard for projection quality. That's a real bug, not a
    reasonable proxy for "the real field's most-duplicated lineup" (which
    is what the earlier real-ownership test's anchor actually was -- a real
    human build, already quality-filtered by construction). A pure
    ownership-max solve will happily take a bad-but-relatively-popular punt
    play over a good one, and pushes total lineup ownership well past real
    winning lineups' norm (~126% total, per DFS Army's 230k-lineup study --
    Greg flagged this directly, 2026-09-23) since it's chasing ownership
    everywhere instead of building a genuinely good lineup that incidentally
    tends to be chalky. Fixed: anchor is now the normal points-maximizing
    solve (matches "build the lineup you think can win first"). The pivot
    step (unchanged below) is still the ownership-driven differentiation
    layer ("then find 2-3 places to get away from the field")."""
    config = optimizer.SITE_CONFIGS[site]
    fixed_counts, flex_count = optimizer.parse_roster_requirements(config["roster_slots"])
    sel = optimizer.solve_lineup(P, config["salary_cap"], fixed_counts, flex_count)
    pid_to_idx = {pid: i for i, pid in enumerate(P.player_id)}
    idxs = [pid_to_idx[pid] for pid in sel["player_id"]]
    return np.array(idxs)


def best_alt_per_slot(P, mask):
    """Same shape as pivot_off_chalk.py's version, but the ownership signal
    is P['own'] (estimated_ownership_pct) -- the live-usable one -- not a
    real post-lock own_map."""
    alts = {}
    for i in mask:
        pos = P.position.iloc[i]
        if pos not in SWAPPABLE_POS:
            continue
        my_own = P["own"].iloc[i]
        pool = P[(P.position == pos) & (~P.index.isin(mask))].copy()
        pool = pool[pool["own"] < my_own].sort_values("final_projection", ascending=False)
        if len(pool):
            alts[i] = pool.index[0]
    return alts


def enumerate_pivots(P, mask, alts, max_swaps=3):
    """Byte-identical to pivot_off_chalk.py's version (including its
    2026-09-22 duplicate-incoming-player bug fix)."""
    swappable_slots = list(alts.keys())
    base_salary = P.salary.iloc[mask].sum()
    for k in range(1, max_swaps + 1):
        for combo in itertools.combinations(swappable_slots, k):
            in_idxs = [alts[slot_idx] for slot_idx in combo]
            if len(set(in_idxs)) != len(in_idxs):
                continue
            new_mask = mask.copy()
            delta = 0
            for slot_idx, in_idx in zip(combo, in_idxs):
                pos_in_arr = np.where(new_mask == slot_idx)[0][0]
                delta += P.salary.iloc[in_idx] - P.salary.iloc[slot_idx]
                new_mask[pos_in_arr] = in_idx
            if base_salary + delta > SALARY_CAP:
                continue
            out_names = [P.player_name.iloc[i] for i in combo]
            in_names = [P.player_name.iloc[alts[i]] for i in combo]
            yield new_mask, out_names, in_names


def score_masks(P, field, masks, n_sims, seed=3):
    """Byte-identical to pivot_off_chalk.py's version: mirrors
    best_lineup_classic.score()'s scenario loop for an externally-built list
    of candidate masks (the anchor + its pivots)."""
    rng = np.random.default_rng(seed + 100)
    field_qb = field["qb"]; field_rb = field["rb"]; field_wr = field["wr"]; field_te = field["te"]
    field_flex = field["flex"]; field_dst = field["dst"]
    top25_results = {name: np.zeros(len(masks)) for name in blc.SCENARIOS}
    for name, params in blc.SCENARIOS.items():
        pts = blc.simulate_scenario_points(P, n_sims, rng, params)
        field_totals = (pts[:, field_qb] + pts[:, field_rb].sum(axis=2) + pts[:, field_wr].sum(axis=2)
                        + pts[:, field_te] + pts[:, field_flex] + pts[:, field_dst])
        field_totals.sort(axis=1)
        for j, mask in enumerate(masks):
            cand_total = pts[:, mask].sum(axis=1)
            rank = np.array([np.searchsorted(field_totals[s], cand_total[s]) for s in range(n_sims)])
            pct = rank / field_totals.shape[1]
            top25_results[name][j] = (pct >= 0.75).mean()
    avg25 = np.mean([top25_results[n] for n in blc.SCENARIOS], axis=0)
    worst25 = np.min([top25_results[n] for n in blc.SCENARIOS], axis=0)
    return avg25, worst25


def main():
    rows = []
    for lab, (f, sid) in rv.SLATES.items():
        t0 = time.time()
        fpts_map, real_own_map, real_points, mine = rv.load_real(f)
        P, field = blc.build_pool_and_field("dk", sid, field_n=FIELD_N, seed=1)
        P["k"] = P.player_name.map(rv.norm)

        try:
            mask = build_live_anchor("dk", P)
        except Exception as exc:
            print(f"{lab}: live anchor build failed ({type(exc).__name__}: {exc})", file=sys.stderr)
            continue

        anchor_ks = [P["k"].iloc[i] for i in mask]
        g_anchor = rv.grade(anchor_ks, fpts_map, real_points)
        anchor_total_own = float(P["own"].iloc[mask].sum())

        alts = best_alt_per_slot(P, mask)
        combos = list(enumerate_pivots(P, mask, alts))
        all_masks = [mask] + [c[0] for c in combos]
        for m in all_masks:
            assert len(set(m.tolist())) == len(m), f"{lab}: duplicate player in a candidate mask -- roster-legality bug"
        avg25, worst25 = score_masks(P, field, all_masks, N_SIMS)

        best_idx = int(worst25.argmax())
        best_mask = all_masks[best_idx]
        best_ks = [P["k"].iloc[i] for i in best_mask]
        g_best = rv.grade(best_ks, fpts_map, real_points)
        best_total_own = float(P["own"].iloc[best_mask].sum())
        is_anchor = (best_idx == 0)

        row = dict(slate=lab, n_pivots=len(combos),
                   anchor_cash=g_anchor["cash"], anchor_pct=g_anchor["pct"],
                   anchor_worst25=worst25[0], anchor_total_own=anchor_total_own,
                   best_cash=g_best["cash"], best_pct=g_best["pct"],
                   best_worst25=worst25[best_idx], best_is_anchor=is_anchor,
                   best_total_own=best_total_own,
                   runtime_s=round(time.time() - t0))
        if mine:
            row["arm1_cash"] = mine["cash"]
            row["arm1_pct"] = mine["pct"]
        rows.append(row)
        if not is_anchor:
            _, out_names, in_names = combos[best_idx - 1]
            print(f"{lab}: pivot swap chosen -- OUT {out_names} / IN {in_names}")
        print(f"{lab}: done in {row['runtime_s']}s ({len(combos)} legal pivots) -- "
              f"anchor pct={g_anchor['pct']:.3f} cash={g_anchor['cash']} (worst25={worst25[0]:.3f}, "
              f"total_own={anchor_total_own:.0f}%) | "
              f"best pct={g_best['pct']:.3f} cash={g_best['cash']} (worst25={worst25[best_idx]:.3f}, "
              f"total_own={best_total_own:.0f}%) "
              f"{'[= anchor]' if is_anchor else '[PIVOT]'}")

    out_df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("\n" + out_df.to_string(index=False))
    print(f"\nlive anchor: {out_df.anchor_cash.sum()}/{len(out_df)} cash, mean pctile {out_df.anchor_pct.mean():.3f}, "
          f"mean total_own {out_df.anchor_total_own.mean():.0f}% (DFS Army winning-lineup norm: ~126%)")
    print(f"live best (anchor or pivot): {out_df.best_cash.sum()}/{len(out_df)} cash, mean pctile {out_df.best_pct.mean():.3f}, "
          f"mean total_own {out_df.best_total_own.mean():.0f}%")
    print(f"pivot beat anchor on {(~out_df.best_is_anchor).sum()}/{len(out_df)} slates")
    print("\ncompare to pivot_off_chalk.py's REAL-ownership-anchor result: 4/6 cash, mean pctile 0.819")
    print("compare to the FIRST (buggy, pure-ownership-max anchor) live attempt: 2/6 cash, mean pctile 0.585")

    out_df.to_csv("analysis/classic_diag/pivot_off_chalk_live_results.csv", index=False)


if __name__ == "__main__":
    main()
