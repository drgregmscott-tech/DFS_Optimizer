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
   produce by chance. A `stack_boost` multiplies a QB's own teammates'
   draw weight when filling the RB/WR/TE/FLEX slots for that same simulated
   entry, then IPF still corrects the final marginal ownership back to
   target -- the boost only changes which players get grouped together
   within a lineup, not who gets rostered overall.

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
MIN_SALARY = 49300  # real entries: 5th pct ~49.3-49.5k, 10th pct ~49.6k across 6 logged classic slates
N_RB, N_WR = 2, 3
DEFAULT_STACK_BOOST = 3.0  # calibrated in validate_classic_field.py to hit real ~85-90% stack>=1 rate


def _topk_distinct(w, k, rng, exclude=None):
    """Gumbel top-k trick, vectorized over the batch (rows of w). w: [n, m].
    exclude: optional [n, m] bool mask of already-picked players to zero out."""
    if exclude is not None:
        w = np.where(exclude, 0.0, w)
    g = np.log(np.maximum(w, 1e-12)) + rng.gumbel(size=w.shape)
    return np.argsort(-g, axis=1)[:, :k]


def simulate_field(pool: pd.DataFrame, n=20000, seed=0, iters=15, batch=200000,
                   min_salary=MIN_SALARY, stack_boost=None):
    """pool needs columns: position, team, salary, own (target ownership %).
    Returns a dict of index arrays {qb, rb[n,2], wr[n,3], te, flex, dst} into
    `pool`'s row order, for n accepted lineups.

    stack_boost: multiplier applied to a QB's own teammates' draw weight when
    filling skill slots. None (default) auto-scales with the number of teams
    in the pool -- a fixed boost dilutes on big multi-game slates (e.g. a DK
    main slate, ~26-32 teams) because the boosted team is competing against
    far more other teams than on a 2-4 game early/afternoon-only slate.
    Calibrated against real per-slate QB-stack rates (2026-09-22, classic
    field validation): boost=3 reproduces the real ~81-95% stack>=1 rate on
    small slates but only ~65% on a 26-team main slate; boost=6 there hits
    ~83% (real target 84%) with a negligible effect on score quantiles."""
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
    if stack_boost is None:
        n_teams = len(set(team.tolist()))
        stack_boost = float(np.clip(DEFAULT_STACK_BOOST * n_teams / 8.0, DEFAULT_STACK_BOOST, 12.0))

    wQB = own[idx["QB"]].copy()
    wRB = own[idx["RB"]].copy()
    wWR = own[idx["WR"]].copy()
    wTE = own[idx["TE"]].copy()
    wFLEX = own[skill_idx].copy()
    wDST = own[idx["DST"]].copy()
    best = (np.inf, wRB.copy(), wWR.copy(), wTE.copy(), wFLEX.copy())

    def _draw_batch(wQB, wRB, wWR, wTE, wFLEX, wDST):
        qb_local = rng.choice(len(idx["QB"]), size=batch, p=wQB / wQB.sum())
        qb = idx["QB"][qb_local]
        qb_team = team[qb]

        rb_boost = np.where(team[idx["RB"]][None, :] == qb_team[:, None], stack_boost, 1.0) * wRB[None, :]
        rb = idx["RB"][_topk_distinct(rb_boost, N_RB, rng)]

        wr_boost = np.where(team[idx["WR"]][None, :] == qb_team[:, None], stack_boost, 1.0) * wWR[None, :]
        wr = idx["WR"][_topk_distinct(wr_boost, N_WR, rng)]

        te_boost = np.where(team[idx["TE"]][None, :] == qb_team[:, None], stack_boost, 1.0) * wTE[None, :]
        te = idx["TE"][_topk_distinct(te_boost, 1, rng)[:, 0]]

        picked = np.concatenate([rb, wr, te[:, None]], axis=1)  # [batch, 6] global indices
        flex_boost = np.where(team[skill_idx][None, :] == qb_team[:, None], stack_boost, 1.0) * wFLEX[None, :]
        excl = (skill_idx[None, :] == picked[:, :, None]).any(axis=1)
        flex = skill_idx[_topk_distinct(flex_boost, 1, rng, exclude=excl)[:, 0]]

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
