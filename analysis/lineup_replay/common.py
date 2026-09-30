"""Shared helpers for the lineup replay (2026 old-vs-new and FC-history construction test)."""
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

# SE3Max Pool (100) preset, data/optimizer_presets.json se3max_pool
PRESET = dict(n_lineups=100, max_exposure_pct=0.5, uniqueness=1, randomization_pct=20.0,
              stack_mode="qb", stack_size=2, stack_positions={"WR", "TE"}, bring_back=True, lam=0.0)


def norm(s):
    s = str(s).lower()
    s = re.sub(r"[.'’]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(s.split())


def build_pool(pool_df, seed, tag, **overrides):
    """Run optimizer.build_multi_lineup on an in-memory pool (writes it to a private temp OUTPUT_DIR)."""
    import optimizer
    d = tempfile.mkdtemp(prefix="lr_")
    sid = f"lr_{tag}"
    pool_df.to_csv(os.path.join(d, f"final_projections_dk_{sid}.csv"), index=False)
    optimizer.OUTPUT_DIR = Path(d)
    kw = dict(PRESET)
    kw.update(overrides)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        L, _, n = optimizer.build_multi_lineup("dk", sid, seed=seed, **kw)
    return L, n


def lineup_table(L, pool):
    """One row per lineup: player keys + structure features."""
    p = pool.drop_duplicates("player_id").set_index("player_id")
    out = []
    for lid, g in L.groupby("lineup_id"):
        g = g.copy()
        g["opp"] = g.player_id.map(p["opponent"])
        g["own"] = g.player_id.map(p["estimated_ownership_pct"]).fillna(0.0)
        qb = g[g.position == "QB"].iloc[0]
        stack = int(((g.team == qb.team) & g.position.isin(["WR", "TE"])).sum())
        bb = int(((g.team == qb.opp) & ~g.position.isin(["QB", "DST"])).sum())
        dst = g[g.position == "DST"].iloc[0]
        skill = g[~g.position.isin(["DST"])]
        dst_conf = int((skill.team == dst.opp).sum())
        flex = g[g.roster_slot == "FLEX"].iloc[0].position if "roster_slot" in g else None
        sal = g.salary
        out.append(dict(lineup_id=lid, pids=tuple(g.player_id), proj=float(g.projection.sum()),
                        own=float(g.own.sum()), salary=int(sal.sum()), stack=stack, bb=bb,
                        dst_conf=dst_conf, flex=flex, dst_sal=int(dst.salary), dst_team=dst.team,
                        punts=int(((sal <= 4000) & (g.position != "DST")).sum()),
                        studs=int(((sal >= 7000) & (g.position != "DST")).sum()),
                        qb_team=qb.team))
    return pd.DataFrame(out)


# ------------------------------------------------------------------ selection rules (pre-game info only)
def pick(T, rule):
    if T.empty:
        return None
    if rule == "top_proj":
        return T.sort_values("proj", ascending=False).iloc[0]
    if rule == "se3_process":  # current SE3max review step 3: full QB+2+bring-back structure, then projection
        S = T[(T.stack >= 2) & (T.bb >= 1)]
        return (S if len(S) else T).sort_values("proj", ascending=False).iloc[0]
    if rule.startswith("own_top"):  # highest modeled ownership among the top-k projected
        k = int(rule[7:])
        return T.sort_values("proj", ascending=False).head(k).sort_values("own", ascending=False).iloc[0]
    if rule == "no_dst_conf":
        S = T[(T.stack >= 2) & (T.bb >= 1) & (T.dst_conf == 0)]
        return (S if len(S) else T).sort_values("proj", ascending=False).iloc[0]
    raise ValueError(rule)


RULES = ["top_proj", "se3_process", "own_top5", "own_top10", "own_top20", "no_dst_conf"]
