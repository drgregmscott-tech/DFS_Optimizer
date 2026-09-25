"""ECR blend experiment (offline). Writes only to analysis/proj_ecr/.

Usage: python analysis/proj_ecr/ecr_blend.py
Inputs (not in repo): scratchpad db_fpecr.parquet, db_playerids.csv.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "analysis" / "backtest_multi"))
import evaluate as ev  # noqa: E402  (reuse load_arm / metrics / TOPN)

SP = Path(r"C:\Users\gmsco\AppData\Local\Temp\claude\C--Users-gmsco-Desktop-DFS-Optimizer"
          r"\1e340482-2297-41aa-82af-a05801d10a60\scratchpad")
SKILL = ["QB", "RB", "WR", "TE"]
W = [0, .1, .2, .3, .4, .5, .7, 1.0]
TOPN = ev.TOPN
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.append(s)


def norm(s):
    s = str(s).lower()
    s = re.sub(r"[.'`,-]", "", s)
    s = re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- ECR + mapping
def load_ecr():
    e = pd.read_parquet(SP / "db_fpecr.parquet")
    e = e[e.page_type.isin([f"weekly-{p.lower()}" for p in SKILL])].copy()
    e["pos"] = e.page_type.str[-2:].str.upper()
    e["sd_"] = pd.to_datetime(e.scrape_date)
    e = e[e.sd_.dt.year.isin([2020, 2021, 2026])]
    rows = []
    games = {}
    for s in (2020, 2021, 2026):
        sc = pd.read_parquet(REPO / "data" / f"schedules_{s}.parquet")
        sc = sc[sc.game_type == "REG"].copy()
        sc["gd"] = pd.to_datetime(sc.gameday)
        games[s] = sc
    for d in sorted(e.scrape_date.unique()):
        dt = pd.Timestamp(d)
        s = dt.year
        sc = games[s]
        later = sc[sc.gd > dt]  # strictly later calendar day -> pre-kickoff by construction
        wk = int(later.sort_values("gd").week.iloc[0]) if len(later) else None
        rows.append(dict(scrape_date=d, season=s, week=wk,
                         weekday=dt.day_name()[:3],
                         week_first_game=str(sc[sc.week == wk].gd.min().date()) if wk else None))
    mp = pd.DataFrame(rows)
    # duplicates: keep the latest snapshot per week (freshest; still pre-kickoff for eligible games)
    mp["dup_dropped"] = mp.duplicated(["season", "week"], keep="last")
    e = e.merge(mp[~mp.dup_dropped][["scrape_date", "season", "week"]], on="scrape_date")
    # eligible teams per snapshot: team's game that week has gameday > scrape_date
    elig = []
    for s, sc in games.items():
        for _, g in sc.iterrows():
            for t in (g.home_team, g.away_team):
                elig.append((s, int(g.week), t, g.gd))
    elig = pd.DataFrame(elig, columns=["season", "week", "team_sched", "gd"])
    return e, mp, elig


TEAMFIX = {"JAC": "JAX", "LA": "LA", "LAR": "LA", "STL": "LA", "SD": "LAC", "OAK": "LV",
           "WSH": "WAS", "KCC": "KC", "GBP": "GB", "NEP": "NE", "NOS": "NO", "SFO": "SF",
           "TBB": "TB", "LVR": "LV"}


def attach_ecr(df, e, label):
    """df: our rows (season, week, player_id, player_name, position, team). Adds ecr, ecr_sd."""
    ids = pd.read_csv(SP / "db_playerids.csv", dtype=str, usecols=["fantasypros_id", "gsis_id"])
    ids = ids.dropna().drop_duplicates("fantasypros_id")
    e = e.merge(ids, left_on="id", right_on="fantasypros_id", how="left")
    e["nm"] = e.player.map(norm)
    e["tm"] = e.team.replace(TEAMFIX)
    key = ["season", "week"]
    out = df.copy()
    out["nm"] = out.player_name.map(norm)
    out["tm"] = out.team.replace(TEAMFIX)
    a = e.dropna(subset=["gsis_id"]).drop_duplicates(key + ["gsis_id", "pos"])
    m1 = out.merge(a[key + ["gsis_id", "pos", "ecr", "sd", "scrape_date"]],
                   left_on=key + ["player_id", "position"], right_on=key + ["gsis_id", "pos"], how="left")
    m1["how"] = np.where(m1.ecr.notna(), "gsis", None)
    miss = m1.ecr.isna()
    b = e.drop_duplicates(key + ["nm", "pos", "tm"])[key + ["nm", "pos", "tm", "ecr", "sd", "scrape_date"]]
    m2 = m1.loc[miss].drop(columns=["ecr", "sd", "scrape_date"]).merge(
        b, left_on=key + ["nm", "position", "tm"], right_on=key + ["nm", "pos", "tm"], how="left",
        suffixes=("", "_b"))
    m1.loc[miss, "ecr"] = m2.ecr.to_numpy()
    m1.loc[miss, "sd"] = m2.sd.to_numpy()
    m1.loc[miss, "scrape_date"] = m2.scrape_date.to_numpy()
    m1.loc[miss & m1.ecr.notna(), "how"] = "name+team"
    # sanity: ECR rows that could not be matched to any of our rows (by week, pos)
    return m1.drop(columns=["gsis_id", "pos"], errors="ignore")


def eligible(m, elig):
    x = m.merge(elig, left_on=["season", "week", "team"], right_on=["season", "week", "team_sched"], how="left")
    ok = x.scrape_date.isna() | (x.gd > pd.to_datetime(x.scrape_date))
    return ok.to_numpy()


# ---------------------------------------------------------------- scores
def pava_dec(x, y):
    """Monotone non-increasing fit of y on x (x=ecr, small is good). Returns (xs, fitted)."""
    o = np.argsort(x, kind="stable")
    xs, ys = x[o], y[o].astype(float)
    # isotonic increasing on -x equivalently non-increasing on x
    v, w, blocks = [], [], []
    for yi in ys:
        v.append(yi); w.append(1.0); blocks.append(1)
        while len(v) > 1 and v[-2] < v[-1]:  # violation for non-increasing
            nv = (v[-2] * w[-2] + v[-1] * w[-1]) / (w[-2] + w[-1])
            nw = w[-2] + w[-1]; nb = blocks[-2] + blocks[-1]
            v = v[:-2] + [nv]; w = w[:-2] + [nw]; blocks = blocks[:-2] + [nb]
    fit = np.repeat(v, blocks)
    return xs, fit


def fit_maps(train):
    maps = {}
    for p, g in train.groupby("position"):
        xs, f = pava_dec(g.ecr.to_numpy(), g.actual_points.to_numpy())
        # collapse duplicate x
        t = pd.DataFrame({"x": xs, "f": f}).groupby("x").f.mean()
        maps[p] = (t.index.to_numpy(), t.to_numpy())
    return maps


def ecr_pts(d, maps):
    out = np.full(len(d), np.nan)
    for p, (xs, f) in maps.items():
        k = (d.position == p).to_numpy()
        out[k] = np.interp(d.ecr.to_numpy()[k], xs, f)
    return out


def add_scores(d, maps, grp):
    d = d.copy()
    g = d.groupby(grp)
    d["r_ours"] = g.final_projection.rank(ascending=False, method="average")
    d["r_ecr"] = g.ecr.rank(ascending=True, method="average")
    d["z_ours"] = (d.final_projection - g.final_projection.transform("mean")) / g.final_projection.transform("std")
    d["z_ecr"] = -(d.ecr - g.ecr.transform("mean")) / g.ecr.transform("std")
    d["ecr_pts"] = ecr_pts(d, maps)
    return d


def score(d, form, w):
    """w = weight on ECR."""
    if form == "rank":
        return -((1 - w) * d.r_ours + w * d.r_ecr)
    if form == "pts":
        return (1 - w) * d.final_projection + w * d.ecr_pts
    if form == "z":
        return (1 - w) * d.z_ours + w * d.z_ecr.fillna(0)
    raise ValueError(form)


# ---------------------------------------------------------------- metrics
def cellstats(d, col, grp):
    """per (week-group) x position: spearman, topN actual, topN hit."""
    rows = []
    for k, g in d.groupby(grp + ["position"]):
        pos = k[-1]
        n = TOPN[pos]
        r = dict(zip(grp + ["position"], k))
        r["sp"] = g[col].corr(g.actual_points, method="spearman") if len(g) >= 5 else np.nan
        if len(g) >= 2 * n:
            top = g.nlargest(n, col)
            r["tn"] = top.actual_points.mean()
            r["hit"] = top.index.isin(g.nlargest(n, "actual_points").index).mean()
        else:
            r["tn"] = r["hit"] = np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def pointstats(d, col):
    e = d[col] - d.actual_points
    return dict(bias=e.mean(), MAE=e.abs().mean(), RMSE=float(np.sqrt((e ** 2).mean())),
                pearson=d[col].corr(d.actual_points))


def summarize(d, col, grp, points=True):
    c = cellstats(d, col, grp)
    r = dict(n=len(d), cells=len(c), spearman=c.sp.mean(), topN=c.tn.mean(), hit=c.hit.mean())
    if points:
        r.update(pointstats(d, col))
    return r


def paired(d, a, b, grp, B=2000, seed=11):
    """b - a, week-resampled 95% CI (weeks = unique grp keys w/o position)."""
    ca, cb = cellstats(d, a, grp), cellstats(d, b, grp)
    c = ca.merge(cb, on=grp + ["position"], suffixes=("_a", "_b"))
    c["dsp"] = c.sp_b - c.sp_a
    c["dtn"] = c.tn_b - c.tn_a
    wk = c.groupby(grp)[["dsp", "dtn"]].mean()
    d = d.assign(dae=(d[b] - d.actual_points).abs() - (d[a] - d.actual_points).abs())
    wa = d.groupby(grp).dae.agg(["sum", "count"])
    wk = wk.join(wa)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(wk), size=(B, len(wk)))
    res = {}
    for m in ("dsp", "dtn"):
        arr = wk[m].to_numpy()
        bs = np.nanmean(arr[idx], axis=1)
        res[m] = (np.nanmean(arr), np.percentile(bs, 2.5), np.percentile(bs, 97.5))
    s, n = wk["sum"].to_numpy(), wk["count"].to_numpy()
    bs = s[idx].sum(1) / n[idx].sum(1)
    res["dMAE"] = (s.sum() / n.sum(), np.percentile(bs, 2.5), np.percentile(bs, 97.5))
    res["weeks"] = len(wk)
    return res


def fmt_ci(t):
    return f"{t[0]:+.3f} [{t[1]:+.3f},{t[2]:+.3f}]"


# ---------------------------------------------------------------- main
def main():
    e, mp, elig = load_ecr()
    log("## snapshot -> week mapping (week = first week with a game on a later calendar day)")
    log(mp.to_string(index=False))
    mp.to_csv(HERE / "snapshot_week_map.csv", index=False)

    # ---------- historical
    hist = {}
    for arm in ("baseline", "no_stack"):
        df = ev.load_arm(arm)
        df = df[df.season.isin([2020, 2021]) & df.position.isin(SKILL) & (df.final_projection > 0)]
        m = attach_ecr(df, e, arm)
        m["elig"] = eligible(m, elig)
        hist[arm] = m
    m = hist["baseline"]
    rel = m[m.final_projection > 8]
    log(f"\n## coverage (baseline, 2020+2021 rows with a snapshot week)")
    snapwk = set(zip(mp.season, mp.week))
    m_ = m[[(s, w) in snapwk for s, w in zip(m.season, m.week)]]
    rel = m_[m_.final_projection > 8]
    log(f"weeks with ECR: {m_.groupby(['season','week']).ngroups}; rows proj>0: {len(m_)}; ECR matched: {m_.ecr.notna().mean():.3f}")
    log(f"rows proj>8 (n={len(rel)}): ECR matched {rel.ecr.notna().mean():.3f}; via gsis {(rel.how=='gsis').mean():.3f}, name+team {(rel.how=='name+team').mean():.3f}")
    log("proj>8 match rate by pos: " + str(rel.groupby('position').ecr.apply(lambda s: round(s.notna().mean(), 3)).to_dict()))
    top = m_.assign(r=m_.groupby(["season", "week", "position"]).final_projection.rank(ascending=False))
    top = top[top.r <= top.position.map(TOPN) * 2]
    log(f"our top-2N per pos (n={len(top)}): ECR matched {top.ecr.notna().mean():.3f}")
    log(f"TNF/same-day-game rows dropped by pre-kickoff guard (among ECR-matched): {int((m_.ecr.notna() & ~m_.elig).sum())}")
    # ECR rows not matched to our pool
    e_h = e[e.season.isin([2020, 2021])]
    got = set(zip(m_.season, m_.week, m_.position, m_.ecr.round(3)))
    unm = e_h[[ (s, w, p, round(x, 3)) not in got for s, w, p, x in zip(e_h.season, e_h.week, e_h.pos, e_h.ecr)]]
    e_h_top = e_h[e_h.ecr <= e_h.pos.map(TOPN) * 1.5]
    unm_top = unm[unm.ecr <= unm.pos.map(TOPN) * 1.5]
    log(f"ECR rows with ecr<=1.5N not joined to our pool: {len(unm_top)}/{len(e_h_top)} (e.g. {unm_top.player.head(8).tolist()})")

    grp = ["season", "week"]
    results = []
    for arm, M in hist.items():
        C = M[M.ecr.notna() & M.elig].copy()
        for pop in ("played", "all"):
            P = C[C.played] if pop == "played" else C
            for tr, te in ((2020, 2021), (2021, 2020)):
                Tr, Te = P[P.season == tr], P[P.season == te]
                # maps fit on the TRAIN played population only
                Trp = C[(C.season == tr) & C.played] if pop == "played" else Tr
                maps = fit_maps(Trp)
                Tr, Te = add_scores(Tr, maps, grp + ["position"]), add_scores(Te, maps, grp + ["position"])
                # choose w on train by within-slate spearman: pooled and per position
                choice = {}
                for form in ("rank", "pts", "z"):
                    sc = []
                    for w in W:
                        Tr["s"] = score(Tr, form, w)
                        c = cellstats(Tr, "s", grp)
                        sc.append((w, c.sp.mean(), c.groupby("position").sp.mean().to_dict()))
                    wbest = max(sc, key=lambda t: t[1])[0]
                    wpos = {p: max(sc, key=lambda t: t[2][p])[0] for p in SKILL}
                    choice[form] = (wbest, wpos)
                Te["ours"] = Te.final_projection
                Te["ecr_only"] = -Te.ecr
                Te["ecr_pts_only"] = Te.ecr_pts
                for form in ("rank", "pts", "z"):
                    wb, wp = choice[form]
                    Te[f"{form}"] = score(Te, form, wb)
                    Te[f"{form}_pp"] = np.nan
                    for p in SKILL:
                        k = Te.position == p
                        Te.loc[k, f"{form}_pp"] = score(Te[k], form, wp[p])
                for col in ["ours", "ecr_only", "ecr_pts_only", "rank", "rank_pp", "pts", "pts_pp", "z", "z_pp"]:
                    pts = col in ("ours", "ecr_pts_only", "pts", "pts_pp")
                    for pos in ["skill"] + SKILL:
                        D = Te if pos == "skill" else Te[Te.position == pos]
                        r = dict(arm=arm, pop=pop, train=tr, test=te, pos=pos, score=col,
                                 w=(choice[col.split("_")[0]][0] if col in ("rank", "pts", "z") else
                                    (str(choice[col.split("_")[0]][1]) if col.endswith("_pp") else "")),
                                 **summarize(D, col, grp, pts))
                        if col != "ours":
                            pr = paired(D, "ours", col, grp)
                            r.update(dsp=fmt_ci(pr["dsp"]), dtn=fmt_ci(pr["dtn"]),
                                     dMAE=fmt_ci(pr["dMAE"]) if pts else "", weeks=pr["weeks"])
                        results.append(r)
                # shuffle test on chosen pooled-weight blends (played/all, both arms)
                rng = np.random.default_rng(0)
                sh = {f: [] for f in ("rank", "pts", "z")}
                for it in range(30):
                    S = Te.copy()
                    S["ecr"] = S.groupby(grp + ["position"]).ecr.transform(lambda s: rng.permutation(s.to_numpy()))
                    S = add_scores(S, maps, grp + ["position"])
                    for f in sh:
                        S["s"] = score(S, f, choice[f][0])
                        sh[f].append(cellstats(S, "s", grp).sp.mean() - cellstats(S, "final_projection", grp).sp.mean())
                log(f"shuffle {arm}/{pop} train{tr}->test{te}: chosen w " +
                    ", ".join(f"{f}={choice[f][0]} (per-pos {choice[f][1]})" for f in sh) +
                    " | shuffled dSpearman mean: " + ", ".join(f"{f} {np.mean(v):+.3f} (sd {np.std(v):.3f})" for f, v in sh.items()))
    R = pd.DataFrame(results)
    R.to_csv(HERE / "results_historical.csv", index=False)

    # reproduction check vs metrics_baseline_played.csv (full set, then common set)
    ref = pd.read_csv(REPO / "analysis/backtest_multi/out/metrics_baseline_played.csv")
    B = hist["baseline"]
    B = B[B.played]
    mine = ev.table(B, ["season", "position"])
    cmp_ = mine.merge(ref, on=["season", "position"], suffixes=("_me", "_ref"))
    log("\n## reproduction: full played set via evaluate.metrics vs metrics_baseline_played.csv")
    log(cmp_[["season", "position", "n_me", "n_ref", "spearman_wxp_me", "spearman_wxp_ref", "MAE_me", "MAE_ref"]].to_string(index=False))

    # ---------- live 2026
    D = pd.read_csv(REPO / "analysis/proj_b1/b1_frame.csv", dtype={"player_id": str})
    D = D.assign(p=D["sub"].map({"main": 0, "early": 1, "afternoon": 2})).sort_values("p") \
         .drop_duplicates(["player_id", "week"])
    D = D[D.position.isin(SKILL)].copy()
    D["season"] = 2026
    D["actual_points"] = D["act"]
    L = attach_ecr(D, e, "live")
    L["elig"] = eligible(L, elig)
    log(f"\n## live 2026: {len(L)} unique player-weeks (proj>8); ECR matched {L.ecr.notna().mean():.3f} "
        f"(gsis {(L.how=='gsis').mean():.3f}, name {(L.how=='name+team').mean():.3f}); by week "
        + str(L.groupby('week').ecr.apply(lambda s: round(s.notna().mean(), 3)).to_dict())
        + "; unmatched: " + str(L[L.ecr.isna()][['week','player_name','position','team']].values.tolist()))
    Lc = L[L.ecr.notna() & L.elig].copy()
    # pooled 2020+2021 fit on baseline played (live stack is shipped -> baseline is the analogue)
    C = hist["baseline"]
    C = C[C.ecr.notna() & C.elig & C.played]
    maps = fit_maps(C)
    Cs = add_scores(C, maps, grp + ["position"])
    choice = {}
    for form in ("rank", "pts", "z"):
        sc = []
        for w in W:
            Cs["s"] = score(Cs, form, w)
            c = cellstats(Cs, "s", grp)
            sc.append((w, c.sp.mean(), c.groupby("position").sp.mean().to_dict()))
        choice[form] = (max(sc, key=lambda t: t[1])[0], {p: max(sc, key=lambda t: t[2][p])[0] for p in SKILL})
        log(f"pooled-fit {form}: train spearman by w " + ", ".join(f"{w}:{s:.3f}" for w, s, _ in sc))
    log("pooled-fit chosen: " + str(choice))
    log("pooled isotonic map (ecr -> pts) at ecr 1/6/12/24/36: " + str({p: [round(float(np.interp(x, *maps[p])), 1) for x in (1, 6, 12, 24, 36)] for p in SKILL}))
    Ls = add_scores(Lc, maps, ["week", "position"])
    Ls["ours"] = Ls.final_projection
    Ls["ecr_only"] = -Ls.ecr
    for form in ("rank", "pts", "z"):
        Ls[form] = score(Ls, form, choice[form][0])
        Ls[form + "_pp"] = np.nan
        for p in SKILL:
            k = Ls.position == p
            Ls.loc[k, form + "_pp"] = score(Ls[k], form, choice[form][1][p])
    Ls["ecr_pts_only"] = Ls.ecr_pts
    live = []
    rng = np.random.default_rng(3)
    for wk in (1, 2, "both"):
        X = Ls if wk == "both" else Ls[Ls.week == wk]
        for pos in ["skill"] + SKILL:
            Y = X if pos == "skill" else X[X.position == pos]
            base = summarize(Y, "ours", ["week"])
            for col in ["ours", "ecr_only", "ecr_pts_only", "rank", "rank_pp", "pts", "pts_pp", "z", "z_pp"]:
                pts = col in ("ours", "ecr_pts_only", "pts", "pts_pp")
                r = dict(week=wk, pos=pos, score=col, **summarize(Y, col, ["week"], pts))
                if col != "ours":
                    # player bootstrap within week x position for dSpearman
                    bs = []
                    cells_ix = [g.index.to_numpy() for _, g in Y.groupby(["week", "position"])]
                    for _ in range(300):
                        ix = np.concatenate([rng.choice(c, len(c)) for c in cells_ix])
                        Z = Y.loc[ix].reset_index(drop=True)
                        c1, c2 = cellstats(Z, col, ["week"]), cellstats(Z, "ours", ["week"])
                        bs.append(c1.sp.mean() - c2.sp.mean())
                    r["dsp"] = f"{r['spearman']-base['spearman']:+.3f} [{np.nanpercentile(bs,2.5):+.3f},{np.nanpercentile(bs,97.5):+.3f}]"
                    r["dtopN"] = r["topN"] - base["topN"]
                    if pts:
                        r["dMAE"] = r["MAE"] - base["MAE"]
                live.append(r)
    LV = pd.DataFrame(live)
    LV.to_csv(HERE / "results_live2026.csv", index=False)
    # live shuffle
    sh = []
    for it in range(50):
        S = Lc.copy()
        S["ecr"] = S.groupby(["week", "position"]).ecr.transform(lambda s: rng.permutation(s.to_numpy()))
        S = add_scores(S, maps, ["week", "position"])
        S["s"] = score(S, "z", choice["z"][0])
        sh.append(cellstats(S, "s", ["week"]).sp.mean() - cellstats(S, "final_projection", ["week"]).sp.mean())
    log(f"live shuffle (z blend, w={choice['z'][0]}): dSpearman mean {np.mean(sh):+.3f} sd {np.std(sh):.3f}")
    (HERE / "run_log.txt").write_text("\n".join(LOG), encoding="utf-8")


if __name__ == "__main__":
    main()
