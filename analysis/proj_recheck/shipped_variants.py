"""Shipped-method (worst_top25_realstack) re-grade on projection variants, reusing the exact scoring path of
analysis/classic_diag/pivot_rerun_corrected_ownership.py run() -> "shipped" branch (blc.score + rv.grade).

make : build variant dirs under WORK from WORK/../pr/{orig,fixed_lowo} (ownership columns kept as-is)
  fixed_ns      fixed_lowo with final_projection := engine_projection (no stack)
  fixed_noblow  fixed_lowo with the moved-team reconcile blow-ups (proj_pass_att > 50) set to OLD projection
  orig_nzK / fixed_nzK  final_projection * exp(N(0, 0.05)) per player, K = 1..3 (perturbation test)
run  : python shipped_variants.py run --work W --variant V [--seed 3]
"""
import argparse, shutil, sys, time
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "classic_diag"))
import pivot_rerun_corrected_ownership as pr  # noqa: E402  (imports optimizer, rv, blc exactly as the harness)


def make(work):
    work = Path(work); src = work.parent / "pr"
    for sid in pr.SLATE_IDS.values():
        n = f"final_projections_dk_{sid}.csv"
        o = pd.read_csv(src / "orig" / n, dtype={"player_id": str, "site_player_id": str})
        f = pd.read_csv(src / "fixed_lowo" / n, dtype={"player_id": str, "site_player_id": str})
        live = f.final_projection > 0
        def w(v, d):
            (work / v).mkdir(parents=True, exist_ok=True); d.to_csv(work / v / n, index=False)
        d = f.copy(); d.loc[live, "final_projection"] = d.loc[live, "engine_projection"]; w("fixed_ns", d)
        d = f.copy(); b = live & (d.proj_pass_att > 50)
        d.loc[b, "final_projection"] = d.loc[b, "player_id"].map(o.set_index("player_id").final_projection)
        print(sid, "blowups reset:", list(d.loc[b, "player_name"])); w("fixed_noblow", d)
        for k in (1, 2, 3):
            for v, base in (("orig", o), ("fixed", f)):
                rng = np.random.default_rng(100 * k + hash(sid) % 97)
                d = base.copy(); d["final_projection"] = d.final_projection * np.exp(rng.normal(0, 0.05, len(d)))
                w(f"{v}_nz{k}", d)


def run(work, variant, seed):
    pr.optimizer.OUTPUT_DIR = Path(work) / variant
    rows = []
    for lab, (f, sid) in pr.rv.SLATES.items():
        t0 = time.time()
        fpts_map, _, own_corr, real_points = pr.load_real_both(f)
        out, cmasks, P2 = pr.blc.score("dk", sid, n_candidates=pr.N_CAND, field_n=pr.FIELD_N, n_sims=pr.N_SIMS,
                                       seed=seed, return_detail=True)
        P2["k"] = P2.player_name.map(pr.rv.norm)
        v = np.where(out["is_real_stack"].to_numpy(), out["worst_top25"].to_numpy(), -np.inf)
        ai = int(v.argmax())
        r = pr.rec("shipped", "model_field", lab, P2, cmasks[ai], fpts_map, real_points, own_corr, len(cmasks), True,
                   out["worst_top25"].iloc[ai])
        # also: where would the ORIG-projection lineup rank among this variant's candidates? (not needed) -> proj pts
        r["proj_pts"] = float(P2.final_projection.iloc[list(cmasks[ai])].sum())
        rows.append(r)
        print(f"{variant} {lab} {r['pct']:.3f} {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(rows); df["variant"], df["seed"] = variant, seed
    df.to_csv(Path(work) / f"ship_{variant}_s{seed}.csv", index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "run"]); ap.add_argument("--work", required=True)
    ap.add_argument("--variant"); ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    make(a.work) if a.cmd == "make" else run(a.work, a.variant, a.seed)
