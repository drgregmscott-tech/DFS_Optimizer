"""Re-run of the chalk-anchor + pivot investigation after the 2026-09-23 data fixes.

WHY: three things changed underneath the earlier numbers
  (a) real ownership: replay_validation.load_real() builds own_map with
      drop_duplicates("k") over the contest export's player table, which lists a
      player once PER ROSTER POSITION (e.g. "RB" row and "FLEX" row). Keeping the
      first row drops the FLEX share -- on ALL 6 slates, not only wk2 (every slate
      sums to ~797% instead of ~897%; sometimes it even keeps the FLEX row only).
      This is the same class of bug as the data/ownership_actual_log.csv wk2 fix,
      but it lives in the oracle's own loader, so the oracle never read the log.
      "corrected" here = sum of %Drafted across a player's rows.
  (b) projections: statline_model reconcile fix -> committed output/*.csv are pre-fix.
  (c) ownership model: FLEX budget split (RB49/WR34/TE17) + an artifact that was fit
      in-sample on the buggy wk2 truth.

Methods (all grade against the same real contest results; cash = top 25%):
  oracle   pivot_off_chalk.py: real most-duplicated lineup as anchor, same-position
           pivots to LOWER REAL post-lock ownership, worst_top25 pick. (real own: buggy|corr)
  live_v1  pivot_off_chalk_live.py: points-max ILP anchor, pivots on model own.
  shipped  recommend_lineup.py / worst_top25_realstack (ownership only enters via the
           simulated field).
  live_v2  shipped pick as anchor + relative model-own pivots.
  live_v3  shipped pick as anchor + absolute <10% model-own pivots.
All scoring code is imported from the original scripts (not re-implemented).

Projection/ownership variants (each a directory of 6 final_projections files; the
optimizer's OUTPUT_DIR is pointed at it for the run):
  orig          committed output/ files (pre-fix projections, ownership as shipped then)
  fixed_lowo    fixed projections; heuristic w/ current FLEX split; layered model refit
                LEAVE-ONE-WEEK-OUT on corrected truth (out-of-sample for the graded slate)
  fixed_shipped fixed projections; current production layering = shipped artifact
                data/ownership_model_dk.json (fit on these 6 slates -> IN-SAMPLE)

"Fixed projections" = current code rebuilt per slate (wk1: statline rebuild; wk2: rebuilt
with build_projections_statline.load_real_team_for_week patched to "week not played",
because the current code otherwise applies decision #4b and zeroes every player with no
real week-2 stat row -- 230/145/83 players on wk2 main/early/afternoon, 100% of whom
scored 0: a direct outcome leak). Pool membership is then forced to match the committed
lock-time file (a player with final_projection 0 there is 0 here too), so old vs new
differ only in projection/ownership values.

usage:
  python analysis/classic_diag/pivot_rerun_corrected_ownership.py prep --work W --wk1-src D1 --wk2-src D2
  python analysis/classic_diag/pivot_rerun_corrected_ownership.py run --work W --variant V [--seed 3]
  python analysis/classic_diag/pivot_rerun_corrected_ownership.py summary --work W
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(HERE))
_ARGV, sys.argv = sys.argv, sys.argv[:1]   # the imported scripts parse sys.argv[1:] as ints at import time
import optimizer  # noqa: E402
import replay_validation as rv  # noqa: E402
import best_lineup_classic as blc  # noqa: E402
import chalk_lineup_analysis as chalk  # noqa: E402
import pivot_off_chalk as poc  # noqa: E402
import pivot_off_chalk_live as live1  # noqa: E402
from pivot_off_chalk_live_v3 import best_alt_per_slot_absolute  # noqa: E402
sys.argv = _ARGV

N_SIMS, FIELD_N, N_CAND, OWN_THRESH = 800, 6000, 80, 10.0
SLATE_IDS = {lab: sid for lab, (_, sid) in rv.SLATES.items()}


# ----------------------------------------------------------------------------- real data
def load_real_both(f):
    """(fpts_map, own_buggy, own_corr, real_points). own_buggy is exactly what
    rv.load_real returns (first row per player); own_corr sums all roster-position rows."""
    fpts_map, own_buggy, real_points, _ = rv.load_real(f)
    df = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    tab = df[["Player", "%Drafted"]].dropna(subset=["Player"]).copy()
    tab["k"] = tab.Player.map(rv.norm)
    tab["own"] = tab["%Drafted"].astype(str).str.rstrip("%").astype(float)
    own_corr = tab.groupby("k")["own"].sum().to_dict()
    return fpts_map, own_buggy, own_corr, real_points


# ----------------------------------------------------------------------------- prep
def _git_show(path):
    return subprocess.run(["git", "show", f"HEAD:{path}"], cwd=REPO, capture_output=True,
                          text=True, check=True, encoding="utf-8").stdout


def prep(work, wk1_src, wk2_src):
    import io
    import build_projections as bp
    import ownership_model as om
    import ownership_heuristic as oh
    import fit_ownership_model as fom

    work = Path(work)
    for v in ("orig", "fixed_lowo", "fixed_shipped"):
        (work / v).mkdir(parents=True, exist_ok=True)
    log = pd.read_csv(REPO / "data/ownership_actual_log.csv", dtype={"player_id": str})
    budgets = oh.compute_position_slot_budgets("dk")
    shipped = json.load(open(REPO / "data/ownership_model_dk.json"))

    frames, bases = [], {}
    for lab, sid in SLATE_IDS.items():
        name = f"final_projections_dk_{sid}.csv"
        orig_txt = _git_show(f"output/{name}")
        (work / "orig" / name).write_text(orig_txt, encoding="utf-8")
        orig = pd.read_csv(io.StringIO(orig_txt), dtype={"player_id": str, "site_player_id": str})
        src = Path(wk1_src if lab.startswith("wk1") else wk2_src) / name
        df = pd.read_csv(src, dtype={"player_id": str, "site_player_id": str})
        dead = set(orig.loc[orig.final_projection <= 0, "player_id"])
        if "injury_status" in orig:
            dead |= set(orig.loc[orig.injury_status == "OUT", "player_id"])
        df.loc[df.player_id.isin(dead) | ~df.player_id.isin(orig.player_id), "final_projection"] = 0.0
        df = df.drop(columns=["chalk_score", "estimated_ownership_pct",
                              "estimated_ownership_pct_heuristic"], errors="ignore")
        df = bp.add_ownership_columns(df, "dk", layered=False)   # heuristic, current FLEX split
        bases[sid] = df
        g = log[log.slate_id == sid]
        f = df[df.final_projection > 0].copy()
        f["own"] = f.player_id.map(g.drop_duplicates("player_id").set_index("player_id")["actual_ownership_pct"]).fillna(0.0)
        f["position_group"] = np.where(f.position.isin(list(om.DEFENSE_LABELS)), "DST", f.position)
        feats = om.build_features(f, om.optimizer_exposure(f, "dk"))
        f = pd.concat([f, feats], axis=1)
        f["slate_id"], f["week"] = sid, int(g.week.iloc[0])
        frames.append(f)
        print(f"prep {lab}: {int((df.final_projection > 0).sum())} live players "
              f"(orig {int((orig.final_projection > 0).sum())})", flush=True)
    F = pd.concat(frames, ignore_index=True)
    F["lowo"] = 0.0
    for w in sorted(F.week.unique()):
        art = fom.fit(F[F.week != w])
        F.loc[F.week == w, "lowo"] = fom.predict_slates(F[F.week == w], art, budgets)
    F["shipped"] = fom.predict_slates(F, shipped, budgets)
    for sid, df in bases.items():
        for v, col in (("fixed_lowo", "lowo"), ("fixed_shipped", "shipped")):
            m = F[F.slate_id == sid].set_index("player_id")[col]
            out = df.copy()
            out["estimated_ownership_pct_heuristic"] = out["estimated_ownership_pct"]
            out["estimated_ownership_pct"] = out.player_id.map(m).fillna(0.0)
            out.to_csv(work / v / f"final_projections_dk_{sid}.csv", index=False)
    # ownership accuracy vs corrected truth, for the report
    for lab, sid in SLATE_IDS.items():
        o = pd.read_csv(work / "orig" / f"final_projections_dk_{sid}.csv", dtype={"player_id": str})
        g = F[F.slate_id == sid].copy()
        g["old"] = g.player_id.map(o.set_index("player_id").estimated_ownership_pct).fillna(0.0)
        msk = g.own >= 5
        print(lab, " ".join(f"{c}: r={np.corrcoef(g[c][msk], g.own[msk])[0, 1]:.2f} "
                            f"mae={(g[c] - g.own)[msk].abs().mean():.1f}" for c in ("old", "lowo", "shipped")))


# ----------------------------------------------------------------------------- run
def pick(P, field, masks, seed):
    _, worst25 = poc.score_masks(P, field, masks, N_SIMS, seed=seed)
    b = int(worst25.argmax())
    return b, worst25


def rec(method, own_src, lab, P, mask, fpts_map, real_points, own_corr, n_cands, is_anchor, w25):
    ks = [P["k"].iloc[i] for i in mask]
    g = rv.grade(ks, fpts_map, real_points)
    return dict(method=method, own_src=own_src, slate=lab, cash=bool(g["cash"]), pct=g["pct"], pts=g["pts"],
                n_cands=n_cands, is_anchor=is_anchor, worst25=float(w25),
                real_own_sum=float(sum(own_corr.get(k, 0.0) for k in ks)),
                lineup="|".join(sorted(P.player_name.iloc[i] for i in mask)))


def run(work, variant, seed):
    optimizer.OUTPUT_DIR = Path(work) / variant
    rows = []
    for lab, (f, sid) in rv.SLATES.items():
        t0 = time.time()
        fpts_map, own_buggy, own_corr, real_points = load_real_both(f)
        # oracle + v1: field seed=1, scoring seed=3 (as in the original scripts)
        P, field = blc.build_pool_and_field("dk", sid, field_n=FIELD_N, seed=1)
        P["k"] = P.player_name.map(rv.norm)
        amask, _, _ = poc.anchor_mask("dk", sid, f, P)
        for own_src, om_ in (("real_buggy", own_buggy), ("real_corr", own_corr)):
            combos = list(poc.enumerate_pivots(P, amask, poc.best_alt_per_slot(P, amask, om_)))
            masks = [amask] + [c[0] for c in combos]
            b, w = pick(P, field, masks, seed)
            rows.append(rec("oracle", own_src, lab, P, masks[b], fpts_map, real_points, own_corr, len(masks), b == 0, w[b]))
        lmask = live1.build_live_anchor("dk", P)
        combos = list(live1.enumerate_pivots(P, lmask, live1.best_alt_per_slot(P, lmask)))
        masks = [lmask] + [c[0] for c in combos]
        b, w = pick(P, field, masks, seed)
        rows.append(rec("live_v1", "model", lab, P, masks[b], fpts_map, real_points, own_corr, len(masks), b == 0, w[b]))
        # shipped + v2/v3: candidate pool seed, field seed=3
        out, cmasks, P2 = blc.score("dk", sid, n_candidates=N_CAND, field_n=FIELD_N, n_sims=N_SIMS,
                                    seed=seed, return_detail=True)
        P2["k"] = P2.player_name.map(rv.norm)
        v = np.where(out["is_real_stack"].to_numpy(), out["worst_top25"].to_numpy(), -np.inf)
        ai = int(v.argmax())
        smask = cmasks[ai]
        rows.append(rec("shipped", "model_field", lab, P2, smask, fpts_map, real_points, own_corr, len(cmasks),
                        True, out["worst_top25"].iloc[ai]))
        _, field2 = blc.build_pool_and_field("dk", sid, field_n=FIELD_N, seed=seed)
        for meth, alts in (("live_v2", live1.best_alt_per_slot(P2, smask)),
                           ("live_v3", best_alt_per_slot_absolute(P2, smask, OWN_THRESH))):
            combos = list(live1.enumerate_pivots(P2, smask, alts))
            masks = [smask] + [c[0] for c in combos]
            b, w = pick(P2, field2, masks, seed)
            rows.append(rec(meth, "model", lab, P2, masks[b], fpts_map, real_points, own_corr, len(masks), b == 0, w[b]))
        print(f"{variant} {lab} done {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    df["variant"], df["seed"] = variant, seed
    df.to_csv(Path(work) / f"results_{variant}_s{seed}.csv", index=False)
    print(df.drop(columns="lineup").to_string(index=False))


# ----------------------------------------------------------------------------- summary
def clopper_pearson(k, n, a=0.05):
    from math import comb

    def cdf(x, p):  # P(X <= x)
        return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x + 1))

    def solve(f):  # f increasing in p on [0,1], find root by bisection
        lo_, hi_ = 0.0, 1.0
        for _ in range(60):
            mid = (lo_ + hi_) / 2
            lo_, hi_ = (mid, hi_) if f(mid) < 0 else (lo_, mid)
        return (lo_ + hi_) / 2
    lo = solve(lambda p: (1 - cdf(k - 1, p)) - a / 2) if k > 0 else 0.0   # P(X>=k)=a/2
    hi = solve(lambda p: (a / 2) - cdf(k, p)) if k < n else 1.0            # P(X<=k)=a/2
    return lo, hi


def summary(work):
    df = pd.concat([pd.read_csv(p) for p in Path(work).glob("results_*.csv")], ignore_index=True)
    rng = np.random.default_rng(0)
    rows = []
    for (v, s, m, o), g in df.groupby(["variant", "seed", "method", "own_src"]):
        g = g.set_index("slate").loc[list(SLATE_IDS)]
        bs = [rng.choice(g.pct.values, 6).mean() for _ in range(5000)]
        lo, hi = clopper_pearson(int(g.cash.sum()), 6)
        rows.append(dict(variant=v, seed=s, method=m, own=o, cash=f"{int(g.cash.sum())}/6",
                         cash_ci=f"{lo:.2f}-{hi:.2f}", mean_pct=round(g.pct.mean(), 3),
                         pct_ci=f"{np.percentile(bs, 2.5):.2f}-{np.percentile(bs, 97.5):.2f}",
                         pivots_used=int((~g.is_anchor).sum()),
                         per_slate=" ".join(f"{p:.2f}{'*' if c else ''}" for p, c in zip(g.pct, g.cash))))
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).to_string(index=False))
    # paired comparisons on fixed_lowo seed 3 (per-slate percentile differences)
    base = df[(df.variant == "fixed_lowo") & (df.seed == 3)]
    if len(base):
        piv = base.assign(key=base.method + ":" + base.own_src).pivot(index="slate", columns="key", values="pct")
        ref = "shipped:model_field"
        for c in piv.columns:
            if c == ref:
                continue
            d = (piv[c] - piv[ref]).values
            bs = [rng.choice(d, 6).mean() for _ in range(5000)]
            print(f"{c:22s} - shipped: mean {d.mean():+.3f}  95% boot {np.percentile(bs, 2.5):+.3f}..{np.percentile(bs, 97.5):+.3f}  "
                  f"wins {int((d > 0).sum())}/6 ties {int((d == 0).sum())}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "run", "summary"])
    ap.add_argument("--work", required=True)
    ap.add_argument("--variant")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--wk1-src")
    ap.add_argument("--wk2-src")
    a = ap.parse_args()
    if a.cmd == "prep":
        prep(a.work, a.wk1_src, a.wk2_src)
    elif a.cmd == "run":
        run(a.work, a.variant, a.seed)
    else:
        summary(a.work)
