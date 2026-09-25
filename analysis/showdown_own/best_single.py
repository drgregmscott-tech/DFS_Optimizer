"""Pick ONE Showdown lineup to maximize P(top 10%) of the field.

1. Candidate pool: many solver lineups (noisy projections, forced captains, forced team splits).
2. Score every candidate against the simulated field (scripts/showdown_field.py) across
   scenarios (game script / correlation structure) x field-ownership variants.
3. Rank by average P(top10%) across scenarios and by the WORST scenario (robustness).

usage: python analysis/showdown_own/best_single.py <projections_csv> [--min-part 0.5]
"""
import sys, time, itertools
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "scripts"))
import optimizer, showdown_field as sf

ROWKEY = optimizer.ROW_KEY_COL


def load_pool(csv):
    P = pd.read_csv(csv, dtype={"player_id": str})
    P["player_id"] = P.player_id.astype(str)
    for c in ("final_projection", "salary", "sigma"):
        P[c] = pd.to_numeric(P[c], errors="coerce")
    P["sigma"] = P.sigma.fillna(P.final_projection * 0.6)
    P[ROWKEY] = P.player_id + "::" + P.roster_role
    return P


def candidates(P, site="dk", n_noise=250, n_forced=30, seed=5, min_part=0.5, top_captains=12):
    """2026-09-23 generalization: this used to hardcode the forced-team-
    split loop to one old slate's real team abbreviations ("LA"/"NYG"),
    which silently generated ZERO forced-split candidates for any other
    slate's teams (no error -- `min_team_players={"LA": 4}` on a slate with
    no LA just never matches anything in solve_showdown_lineup(), so the
    loop quietly no-ops). Also hardcoded site="dk" in the solve call.
    Both are now read from the pool itself, so this works for any real
    2-team Showdown slate on either site."""
    pool = P[(P.final_projection > 0.5) & (P.participation_effective.fillna(1) >= min_part)].copy()
    teams = sorted(pool.team.dropna().unique().tolist())
    rng = np.random.default_rng(seed)
    seen, out = set(), []

    def add(sel):
        key = (sel[sel.roster_role == "CPT"].player_id.iloc[0], frozenset(sel[sel.roster_role == "FLEX"].player_id))
        if key in seen:
            return False
        seen.add(key)
        out.append(sel[[ROWKEY, "player_id", "roster_role"]].copy())
        return True

    def run(n, noise, **kw):
        prev, made, tries = [], 0, 0
        while made < n and tries < n * 3:
            tries += 1
            opt = optimizer.randomize_showdown_projections(pool, noise, rng)
            try:
                sel = optimizer.solve_showdown_lineup(pool, site, previous_player_sets=prev, uniqueness=1,
                                                      optimization_projection=opt, **kw)
            except RuntimeError:
                break
            prev.append(set(sel.player_id))
            made += add(sel)

    t = time.time()
    run(n_noise, 20)
    # Forced team splits: both real teams, at k=3/4/5 of the 6 roster
    # slots (a lopsided-toward-one-team build) -- symmetric coverage of
    # both sides, unlike the old hardcoded list which only covered one
    # team at 3/4/5 and the other at 3/4.
    for tm in teams:
        for k in (3, 4, 5):
            run(n_forced, 25, min_team_players={tm: k})
    caps = P[P.roster_role == "CPT"].sort_values("final_projection", ascending=False).head(top_captains)
    for _, r in caps.iterrows():
        run(n_forced, 25, locked_player_ids={r.player_id}, locked_role_map={r.player_id: "CPT"})
    print(f"candidates: {len(out)} in {time.time()-t:.0f}s")
    return out


def scenarios():
    # name: (game factor a, own-offense factor b, corr between the two offenses, dst_rho, dst_sig_mult)
    return {
        "base": (0.20, 0.45, 0.0, -0.5, 1.0),
        "shootout": (0.40, 0.35, 0.0, -0.5, 1.0),
        "blowout-linked": (0.15, 0.45, -0.5, -0.5, 1.0),
        "quiet-DST": (0.20, 0.45, 0.0, 0.0, 0.6),
    }


def evaluate(P, cands, fields, n_sims=2500, seed=17):
    fl = P[P.roster_role == "FLEX"].reset_index(drop=True)
    idx = {pid: i for i, pid in enumerate(fl.player_id)}
    m = len(fl)
    teams = fl.team.unique().tolist()
    tix = fl.team.map({t: i for i, t in enumerate(teams)}).values
    opp = 1 - tix
    pos = fl.position.values
    isk = pos == "K"; isd = np.isin(pos, ["DST", "D", "DEF"])
    proj = fl.final_projection.values; sig = fl.sigma.values
    W = np.zeros((m, len(cands)))
    for j, c in enumerate(cands):
        for r in c.itertuples():
            W[idx[r.player_id], j] = 1.5 if r.roster_role == "CPT" else 1.0
    res = {}
    for sname, (a, b, rhoT, drho, dmult) in scenarios().items():
        for fname, (fc, ff) in fields.items():
            rng = np.random.default_rng(seed)
            p10 = np.zeros(len(cands)); p1 = np.zeros(len(cands)); mp = np.zeros(len(cands))
            for _ in range(n_sims):
                G = rng.normal(); t1, t2 = rng.normal(size=2)
                T = np.array([t1, rhoT * t1 + np.sqrt(1 - rhoT ** 2) * t2])
                e = rng.normal(size=m)
                z = a * G + b * T[tix] + np.sqrt(max(1e-6, 1 - a * a - b * b)) * e
                z = np.where(isk, 0.45 * T[tix] + np.sqrt(1 - 0.2025) * e, z)
                z = np.where(isd, drho * T[opp] + np.sqrt(1 - drho ** 2) * e, z)
                pts = np.maximum(0.0, proj + sig * np.where(isd, dmult, 1.0) * z)
                field = np.sort(1.5 * pts[fc] + pts[ff].sum(axis=1))
                sc = pts @ W
                pc = np.searchsorted(field, sc) / len(field)
                p10 += pc >= 0.90; p1 += pc >= 0.99; mp += pc
            res[(sname, fname)] = (p10 / n_sims, p1 / n_sims, mp / n_sims)
    return res


def score(site, slate_id, n_candidates=250, n_forced=30, field_n=10000, n_sims=800,
          seed=5, return_detail=False):
    """2026-09-23 addition -- Showdown counterpart to best_lineup_classic.
    score(), same `return_detail` contract ((out, masks, P) for a caller
    like recommend_lineup.py to rank and pick from) so that script's
    existing candidate/mask/roster-assignment flow needs only a branch,
    not a rewrite.

    Candidate pool: candidates() (generalized above -- noisy solves +
    forced-captain + forced-team-split solves, real slate teams, not
    hardcoded).

    Field: simulated from the pool's own live `estimated_ownership_pct`
    (showdown_field.py) -- the model's own pre-lock estimate, since real
    post-lock ownership doesn't exist yet for a live slate (identical
    reasoning to best_lineup_classic.build_pool_and_field()'s own field).

    Scoring: avg/worst-case P(top-10%) and P(top-1%) across the 4
    correlated scenarios in scenarios() -- a GPP ceiling metric, not a
    cash-line threshold. This is deliberate, not a leftover from the old
    analysis script: every real logged Showdown slate
    (data/ownership_actual_log.csv) is a real `single_entry_gpp` contest
    (field size ~4700-8900), not an SE3max cash game like classic, so
    classic's "top25%" cash-line concept has no Showdown analogue --
    confirmed via replay_showdown.py's real-data test against the 2 real
    Showdown slates with both real ownership AND real logged results
    (see that file for which specific ranking metric it validated best).
    `masks[i]` indexes into `P` (one row per CPT/FLEX pool entry, not per
    real player) -- exactly 1 captain-role row + 5 flex-role rows,
    directly usable with optimizer.assign_showdown_roster_slots()."""
    P = optimizer.load_showdown_pool(site, slate_id).reset_index(drop=True)
    P["sigma"] = pd.to_numeric(P.get("sigma", np.nan), errors="coerce")
    P["sigma"] = P["sigma"].fillna(P.final_projection * 0.6)
    P["participation_effective"] = pd.to_numeric(
        P.get("participation_effective", 1.0), errors="coerce")

    cands = candidates(P, site=site, n_noise=n_candidates, n_forced=n_forced, seed=seed)
    if not cands:
        raise SystemExit(
            f"showdown best_single.score: no candidates generated for "
            f"{site}/{slate_id} -- check final_projections and the salary "
            f"pool (min-1-per-team / salary-cap feasibility)."
        )

    fl = P[P.roster_role == "FLEX"].reset_index(drop=True)
    cpt_by_pid = P[P.roster_role == "CPT"].set_index("player_id")["estimated_ownership_pct"]
    cpt_own = fl.player_id.map(cpt_by_pid).fillna(0.0).values
    flex_own = pd.to_numeric(fl["estimated_ownership_pct"], errors="coerce").fillna(0.0).values
    fc, ff = sf.simulate_field(fl.salary.values, fl.team.values, cpt_own, flex_own,
                               n=field_n, seed=seed)
    fields = {"model_own": (fc, ff)}

    res = evaluate(P, cands, fields, n_sims=n_sims, seed=seed + 100)
    names = list(scenarios())
    avg10 = np.mean([res[(s, "model_own")][0] for s in names], axis=0)
    worst10 = np.min([res[(s, "model_own")][0] for s in names], axis=0)
    avg1 = np.mean([res[(s, "model_own")][1] for s in names], axis=0)
    avgpct = np.mean([res[(s, "model_own")][2] for s in names], axis=0)

    nm = P.drop_duplicates("player_id").set_index("player_id")["player_name"]
    out = pd.DataFrame({
        "avg_top10": avg10, "worst_top10": worst10, "avg_top1": avg1, "avg_pct": avgpct,
        "names": [", ".join(sorted(nm.reindex(c.player_id).tolist())) for c in cands],
    })

    rowkey_to_pos = {rk: i for i, rk in enumerate(P[ROWKEY])}
    masks = [np.array([rowkey_to_pos[rk] for rk in c[ROWKEY]]) for c in cands]

    # 2026-09-23: sorted by worst_top10 (worst-case P(top-10%) across the 4
    # correlated scenarios), not avg_top10 -- replay_showdown.py's real-data
    # test against the 2 real logged Showdown slates (both real ownership
    # AND real results) found worst_top10 tied-or-beat every other rule
    # (avg_top10/avg_top1/avg_pct/raw_proj) on both the realistic
    # (estimated-ownership) and idealized (real-ownership) arms -- see that
    # file's results. Same "worst-case across scenarios beats the average"
    # finding classic's own replay already established for worst_top25.
    order = out["worst_top10"].to_numpy().argsort()[::-1]
    out = out.iloc[order].reset_index(drop=True)
    if return_detail:
        ordered_masks = [masks[i] for i in order]
        return out, ordered_masks, P
    return out


def describe(P, c):
    nm = P.drop_duplicates("player_id").set_index("player_id")
    cap = c[c.roster_role == "CPT"].player_id.iloc[0]
    fx = c[c.roster_role == "FLEX"].player_id.tolist()
    tag = lambda pid: nm.loc[pid, "player_name"].split()[-1] + ("(K)" if nm.loc[pid, "position"] == "K" else "(D)" if nm.loc[pid, "position"] == "DST" else "")
    tms = pd.Series([nm.loc[p, "team"] for p in [cap] + fx]).value_counts()
    return f"CPT {tag(cap)} | " + ", ".join(tag(p) for p in fx) + f"  [{'/'.join(f'{k}{v}' for k, v in tms.items())}]"


def main(csv, min_part=0.5):
    P = load_pool(csv)
    cands = candidates(P, min_part=min_part)
    fl = P[P.roster_role == "FLEX"].reset_index(drop=True)
    cpt_own = fl.player_id.map(P[P.roster_role == "CPT"].set_index("player_id").estimated_ownership_pct).values
    fields = {}
    fc, ff = sf.simulate_field(fl.salary.values, fl.team.values, cpt_own, fl.estimated_ownership_pct.values, n=10000, seed=1)
    fields["model-own"] = (fc, ff)
    if "estimated_ownership_pct_heuristic" in P.columns:
        h = P[P.roster_role == "CPT"].set_index("player_id").estimated_ownership_pct_heuristic
        fc, ff = sf.simulate_field(fl.salary.values, fl.team.values, fl.player_id.map(h).values,
                                   fl.estimated_ownership_pct_heuristic.values, n=10000, seed=1)
        fields["old-heuristic-own"] = (fc, ff)
    t = time.time()
    res = evaluate(P, cands, fields)
    print(f"evaluated in {time.time()-t:.0f}s ({len(res)} scenario/field combos)")
    keys = list(res)
    p10 = np.vstack([res[k][0] for k in keys]); p1 = np.vstack([res[k][1] for k in keys]); mp = np.vstack([res[k][2] for k in keys])
    df = pd.DataFrame({"avg_top10": p10.mean(0) * 100, "min_top10": p10.min(0) * 100, "avg_top1": p1.mean(0) * 100,
                       "avg_pct": mp.mean(0) * 100})
    df["desc"] = [describe(P, c) for c in cands]
    df["proj"] = [float(P.set_index(ROWKEY).loc[c[ROWKEY], "final_projection"].sum()) for c in cands]  # CPT rows already carry the 1.5x
    df = df.sort_values("avg_top10", ascending=False)
    pd.set_option("display.width", 250, "display.max_colwidth", 110)
    print("\nTOP 15 by average P(top10%) across scenarios/fields:")
    print(df.head(15).round(1).to_string())
    print("\nTOP 8 by WORST-case P(top10%):")
    print(df.sort_values("min_top10", ascending=False).head(8).round(1).to_string())
    df.to_csv(R / "analysis/showdown_own/best_single_results.csv")
    # structure-level summary
    df["cpt"] = df.desc.str.extract(r"CPT (\S+)")
    df["split"] = df.desc.str.extract(r"\[(.*?)\]")
    df["hasK"] = df.desc.str.contains(r"\(K\)")
    df["hasD"] = df.desc.str.contains(r"\(D\)")
    print("\nBy captain (best 3 lineups' mean):"); print(df.groupby("cpt").avg_top10.agg(lambda x: x.nlargest(3).mean()).sort_values(ascending=False).round(1).head(10).to_string())
    print("\nBy kicker/DST presence (top-50 mean):"); print(df.head(50).groupby(["hasK", "hasD"]).avg_top10.agg(["size", "mean"]).round(1).to_string())
    print("\nBy split (top-50 mean):"); print(df.head(50).groupby("split").avg_top10.agg(["size", "mean"]).round(1).to_string())
    return df, P, cands


if __name__ == "__main__":
    main(sys.argv[1])
