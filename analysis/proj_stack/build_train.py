"""Stack training data on GUARDED history (QB1 rebuild, analysis/proj_qb/run_qb1.py).
Research only; no FC data in this file. Output (FC-derived salaries/scores -> git-ignored):
  data/fc_history/derived/proj_stack/train.csv  (all DK main-slate rows, all positions, 88 slates)
Features recomputed exactly as at runtime: projection_stack.usage_features(season, week) (games strictly
before the slate week, rolling across seasons), salary/1000, engine_projection (pre-stack, guard on).
Sanity check: old artifact re-applied via apply_stack+combine must reproduce the rebuild's final_projection.
    python analysis/proj_stack/build_train.py
"""
import glob, os, sys
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(R, "scripts"))
import projection_stack as ps  # noqa: E402

DER = os.path.join(R, "data/fc_history/derived")
OUT = os.path.join(DER, "proj_stack")
POS = ["QB", "RB", "WR", "TE", "DST"]


def main():
    fc = pd.read_csv(os.path.join(DER, "fc_master_mapped.csv"), low_memory=False, dtype={"player_id": str})
    fc = fc[(fc.site == "dk") & (fc.slate_kind == "classic") & (fc.slate_raw == "main") & fc.player_id.notna() & fc.pos.isin(POS)]
    fc = fc.drop_duplicates(["season", "week", "player_id"])[["season", "week", "player_id", "pos", "team", "salary", "score"]]
    played = set()
    for s in range(2021, 2027):
        w = pd.read_parquet(os.path.join(R, f"data/weekly_stats_{s}.parquet"), columns=["player_id", "season", "week"])
        played |= set(zip(w.season, w.week, w.player_id))
    fc["dnp"] = [(p != "DST") and ((s, w, i) not in played) for s, w, i, p in zip(fc.season, fc.week, fc.player_id, fc.pos)]
    fc["act"] = fc.score.fillna(0.0).where(~fc.dnp, 0.0)
    art = ps.load_artifact("dk")
    rows = []
    for f in sorted(glob.glob(os.path.join(DER, "proj_qb/ourproj_qb1/proj_*.csv"))):
        d = pd.read_csv(f, dtype={"player_id": str})
        s, w = int(d.season.iloc[0]), int(d.week.iloc[0])
        uf = ps.usage_features(s, w).set_index("player_id")
        for c in ps.USAGE_COLS:
            d[c] = d.player_id.map(uf[c]) if c in uf.columns else np.nan
        d["usage_missing"] = d[ps.USAGE_COLS[0]].isna()
        # runtime fill for missing usage = artifact usage_fill (production); keep raw NaN + fill both
        S = ps.apply_stack(d, "engine_projection", "dk", s, w, art)
        e = d.engine_projection.astype(float)
        d["old_recalc"] = ps.combine(e, e, S, pd.Series(False, index=d.index)).where(S.notna(), d.final_projection)
        rows.append(d)
    A = pd.concat(rows, ignore_index=True)
    err = (A.old_recalc - A.final_projection).abs()
    print(f"rows {len(A)} slates {A.groupby(['season','week']).ngroups}; old-stack reproduction max|err| {err.max():.4f}, "
          f"share>0.01: {(err > 0.01).mean():.4f}")
    keep = ["season", "week", "player_id", "player_name", "position", "team", "salary", "engine_projection",
            "final_projection", "stack_delta", "statline_p10", "statline_p90", "estimated_ownership_pct",
            "proj_pass_att", "usage_missing"] + ps.USAGE_COLS
    A = A[keep].merge(fc[["season", "week", "player_id", "pos", "salary", "act", "dnp"]].rename(columns={"salary": "fc_salary"}),
                      on=["season", "week", "player_id"], how="inner")
    A.to_csv(os.path.join(OUT, "train.csv"), index=False)
    print(A.groupby("season").size().to_dict(), "positions", A.position.value_counts().to_dict())


if __name__ == "__main__":
    main()
