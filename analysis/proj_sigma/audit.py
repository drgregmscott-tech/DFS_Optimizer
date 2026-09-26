"""Sigma / p10 / p90 calibration audit (research only; contains NO FC data).
Reads (git-ignored, FC-derived): fc_master_mapped.csv, proj_qb/ourproj_qb1/proj_*.csv (production-faithful
QB1-guard history build, all positions), proj_sigma/draws/*.parquet (MC quantiles from capture_draws.py).
Writes: data/fc_history/derived/proj_sigma/{frame.parquet, audit_report.txt}
    python analysis/proj_sigma/audit.py
"""
import os, glob
import numpy as np, pandas as pd
from scipy import stats

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DER = os.path.join(R, "data/fc_history/derived")
OUT = os.path.join(DER, "proj_sigma")
LOG = None
def P(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 500)
Q = np.arange(1, 100)


def load():
    fc = pd.read_csv(os.path.join(DER, "fc_master_mapped.csv"), low_memory=False, dtype={"player_id": str})
    fc = fc[(fc.site == "dk") & (fc.slate_kind == "classic") & (fc.slate_raw == "main") & fc.player_id.notna()
            & fc.pos.isin(["QB", "RB", "WR", "TE", "DST"])]
    fc = fc.drop_duplicates(["season", "week", "player_id"])[["season", "week", "player_id", "pos", "salary", "fc_proj", "floor", "ceiling", "stdv", "score"]]
    o = pd.concat([pd.read_csv(f, dtype={"player_id": str}) for f in glob.glob(os.path.join(DER, "proj_qb/ourproj_qb1/proj_*.csv"))])
    o = o.drop_duplicates(["season", "week", "player_id"])
    keep = ["season", "week", "player_id", "player_name", "position", "team", "final_projection", "sigma", "sigma_source",
            "statline_p10", "statline_p90", "stack_delta", "proj_pass_yd", "proj_pass_td", "proj_rush_att", "proj_rush_yd",
            "proj_rush_td", "proj_targets", "proj_rec", "proj_rec_yd", "proj_rec_td"]
    X = fc.merge(o[keep], on=["season", "week", "player_id"], how="inner")
    ws = []
    for s in range(2021, 2027):
        w = pd.read_parquet(os.path.join(R, f"data/weekly_stats_{s}.parquet"))
        ws.append(w[["player_id", "season", "week", "passing_yards", "passing_tds", "carries", "rushing_yards", "rushing_tds",
                     "targets", "receptions", "receiving_yards", "receiving_tds"]])
    W = pd.concat(ws).drop_duplicates(["season", "week", "player_id"])
    X = X.merge(W, on=["season", "week", "player_id"], how="left", indicator=True)
    X["played"] = (X._merge == "both") | (X.position == "DST"); X = X.drop(columns="_merge")
    X["act"] = X.score.fillna(0.0).where(X.played, 0.0)
    dr = glob.glob(os.path.join(OUT, "draws/draws_*.parquet"))
    if dr:
        D = pd.concat([pd.read_parquet(f) for f in dr]).drop_duplicates(["season", "week", "player_id"])
        X = X.merge(D, on=["season", "week", "player_id"], how="left")
    X = X[X.final_projection > 0].reset_index(drop=True)
    X["err"] = X.act - X.final_projection
    X["z"] = X.err / X.sigma.where(X.sigma > 0)
    X["ptier"] = pd.cut(X.final_projection, [0, 5, 8, 12, 16, 20, 99], labels=["<5", "5-8", "8-12", "12-16", "16-20", "20+"])
    X["stier"] = X.groupby("position").salary.transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False)).map({0: "lo", 1: "mid", 2: "hi"})
    X["wb"] = pd.cut(X.week, [0, 3, 8, 13, 18], labels=["w1-3", "w4-8", "w9-13", "w14-18"])
    if "q50" in X:
        qs = X[[f"q{q}" for q in Q]].values + X.stack_delta.fillna(0).values[:, None]
        a = X.act.values
        ok = np.isfinite(qs[:, 0])
        pit = np.full(len(a), np.nan); lo = pit.copy(); hi = pit.copy()
        for i in np.where(ok)[0]:
            pit[i] = np.interp(a[i], qs[i], Q / 100, left=0.0, right=1.0)
            lo[i] = (qs[i] < a[i]).mean(); hi[i] = (qs[i] <= a[i]).mean()
        # ties at a point mass (e.g. many 0 draws): spread uniformly over the tied mass
        tie = ok & (hi - lo > 0.015)
        pit[tie] = lo[tie] + np.random.default_rng(3).random(tie.sum()) * (hi[tie] - lo[tie])
        X["pit"] = pit
        X["mc_p10"] = X.q10 + X.stack_delta.fillna(0)
    X.to_parquet(os.path.join(OUT, "frame.parquet"))
    return X


def cov(g, lo="statline_p10", hi="statline_p90"):
    return pd.Series(dict(n=len(g), below=(g.act < g[lo]).mean(), inside=((g.act >= g[lo]) & (g.act <= g[hi])).mean(),
                          above=(g.act > g[hi]).mean()))


def zst(g):
    z = g.z.dropna()
    return pd.Series(dict(n=len(z), z_mean=z.mean(), z_sd=z.std(), rmse=np.sqrt((g.err ** 2).mean()), sig_rms=np.sqrt((g.sigma ** 2).mean()),
                          in68=(z.abs() <= 1).mean(), above128=(z > 1.2816).mean(), below128=(z < -1.2816).mean()))


def pitflat(g):
    p = g.pit.dropna()
    h = np.histogram(p, bins=10, range=(0, 1))[0] / max(len(p), 1)
    return pd.Series(dict(n=len(p), **{f"d{i}": h[i] for i in range(10)}, maxdev=np.abs(h - .1).max(), pit_sd=p.std()))


def main():
    global LOG
    LOG = open(os.path.join(OUT, "audit_report.txt"), "w")
    X = load()
    SK = X[X.position != "DST"]
    P(f"rows {len(X)}; skill {len(SK)}; played {SK.played.mean():.3f}; seasons {sorted(X.season.unique())}")
    P("NOTE: statline_p10 in production = linear QR a+b*final (2026-09-24 p10 calibration); p90 = raw MC p90 + stack shift;"
      " sigma = 10.4b recal a*sigma_raw^b fit on 2014-17. mc_p10 = raw MC q10 + stack shift.")
    sets = {"played": SK[SK.played], "inclDNP": SK, "meaningful(proj>8,played)": SK[SK.played & (SK.final_projection > 8)]}
    for nm, S in sets.items():
        P(f"\n== Coverage [{nm}] production p10/p90 by position x season")
        P(S.groupby(["position", "season"]).apply(cov).unstack("season").round(3).to_string())
        P(f"-- pooled 2023+ by position [{nm}]: prod p10/p90 | raw MC q10/p90")
        T = S[S.season >= 2023]
        a = T.groupby("position").apply(cov)
        if "mc_p10" in T: a = a.join(T.groupby("position").apply(cov, lo="mc_p10").add_prefix("mc_"))
        P(a.round(3).to_string())
    M = sets["meaningful(proj>8,played)"]; PL = sets["played"]
    for by in ["ptier", "stier", "wb"]:
        P(f"\n== Coverage (played, all seasons) by position x {by}")
        P(PL.groupby(["position", by], observed=True).apply(cov).round(3).to_string())
    P("\n== sigma calibration: z=(act-final)/sigma (played). Want z_mean~0 (bias), z_sd~1, rmse~sig_rms")
    P(PL.groupby(["position", "season"]).apply(zst).round(3).to_string())
    P("\n-- by position x proj tier (played, all seasons)")
    P(PL.groupby(["position", "ptier"], observed=True).apply(zst).round(3).to_string())
    P("-- DST (all)"); P(X[X.position == "DST"].groupby("season").apply(zst).round(3).to_string())
    P("\n-- z_sd by position x season, inclDNP"); P(SK.groupby(["position", "season"]).apply(zst).z_sd.unstack().round(3).to_string())
    P("\n== Does sigma track |error| within position? Spearman(sigma,|err|), and within proj tier (played)")
    rows = []
    for (p, s), g in pd.concat([PL, X[X.position == "DST"]]).groupby(["position", "season"]):
        r = dict(pos=p, season=s, n=len(g), rho_sigma=stats.spearmanr(g.sigma, g.err.abs())[0],
                 rho_proj=stats.spearmanr(g.final_projection, g.err.abs())[0],
                 rho_fcstdv=stats.spearmanr(g.stdv, (g.act - g.fc_proj).abs(), nan_policy="omit")[0] if (g.stdv > 0).sum() > 30 else np.nan)
        g2 = g.copy(); g2["rs"] = g2.groupby("ptier", observed=True).sigma.rank(pct=True); g2["re"] = g2.groupby("ptier", observed=True).err.transform(lambda e: e.abs().rank(pct=True))
        r["rho_sigma_within_ptier"] = stats.spearmanr(g2.rs, g2.re)[0]
        if "pts_sd" in g: r["rho_rawsd"] = stats.spearmanr(g.pts_sd, g.err.abs(), nan_policy="omit")[0]
        rows.append(r)
    P(pd.DataFrame(rows).round(3).to_string(index=False))
    P("\n== FC benchmark (played, skill): floor/ceiling coverage and z_fc=(act-fc)/stdv")
    F = PL[PL.stdv > 0].copy(); F["zf"] = (F.act - F.fc_proj) / F.stdv
    P(F.groupby(["position", "season"]).apply(lambda g: pd.Series(dict(n=len(g), below=(g.act < g.floor).mean(), above=(g.act > g.ceiling).mean(),
        zf_mean=g.zf.mean(), zf_sd=g.zf.std(), stdv=g.stdv.mean(), our_sig=g.sigma.mean()))).round(3).to_string())
    P("(FC stdv>0 share by season: " + str(X.groupby("season").stdv.apply(lambda s: round((s > 0).mean(), 2)).to_dict()) + ")")
    if "pit" in X:
        P("\n== PIT histogram (raw MC distribution + stack shift; played). d0..d9 decile shares, flat=0.10")
        P(PL.groupby(["position", "season"]).apply(pitflat).round(3).to_string())
        P("-- meaningful cut"); P(M.groupby("position").apply(pitflat).round(3).to_string())
        P("-- by proj tier (played, 2023+)"); P(PL[PL.season >= 2023].groupby(["position", "ptier"], observed=True).apply(pitflat).round(3).to_string())
        P("\n== Raw MC sd vs recal sigma vs realized residual sd (played), by pos x ptier")
        P(PL.groupby(["position", "ptier"], observed=True).apply(lambda g: pd.Series(dict(n=len(g), raw_sd=np.sqrt((g.pts_sd ** 2).mean()),
            recal=np.sqrt((g.sigma ** 2).mean()), realized=g.err.std(), bias=g.err.mean(),
            p90_implied_sd=((g.statline_p90 - g.final_projection) / 1.2816).mean(), up_real=(g.err.clip(lower=0) ** 2).mean() ** .5,
            dn_real=(g.err.clip(upper=0) ** 2).mean() ** .5))).round(2).to_string())
    LOG.close()


if __name__ == "__main__":
    main()
