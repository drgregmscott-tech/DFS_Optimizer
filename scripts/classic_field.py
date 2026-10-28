"""
classic_field.py -- simulated DK Classic field from real per-player ownership.

Generalizes scripts/showdown_field.py's method to a full 9-slot classic
roster (QB, RB, RB, WR, WR, WR, TE, FLEX[RB/WR/TE], DST). Two things
Showdown's 2-team, 6-slot field didn't need that classic does:

1. Slot groups. Classic has 5 distinct weight groups (QB, RB, WR, TE, FLEX)
   instead of Showdown's 2 (CPT, FLEX), and a player's real ownership number
   is a SINGLE figure covering both a dedicated slot and the FLEX slot (DK's
   real ownership export doesn't split "rostered as WR" from "rostered as
   FLEX" the way it splits CPT from FLEX in Showdown). So the IPF correction
   tracks each player's TOTAL observed exposure (dedicated-slot + FLEX-if-
   eligible) against one ownership target, and applies the same correction
   factor to every weight vector that player appears in.
2. Stack correlation. Classic's cash-line diagnostic (2026-09-22,
   WK2_POSTMORTEM.md) found real fields QB-stack 81-95% of the time -- far
   above what an independent per-slot draw from marginal ownership would
   produce by chance. WK7 postmortem (2026-10-26/28, `WK7_POSTMORTEM_ACTION_ITEMS.md`
   "classic_field.py simulator over-concentrates team stacking") found the
   original fix -- a single `stack_boost` multiplier applied independently to
   every skill slot -- correctly hit the real stack>=1 rate but overshot
   stack>=2/3+/4+ by 34-39 points, because independent per-slot boosts compound
   across slots in a way no single multiplier can match a real joint
   distribution. Replaced with: sample each lineup's exact teammate count k
   (0-4+) directly from the real per-lineup distribution computed from 134 real
   DK SE main-slate contests (`analysis/wk7_postmortem_item4/`), then randomly
   choose which k of the lineup's 7 skill slots (RB,RB,WR,WR,WR,TE,FLEX) are
   "hot" -- a hot slot draws only from the QB's own teammates (falling back to
   the unboosted pool if none remain available), every other slot draws
   unboosted. IPF still corrects final marginal ownership back to target
   regardless -- this only changes which players get grouped together within
   a lineup, not who gets rostered overall.

Usage: build a pool DataFrame with columns player_id, position (QB/RB/WR/TE/
DST), team, salary, own (target ownership %), call simulate_field(), then
score_lineups() with either real actual points (for validation, see
analysis/classic_diag/validate_classic_field.py) or simulated scenario
points (for scoring candidate lineups, not yet wired up).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from optimizer import DEFENSE_POSITION_LABELS  # noqa: E402

CAP_SALARY = 50000
# WK7 postmortem (2026-10-26/28, "classic_field.py simulator under-uses the salary cap"): 134 real
# DK SE main-slate contests put the real-field salary floor at mean $49,880 [IQR 49,870-49,900], p10
# ~$49,700. The previous $49,300 floor left the sim $200-260 light on the mean with p10 pinned to the
# floor itself. Tested $49,500 and $49,700 against the same real-contest baseline (analysis/
# wk7_postmortem_item4/min_salary_test.py, not committed): $49,700 closes the mean gap to +$11/-$36
# (both 2026 wk1/wk2 pools) vs $49,500's -$90/-$144, at a modest ~9-10% relative cost to IPF
# ownership-convergence accuracy (own_MAE_vs_target). p50 gap narrows from ~$350 to ~$150 but isn't
# fully closed -- real fields concentrate even more tightly near the cap than this single floor bump
# captures.
MIN_SALARY = 49700
N_RB, N_WR = 2, 3
# Per-lineup count of the QB's 7 skill slots (RB,RB,WR,WR,WR,TE,FLEX) held by his own
# teammate, k=0..4+ (4+ lumped into one bucket -- real share beyond 4 is ~0.05%).
# Derived from the same 134 real DK SE main-slate contests (2022-2026) as the
# WK7 postmortem's stack-rate diagnostic; see analysis/wk7_postmortem_item4/exact_k_stack*.csv.
STACK_K_PROBS = np.array([0.157784, 0.462955, 0.334041, 0.041263, 0.003957])


def _topk_distinct(w, k, rng, exclude=None):
    """Gumbel top-k trick, vectorized over the batch (rows of w). w: [n, m].
    exclude: optional [n, m] bool mask of already-picked players to zero out."""
    if exclude is not None:
        w = np.where(exclude, 0.0, w)
    g = np.log(np.maximum(w, 1e-12)) + rng.gumbel(size=w.shape)
    return np.argsort(-g, axis=1)[:, :k]


def simulate_field(pool: pd.DataFrame, n=20000, seed=0, iters=15, batch=200000,
                   min_salary=MIN_SALARY):
    """pool needs columns: position, team, salary, own (target ownership %).
    Returns a dict of index arrays {qb, rb[n,2], wr[n,3], te, flex, dst} into
    `pool`'s row order, for n accepted lineups.

    Each lineup's QB-teammate count is drawn directly from STACK_K_PROBS (the
    real per-lineup distribution), then that many of the lineup's 7 skill
    slots are randomly chosen to draw from the QB's own teammates only; the
    rest draw unboosted. See module docstring point 2."""
    rng = np.random.default_rng(seed)
    pos = pool.position.to_numpy(dtype=object)
    team = pool.team.to_numpy(dtype=object)
    sal = pool.salary.to_numpy(float)
    own = np.maximum(pool.own.to_numpy(float), 1e-4) / 100.0
    m = len(pool)
    # 2026-09-23 fix: "DST" is DK's own label -- FD's real defense position
    # value is "D" (optimizer.py's SITE_CONFIGS["fd"]["defense_position_values"],
    # confirmed against a real FD export). A literal `pos == "DST"` match left
    # idx["DST"] empty for every FD pool, so wDST.sum() was 0 and
    # rng.choice(0, ...) crashed with "a must be a positive integer" -- FD
    # never got past this line. DEFENSE_POSITION_LABELS (optimizer.py, Session
    # 1.3) is this codebase's existing single source of truth for every real
    # defense label across both sites; used here instead of hardcoding one.
    idx = {p: np.where(pos == p)[0] for p in ("QB", "RB", "WR", "TE")}
    idx["DST"] = np.where(np.isin(pos, list(DEFENSE_POSITION_LABELS)))[0]
    skill_idx = np.where(np.isin(pos, ("RB", "WR", "TE")))[0]

    wQB = own[idx["QB"]].copy()
    wRB = own[idx["RB"]].copy()
    wWR = own[idx["WR"]].copy()
    wTE = own[idx["TE"]].copy()
    wFLEX = own[skill_idx].copy()
    wDST = own[idx["DST"]].copy()
    best = (np.inf, wRB.copy(), wWR.copy(), wTE.copy(), wFLEX.copy())

    def _slot_weight(is_hot, cand_idx, base_w, qb_team):
        """base_w broadcast to [batch, len(cand_idx)]. A hot slot draws only from the QB's
        own teammates among cand_idx; a cold slot draws only from NON-teammates -- each with
        a fallback to the unrestricted pool if that row has none available (e.g. already
        picked, or the pool here has only/none of the QB's team). Without the cold-slot
        exclusion, non-hot slots still incidentally pick the QB's (often above-average-owned)
        teammates at their natural rate, double-counting correlation on top of the hot slots
        and overshooting the target k -- confirmed 2026-10-28 (stack>=2 landed at ~52% vs the
        ~38% STACK_K_PROBS implies, before this exclusion was added)."""
        team_match = team[cand_idx][None, :] == qb_team[:, None]
        base = np.broadcast_to(base_w[None, :], team_match.shape)
        teammate_only = np.where(team_match, base, 0.0)
        non_teammate_only = np.where(team_match, 0.0, base)
        hot_weight = np.where(teammate_only.sum(axis=1, keepdims=True) > 0, teammate_only, base)
        cold_weight = np.where(non_teammate_only.sum(axis=1, keepdims=True) > 0, non_teammate_only, base)
        return np.where(is_hot[:, None], hot_weight, cold_weight)

    def _draw_batch(wQB, wRB, wWR, wTE, wFLEX, wDST):
        qb_local = rng.choice(len(idx["QB"]), size=batch, p=wQB / wQB.sum())
        qb = idx["QB"][qb_local]
        qb_team = team[qb]

        # draw this lineup's teammate count k, then pick which k of the 7 skill slots
        # (RB,RB,WR,WR,WR,TE,FLEX) are "hot" (uniformly at random among the 7)
        k = rng.choice(len(STACK_K_PROBS), size=batch, p=STACK_K_PROBS)
        hot_noise = rng.standard_normal((batch, 7))
        order = np.argsort(-hot_noise, axis=1)
        rank = np.empty_like(order)
        rows = np.arange(batch)[:, None]
        rank[rows, order] = np.arange(7)[None, :]
        hot = rank < k[:, None]

        rb_picks, excl_rb = [], np.zeros((batch, len(idx["RB"])), dtype=bool)
        for s in range(N_RB):
            w = _slot_weight(hot[:, s], idx["RB"], wRB, qb_team)
            pick_local = _topk_distinct(w, 1, rng, exclude=excl_rb)[:, 0]
            rb_picks.append(idx["RB"][pick_local])
            excl_rb[np.arange(batch), pick_local] = True
        rb = np.stack(rb_picks, axis=1)

        wr_picks, excl_wr = [], np.zeros((batch, len(idx["WR"])), dtype=bool)
        for s in range(N_WR):
            w = _slot_weight(hot[:, N_RB + s], idx["WR"], wWR, qb_team)
            pick_local = _topk_distinct(w, 1, rng, exclude=excl_wr)[:, 0]
            wr_picks.append(idx["WR"][pick_local])
            excl_wr[np.arange(batch), pick_local] = True
        wr = np.stack(wr_picks, axis=1)

        w = _slot_weight(hot[:, N_RB + N_WR], idx["TE"], wTE, qb_team)
        te = idx["TE"][_topk_distinct(w, 1, rng)[:, 0]]

        picked = np.concatenate([rb, wr, te[:, None]], axis=1)  # [batch, 6] global indices
        excl_flex = (skill_idx[None, :] == picked[:, :, None]).any(axis=1)
        w = _slot_weight(hot[:, N_RB + N_WR + 1], skill_idx, wFLEX, qb_team)
        flex = skill_idx[_topk_distinct(w, 1, rng, exclude=excl_flex)[:, 0]]

        dst_local = rng.choice(len(idx["DST"]), size=batch, p=wDST / wDST.sum())
        dst = idx["DST"][dst_local]
        return qb, rb, wr, te, flex, dst

    for it in range(iters + 1):
        qb, rb, wr, te, flex, dst = _draw_batch(wQB, wRB, wWR, wTE, wFLEX, wDST)
        tot = sal[qb] + sal[rb].sum(axis=1) + sal[wr].sum(axis=1) + sal[te] + sal[flex] + sal[dst]
        ok = (tot <= CAP_SALARY) & (tot >= min_salary)
        if ok.sum() < 2000:  # weights drifted to an (almost) infeasible corner: go back to the best so far
            wRB, wWR, wTE, wFLEX = (a.copy() for a in best[1:])
            qb, rb, wr, te, flex, dst = _draw_batch(wQB, wRB, wWR, wTE, wFLEX, wDST)
            tot = sal[qb] + sal[rb].sum(axis=1) + sal[wr].sum(axis=1) + sal[te] + sal[flex] + sal[dst]
            ok = (tot <= CAP_SALARY) & (tot >= min_salary)
            qb, rb, wr, te, flex, dst = qb[ok], rb[ok], wr[ok], te[ok], flex[ok], dst[ok]
            w = np.ones(len(qb))
            break

        qb, rb, wr, te, flex, dst = qb[ok], rb[ok], wr[ok], te[ok], flex[ok], dst[ok]
        w = np.ones(len(qb))

        def obs_marginal(*groups):
            c = np.zeros(m)
            for g in groups:
                g = np.atleast_2d(g.T).T
                for col in range(g.shape[1]):
                    c += np.bincount(g[:, col], weights=w, minlength=m)
            return c / w.sum()

        obs_qb = obs_marginal(qb)[idx["QB"]]
        obs_dst = obs_marginal(dst)[idx["DST"]]
        # total exposure per skill player = dedicated-slot appearances + flex appearances
        obs_skill = obs_marginal(rb, wr, te[:, None], flex[:, None])
        obs_rb, obs_wr, obs_te = obs_skill[idx["RB"]], obs_skill[idx["WR"]], obs_skill[idx["TE"]]
        obs_flex_pool = obs_skill[skill_idx]

        target_skill = np.zeros(m)
        target_skill[idx["RB"]] = own[idx["RB"]]
        target_skill[idx["WR"]] = own[idx["WR"]]
        target_skill[idx["TE"]] = own[idx["TE"]]
        err = (np.abs(obs_qb - own[idx["QB"]]).sum() + np.abs(obs_dst - own[idx["DST"]]).sum()
               + np.abs(obs_skill[skill_idx] - target_skill[skill_idx]).sum())
        if err < best[0]:
            best = (err, wRB.copy(), wWR.copy(), wTE.copy(), wFLEX.copy())
        if it == iters:
            break

        wQB = wQB * np.clip(own[idx["QB"]] / np.maximum(obs_qb, 1e-4), 0.5, 2.0) ** 0.6
        wDST = wDST * np.clip(own[idx["DST"]] / np.maximum(obs_dst, 1e-4), 0.5, 2.0) ** 0.6
        skill_ratio = np.clip(target_skill / np.maximum(obs_skill, 1e-4), 0.5, 2.0) ** 0.6
        wRB = wRB * skill_ratio[idx["RB"]]
        wWR = wWR * skill_ratio[idx["WR"]]
        wTE = wTE * skill_ratio[idx["TE"]]
        wFLEX = wFLEX * skill_ratio[skill_idx]

    sel = rng.choice(len(qb), size=n, replace=True, p=w / w.sum())
    return dict(qb=qb[sel], rb=rb[sel], wr=wr[sel], te=te[sel], flex=flex[sel], dst=dst[sel])


def score_lineups(lineups: dict, pts: np.ndarray) -> np.ndarray:
    p = np.asarray(pts, float)
    return (p[lineups["qb"]] + p[lineups["rb"]].sum(axis=1) + p[lineups["wr"]].sum(axis=1)
            + p[lineups["te"]] + p[lineups["flex"]] + p[lineups["dst"]])
