"""Matchup-factor ablation on FC-history regenerated projections (2021-2026).
Reads FC-derived files (git-ignored); writes results to data/fc_history/derived/matchup_history/.
"""
import numpy as np, pandas as pd
from pathlib import Path
from scipy.stats import spearmanr, pearsonr
REPO = Path(__file__).resolve().parents[2]
DER = REPO / "data/fc_history/derived"
OUT = DER / "matchup_history"; OUT.mkdir(exist_ok=True)
SKILL = ["QB", "RB", "WR", "TE"]
TOPN = {"QB": 6, "RB": 12, "WR": 18, "TE": 6}
rng = np.random.default_rng(0)

act = pd.read_csv(DER / "fc_master_mapped.csv", low_memory=False, dtype={"player_id": str})
act = act[act.player_id.notna() & act.score.notna()].sort_values("contest")
act = act.drop_duplicates(["season", "week", "player_id"])[["season", "week", "player_id", "score"]]

def load(d):
    fs = sorted((DER / d).glob("proj_*.csv"))
    df = pd.concat([pd.read_csv(f, dtype={"player_id": str}) for f in fs])
    return df[df.position.isin(SKILL)]

def scaled_pts(df):
    return (df.proj_pass_yd * .04 + df.proj_pass_td * 4 + df.proj_rush_yd * .1 + df.proj_rush_td * 6
            + df.proj_rec_yd * .1 + df.proj_rec_td * 6)

base = load("ourproj")
key = ["season", "week", "player_id"]
fr = base[key + ["player_name", "position", "team", "salary", "engine_projection", "final_projection", "vegas_factor", "games_played"]].rename(
    columns={"engine_projection": "eng_a0", "final_projection": "fin_a0"})
variants = [v for v in ["k4", "k16", "kq16"] if (DER / f"ourproj_mh_{v}").exists()]
for v in variants:
    d = load(f"ourproj_mh_{v}")
    d = d[key + ["engine_projection", "final_projection", "matchup_factor"]].rename(columns={
        "engine_projection": f"eng_{v}", "final_projection": f"fin_{v}", "matchup_factor": f"mf_{v}"})
    if v == "k4":
        d["S_k4"] = scaled_pts(load("ourproj_mh_k4")).to_numpy()
    fr = fr.merge(d, on=key, how="inner")
fr = fr.merge(act, on=key, how="inner")
fr = fr[fr.fin_a0 > 8].copy()
# exponent sweep via validated emulator (analysis/proj_b1): only yd/td scale with market factor
for a in [0.25, 0.5, 0.75, 1.25]:
    r = fr.mf_k4 ** (a - 1)
    fr[f"eng_a{a}"] = fr.eng_k4 + fr.S_k4 * (r - 1)
    fr[f"fin_a{a}"] = fr[f"eng_a{a}"] + (fr.fin_k4 - fr.eng_k4)
# drop vegas (emulated from baseline): market = vegas only in a0
Sb = scaled_pts(base.set_index(key).loc[pd.MultiIndex.from_frame(fr[key])]).to_numpy()
fr["eng_novegas"] = fr.eng_a0 + Sb * (1 / fr.vegas_factor - 1)
fr["fin_novegas"] = fr.eng_novegas + (fr.fin_a0 - fr.eng_a0)
fr["bucket"] = pd.cut(fr.week, [0, 2, 4, 8, 99], labels=["wk1-2", "wk3-4", "wk5-8", "wk9+"])
fr.to_parquet(OUT / "frame.parquet")
V = ["a0", "a0.25", "a0.5", "a0.75", "k4", "a1.25", "k16", "kq16", "novegas"]
V = [v for v in V if f"fin_{v}" in fr]

def cell_metrics(g, col):
    if len(g) < 6: return None
    n = TOPN[g.position.iat[0]]
    top = g.nlargest(n, col).score.mean()
    return spearmanr(g[col], g.score)[0], pearsonr(g[col], g.score)[0], top

rows = []
for (s, w, p), g in fr.groupby(["season", "week", "position"]):
    for v in V:
        m = cell_metrics(g, f"fin_{v}")
        if m: rows.append(dict(season=s, week=w, position=p, variant=v, sp=m[0], pe=m[1], top=m[2]))
cells = pd.DataFrame(rows)
cells["bucket"] = pd.cut(cells.week, [0, 2, 4, 8, 99], labels=["wk1-2", "wk3-4", "wk5-8", "wk9+"])
cells.to_csv(OUT / "cells.csv", index=False)

def paired(sub, v, ref="a0", metric="sp"):
    p = sub.pivot_table(index=["season", "week", "position"], columns="variant", values=metric)
    d = (p[v] - p[ref]).dropna()
    slates = d.groupby(level=[0, 1]).mean()   # bootstrap over slates
    bs = [rng.choice(slates.values, len(slates)).mean() for _ in range(2000)]
    return d.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5), len(slates)

lines = []
hist = cells[cells.season <= 2025]
for b in ["wk1-2", "wk3-4", "wk5-8", "wk9+"]:
    sub = hist[hist.bucket == b]
    lines.append(f"\n== {b} (2021-25) level: " + ", ".join(f"{v} sp={sub[sub.variant==v].sp.mean():.3f} pe={sub[sub.variant==v].pe.mean():.3f} top={sub[sub.variant==v].top.mean():.2f}" for v in V))
    for v in V:
        if v == "a0": continue
        for m in ["sp", "pe", "top"]:
            mu, lo, hi, n = paired(sub, v, metric=m)
            loso = [paired(sub[sub.season == s], v, metric=m)[0] for s in range(2021, 2026) if (sub.season == s).any()]
            lines.append(f"  {v:8s} {m:3s} d vs a0 {mu:+.4f} [{lo:+.4f},{hi:+.4f}] nslate={n} per-season {' '.join(f'{x:+.3f}' for x in loso)}")
# by position, all weeks, k4 vs a0
lines.append("\n== k4 minus a0 by position x bucket (Spearman) 2021-25")
for p in SKILL:
    lines.append(p + " " + " ".join(f"{b}:{paired(hist[(hist.position==p)&(hist.bucket==b)],'k4')[0]:+.3f}" for b in ["wk1-2", "wk3-4", "wk5-8", "wk9+"]))
# 2026
c26 = cells[cells.season == 2026]
if len(c26):
    lines.append("\n== 2026 wk1-2 (regen): " + ", ".join(f"{v} sp d={paired(c26, v)[0]:+.3f} top d={paired(c26, v, metric='top')[0]:+.2f}" for v in V if v != "a0"))
# calibration slope by position (actual ~ proj), pooled 2021-25, baseline, plus stud compression
h = fr[fr.season <= 2025]
lines.append("\n== calibration (baseline a0 final; slope of actual on proj; within slate-pos Spearman)")
for p in SKILL:
    g = h[h.position == p]
    sl, ic = np.polyfit(g.fin_a0, g.score, 1)
    csp = hist[(hist.position == p) & (hist.variant == "a0")].sp.mean()
    g = g.assign(dec=g.groupby(["season", "week"]).fin_a0.rank(pct=True, ascending=False))
    stud = g[g.dec <= .1]
    lines.append(f"{p}: n={len(g)} slope={sl:.2f} int={ic:+.1f} r={np.corrcoef(g.fin_a0,g.score)[0,1]:.3f} cellSp={csp:.3f} "
                 f"top10% proj={stud.fin_a0.mean():.1f} act={stud.score.mean():.1f}  bottom-half proj={g[g.dec>.5].fin_a0.mean():.1f} act={g[g.dec>.5].score.mean():.1f}")
lines.append(f"\nrows={len(fr)} variants={variants}")
txt = "\n".join(lines); print(txt); (OUT / "results.txt").write_text(txt)
