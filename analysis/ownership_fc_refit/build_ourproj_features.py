"""Ownership features for FC-history slates using OUR reconstructed projection
(run_ourproj.py) instead of FC's. Same pipeline as build_fc_features.py
(heuristic -> optimizer exposure -> om.build_features), with final_projection
and sigma from data/fc_history/derived/ourproj/proj_{season}_wk{week}.csv.

Pool handling (mirrors production, where OUT players are zeroed by status news):
  * FC players with no gsis id or no our-projection row -> projection 0 (dropped
    from the model, like production's 0-projection players).
  * Skill players with no nflverse weekly_stats row that week (inactive/DNP)
    -> projection 0. Proxy for pre-lock inactive news; slightly optimistic
    (late scratches were known only near lock).
Writes data/fc_history/derived/fc_own_features_ourproj.parquet (FC-derived, git-ignored).
"""
import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "analysis/ownership_fc_refit"))
import ownership_model as om  # noqa: E402
import build_projections as bp  # noqa: E402
from build_fc_features import slate_frame  # noqa: E402

DER = REPO / "data/fc_history/derived"


def played_ids():
    out = {}
    for s in range(2021, 2027):
        w = pd.read_parquet(REPO / f"data/weekly_stats_{s}.parquet", columns=["player_id", "week"])
        for wk, g in w.groupby("week"):
            out[(s, int(wk))] = set(g["player_id"])
    return out


def main():
    d = pd.read_csv(DER / "fc_master_mapped.csv", dtype={"player_id": str}, low_memory=False)
    d = d[(d["contest"] == "single_entry") & (d["slate_kind"] == "classic")]
    played = played_ids()
    frames, t0 = [], time.time()
    for sf, g in d.groupby("source_file"):
        s, w = int(g["season"].iloc[0]), int(g["week"].iloc[0])
        p = pd.read_csv(DER / f"ourproj/proj_{s}_wk{w}.csv", dtype={"player_id": str})
        p = p.drop_duplicates("player_id").set_index("player_id")
        df = slate_frame(g)
        own_total_all = df["own"].sum()
        df["fc_proj"] = df["final_projection"]
        df["fc_sigma"] = df["sigma"]
        df["final_projection"] = df["player_id"].map(p["final_projection"]).astype(float).fillna(0.0)
        df["sigma"] = df["player_id"].map(p["sigma"]).astype(float).fillna(0.0)
        df["has_ourproj"] = df["player_id"].isin(p.index)
        pl = played.get((s, w), set())
        df["played"] = (df["position"] == "DST") | df["player_id"].isin(pl)
        df.loc[~df["played"], "final_projection"] = 0.0
        df = bp.add_ownership_columns(df, "dk", layered=False)
        df = df[df["final_projection"] > 0].copy()
        df["position_group"] = df["position"]
        exposure = om.optimizer_exposure(df, "dk")
        feats = om.build_features(df, exposure).drop(columns=["pub_val", "ffc_listed", "l_ffc"])
        df = pd.concat([df, feats], axis=1)
        pos = df["position"]
        df["sal_rank"] = df.groupby(pos)["salary"].rank(ascending=False, method="min")
        df["val"] = df["final_projection"] / (df["salary"] / 1000.0)
        df["val_rank"] = df.groupby(pos)["val"].rank(ascending=False, method="min")
        df["proj_rank"] = df.groupby(pos)["final_projection"].rank(ascending=False, method="min")
        df["n_pos"] = df.groupby(pos)["player_id"].transform("size")
        df["season"], df["week"], df["slate_id"] = s, w, sf
        df["own_total_all"] = own_total_all
        frames.append(df)
        print(f"{sf}: {len(df)} kept, own kept {df['own'].sum():.0f}/{own_total_all:.0f} ({time.time()-t0:.0f}s)", flush=True)
    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(DER / "fc_own_features_ourproj.parquet")
    print(f"wrote {len(out)} rows")


if __name__ == "__main__":
    main()
