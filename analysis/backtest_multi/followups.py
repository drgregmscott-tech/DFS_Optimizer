"""Follow-up analyses on the multi-season DK 2014-2021 backtest (items 1-6 of
HANDOFF_next_session_backtest_2026-09-24.md). Post-processing only: reads
analysis/backtest_multi/out/proj/<arm>/ and writes out/followups_*.txt.

  python analysis/backtest_multi/followups.py level  [--arm baseline]
  python analysis/backtest_multi/followups.py sigma  [--arm baseline]
  python analysis/backtest_multi/followups.py qbrush [--arm baseline]
  python analysis/backtest_multi/followups.py compare --arms baseline qbrush   (paired, week-bootstrap)

All CIs: 95%, bootstrap over season-weeks (B=2000, seed 7).
Population "played" = evaluate.py's default (skill player has an nflverse
stat row that week; this conditions on recording a stat, see REPORT_followups
caveat), "all" = every pool player with proj > 0 (inactives score 0).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as ev  # noqa: E402

REPO = ev.REPO
OUT = ev.OUT
SKILL = ev.SKILL
SEASONS = list(range(2014, 2022))
B, SEED = 2000, 7
Z10 = 1.2815515655446004


def load(arm, pop="played"):
    df = ev.load_arm(arm)
    df = df[df["final_projection"] > 0]
    if pop == "played":
        df = df[df["played"]]
    return df.reset_index(drop=True)


# ---------------------------------------------------------------- metrics
def week_stats(d, col):
    """Per season-week sufficient stats for proj column `col`."""
    rows = []
    for (s, w), g in d.groupby(["season", "week"]):
        e = g[col] - g["actual_points"]
        sp, tn = [], []
        for pos, gp in g.groupby("position"):
            if len(gp) >= 5:
                sp.append(gp[col].corr(gp["actual_points"], method="spearman"))
            n = ev.TOPN.get(pos, 12)
            if len(gp) >= 2 * n:
                tn.append(gp.nlargest(n, col)["actual_points"].mean())
        sk = g[g["position"].isin(SKILL)]
        xsp = sk[col].corr(sk["actual_points"], method="spearman") if len(sk) >= 10 else np.nan
        rows.append({"season": s, "week": w, "n": len(g), "se": e.sum(), "sae": e.abs().sum(),
                     "sse": (e ** 2).sum(), "sp": np.nanmean(sp) if sp else np.nan,
                     "tn": np.mean(tn) if tn else np.nan, "xsp": xsp})
    return pd.DataFrame(rows)


def summarize(d, col):
    w = week_stats(d, col)
    return {"n": int(w["n"].sum()), "weeks": len(w), "bias": w["se"].sum() / w["n"].sum(),
            "MAE": w["sae"].sum() / w["n"].sum(), "RMSE": np.sqrt(w["sse"].sum() / w["n"].sum()),
            "pearson": d[col].corr(d["actual_points"]), "spearman_wxp": w["sp"].mean(),
            "xpos_spearman": w["xsp"].mean(), "topN": w["tn"].mean()}


def paired(d, ref, alt):
    """alt - ref deltas with week-bootstrap CIs."""
    a, r = week_stats(d, alt), week_stats(d, ref)
    n = r["n"].to_numpy()
    comp = {"dMAE": (a["sae"] - r["sae"]).to_numpy(), "dBias_abs": None,
            "dRMSE2": (a["sse"] - r["sse"]).to_numpy()}
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(r), size=(B, len(r)))
    out = {"n": int(n.sum()), "weeks": len(r)}
    dm = comp["dMAE"]
    out["dMAE"] = dm.sum() / n.sum()
    bs = dm[idx].sum(1) / n[idx].sum(1)
    out["dMAE_ci"] = (np.percentile(bs, 2.5), np.percentile(bs, 97.5))
    out["bias_ref"] = r["se"].sum() / n.sum()
    out["bias_alt"] = a["se"].sum() / n.sum()
    out["dRMSE"] = np.sqrt(a["sse"].sum() / n.sum()) - np.sqrt(r["sse"].sum() / n.sum())
    for k, c in (("dSpearman_wxp", "sp"), ("dXposSpearman", "xsp"), ("dTopN", "tn")):
        dd = (a[c] - r[c]).to_numpy()
        out[k] = np.nanmean(dd)
        bs = np.nanmean(dd[idx], axis=1)
        out[k + "_ci"] = (np.percentile(bs, 2.5), np.percentile(bs, 97.5))
    out["dPearson"] = d[alt].corr(d["actual_points"]) - d[ref].corr(d["actual_points"])
    return out


def fmt_p(label, p):
    return (f"{label:26s} n={p['n']:6d} wks={p['weeks']:3d} bias {p['bias_ref']:+.3f}->{p['bias_alt']:+.3f} "
            f"dMAE={p['dMAE']:+.4f} [{p['dMAE_ci'][0]:+.4f},{p['dMAE_ci'][1]:+.4f}] dRMSE={p['dRMSE']:+.4f} "
            f"dPearson={p['dPearson']:+.4f} dSpW={p['dSpearman_wxp']:+.4f} "
            f"dXposSp={p['dXposSpearman']:+.4f} [{p['dXposSpearman_ci'][0]:+.4f},{p['dXposSpearman_ci'][1]:+.4f}] "
            f"dTopN={p['dTopN']:+.3f}")


# ---------------------------------------------------------------- item 1
def fit_level(train, method):
    """Return {pos: (a, b)} with corrected = max(0, a + b*proj)."""
    par = {}
    for pos, g in train.groupby("position"):
        x, y = g["final_projection"].to_numpy(), g["actual_points"].to_numpy()
        if method == "add":
            par[pos] = (float((y - x).mean()), 1.0)
        elif method == "mult":
            par[pos] = (0.0, float(y.sum() / x.sum()))
        elif method == "affine":
            b, a = np.polyfit(x, y, 1)
            par[pos] = (float(a), float(b))
        elif method == "add_skill":
            pass
    if method in ("add_skill", "mult_skill"):
        sk = train[train["position"].isin(SKILL)]
        x, y = sk["final_projection"].to_numpy(), sk["actual_points"].to_numpy()
        v = (float((y - x).mean()), 1.0) if method == "add_skill" else (0.0, float(y.sum() / x.sum()))
        par = {p: v for p in SKILL}
    return par


def apply_level(d, par):
    a = d["position"].map(lambda p: par.get(p, (0.0, 1.0))[0])
    b = d["position"].map(lambda p: par.get(p, (0.0, 1.0))[1])
    return (a + b * d["final_projection"]).clip(lower=0.0)


def cmd_level(arm):
    lines = []
    for pop in ("played", "all"):
        d = load(arm, pop)
        d = d[d["position"].isin(SKILL)].copy()
        lines.append(f"\n######## pop={pop} arm={arm} skill n={len(d)} ########")
        base = summarize(d, "final_projection")
        lines.append("baseline: " + " ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}"
                                             for k, v in base.items()))
        # bias by position x projection bin (shape of the bias)
        d["bin"] = pd.cut(d["final_projection"], [0, 3, 6, 10, 15, 20, 60])
        t = d.groupby(["position", "bin"], observed=True).apply(
            lambda g: pd.Series({"n": len(g), "bias": (g["final_projection"] - g["actual_points"]).mean()}))
        lines.append("bias by position x proj bin:\n" + t.unstack(0).round(2).to_string())
        folds = [("fit14-19/test20-21", list(range(2014, 2020)), [2020, 2021])]
        folds += [(f"LOSO test {s}", [x for x in SEASONS if x != s], [s]) for s in SEASONS]
        for method in ("add", "mult", "affine", "add_skill", "mult_skill"):
            lines.append(f"\n-- method={method} --")
            loso_parts = []
            for name, tr, te in folds:
                par = fit_level(d[d["season"].isin(tr)], method)
                dt = d[d["season"].isin(te)].copy()
                dt["corr"] = apply_level(dt, par)
                if name.startswith("LOSO"):
                    loso_parts.append(dt)
                    continue
                lines.append(f"{name} params " + ", ".join(f"{p}:({v[0]:+.2f},{v[1]:.3f})" for p, v in sorted(par.items())))
                lines.append(fmt_p(f"  {name} skill", paired(dt, "final_projection", "corr")))
                for pos in SKILL:
                    lines.append(fmt_p(f"  {name} {pos}", paired(dt[dt["position"] == pos], "final_projection", "corr")))
            dl = pd.concat(loso_parts)
            lines.append(fmt_p("  LOSO pooled skill", paired(dl, "final_projection", "corr")))
            for pos in SKILL:
                lines.append(fmt_p(f"  LOSO pooled {pos}", paired(dl[dl["position"] == pos], "final_projection", "corr")))
            # production params (fit on all 8 seasons)
            par = fit_level(d, method)
            lines.append("  all-seasons params " + ", ".join(f"{p}:({v[0]:+.3f},{v[1]:.4f})" for p, v in sorted(par.items())))
    write("followups_level", lines)


# ---------------------------------------------------------------- item 2
def p10_candidates(d, par, kind):
    mean = d["final_projection"]
    if kind == "sigma":      # p10 = max(0, mean - Z*c*sigma)
        c = d["position"].map(par)
        return (mean - Z10 * c * d["sigma"]).clip(lower=0.0)
    if kind == "mcscale":    # p10 = max(0, mean - c*(mean - statline_p10))
        c = d["position"].map(par)
        return (mean - c * (mean - d["statline_p10"])).clip(lower=0.0)
    raise ValueError(kind)


def fit_c(train, kind, pooled):
    """Choose c so the train below-p10 share == 10% (grid search)."""
    grid = np.round(np.arange(0.30, 3.001, 0.01), 2)

    def best(g):
        rates = [(abs((g["actual_points"] < p10_candidates(g, {p: c for p in SKILL}, kind)).mean() - 0.10), c)
                 for c in grid]
        return min(rates)[1]
    if pooled:
        c = best(train)
        return {p: c for p in SKILL}
    return {p: best(g) for p, g in train.groupby("position")}


def coverage_by(d, p10col, extra=None):
    g = d.assign(below=d["actual_points"] < d[p10col])
    keys = ["position"] + ([extra] if extra else [])
    return g.groupby(keys)["below"].agg(["size", "mean"])


def week_ci_rate(d, flag):
    w = d.assign(f=flag).groupby(["season", "week"])["f"].agg(["sum", "size"])
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(w), size=(B, len(w)))
    bs = w["sum"].to_numpy()[idx].sum(1) / w["size"].to_numpy()[idx].sum(1)
    return w["sum"].sum() / w["size"].sum(), np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def pinball10(y, q):
    u = y - q
    return np.mean(np.maximum(0.1 * u, -0.9 * u))


def cmd_sigma(arm):
    lines = []
    d = load(arm, "played")
    d = d[d["position"].isin(SKILL) & d["sigma"].gt(0) & d["statline_p10"].notna()].copy()
    lines.append(f"arm={arm} pop=played skill n={len(d)}; current statline_p10 below-rate by season:")
    lines.append((d.assign(b=d["actual_points"] < d["statline_p10"]).groupby(["season", "position"])["b"]
                  .mean().unstack().round(3)).to_string())
    folds = [("fit14-17/test18-21", [2014, 2015, 2016, 2017], [2018, 2019, 2020, 2021])]
    for kind in ("sigma", "mcscale"):
        for pooled in (False, True):
            tag = f"{kind}/{'skill-pooled' if pooled else 'per-position'}"
            lines.append(f"\n==== {tag} ====")
            for name, tr, te in folds:
                par = fit_c(d[d["season"].isin(tr)], kind, pooled)
                dt = d[d["season"].isin(te)].copy()
                dt["p10n"] = p10_candidates(dt, par, kind)
                lines.append(f"{name}: c = " + ", ".join(f"{p}:{v:.2f}" for p, v in sorted(par.items())))
                for pos in SKILL + ["skill"]:
                    g = dt if pos == "skill" else dt[dt["position"] == pos]
                    r, lo, hi = week_ci_rate(g, g["actual_points"] < g["p10n"])
                    r0 = (g["actual_points"] < g["statline_p10"]).mean()
                    lines.append(f"   {pos:5s} n={len(g):5d} below_p10 {r0:.3f} -> {r:.3f} [{lo:.3f},{hi:.3f}] "
                                 f"pinball10 {pinball10(g['actual_points'], g['statline_p10']):.3f} -> "
                                 f"{pinball10(g['actual_points'], g['p10n']):.3f}")
                # by season within test
                cov = dt.assign(b=dt["actual_points"] < dt["p10n"]).groupby(["season", "position"])["b"].mean().unstack()
                lines.append("   test below-rate by season:\n" + cov.round(3).to_string())
            # LOSO
            parts, cs = [], {}
            for s in SEASONS:
                par = fit_c(d[d["season"] != s], kind, pooled)
                cs[s] = par
                dt = d[d["season"] == s].copy()
                dt["p10n"] = p10_candidates(dt, par, kind)
                parts.append(dt)
            dl = pd.concat(parts)
            lines.append("LOSO c by held-out season: " + "; ".join(
                f"{s}:" + ",".join(f"{p}{v:.2f}" for p, v in sorted(par.items())) for s, par in cs.items()))
            cov = dl.assign(b=dl["actual_points"] < dl["p10n"]).groupby(["season", "position"])["b"].mean().unstack()
            lines.append("LOSO held-out below-rate by season:\n" + cov.round(3).to_string())
            for pos in SKILL + ["skill"]:
                g = dl if pos == "skill" else dl[dl["position"] == pos]
                r, lo, hi = week_ci_rate(g, g["actual_points"] < g["p10n"])
                lines.append(f"   LOSO {pos:5s} n={len(g):5d} below {r:.3f} [{lo:.3f},{hi:.3f}] "
                             f"season range {cov[pos].min() if pos != 'skill' else np.nan:.3f}-"
                             f"{cov[pos].max() if pos != 'skill' else np.nan:.3f}")
            par = fit_c(d, kind, pooled)
            lines.append("all-seasons c (production): " + ", ".join(f"{p}:{v:.2f}" for p, v in sorted(par.items())))
    write("followups_sigma", lines)


# ---------------------------------------------------------------- item 3
def stat_actuals(season):
    ws = pd.read_parquet(REPO / "data" / f"weekly_stats_{season}.parquet",
                         columns=["player_id", "week", "season_type", "carries", "rushing_yards", "rushing_tds",
                                  "attempts", "passing_yards", "passing_tds", "targets", "receptions",
                                  "receiving_yards", "receiving_tds"])
    return ws[ws["season_type"] == "REG"].drop(columns="season_type")


def cmd_qbrush(arm):
    d = load(arm, "played")
    q = d[d["position"] == "QB"].copy()
    q = q.merge(pd.concat([stat_actuals(s).assign(season=s) for s in SEASONS]),
                on=["season", "week", "player_id"], how="left")
    lines = [f"arm={arm} QB played n={len(q)}"]
    pairs = [("proj_rush_att", "carries"), ("proj_rush_yd", "rushing_yards"), ("proj_rush_td", "rushing_tds"),
             ("proj_pass_att", "attempts"), ("proj_pass_yd", "passing_yards"), ("proj_pass_td", "passing_tds")]
    q["proj_rush_pts"] = 0.1 * q["proj_rush_yd"] + 6 * q["proj_rush_td"]
    q["act_rush_pts"] = 0.1 * q["rushing_yards"] + 6 * q["rushing_tds"]
    pairs.append(("proj_rush_pts", "act_rush_pts"))
    q["starter"] = q["attempts"].fillna(0) >= 15
    for sub, g in (("all QB", q), ("QB with >=15 att", q[q["starter"]])):
        lines.append(f"\n-- {sub} n={len(g)} --")
        for p, a in pairs:
            r, lo, hi = boot_mean(g, g[p] - g[a].fillna(0))
            lines.append(f"  {p:15s} proj {g[p].mean():7.2f} act {g[a].fillna(0).mean():7.2f} bias {r:+.3f} [{lo:+.3f},{hi:+.3f}]")
        by = g.assign(e=g["proj_rush_pts"] - g["act_rush_pts"]).groupby("season")["e"].mean()
        lines.append("  rush-pts bias by season: " + " ".join(f"{s}:{v:+.2f}" for s, v in by.items()))
        # by rushing-QB tercile of projected rush att
        g = g.assign(tier=pd.qcut(g["proj_rush_att"], 3, labels=["low", "mid", "high"]))
        t = g.groupby("tier", observed=True).apply(lambda x: pd.Series({
            "n": len(x), "proj_att": x["proj_rush_att"].mean(), "act_att": x["carries"].fillna(0).mean(),
            "proj_yd": x["proj_rush_yd"].mean(), "act_yd": x["rushing_yards"].fillna(0).mean(),
            "ypc_proj": x["proj_rush_yd"].sum() / x["proj_rush_att"].sum(),
            "ypc_act": x["rushing_yards"].fillna(0).sum() / max(x["carries"].fillna(0).sum(), 1)}))
        lines.append(t.round(2).to_string())
    write("followups_qbrush", lines)


def boot_mean(d, x):
    w = d.assign(x=x).groupby(["season", "week"])["x"].agg(["sum", "size"])
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(w), size=(B, len(w)))
    bs = w["sum"].to_numpy()[idx].sum(1) / w["size"].to_numpy()[idx].sum(1)
    return w["sum"].sum() / w["size"].sum(), np.percentile(bs, 2.5), np.percentile(bs, 97.5)


# ---------------------------------------------------------------- arms
def cmd_compare(arms, pop, seasons=None):
    ref = load(arms[0], pop)
    lines = []
    key = ["season", "week", "site_player_id"]
    for arm in arms[1:]:
        alt = load(arm, "all")[key + ["final_projection"]].rename(columns={"final_projection": "alt"})
        m = ref.merge(alt, on=key, how="inner")
        if seasons:
            m = m[m["season"].isin(seasons)]
        lines.append(f"\n==== {arm} minus {arms[0]} (pop={pop}, rows in both with proj>0 in ref) ====")
        for label, pos in (("skill", SKILL), ("QB", ["QB"]), ("RB", ["RB"]), ("WR", ["WR"]), ("TE", ["TE"]), ("DST", ["DST"])):
            g = m[m["position"].isin(pos)]
            if len(g):
                lines.append(fmt_p(label, paired(g, "final_projection", "alt")))
        for s in sorted(m["season"].unique()):
            g = m[(m["season"] == s) & m["position"].isin(SKILL)]
            lines.append(fmt_p(f"  skill {s}", paired(g, "final_projection", "alt")))
    write(f"followups_compare_{'_vs_'.join(arms)}_{pop}", lines)


# ---------------------------------------------------------------- item 2b: dart filter
P10_C = {"QB": 1.03, "RB": 0.61, "TE": 0.64, "WR": 0.68}   # all-seasons fit, sigma/per-position


def p10_cal(d, c=P10_C):
    return (d["final_projection"] - Z10 * d["position"].map(c) * d["sigma"]).clip(lower=0.0)


def cmd_darts(arm):
    lines = []
    d = load(arm, "played")
    d = d[d["position"].isin(SKILL) & d["sigma"].gt(0)].copy()
    d["p10c"] = p10_cal(d)
    for floor in (5.0, 8.0):
        g = d[d["final_projection"] >= floor].copy()
        g["flagA"] = g["statline_p10"] < 1.0
        nA = int(g["flagA"].sum())
        # threshold on p10c giving the same total count
        T = float(np.sort(g["p10c"].to_numpy())[nA]) if nA else 0.0
        g["flagB"] = g["p10c"] < T
        g["bust"] = g["actual_points"] < 0.5 * g["final_projection"]
        g["ratio"] = g["actual_points"] / g["final_projection"]
        lines.append(f"\n-- rosterable final>={floor}: n={len(g)}  current flags (p10<1.0) {nA} "
                     f"({nA/len(g):.3%}); matched-count p10_cal threshold T={T:.2f} -> {int(g['flagB'].sum())} flags")
        for f in ("flagA", "flagB"):
            x = g[g[f]]
            r, lo, hi = week_ci_rate(x, x["bust"]) if len(x) > 20 else (x["bust"].mean(), np.nan, np.nan)
            lines.append(f"   {f}: n={len(x)} bust(actual<0.5*proj) {r:.3f} [{lo:.3f},{hi:.3f}] "
                         f"mean actual/proj {x['ratio'].mean():.3f} mean proj {x['final_projection'].mean():.2f}; "
                         f"unflagged bust {g.loc[~g[f], 'bust'].mean():.3f}")
        # quality at equal count: rank-based AUC of each p10 for predicting bust (within rosterable)
        from scipy.stats import mannwhitneyu
        for col in ("statline_p10", "p10c"):
            # lower p10 (relative to proj) should mean more bust risk; use p10/proj
            sc = -(g[col] / g["final_projection"])
            u = mannwhitneyu(sc[g["bust"]], sc[~g["bust"]]).statistic
            lines.append(f"   AUC({col}/proj -> bust) = {u / (g['bust'].sum() * (~g['bust']).sum()):.4f}")
    # 2026 pools
    lines.append("\n-- 2026 DK classic pools (output/, read-only) --")
    for f in sorted((REPO / "output").glob("final_projections_dk_dk_classic_wk*_*2026.csv")):
        p = pd.read_csv(f)
        p = p[~p["position"].isin(["DST", "D", "DEF"]) & p["position"].isin(SKILL)]
        p = p[p["final_projection"] > 0]
        p["p10c"] = p10_cal(p)
        row = [f.name.replace("final_projections_dk_dk_classic_", "")]
        for floor in (0.0, 5.0, 8.0):
            q = p[p["final_projection"] >= floor]
            nA = int((q["statline_p10"] < 1.0).sum())
            T = float(np.sort(q["p10c"].to_numpy())[nA]) if 0 < nA < len(q) else float("nan")
            row.append(f"final>={floor:.0f}: n={len(q)} cur={nA} newAt1.0={int((q['p10c'] < 1.0).sum())} "
                       f"T_match={T:.2f}")
        lines.append("  " + " | ".join(row))
    write("followups_darts", lines)


def write(name, lines):
    text = "\n".join(lines)
    (OUT / f"{name}.txt").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["level", "sigma", "qbrush", "compare", "darts", "movedqb"])
    ap.add_argument("--arm", default="baseline")
    ap.add_argument("--arms", nargs="+")
    ap.add_argument("--pop", default="played", choices=["played", "all"])
    ap.add_argument("--seasons", default=None)
    a = ap.parse_args()
    if a.cmd == "level":
        cmd_level(a.arm)
    elif a.cmd == "sigma":
        cmd_sigma(a.arm)
    elif a.cmd == "qbrush":
        cmd_qbrush(a.arm)
    elif a.cmd == "darts":
        cmd_darts(a.arm)
    elif a.cmd == "movedqb":
        cmd_movedqb(a.arms or [a.arm])
    else:
        seas = None
        if a.seasons:
            from run_backtest import parse_range
            seas = parse_range(a.seasons)
        cmd_compare(a.arms, a.pop, seas)



# ---------------------------------------------------------------- item 6: moved QBs
def moved_qb_table(arm):
    """QB rows with mover flag: most recent REG game before the target week
    (any earlier season allowed) was for a different (canonical) team."""
    from run_backtest import TEAM_CANON
    canon = lambda t: TEAM_CANON.get(t, t)  # noqa: E731
    hist = []
    for s in range(2013, 2022):
        w = pd.read_parquet(REPO / "data" / f"weekly_stats_{s}.parquet",
                            columns=["player_id", "week", "season_type", "team", "attempts"])
        w = w[w["season_type"] == "REG"]
        w["season"] = s
        hist.append(w)
    hist = pd.concat(hist)
    hist["team"] = hist["team"].map(canon)
    hist["t"] = hist["season"] * 100 + hist["week"]
    hist = hist.sort_values("t")
    q = load(arm, "played")
    q = q[q["position"] == "QB"].copy()
    q["t"] = q["season"] * 100 + q["week"]
    q = q.sort_values("t")
    prev = pd.merge_asof(q[["t", "player_id"]].reset_index(), hist[["t", "player_id", "team"]]
                         .rename(columns={"team": "prev_team"}), on="t", by="player_id",
                         allow_exact_matches=False).set_index("index")
    q["prev_team"] = prev["prev_team"]
    q["team_c"] = q["team"].map(canon)
    q["moved"] = q["prev_team"].notna() & (q["prev_team"] != q["team_c"])
    act = pd.concat([stat_actuals(s).assign(season=s) for s in SEASONS])
    q = q.merge(act[["season", "week", "player_id", "attempts"]], on=["season", "week", "player_id"], how="left")
    q["starter"] = q["attempts"].fillna(0) >= 20
    return q


def cmd_movedqb(arms):
    lines = []
    for arm in arms:
        q = moved_qb_table(arm)
        lines.append(f"\n==== arm={arm}: QBs, starter = actual pass attempts >= 20 (outcome-conditioned proxy) ====")
        for lab, g in (("moved starters", q[q["moved"] & q["starter"]]),
                       ("non-moved starters", q[~q["moved"] & q["starter"]]),
                       ("moved, early (wk<=4) starters", q[q["moved"] & q["starter"] & (q["week"] <= 4)])):
            e = g["final_projection"] - g["actual_points"]
            ea = g["proj_pass_att"] - g["attempts"]
            r, lo, hi = boot_mean(g, e) if len(g) > 20 else (e.mean(), np.nan, np.nan)
            lines.append(f"  {lab:32s} n={len(g):4d} pts bias {r:+.2f} [{lo:+.2f},{hi:+.2f}] MAE {e.abs().mean():.2f} | "
                         f"pass att proj {g['proj_pass_att'].mean():.1f} act {g['attempts'].mean():.1f} "
                         f"bias {ea.mean():+.2f}; share proj<20 att {(g['proj_pass_att'] < 20).mean():.3f}")
        worst = q[q["moved"] & q["starter"]].assign(err=lambda x: x["final_projection"] - x["actual_points"]) \
            .nsmallest(10, "proj_pass_att")[["season", "week", "player_name", "team", "prev_team", "proj_pass_att",
                                             "attempts", "final_projection", "actual_points"]]
        lines.append("  lowest projected-volume moved starters:\n" + worst.round(1).to_string(index=False))
    write(f"followups_movedqb_{'_'.join(arms)}", lines)


if __name__ == "__main__":
    main()
