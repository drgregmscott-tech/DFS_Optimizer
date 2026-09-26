"""Step 3: production showdown-ownership features (oms.build_features: noisy-ILP exposure) on the REPLAYED pools
(our projections), joined to realized CPT/FLEX ownership. Also caches the 4 real 2026 slates (oms._training_frame()).
Outputs (gitignored): data/fc_history/derived/showdown/own_feats_ourproj[_<tag>].parquet, own_feats_real4.parquet
    python analysis/showdown_history/sd_features.py [--tag qb] [--workers 6]"""
import argparse, glob, sys, warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
R = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(R / "scripts"))
SD = R / "data/fc_history/derived/showdown"


def one(path):
    import ownership_model_showdown as oms
    pool = pd.read_csv(path, dtype={"player_id": str})
    f = oms.build_features(pool)
    keep = ["slate", "season", "week", "player_id", "player_name", "position", "team", "salary", "roster_role",
            "final_projection", "sigma", "inactive_out"]
    out = pd.concat([pool[keep], f], axis=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", default="qb"); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--real", action="store_true")
    a = ap.parse_args()
    if a.real:
        import ownership_model_showdown as oms
        rl = oms._training_frame(); rl.to_parquet(SD / "own_feats_real4.parquet"); print("real4", rl.shape); sys.exit()
    files = sorted(glob.glob(str(SD / f"ourproj_{a.tag}" / "proj_*.csv")))
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(one, files))
    d = pd.concat(res, ignore_index=True)
    M = pd.read_parquet(SD / "sd_id_map.parquet")[["slate", "player_id", "cpt_own", "flex_own", "proj", "Player"]]
    d = d.merge(M, on=["slate", "player_id"], how="left")
    assert d.cpt_own.notna().all(), d[d.cpt_own.isna()][["slate", "player_name"]]
    d["own"] = np.where(d.role == "CPT", d.cpt_own, d.flex_own)
    d["year"] = d.season
    name = "own_feats_ourproj.parquet" if a.tag == "qb" else f"own_feats_ourproj_{a.tag}.parquet"
    d.to_parquet(SD / name); print("wrote", name, d.shape, d.slate.nunique())
