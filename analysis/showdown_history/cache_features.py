"""Cache production showdown-ownership features (build_features, FC Proj as projection) per FC history slate.
Output: data/fc_history/derived/showdown/prod_feats.parquet (gitignored)."""
import sys, warnings
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
R = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(R / "scripts"))
import ownership_model_showdown as oms

def one(a):
    s, g = a
    g = g.reset_index(drop=True); g["player_id"] = [f"p{i}" for i in range(len(g))]
    rows = []
    for role, m in (("CPT", 1.5), ("FLEX", 1.0)):
        rows.append(pd.DataFrame(dict(player_id=g.player_id, roster_role=role, team=g.Team, position=g.pos,
            salary=g.sal * m, final_projection=g.proj * m, sigma=g.stdv.fillna(0) * m,
            own=np.where(role == "CPT", g.cpt_own, g.flex_own), season=g.season if "season" in g else 0)))
    pool = pd.concat(rows, ignore_index=True)
    f = oms.build_features(pool)
    out = pd.concat([pool[["player_id", "roster_role", "position", "own", "season"]], f], axis=1)
    out["slate"] = s
    return out

if __name__ == "__main__":
    df = pd.read_parquet(R / "data/fc_history/derived/showdown/players.parquet")
    with ProcessPoolExecutor(6) as ex:
        res = list(ex.map(one, list(df.groupby("slate"))))
    pd.concat(res).to_parquet(R / "data/fc_history/derived/showdown/prod_feats.parquet")
    print("done", len(res))
