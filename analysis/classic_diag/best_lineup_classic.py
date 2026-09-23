"""Classic counterpart to analysis/showdown_own/best_single.py: pick ONE classic
lineup to maximize P(top 10%) of the field, using scripts/classic_field.py (validated
2026-09-22) as the field and a QB-stack correlation factor model for outcome scenarios.

1. Candidate pool: many solver lineups (noisy projections + forced QB-stacks on the
   top-projected teams), via optimizer.build_single_lineup (the same function the CLI uses).
2. Score every candidate against the simulated field across several correlated-outcome
   scenarios; report the average P(top10%)/P(top1%) AND the worst-case scenario (the
   Showdown session's "trap" lineup was only caught by the worst-case view, not the average).

Correlation model (calibrated from WK2_POSTMORTEM.md's "Joint game structure" 2014-21
rotoguru finding): QB vs. own WR+TE +0.77, own vs. opposing team skill total +0.21 (shared
game-environment factor), own DST vs. opposing offense -0.44. RB's correlation to the team
passing factor isn't directly measured; treated as weak/moderate (0.3) here -- documented
approximation, not a measured constant, and worth a note if this method gets adopted.

usage: python analysis/classic_diag/best_lineup_classic.py <site> <slate_id> [n_candidates]
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "scripts"))
import optimizer
import classic_field as cf

SCENARIOS = {
    # name: (a=sqrt(corr(own,opp skill)), rho_qb, rho_pass, rho_rb, rho_dst)
    "base": (np.sqrt(0.21), 0.88, 0.88, 0.30, -0.44),
    "shootout": (np.sqrt(0.40), 0.90, 0.90, 0.35, -0.30),
    "quiet_dst": (np.sqrt(0.21), 0.88, 0.88, 0.30, 0.0),
    "run_heavy": (np.sqrt(0.15), 0.80, 0.75, 0.55, -0.44),
}


def candidates(site, slate_id, n_noise=200, n_stack_per_team=15, top_teams=10, seed=5,
                team_rank_key="proj", excluded_player_ids=None):
    """Returns (out, is_stack_forced): is_stack_forced[i] is True iff candidate i
    came from the QB-stack-forced generation loop (not the unconstrained noise
    loop). Added 2026-09-22 so selection rules can optionally restrict to
    stack-forced candidates only -- see replay_selection_criteria.py's
    "*_stackonly" rules, added after raw_proj and avg_top25 both independently
    picked the SAME unstacked, single-bust-vulnerable candidate on wk2_early."""
    rng = np.random.default_rng(seed)
    seen, out, is_stack_forced = set(), [], []

    def add(sel, forced):
        key = frozenset(sel.player_id)
        if key in seen:
            return False
        seen.add(key)
        out.append(sel[["player_id", "position", "roster_slot"]].copy() if "roster_slot" in sel.columns
                   else sel[["player_id", "position"]].copy())
        is_stack_forced.append(forced)
        return True

    made = 0
    for _ in range(n_noise):
        try:
            sel = optimizer.build_single_lineup(site, slate_id, randomization_pct=20, rng=rng,
                                                 excluded_player_ids=excluded_player_ids)
        except RuntimeError:
            continue
        made += add(sel, False)

    P = optimizer.load_final_projections(site, slate_id)
    # team_rank_key: which teams get forced-stack candidates generated for them.
    # Added 2026-09-22 to test HANDOFF_dfs_army_variables.md's V1 (Greg's DFS Army
    # rule: stack the best GAME ENVIRONMENT -- implied team total -- not just the
    # best-projected QB). Default "proj" reproduces prior behavior exactly (QB
    # final_projection, which already partially proxies implied_total: rank
    # correlation ~0.83-0.93 across the 6 logged slates, so this is a real but
    # not drastic reordering, not an independent signal from scratch).
    if team_rank_key == "implied_total":
        qb = P[P.position == "QB"].groupby("team").implied_total.max()
    else:
        qb = P[P.position == "QB"].groupby("team").final_projection.max()
    teams = qb.sort_values(ascending=False).head(top_teams).index.tolist()
    for tm in teams:
        for _ in range(n_stack_per_team):
            try:
                sel = optimizer.build_single_lineup(
                    site, slate_id, randomization_pct=25, rng=rng,
                    stack_mode="qb", stack_size=2, stack_positions={"WR", "TE"},
                    bring_back=True, stack_teams=[tm],
                    excluded_player_ids=excluded_player_ids)
            except RuntimeError:
                continue
            made += add(sel, True)
    print(f"generated {made} solves -> {len(out)} distinct candidates ({sum(is_stack_forced)} stack-forced)")
    return out, is_stack_forced


def build_pool_and_field(site, slate_id, field_n=10000, seed=1):
    P = optimizer.load_final_projections(site, slate_id)
    P = P[P.position.isin(["QB", "RB", "WR", "TE", "DST"])].copy()
    P["own"] = pd.to_numeric(P.get("estimated_ownership_pct", 0.0), errors="coerce").fillna(0.0)
    P["sigma"] = pd.to_numeric(P.get("sigma", np.nan), errors="coerce")
    P["sigma"] = P["sigma"].fillna(P.final_projection * 0.55)
    P = P[P.final_projection > 0].reset_index(drop=True)
    field = cf.simulate_field(P, n=field_n, seed=seed)
    return P, field


def simulate_scenario_points(P: pd.DataFrame, n_sims: int, rng, params):
    a, rho_qb, rho_pass, rho_rb, rho_dst = params
    m = len(P)
    teams = P.team.to_numpy(dtype=object)
    opp = P.opponent.to_numpy(dtype=object)
    uniq = list(pd.unique(teams))
    tmap = {t: i for i, t in enumerate(uniq)}
    tid = np.array([tmap[t] for t in teams])
    opp_id = np.array([tmap.get(o, tmap[t]) for t, o in zip(teams, opp)])  # falls back to own team if opp missing (e.g. bye/DST-less edge case)
    n_teams = len(uniq)

    game_of_team = np.full(n_teams, -1)
    gid = 0
    for t in uniq:
        i = tmap[t]
        if game_of_team[i] >= 0:
            continue
        o = P.loc[teams == t, "opponent"].iloc[0]
        j = tmap.get(o, i)
        game_of_team[i] = gid
        game_of_team[j] = gid
        gid += 1
    n_games = gid

    Gd = rng.normal(size=(n_sims, n_games))
    team_noise = rng.normal(size=(n_sims, n_teams))
    T = a * Gd[:, game_of_team] + np.sqrt(max(1e-6, 1 - a * a)) * team_noise  # [n_sims, n_teams]
    Tp = T[:, tid]        # own-team factor per player
    Topp = T[:, opp_id]   # opposing-team factor per player

    pos = P.position.to_numpy(dtype=object)
    noise = rng.normal(size=(n_sims, m))
    z = np.zeros((n_sims, m))
    isQB, isRB, isWT, isD = pos == "QB", pos == "RB", np.isin(pos, ["WR", "TE"]), pos == "DST"
    z[:, isQB] = rho_qb * Tp[:, isQB] + np.sqrt(max(1e-6, 1 - rho_qb ** 2)) * noise[:, isQB]
    z[:, isWT] = rho_pass * Tp[:, isWT] + np.sqrt(max(1e-6, 1 - rho_pass ** 2)) * noise[:, isWT]
    z[:, isRB] = rho_rb * Tp[:, isRB] + np.sqrt(max(1e-6, 1 - rho_rb ** 2)) * noise[:, isRB]
    z[:, isD] = rho_dst * Topp[:, isD] + np.sqrt(max(1e-6, 1 - rho_dst ** 2)) * noise[:, isD]

    proj = P.final_projection.to_numpy(float)
    sigma = P.sigma.to_numpy(float)
    return np.maximum(0.0, proj[None, :] + sigma[None, :] * z)


def has_real_stack(P: pd.DataFrame, mask: np.ndarray, min_teammates: int = 1, min_bringback: int = 0) -> bool:
    """True iff the lineup at `mask` actually contains a QB with >= min_teammates
    same-team WR/TE AND >= min_bringback opponent-team WR/TE -- checked on the
    ROSTER ITSELF, not on how the candidate was generated.

    Added 2026-09-22 to replace the origin-based `is_stack_forced` tag: that tag
    excluded a legitimately good wk2_main candidate purely because it came from
    the unconstrained noise-generation loop. The first fix (min_teammates=1,
    default here) was TOO WEAK and tested worse than origin-tagging (2-3/6 cash
    vs. 4/6) -- most noise-loop candidates incidentally include >=1 same-team
    pair just because good players cluster on good offenses, so it barely
    filtered anything. The origin tag apparently worked well not because of
    generation source but because that loop enforces the exact VALIDATED
    structure (stack_size=2 AND bring_back=True). Callers wanting to replicate
    that should pass min_teammates=2, min_bringback=1 (see
    replay_selection_criteria.py's `*_validated` rules)."""
    pos = P.position.to_numpy(dtype=object)[mask]
    team = P.team.to_numpy(dtype=object)[mask]
    opp = P.opponent.to_numpy(dtype=object)[mask]
    qb_idx = np.where(pos == "QB")[0]
    if len(qb_idx) == 0:
        return False
    qb_team = team[qb_idx[0]]
    qb_opp = opp[qb_idx[0]]
    n_teammates = int(np.sum((team == qb_team) & np.isin(pos, ["WR", "TE"])))
    n_bringback = int(np.sum((team == qb_opp) & np.isin(pos, ["WR", "TE"])))
    return n_teammates >= min_teammates and n_bringback >= min_bringback


def score(site, slate_id, n_candidates=200, field_n=10000, n_sims=2000, seed=1, return_detail=False,
          team_rank_key="proj", cheapest_dst_only=False, cheapest_viable_dst_only=False):
    P, field = build_pool_and_field(site, slate_id, field_n=field_n, seed=seed)
    field_pts_template = P.final_projection.to_numpy(float)
    field_score_base = cf.score_lineups(field, field_pts_template)  # sanity only

    # cheapest_dst_only / cheapest_viable_dst_only: HANDOFF_dfs_army_variables.md's
    # V3a (Greg's DFS Army rule: DST is the cheapest VIABLE play -- clarified
    # 2026-09-22: not literally the cheapest regardless of matchup, but the
    # cheapest one you'd actually believe could limit points/get sacks/get picks --
    # pay up elsewhere, defense upside is capped anyway). Two variants, both
    # restrict OUR OWN candidate generation only (via excluded_player_ids) -- NOT
    # applied to `P`/`field` above, since those represent the real opposing field,
    # which played DST however it actually did:
    #   cheapest_dst_only: literal cheapest-salary DST, no matchup filter at all.
    #     Kept as a deliberate negative control/contrast, not the real V3a test --
    #     it can pick a bad matchup just because it's cheap (e.g. wk2_main:
    #     Dolphins $2000/4.9 proj vs. Panthers $2700/10.0 proj -- cheapest-only
    #     would take the Dolphins purely on price).
    #   cheapest_viable_dst_only: the real V3a test. Went through 3 revisions with
    #     Greg before landing here, 2026-09-22: not literally the cheapest
    #     regardless of matchup; not a separate opponent-implied-total filter
    #     either, once Greg pointed out the existing DST model "does a really good
    #     job" already (real example: cheap, top-projected Carolina DST this past
    #     week) -- so "cheap AND viable" collapses to POINTS-PER-DOLLAR VALUE
    #     (final_projection / salary), trusting the existing projection to have
    #     already priced in matchup quality. Picks the single best-value DST in
    #     the pool. Confirmed on wk2_main: Panthers ($2700, 9.98 proj) is the
    #     clear #1 by value (3.69 pts/$1000 vs. #2's 3.02) -- cheap-ish AND
    #     genuinely well-projected, the Carolina pattern, not just "the cheapest
    #     name on the slate" (that would've been the $2000 Dolphins facing a
    #     29-point favorite -- a bad matchup the raw-cheapest version doesn't see).
    excluded_player_ids = None
    if cheapest_dst_only:
        dst = P[P.position == "DST"].sort_values("salary")
        excluded_player_ids = set(dst.player_id.iloc[1:])
    elif cheapest_viable_dst_only:
        dst = P[P.position == "DST"].copy()
        dst["value"] = dst.final_projection / dst.salary
        best = dst.sort_values("value", ascending=False).iloc[0]
        excluded_player_ids = set(dst.player_id) - {best.player_id}

    cands, cand_forced_flags = candidates(site, slate_id, n_noise=n_candidates, n_stack_per_team=max(5, n_candidates // 20),
                                           team_rank_key=team_rank_key, excluded_player_ids=excluded_player_ids)
    pid_to_idx = {pid: i for i, pid in enumerate(P.player_id)}
    cand_masks = []
    is_stack_forced = []
    for c, forced in zip(cands, cand_forced_flags):
        idxs = [pid_to_idx[p] for p in c.player_id if p in pid_to_idx]
        if len(idxs) != len(c):
            continue
        cand_masks.append(np.array(idxs))
        is_stack_forced.append(forced)
    is_real_stack = [has_real_stack(P, m) for m in cand_masks]
    is_validated_stack = [has_real_stack(P, m, min_teammates=2, min_bringback=1) for m in cand_masks]

    rng = np.random.default_rng(seed + 100)
    results = {name: np.zeros(len(cand_masks)) for name in SCENARIOS}
    top1_results = {name: np.zeros(len(cand_masks)) for name in SCENARIOS}
    # top25 = P(pct >= 0.75) -- the ACTUAL SE3max min-cash line (CASH_PCT=0.25 elsewhere
    # in this codebase), added 2026-09-22. avg_top10/worst_top10 above target a GPP-style
    # ceiling (top-10%) that was never actually the right threshold for a min-cash format;
    # see HANDOFF_classic_construction_replay.md for the reasoning.
    top25_results = {name: np.zeros(len(cand_masks)) for name in SCENARIOS}
    field_qb = field["qb"]; field_rb = field["rb"]; field_wr = field["wr"]; field_te = field["te"]
    field_flex = field["flex"]; field_dst = field["dst"]
    for name, params in SCENARIOS.items():
        pts = simulate_scenario_points(P, n_sims, rng, params)
        field_totals = (pts[:, field_qb] + pts[:, field_rb].sum(axis=2) + pts[:, field_wr].sum(axis=2)
                        + pts[:, field_te] + pts[:, field_flex] + pts[:, field_dst])  # [n_sims, n_field]
        field_totals.sort(axis=1)
        for j, mask in enumerate(cand_masks):
            cand_total = pts[:, mask].sum(axis=1)  # [n_sims]
            rank = np.array([np.searchsorted(field_totals[s], cand_total[s]) for s in range(n_sims)])
            pct = rank / field_totals.shape[1]
            results[name][j] = (pct >= 0.90).mean()
            top1_results[name][j] = (pct >= 0.99).mean()
            top25_results[name][j] = (pct >= 0.75).mean()
        print(f"scenario {name} done")

    avg10 = np.mean([results[n] for n in SCENARIOS], axis=0)
    worst10 = np.min([results[n] for n in SCENARIOS], axis=0)
    avg1 = np.mean([top1_results[n] for n in SCENARIOS], axis=0)
    avg25 = np.mean([top25_results[n] for n in SCENARIOS], axis=0)
    worst25 = np.min([top25_results[n] for n in SCENARIOS], axis=0)
    out = pd.DataFrame({"avg_top10": avg10, "worst_top10": worst10, "avg_top1": avg1,
                         "avg_top25": avg25, "worst_top25": worst25})
    for name in SCENARIOS:
        out[f"top10_{name}"] = results[name]
        out[f"top25_{name}"] = top25_results[name]
    out["names"] = [", ".join(sorted(P.player_name.iloc[m].tolist())) for m in cand_masks]
    out["is_stack_forced"] = is_stack_forced
    out["is_real_stack"] = is_real_stack
    out["is_validated_stack"] = is_validated_stack
    order = out["avg_top10"].to_numpy().argsort()[::-1]
    out = out.iloc[order].reset_index(drop=True)
    if return_detail:
        ordered_masks = [cand_masks[i] for i in order]
        return out, ordered_masks, P
    return out


def pick_top(site, slate_id, **kwargs):
    """Convenience wrapper for replay/production use: returns the #1-ranked
    candidate's player_name list (for grading or export) alongside its score row."""
    out, masks, P = score(site, slate_id, return_detail=True, **kwargs)
    top_names = P.player_name.iloc[masks[0]].tolist()
    return top_names, out.iloc[0]


if __name__ == "__main__":
    site, slate_id = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 150
    t0 = time.time()
    res = score(site, slate_id, n_candidates=n)
    res.to_csv("analysis/classic_diag/best_lineup_classic_results.csv", index=False)
    print(res.head(15).to_string())
    print(f"done in {time.time() - t0:.0f}s")
