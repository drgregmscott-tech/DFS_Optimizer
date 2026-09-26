"""QB accuracy / decomposition / distribution: stubbed-depth history (ourproj) vs QB1-by-salary
rebuild (proj_qb/ourproj_qb1) vs FC. Research only, contains no FC data.
Writes data/fc_history/derived/proj_qb/{qb_rows.csv, qb_eval.txt}
"""
import glob, os, sys
import numpy as np, pandas as pd
from scipy.stats import spearmanr

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DER = os.path.join(R, "data/fc_history/derived")
OUT = os.path.join(DER, "proj_qb")
sys.path.insert(0, os.path.join(R, "scripts"))
STAT = ["attempts", "passing_yards", "passing_tds", "passing_interceptions", "carries", "rushing_yards", "rushing_tds"]


def load_proj(d, tag):
    o = pd.concat([pd.read_csv(f, dtype={"player_id": str}) for f in glob.glob(os.path.join(DER, d, "proj_*.csv"))])
    o = o[o.position == "QB"].drop_duplicates(["season", "week", "player_id"])
    keep = ["final_projection", "sigma", "statline_p10", "statline_p90", "proj_pass_att", "proj_pass_yd", "proj_pass_td",
            "proj_rush_att", "proj_rush_yd", "proj_rush_td"]
    cols = ["season", "week", "player_id"] + (["team", "salary"] if tag == "q" else [])
    return o[cols + keep].rename(columns={k: f"{tag}_{k}" for k in keep})


def build():
    fc = pd.read_csv(os.path.join(DER, "fc_master_mapped.csv"), low_memory=False, dtype={"player_id": str})
    fc = fc[(fc.site == "dk") & (fc.slate_kind == "classic") & (fc.slate_raw == "main") & (fc.pos == "QB") & fc.player_id.notna()]
    fc = fc.drop_duplicates(["season", "week", "player_id"])[["season", "week", "player_id", "player", "fc_proj", "score"]]
    X = load_proj("proj_qb/ourproj_qb1", "q").merge(load_proj("ourproj", "a"), on=["season", "week", "player_id"])
    X = X.merge(fc, on=["season", "week", "player_id"], how="left")
    ws = pd.concat([pd.read_parquet(os.path.join(R, f"data/weekly_stats_{s}.parquet")) for s in range(2021, 2027)])
    ws = ws[ws.season_type == "REG"][["player_id", "season", "week"] + STAT]
    X = X.merge(ws, on=["player_id", "season", "week"], how="left")
    X["played"] = X.attempts.notna()
    X[STAT] = X[STAT].fillna(0)
    X["act"] = np.where(X.played, X.score.fillna(0), 0.0)
    X["qb1"] = X.groupby(["season", "week", "team"]).salary.rank(ascending=False, method="first") == 1
    X["started"] = X.attempts >= 15
    X["wb"] = pd.cut(X.week, [0, 1, 4, 9, 18], labels=["w1", "w2-4", "w5-9", "w10-18"])
    X["fc"] = X.fc_proj
    return X


def metr(g, p, y="act"):
    x, a = g[p].values, g[y].values
    ok = ~np.isnan(x)
    x, a = x[ok], a[ok]
    b, c = np.polyfit(x, a, 1)
    return dict(n=len(x), bias=(x - a).mean(), mae=np.abs(x - a).mean(), rmse=np.sqrt(((x - a) ** 2).mean()), slope=b, icpt=c)


def within_sp(g, p):
    return np.nanmean([spearmanr(h[p], h.act)[0] for _, h in g.groupby(["season", "week"]) if len(h) >= 6])


def topn(g, p, n=5):
    return np.mean([h.nlargest(n, p).act.mean() for _, h in g.groupby(["season", "week"])])


def main():
    X = build()
    X.to_csv(os.path.join(OUT, "qb_rows.csv"), index=False)
    L = []

    def pr(*a):
        L.append(" ".join(str(x) for x in a)); print(*a)
    Q = X[X.qb1]
    pr(f"QB rows {len(X)}, QB1(salary) rows {len(Q)}; QB1 that started (>=15 att) {Q.started.mean():.3f}; "
       f"actual starters who were salary-QB1 {X[X.started].qb1.mean():.3f}")
    pr("\n== (2) QB1 accuracy, act = DK pts (DNP=0), rows with FC proj. a=stubbed history, q=QB1 guard, f=FC ==")
    for key in ["season", "wb"]:
        for k, g in Q[Q.fc.notna()].groupby(key, observed=True):
            row = [f"{k}"]
            for p in ["a_final_projection", "q_final_projection", "fc"]:
                m = metr(g, p)
                row.append(f"{p[:1]}: n{m['n']} bias{m['bias']:+.2f} mae{m['mae']:.2f} rmse{m['rmse']:.2f} sl{m['slope']:.2f} ic{m['icpt']:+.1f}")
            pr(" | ".join(row))
    pr("\nno-FC-filter QB1 (all seasons incl 2024 wk1-4):")
    for k, g in Q.groupby("season"):
        m = metr(g, "q_final_projection"); pr(k, {x: round(v, 2) for x, v in m.items()})
    pr("\nwithin-slate Spearman (all pool QBs with FC proj) / top-5 by proj mean actual:")
    for s, g in X[X.fc.notna()].groupby("season"):
        pr(s, " ".join(f"{p[:1]}:sp{within_sp(g, p):.3f}/top5 {topn(g, p):.2f}" for p in ["a_final_projection", "q_final_projection", "fc"]))
    S = Q[Q.started].copy()
    S["q_int"] = S.q_proj_pass_att * 0.0233  # approx; proj INT not exported
    comps = [("att", "q_proj_pass_att", "attempts", 0), ("pyd", "q_proj_pass_yd", "passing_yards", .04),
             ("ptd", "q_proj_pass_td", "passing_tds", 4), ("int", "q_int", "passing_interceptions", -1),
             ("ryd", "q_proj_rush_yd", "rushing_yards", .1), ("rtd", "q_proj_rush_td", "rushing_tds", 6)]
    pr("\n== component bias (proj-actual), QB1 starters; DK-pt equivalent in [] ==")
    for key in ["season", "wb"]:
        for s, g in S.groupby(key, observed=True):
            pr(s, f"n{len(g)} pts{(g.q_final_projection-g.act).mean():+.2f} (stub:{(g.a_final_projection-g.act).mean():+.2f})",
               " ".join(f"{n}{(g[p]-g[a]).mean():+.2f}[{w*(g[p]-g[a]).mean():+.2f}]" for n, p, a, w in comps),
               f"ypa p{g.q_proj_pass_yd.sum()/g.q_proj_pass_att.sum():.2f} a{g.passing_yards.sum()/g.attempts.sum():.2f}",
               f"stubAtt{(g.a_proj_pass_att-g.attempts).mean():+.1f}")
    pr("\n== (3) QB1 coverage: share act>p90, act<p10 (nominal .10/.10); sigma vs resid sd ==")
    for s, g in Q.groupby("season"):
        r = g.act - g.q_final_projection; st = g[g.started]
        pr(s, f"n{len(g)} >p90 {(g.act>g.q_statline_p90).mean():.3f} <p10 {(g.act<g.q_statline_p10).mean():.3f} "
           f"| starters >p90 {(st.act>st.q_statline_p90).mean():.3f} <p10 {(st.act<st.q_statline_p10).mean():.3f}"
           f" | mean sigma {g.q_sigma.mean():.2f} resid sd {r.std():.2f} (starters {r[g.started].std():.2f})")
    import statline_model as sm
    comp = sm.load_variance()["positions"]["QB"]["components"]["pass"]
    pr("variance artifact QB pass:", {k: comp[k] for k in ("r", "yards_cv", "latent_sd") if k in comp})
    rng = np.random.default_rng(7)
    simc, tdsd, ydsd, tdvar = [], [], [], []
    for row in S[S.q_proj_pass_att >= 5].itertuples():
        v, y, t = sm._draw_component(rng, 4000, row.q_proj_pass_att, comp["r"], row.q_proj_pass_yd / row.q_proj_pass_att,
                                     row.q_proj_pass_td / row.q_proj_pass_att, comp["yards_cv"], comp["latent_sd"])
        simc.append(np.corrcoef(y, t)[0, 1]); tdsd.append(t.std()); ydsd.append(y.std()); tdvar.append(t.var())
    ry = S.passing_yards - S.q_proj_pass_yd; rt = S.passing_tds - S.q_proj_pass_td
    pr(f"yards-TD corr: actual residual (QB1 starters n{len(S)}) {np.corrcoef(ry, rt)[0,1]:.3f}; sim within-player {np.mean(simc):.3f}")
    pr(f"pass TD sd: actual resid {rt.std():.3f} vs sim {np.sqrt(np.mean(tdvar)):.3f}; pass yd sd: actual resid {ry.std():.1f} vs sim {np.sqrt(np.mean(np.square(ydsd))):.1f}")
    pr(f"(actual resid includes projection error, so actual >= sim expected even if draws are right)")
    for s, g in S.groupby("season"):
        a, b = g.passing_yards - g.q_proj_pass_yd, g.passing_tds - g.q_proj_pass_td
        pr(f"  {s} n{len(g)} resid corr {np.corrcoef(a,b)[0,1]:.3f} td resid sd {b.std():.2f} yd resid sd {a.std():.1f}")
    open(os.path.join(OUT, "qb_eval.txt"), "w").write("\n".join(L))


if __name__ == "__main__":
    main()
