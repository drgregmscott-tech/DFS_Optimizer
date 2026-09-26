"""Component-level dispersion check: simulated stat sd / yards-TD correlation vs actual residuals
(research only; NO FC data). Reads proj_sigma/frame.parquet (audit.py). Appends to components_report.txt.
    python analysis/proj_sigma/components.py
"""
import os
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(R, "data/fc_history/derived/proj_sigma")
LOG = open(os.path.join(OUT, "components_report.txt"), "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n")
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)

X = pd.read_parquet(os.path.join(OUT, "frame.parquet"))
X = X[X.played & (X.position != "DST") & X.pts_sd.notna()].copy()
PAIRS = {"pass": ("passing_yards", "passing_tds", "proj_pass_yd", "proj_pass_td", "sim_pass_yd", "sim_pass_td"),
         "rush": ("rushing_yards", "rushing_tds", "proj_rush_yd", "proj_rush_td", "sim_rush_yd", "sim_rush_td"),
         "rec": ("receiving_yards", "receiving_tds", "proj_rec_yd", "proj_rec_td", "sim_rec_yd", "sim_rec_td")}
USE = {"QB": ["pass", "rush"], "RB": ["rush", "rec"], "WR": ["rec"], "TE": ["rec"]}
VOL = {"rush": ("carries", "proj_rush_att", "sim_rush_att"), "rec": ("targets", "proj_targets", "sim_targets")}
P("Actual residual sd INCLUDES mean-projection error, so sim_sd > act_resid_sd => sim definitely too dispersed;")
P("sim_sd < act_resid_sd is ambiguous. TD 'poisson_sd' = sqrt(mean proj TD).  corr = within-player yards-TD residual corr.")
rows = []
for pos, comps in USE.items():
    for c in comps:
        ya, ta, yp, tp, ys, ts = PAIRS[c]
        for seas, g in list(X[X.position == pos].groupby("season")) + [("2023+", X[(X.position == pos) & (X.season >= 2023)]), ("all", X[X.position == pos])]:
            g = g[g[yp] > (150 if c == "pass" else 5)]
            if len(g) < 40: continue
            ry = g[ya].fillna(0) - g[yp]; rt = g[ta].fillna(0) - g[tp]
            d = dict(pos=pos, comp=c, season=seas, n=len(g),
                     yd_act_sd=ry.std(), yd_sim_sd=np.sqrt((g[ys + "_sd"] ** 2).mean()),
                     td_act_sd=rt.std(), td_sim_sd=np.sqrt((g[ts + "_sd"] ** 2).mean()), td_pois_sd=np.sqrt(g[tp].mean()),
                     corr_act=np.corrcoef(ry, rt)[0, 1], corr_sim=g["sim_c_" + ys[4:]].mean())
            if c in VOL:
                va, vp, vs = VOL[c]
                rv = g[va].fillna(0) - g[vp]
                d.update(vol_act_sd=rv.std(), vol_sim_sd=np.sqrt((g[vs + "_sd"] ** 2).mean()))
                # efficiency given volume: yards residual after regressing on volume residual
                b = np.cov(ry, rv)[0, 1] / rv.var()
                d.update(eff_act_sd=(ry - b * rv).std())
            rows.append(d)
T = pd.DataFrame(rows)
T["yd_ratio"] = T.yd_sim_sd / T.yd_act_sd; T["td_ratio"] = T.td_sim_sd / T.td_act_sd
P(T.round(3).to_string(index=False))

# fantasy-point level: sim sd vs actual residual sd by pos x season x ptier
P("\n== Fantasy points: raw MC sd / realized residual sd (played), by pos x season")
F = X.groupby(["position", "season"]).apply(lambda g: pd.Series(dict(n=len(g), raw=np.sqrt((g.pts_sd ** 2).mean()), sigma=np.sqrt((g.sigma ** 2).mean()),
    realized=g.err.std()))).assign(raw_ratio=lambda d: d.raw / d.realized, sig_ratio=lambda d: d.sigma / d.realized)
P(F.round(3).to_string())
# upper tail shape: how far above p90 do the misses go, and skew
P("\n== Upper tail shape (played, 2023+): P(act>q90), P(act>q95), P(act>q99) of raw MC; realized skew vs sim skew proxy (q90-q50)/(q50-q10)")
Y = X[X.season >= 2023]
for p, g in Y.groupby("position"):
    sh = g.stack_delta.fillna(0)
    P(f"  {p}: n {len(g)} >q90 {(g.act > g.q90 + sh).mean():.3f} >q95 {(g.act > g.q95 + sh).mean():.3f} >q99 {(g.act > g.q99 + sh).mean():.3f}"
      f" <q10 {(g.act < g.q10 + sh).mean():.3f} <q5 {(g.act < g.q5 + sh).mean():.3f} | sim skew ratio {((g.q90 - g.q50) / (g.q50 - g.q10).clip(lower=.1)).median():.2f}"
      f" act-resid skew {g.err.skew():.2f}")
LOG.close()
