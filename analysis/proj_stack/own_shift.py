"""Ownership implication (note only): re-score wk3 DK main ownership with refit-stack projections.
Reads output/final_projections_dk_dk_classic_wk3_main_27Sep2026.csv (read only; nothing written to output/).
final_new = final - old stack_delta + new delta (props-matched rows get 0.5x delta, as in production).
    python analysis/proj_stack/own_shift.py
"""
import json, os, sys
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(R, "scripts"))
import projection_stack as ps  # noqa: E402
import build_projections as bp  # noqa: E402

F = os.path.join(R, "output/final_projections_dk_dk_classic_wk3_main_27Sep2026.csv")


def delta(df, art):
    S = ps.apply_stack(df, "engine_projection", "dk", 2026, 3, art)
    e = df.engine_projection.astype(float)
    ok = S.notna() & (e > 0)
    return (S.clip(lower=0.5 * e, upper=1.8 * e) - e).where(ok, 0.0)


def main():
    df = pd.read_csv(F, dtype={"player_id": str})
    d_old = delta(df, ps.load_artifact("dk"))
    ratio = (df.stack_delta / d_old.replace(0, np.nan))
    matched = (ratio - 0.5).abs() < 0.02
    print(f"old delta reproduced: unmatched {((df.stack_delta - d_old).abs() < 0.02).mean():.3f}, props-matched(0.5x) {matched.mean():.3f}")
    new_art = json.load(open(os.path.join(R, "data/projection_stack_dk_refit_2026-09-26.json")))
    d_new = delta(df, new_art)
    share = np.where(matched, 0.5, 1.0)
    base = df.drop(columns=[c for c in df.columns if c in ("chalk_score", "estimated_ownership_pct") or c.startswith("estimated_ownership_pct_heuristic")])
    res = {}
    for name, fin in [("old", df.final_projection), ("refit", (df.final_projection - df.stack_delta + share * d_new).clip(lower=0))]:
        x = base.copy(); x["final_projection"] = fin.where(df.final_projection > 0, 0.0)
        o = bp.add_ownership_columns(x, "dk")
        res[name] = o.set_index("player_id")[["final_projection", "estimated_ownership_pct"]]
    t = df.set_index("player_id")[["player_name", "position", "salary", "estimated_ownership_pct"]].rename(columns={"estimated_ownership_pct": "own_file"})
    t = t.join(res["old"].add_suffix("_old")).join(res["refit"].add_suffix("_new"))
    for pos in ps.POSITIONS:
        s = t[t.position == pos].sort_values("final_projection_old", ascending=False).head(8 if pos == "QB" else 5)
        print(f"\n{pos}\n" + s.round(1).to_string())


if __name__ == "__main__":
    main()
