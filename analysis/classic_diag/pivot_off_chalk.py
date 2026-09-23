"""Tests HANDOFF_dfs_army_variables.md's V2: Greg's DFS Army rule that SE3max
should be built as a PIVOT off your cash lineup (1-3 differentiating swaps),
not an independently-built lineup. Anchor definition settled 2026-09-22 via
chalk_lineup_analysis.py: the real field's single most-duplicated lineup on
each slate (guaranteed salary-legal, since real people actually played it) --
NOT the "highest-owned-per-slot" assembly, which busted the salary cap on
every one of the 6 logged slates.

Simplification vs. Greg's exact example ("fade Chase for Higgins OR Chase
Brown" -- a WR-to-RB swap): only SAME-POSITION swaps (RB<->RB, WR<->WR,
TE<->TE) are tested here. A cross-position swap changes which slot absorbs
FLEX and isn't a clean 1-for-1 -- doable later if same-position swaps alone
don't capture the effect, but same-position keeps roster legality trivial and
still tests the core idea (differentiate a chalk piece for a lower-owned
one), just not the exact positions in Greg's example.

Method: for each of the anchor's 6 RB/WR/TE slots, find same-position
alternatives with LOWER real post-lock ownership than the anchor's own
player (using the real own_map -- fine for this historical replay; a live
slate would need the model's estimated_ownership_pct instead, flagged as a
follow-up). Take each slot's single best-projected lower-owned alternative,
then enumerate every 1-, 2-, and 3-slot swap combo from those 6 candidates
(41 combos), filter to salary-legal ones, and score every legal combo PLUS
the anchor itself with the identical 4-scenario Monte Carlo
best_lineup_classic.py already uses, picking the best by worst_top25 (the
winning selection rule from replay_selection_criteria.py). Grades the pivot
pick against real results and compares directly to the pure anchor's own
real grade.

usage: python analysis/classic_diag/pivot_off_chalk.py [n_sims] [field_n]
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
import chalk_lineup_analysis as chalk

N_SIMS = int(sys.argv[1]) if len(sys.argv) > 1 else 800
FIELD_N = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
SALARY_CAP = 50000
SWAPPABLE_POS = {"RB", "WR", "TE"}


def anchor_mask(site, slate_id, raw_csv, P):
    build, count, n_total, _ = chalk.most_repeated_lineup(raw_csv)
    pid_by_k = {k: i for i, k in zip(P.index, P["k"])}
    idxs = [pid_by_k[k] for k in build if k in pid_by_k]
    if len(idxs) != len(build):
        missing = build - {P["k"].iloc[i] for i in idxs}
        raise RuntimeError(f"anchor player(s) not found in pool: {missing}")
    return np.array(idxs), count, n_total


def best_alt_per_slot(P, mask, own_map):
    """For each RB/WR/TE index in mask, returns the single best-projected
    same-position alternative with strictly lower real ownership, or None."""
    alts = {}
    for i in mask:
        pos = P.position.iloc[i]
        if pos not in SWAPPABLE_POS:
            continue
        my_own = own_map.get(P["k"].iloc[i], 0.0)
        pool = P[(P.position == pos) & (~P.index.isin(mask))].copy()
        pool["own"] = pool["k"].map(own_map).fillna(0.0)
        pool = pool[pool["own"] < my_own].sort_values("final_projection", ascending=False)
        if len(pool):
            alts[i] = pool.index[0]
    return alts


def enumerate_pivots(P, mask, alts, max_swaps=3):
    """Yields (combo_mask, swapped_out_names, swapped_in_names) for every
    1..max_swaps-slot swap combo built from `alts`, salary-legal only."""
    swappable_slots = list(alts.keys())
    base_salary = P.salary.iloc[mask].sum()
    for k in range(1, max_swaps + 1):
        for combo in itertools.combinations(swappable_slots, k):
            in_idxs = [alts[slot_idx] for slot_idx in combo]
            if len(set(in_idxs)) != len(in_idxs):
                # BUG FOUND 2026-09-22: two different outgoing slots can independently
                # pick the SAME best alternative (e.g. two WRs both fade to the same
                # "next best low-owned WR"), which would roster that player twice --
                # an illegal lineup. Skip any combo where the incoming players aren't
                # all distinct from each other, rather than silently double-rostering.
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
    """Mirrors best_lineup_classic.score()'s scenario loop but for an
    arbitrary externally-built list of candidate masks (the anchor + its
    pivots) instead of candidates() output."""
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
        fpts_map, own_map, real_points, mine = rv.load_real(f)
        P, field = blc.build_pool_and_field("dk", sid, field_n=FIELD_N, seed=1)
        P["k"] = P.player_name.map(rv.norm)

        try:
            mask, dup_count, n_total = anchor_mask("dk", sid, f, P)
        except RuntimeError as exc:
            print(f"{lab}: anchor build failed ({exc})", file=sys.stderr)
            continue

        anchor_ks = [P["k"].iloc[i] for i in mask]
        g_anchor = rv.grade(anchor_ks, fpts_map, real_points)

        alts = best_alt_per_slot(P, mask, own_map)
        combos = list(enumerate_pivots(P, mask, alts))
        all_masks = [mask] + [c[0] for c in combos]
        for m in all_masks:
            assert len(set(m.tolist())) == len(m), f"{lab}: duplicate player in a candidate mask -- roster-legality bug"
        avg25, worst25 = score_masks(P, field, all_masks, N_SIMS)

        best_idx = int(worst25.argmax())
        best_mask = all_masks[best_idx]
        best_ks = [P["k"].iloc[i] for i in best_mask]
        g_best = rv.grade(best_ks, fpts_map, real_points)
        is_anchor = (best_idx == 0)

        row = dict(slate=lab, dup_count=dup_count, n_total=n_total, n_pivots=len(combos),
                   anchor_cash=g_anchor["cash"], anchor_pct=g_anchor["pct"],
                   anchor_worst25=worst25[0],
                   best_cash=g_best["cash"], best_pct=g_best["pct"],
                   best_worst25=worst25[best_idx], best_is_anchor=is_anchor,
                   runtime_s=round(time.time() - t0))
        if mine:
            row["arm1_cash"] = mine["cash"]
            row["arm1_pct"] = mine["pct"]
        rows.append(row)
        if not is_anchor:
            _, out_names, in_names = combos[best_idx - 1]
            print(f"{lab}: pivot swap chosen -- OUT {out_names} / IN {in_names}")
        print(f"{lab}: done in {row['runtime_s']}s ({len(combos)} legal pivots) -- "
              f"anchor pct={g_anchor['pct']:.3f} cash={g_anchor['cash']} (worst25={worst25[0]:.3f}) | "
              f"best pct={g_best['pct']:.3f} cash={g_best['cash']} (worst25={worst25[best_idx]:.3f}) "
              f"{'[= anchor]' if is_anchor else '[PIVOT]'}")

    out_df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("\n" + out_df.to_string(index=False))
    print(f"\nanchor: {out_df.anchor_cash.sum()}/{len(out_df)} cash, mean pctile {out_df.anchor_pct.mean():.3f}")
    print(f"best (anchor or pivot): {out_df.best_cash.sum()}/{len(out_df)} cash, mean pctile {out_df.best_pct.mean():.3f}")
    print(f"pivot beat anchor on {(~out_df.best_is_anchor).sum()}/{len(out_df)} slates")

    out_df.to_csv("analysis/classic_diag/pivot_off_chalk_results.csv", index=False)


if __name__ == "__main__":
    main()
