"""B. Biggest misses and WR/TE cause tests (no FC data in this file).
Input: data/fc_history/derived/model_vs_fc/frame.parquet, data/weekly_stats_*.parquet, data/projection_error_log.csv,
data/props/audit_*wk3*.csv. Output: data/fc_history/derived/model_vs_fc/misses_*.csv, causes_out.txt (git-ignored).
"""
from pathlib import Path
import numpy as np, pandas as pd


class _Fit:
    pass


def ols(y, X, groups=None):
    """OLS with slate-clustered SEs (numpy). X: DataFrame without constant."""
    Xc = np.column_stack([np.ones(len(X)), X.to_numpy(float)]); yv = y.to_numpy(float)
    b = np.linalg.lstsq(Xc, yv, rcond=None)[0]; e = yv - Xc @ b
    XtXi = np.linalg.pinv(Xc.T @ Xc)
    if groups is not None:
        meat = sum(np.outer(Xc[i].T @ e[i], Xc[i].T @ e[i]) for i in [np.where(groups.to_numpy() == g)[0] for g in np.unique(groups)])
    else:
        meat = Xc.T @ (Xc * (e ** 2)[:, None])
    se = np.sqrt(np.diag(XtXi @ meat @ XtXi))
    f = _Fit(); names = ["const"] + list(X.columns)
    f.params = dict(zip(names, b)); f.tvalues = dict(zip(names, b / se))
    f.rsquared = 1 - (e ** 2).sum() / ((yv - yv.mean()) ** 2).sum()
    return f

R = Path(__file__).resolve().parents[2]
OUT = R / "data/fc_history/derived/model_vs_fc"
LOG = open(OUT / "causes_out.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n")

J = pd.read_parquet(OUT / "frame.parquet")
J = J[J.act.notna() & J.fc.notna() & J.ours.notna()].copy()
J["mx"] = J[["fc", "ours"]].max(axis=1)

# ---------- teammate-absence (pre-lock knowable: inactives are public 90 min before kick) ----------
ws = pd.concat([pd.read_parquet(R / f"data/weekly_stats_{s}.parquet") for s in range(2021, 2027)])
ws = ws[ws.season_type.fillna("REG") == "REG"][["player_id", "season", "week", "team", "targets", "carries"]]
ws = ws.sort_values(["player_id", "season", "week"])
ws["p3"] = ws.groupby(["player_id", "season"]).targets.transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
last = ws.groupby(["player_id", "season"])  # expand: for each team-week, who played in prior 3 team weeks with p3>=5 but not this week
tw = ws[["season", "week", "team"]].drop_duplicates()
absn = []
for (s, t), g in ws.groupby(["season", "team"]):
    weeks = sorted(g.week.unique())
    for i, w in enumerate(weeks):
        prev = g[g.week.isin(weeks[max(0, i - 3):i])]
        if prev.empty:
            continue
        m = prev.groupby("player_id").targets.mean()
        big = set(m[m >= 5].index); now = set(g[g.week == w].player_id)
        gone = big - now
        absn.append((s, w, t, len(gone), float(m[list(gone)].sum()) if gone else 0.0))
AB = pd.DataFrame(absn, columns=["season", "week", "team_ws", "n_absent", "absent_tgt"])
tmap = ws[["player_id", "season", "week", "team"]].rename(columns={"team": "team_ws"})
J = J.merge(tmap, on=["player_id", "season", "week"], how="left").merge(AB, on=["season", "week", "team_ws"], how="left")
J["absent_tgt"] = J.absent_tgt.fillna(0)


def cause(r, m):
    """cause class for a miss of model m (column name), using realized stat lines."""
    err = r[m] - r.act
    if pd.isna(r.targets) and r.act <= 0.5 and r.pos != "DST":
        return "inactive/DNP"
    if r.pos == "DST":
        return "DST variance"
    if r.pos in ("WR", "TE", "RB") and pd.notna(r.prior3_share) and pd.notna(r.tgt_share) and abs(r.tgt_share - r.prior3_share) >= .10:
        return "role/usage change"
    td = (r.receiving_tds if pd.notna(r.receiving_tds) else 0) + (r.rushing_tds if pd.notna(r.rushing_tds) else 0)
    ptd = (r.proj_rec_td if pd.notna(r.proj_rec_td) else 0) + 0  # rough
    if abs(-err) > 0 and abs((td - ptd) * 6) >= 0.5 * abs(err):
        return "TD variance"
    if r.absent_tgt >= 5 and r.pos in ("WR", "TE", "RB"):
        return "teammate out"
    return "efficiency/game script"


def list_misses(d, m, n, label):
    x = d.assign(err=d[m] - d.act, abserr=(d[m] - d.act).abs()).nlargest(n, "abserr").copy()
    x["cause"] = x.apply(lambda r: cause(r, m), axis=1)
    x["other_err"] = (x["fc" if m == "ours" else "ours"] - x.act)
    return x


s26 = J[(J.regime == "prod2026") & (J.mx > 8)]
cols = ["season", "week", "player", "pos", "team", "salary", "ours", "fc", "act", "err", "other_err", "targets", "prior3_tgt",
        "tgt_share", "prior3_share", "absent_tgt", "cause"]
for m, lab in [("ours", "OURS"), ("fc", "FC")]:
    x = list_misses(s26, m, 40, lab)
    x[cols].to_csv(OUT / f"misses_2026_{m}.csv", index=False)
    P(f"\n== 2026 wk1-2 main, {lab} top-40 misses by |err|: cause mix"); P(x.cause.value_counts().to_string())
    P(f"   sign: over-proj {int((x.err > 0).sum())} / under-proj {int((x.err < 0).sum())}; mean |err| {x.err.abs().mean():.1f}; "
      f"other model on same rows mean |err| {x.other_err.abs().mean():.1f}")
# where they differ: rows where |our err| - |fc err| is largest
s26 = s26.assign(gap=(s26.ours - s26.act).abs() - (s26.fc - s26.act).abs())
d = s26.nlargest(25, "gap").assign(err=lambda z: z.ours - z.act, other_err=lambda z: z.fc - z.act)
d["cause"] = d.apply(lambda r: cause(r, "ours"), axis=1)
d[cols + ["gap"]].to_csv(OUT / "misses_2026_ours_worse.csv", index=False)
P("\n== 2026: 25 rows where OURS is most worse than FC (|ours err|-|fc err|)"); P(d[["week", "player", "pos", "salary", "ours", "fc", "act", "cause"]].round(1).to_string(index=False))
e = s26.nsmallest(25, "gap"); P(f"   ... and 25 where OURS most better: mean gap {e.gap.mean():.1f}, worse-25 mean gap {d.gap.mean():.1f}")
P("   rows where ours worse by pos:", d.pos.value_counts().to_dict(), " ours better by pos:", e.pos.value_counts().to_dict())

hs = J[(J.regime == "hist") & (J.mx > 8)]
for m in ["ours", "fc"]:
    x = list_misses(hs, m, 300, m)
    x[cols].to_csv(OUT / f"misses_hist_{m}_top300.csv", index=False)
    P(f"\n== History top-300 misses, {m}: cause mix {x.cause.value_counts(normalize=True).round(2).to_dict()}; "
      f"over-proj share {(x.err > 0).mean():.2f}; pos {x.pos.value_counts().to_dict()}")

# ---------- cause classes over ALL relevant rows: share of squared error by cause, both models ----------
P("\n== Share of total squared error by cause class (relevant skill rows), OURS vs FC")
for reg in ["hist", "prod2026"]:
    d = J[(J.regime == reg) & (J.mx > 8) & (J.pos != "DST")].copy()
    for m in ["ours", "fc"]:
        d["c_" + m] = d.apply(lambda r: cause(r, m), axis=1)
        d["se_" + m] = (d[m] - d.act) ** 2
    t = pd.DataFrame({m: d.groupby("c_" + m)["se_" + m].sum() / len(d) for m in ["ours", "fc"]})
    t["n_ours"] = d.c_ours.value_counts()
    P(f"  {reg} (MSE contribution per row; totals ours {d.se_ours.mean():.1f}, fc {d.se_fc.mean():.1f})"); P(t.round(2).to_string())

# ---------- cheap WR/TE: stat-line decomposition ----------
P("\n" + "#" * 100 + "\n# CHEAP WR/TE (<$5.5k, relevant, both>0): what drives the error, OURS vs FC")
W = J[J.pos.isin(["WR", "TE"]) & (J.salary < 5500) & (J.mx > 8) & (J.fc > 0) & (J.ours > 0)].copy()
W = W[W.targets.notna()]
W["act_rp"] = W.receptions + .1 * W.receiving_yards + 6 * W.receiving_tds
for reg in ["hist", "prod2026"]:
    d = W[W.regime == reg].copy()
    if d.empty: continue
    P(f"\n-- {reg}: n={len(d)}; MAE ours {(d.ours - d.act).abs().mean():.2f} fc {(d.fc - d.act).abs().mean():.2f}; "
      f"corr ours {d.ours.corr(d.act):.3f} fc {d.fc.corr(d.act):.3f}; bias ours {(d.ours - d.act).mean():+.2f} fc {(d.fc - d.act).mean():+.2f}")
    has = d.fc_tar.notna()
    dd = d[has]
    P(f"   TARGETS (n={len(dd)} rows with FC stat line): corr(proj_tgt, act) ours {dd.proj_targets.corr(dd.targets):.3f} fc {dd.fc_tar.corr(dd.targets):.3f}; "
      f"MAE ours {(dd.proj_targets - dd.targets).abs().mean():.2f} fc {(dd.fc_tar - dd.targets).abs().mean():.2f}; "
      f"bias ours {(dd.proj_targets - dd.targets).mean():+.2f} fc {(dd.fc_tar - dd.targets).mean():+.2f}")
    P(f"   naive pre-lock usage: corr(prior3_tgt, act tgt) {dd.prior3_tgt.corr(dd.targets):.3f} (n={dd.prior3_tgt.notna().sum()}); "
      f"corr(lag1_tgt, act) {dd.lag1_tgt.corr(dd.targets):.3f}")
    # per-target efficiency: projected pts per projected target vs actual
    for m, tcol in [("ours", "proj_targets"), ("fc", "fc_tar")]:
        ppt = dd[m] / dd[tcol].replace(0, np.nan)
        # volume-oracle: rescale projection by actual/projected targets
        orc = ppt * dd.targets
        P(f"   {m}: MSE {((dd[m] - dd.act) ** 2).mean():.1f}  |  with PERFECT target volume (proj pts/tgt x actual tgt) MSE {((orc - dd.act) ** 2).mean():.1f}")
    # does pre-lock usage add to each model's target projection?
    z = dd.dropna(subset=["prior3_tgt"])
    for m, tcol in [("ours", "proj_targets"), ("fc", "fc_tar")]:
        f = ols(z.targets, z[[tcol, "prior3_tgt"]], z.slate)
        r0 = ols(z.targets, z[[tcol]]).rsquared
        P(f"   act_tgt ~ {m}_tgt + prior3_tgt: coef {m} {f.params[tcol]:.2f}, prior3 {f.params['prior3_tgt']:.2f} (t {f.tvalues['prior3_tgt']:.1f}); R2 {r0:.3f} -> {f.rsquared:.3f}")
    # points: does FC add to ours, and does prior usage add to ours (pts)?
    z2 = d.dropna(subset=["prior3_tgt"])
    f = ols(z2.act, z2[["ours", "fc"]], z2.slate)
    P(f"   act ~ ours + fc: coef ours {f.params['ours']:.2f} (t {f.tvalues['ours']:.1f}) fc {f.params['fc']:.2f} (t {f.tvalues['fc']:.1f})")
    f = ols(z2.act, z2[["ours", "prior3_tgt"]], z2.slate)
    P(f"   act ~ ours + prior3_tgt: coef prior3 {f.params['prior3_tgt']:.2f} (t {f.tvalues['prior3_tgt']:.1f})")
    # teammate absence
    for lab, g in [("teammate out (absent_tgt>=5)", d[d.absent_tgt >= 5]), ("no big absence", d[d.absent_tgt < 5])]:
        if len(g) < 10: continue
        P(f"   {lab:30s} n={len(g):5d} bias ours {(g.ours - g.act).mean():+.2f} fc {(g.fc - g.act).mean():+.2f} | MAE ours {(g.ours - g.act).abs().mean():.2f} fc {(g.fc - g.act).abs().mean():.2f}"
          + (f" | tgt bias ours {(g.proj_targets - g.targets).mean():+.2f} fc {(g.fc_tar - g.targets).mean():+.2f}" if g.fc_tar.notna().any() else ""))
    # role change: realized share vs prior share
    rc = d.dropna(subset=["prior3_share", "tgt_share"])
    for lab, g in [("share UP >=.08", rc[rc.tgt_share - rc.prior3_share >= .08]), ("share DOWN >=.08", rc[rc.tgt_share - rc.prior3_share <= -.08]),
                   ("stable", rc[(rc.tgt_share - rc.prior3_share).abs() < .08])]:
        P(f"   {lab:30s} n={len(g):5d} bias ours {(g.ours - g.act).mean():+.2f} fc {(g.fc - g.act).mean():+.2f} | MAE ours {(g.ours - g.act).abs().mean():.2f} fc {(g.fc - g.act).abs().mean():.2f}")
    # week 1 / early season
    for lab, g in [("weeks 1-3", d[d.week <= 3]), ("weeks 4+", d[d.week > 3])]:
        if len(g) < 10: continue
        P(f"   {lab:30s} n={len(g):5d} MAE ours {(g.ours - g.act).abs().mean():.2f} fc {(g.fc - g.act).abs().mean():.2f} | corr ours {g.ours.corr(g.act):.3f} fc {g.fc.corr(g.act):.3f}")

# ---------- props on 2026 wk3 (only slates where the props anchor existed) ----------
P("\n" + "#" * 100 + "\n# PROPS: were they applied, did they move cheap WR/TE, did they help? (2026)")
P("  wk1/wk2 classic: NO props snapshot exists (data/props has none; props anchor added after WK2 postmortem) -> props were NOT applied on any FC-comparable slate.")
el = pd.read_csv(R / "data/projection_error_log.csv", dtype={"player_id": str})
for sl in ["main", "early", "afternoon"]:
    a = pd.read_csv(R / f"data/props/audit_dk_classic_wk3_{sl}_27Sep2026.csv", dtype={"player_id": str})
    e = el[el.slate_id == f"dk_classic_wk3_{sl}_27Sep2026"][["player_id", "salary"] if "salary" in el else ["player_id", "final_projection", "actual_fpts"]]
    e = el[el.slate_id == f"dk_classic_wk3_{sl}_27Sep2026"][["player_id", "final_projection", "actual_fpts"]]
    x = a.merge(e, on="player_id")
    x = x[x.position.isin(["WR", "TE"])]
    m = x.props_matched.fillna(False).astype(bool)
    eng = x.props_rec_engine + .1 * x.props_recyd_engine + 6 * x.props_td_engine.fillna(0)
    mkt = x.props_rec_market.fillna(x.props_rec_engine) + .1 * x.props_recyd_market.fillna(x.props_recyd_engine) + 6 * x.props_td_market.fillna(x.props_td_engine).fillna(0)
    xm = x[m]
    P(f"  wk3 {sl}: WR/TE rows {len(x)}, props matched {int(m.sum())}; mean |market-engine| rec-pts {(mkt - eng)[m].abs().mean():.2f}; "
      f"corr(engine recpts, act) {eng[m].corr(xm.actual_fpts):.3f} vs corr(market recpts, act) {mkt[m].corr(xm.actual_fpts):.3f}; "
      f"MAE final {(xm.final_projection - xm.actual_fpts).abs().mean():.2f}")
J.to_parquet(OUT / "frame_with_absence.parquet")
LOG.close()
