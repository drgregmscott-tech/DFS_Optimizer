"""
ownership_v2.py
===============

Ownership v2 (2026-09-29, analysis/ownership_v2/RESULTS.md), DK classic only.

WHAT IT DOES
------------
Runs inside ownership_model.refine_ownership() AFTER the live layered model.

- Skill groups (QB/RB/WR/TE): a per-position softmax over a linear score of
  ~47 pre-lock features (price, our projection, Vegas, public value rebuilt
  from nflverse, recency, name value, price move, last-week ownership, role /
  vacated usage, optimizer exposure, heuristic), times the group budgets stored
  in the artifact, water-filled at 75%.
- When the slate has an FFC public-ownership table (live FFC variant in use)
  the score is log-blended with the live model:
      F = a * F_v2 + (1 - a) * log(max(live_ffc_pred, .05)),  a = 0.45
  (0.4-0.5 was best leave-one-week-out on 9 slates). Without FFC: pure v2.
- DST group: replaced by the v2 DST softmax (cheapness, weak opponent,
  viable / cheapest-viable flags, pressure), budget 100.

LEAKAGE RULES (enforced here)
-----------------------------
- nflverse weekly stats: only rows with (season, week) strictly before the
  slate's (season, week). A Thursday game of the current week already in the
  parquet is ignored.
- Vacated usage uses the pool as it stands (final_projection > 0). The build
  and status_check apply zero OUT/DOUBTFUL before ownership is (re)computed,
  so vacated reflects the pre-lock OUT list, never who actually played.
- Team totals are derived from skill rows (DST opponent total = opponent's
  team total), never from the DST row's own implied_total.
- Group budgets come from the artifact, not from any realized slate total.
- No Fantasy Cruncher input of any kind.

Artifacts: data/ownership_v2_dk_linear.json, data/ownership_v2_dk_dst.json
(coefficients only; fitted on realized DK SE ownership 2021-25).

Switch: env DFS_OWNERSHIP_V2=0 (or ownership_model.OWNERSHIP_V2_ENABLED=False)
restores the previous path exactly. Any failure falls back to the previous
path with a warning.
"""

import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"

GROUPS = ["QB", "RB", "WR", "TE", "DST"]
CAP = 75.0
FFC_BLEND_ALPHA = 0.45
TEAM_FIX = {"JAC": "JAX", "LAR": "LA", "LVR": "LV", "WSH": "WAS"}
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def linear_path(site="dk"):
    return DATA_DIR / f"ownership_v2_{site}_linear.json"


def dst_path(site="dk"):
    return DATA_DIR / f"ownership_v2_{site}_dst.json"


def load_artifacts(site="dk"):
    lp, dp = linear_path(site), dst_path(site)
    if not lp.exists() or not dp.exists():
        return None, None
    with open(lp, encoding="utf-8") as f:
        lin = json.load(f)
    with open(dp, encoding="utf-8") as f:
        dst = json.load(f)
    return lin, dst


def infer_season():
    env = os.environ.get("DFS_SEASON")
    if env:
        return int(env)
    yrs = [int(m.group(1)) for p in DATA_DIR.glob("weekly_stats_*.parquet")
           if (m := re.search(r"weekly_stats_(\d{4})\.parquet$", p.name))]
    if not yrs:
        raise RuntimeError("no data/weekly_stats_*.parquet to infer season from")
    return max(yrs)


# ----------------------------------------------------------------------------- stats / context
def dk_points(w):
    return (w.passing_yards.fillna(0) * .04 + w.passing_tds.fillna(0) * 4 - w.passing_interceptions.fillna(0)
            + w.rushing_yards.fillna(0) * .1 + w.rushing_tds.fillna(0) * 6 + w.receptions.fillna(0)
            + w.receiving_yards.fillna(0) * .1 + w.receiving_tds.fillna(0) * 6
            + 3 * (w.passing_yards.fillna(0) >= 300) + 3 * (w.rushing_yards.fillna(0) >= 100)
            + 3 * (w.receiving_yards.fillna(0) >= 100)
            - w[["sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"]].fillna(0).sum(1)
            + 2 * w[["passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions"]].fillna(0).sum(1))


def load_stats(season, week):
    """nflverse weekly REG rows strictly before (season, week)."""
    out = []
    for s in range(season - 3, season + 1):
        f = DATA_DIR / f"weekly_stats_{s}.parquet"
        if not f.exists():
            continue
        w = pd.read_parquet(f)
        if "season_type" in w:
            w = w[w.season_type.fillna("REG") == "REG"]
        w = w.copy()
        w["dk"] = dk_points(w)
        w["team"] = w.team.replace(TEAM_FIX)
        w["usage"] = w.targets.fillna(0) + w.carries.fillna(0)
        keep = ["player_id", "season", "week", "team", "position", "dk", "targets", "carries", "usage",
                "def_sacks", "sacks_suffered", "opponent_team"]
        out.append(w[[c for c in keep if c in w]])
    if not out:
        raise RuntimeError("no weekly_stats parquet files for ownership v2")
    a = pd.concat(out, ignore_index=True)
    a["opponent_team"] = a.opponent_team.replace(TEAM_FIX)
    a["t"] = a.season * 100 + a.week
    a = a[a.t < season * 100 + week]  # Thursday-game trap: current week never enters
    return a.sort_values(["player_id", "t"])


def load_prior_salary(site, season, week):
    """(season, week, player_id, salary) from earlier-week classic final_projections files."""
    rows = []
    pat = re.compile(rf"final_projections_{site}_{site}_classic_wk(\d+)_[A-Za-z]+_(\d\d)([A-Z][a-z]{{2}})(\d{{4}})\.csv$")
    for p in OUTPUT_DIR.glob(f"final_projections_{site}_{site}_classic_wk*.csv"):
        m = pat.search(p.name)
        if not m:
            continue
        wk, mon, yr = int(m.group(1)), _MONTHS.get(m.group(3), 9), int(m.group(4))
        ssn = yr - 1 if mon <= 3 else yr
        if ssn != season or wk >= week:
            continue
        d = pd.read_csv(p, usecols=["player_id", "salary", "final_projection"], dtype={"player_id": str})
        d = d[pd.to_numeric(d.final_projection, errors="coerce").fillna(0) > 0]
        rows.append(pd.DataFrame({"season": ssn, "week": wk, "player_id": d.player_id,
                                  "salary": pd.to_numeric(d.salary, errors="coerce")}))
    if not rows:
        return None
    return pd.concat(rows).drop_duplicates(["season", "week", "player_id"])


def load_lag_own(site, season):
    p = DATA_DIR / "ownership_actual_log.csv"
    if not p.exists():
        return None
    lg = pd.read_csv(p, dtype={"player_id": str})
    lg = lg[(lg.site == site) & (lg.slate_format == "classic") & lg.slate_id.str.contains("_main_")
            & (lg.season == season)].copy()
    if lg.empty:
        return None
    lg["week"] = lg.slate_id.str.extract(r"wk(\d+)")[0].astype(int)
    return lg.groupby(["season", "week", "player_id"]).actual_ownership_pct.mean().rename("own").reset_index()


class Ctx:
    """Pre-lock lookup tables. Every query for (season, week) only uses rows with t < season*100+week."""

    def __init__(self, stats, prior_salary=None, lag_own=None):
        self.st = stats
        self.prior_salary = prior_salary
        self.lag_own = lag_own
        g = stats.groupby(["player_id", "season"])
        ss = g.agg(ppg=("dk", "mean"), tot=("dk", "sum"), gp=("dk", "size"), pos=("position", "last")).reset_index()
        ss["pos_rank"] = ss.groupby(["season", "pos"]).tot.rank(ascending=False, method="min")
        self.season_sum = ss
        tm = stats.groupby(["season", "week", "team"]).agg(sk=("def_sacks", "sum"), sa=("sacks_suffered", "sum"),
                                                          opp=("opponent_team", "first")).reset_index()
        tm["t"] = tm.season * 100 + tm.week
        self.team_week = tm.sort_values("t")

    def player_feats(self, season, week, ids):
        t = season * 100 + week
        st = self.st[(self.st.t < t) & self.st.player_id.isin(ids)]
        cur = st[st.season == season]
        o = pd.DataFrame(index=pd.Index(ids, name="player_id"))
        g = cur.groupby("player_id")
        o["ytd_ppg"] = g.dk.mean()
        o["ytd_gp"] = g.dk.size()
        last = st.groupby("player_id").tail(1).set_index("player_id")
        o["last_dk"] = last.dk
        o["last_same_season"] = (last.season == season).astype(float)
        o["last_team"] = last.team
        l3 = st.groupby("player_id").tail(3).groupby("player_id")
        o["p3_usage"] = l3.usage.mean()
        o["p3_tgt"] = l3.targets.mean()
        o["p3_car"] = l3.carries.mean()
        o["p3_dk"] = l3.dk.mean()
        ps = self.season_sum[self.season_sum.season == season - 1].set_index("player_id")
        o["prev_ppg"] = ps.ppg
        o["prev_gp"] = ps.gp
        o["prev_rank"] = ps.pos_rank
        return o

    def team_share(self, season, week):
        t = season * 100 + week
        st = self.st[(self.st.t < t) & (self.st.t >= t - 100)]
        st = st[st.season == season] if (st.season == season).any() else st[st.season == season - 1]
        lastw = st.groupby("team").t.apply(lambda x: sorted(x.unique())[-3:])
        rows = [st[(st.team == tm) & st.t.isin(ws)] for tm, ws in lastw.items()]
        return pd.concat(rows) if rows else st.iloc[:0]

    def dst_feats(self, season, week, teams):
        t = season * 100 + week
        tw = self.team_week[self.team_week.t < t]
        o = pd.DataFrame(index=pd.Index(teams, name="team"))
        last8 = tw.groupby("team").tail(8).groupby("team")
        o["sk_pg"] = last8.sk.mean()
        o["sa_pg"] = last8.sa.mean()
        return o


# ----------------------------------------------------------------------------- features (port of analysis/ownership_v2/common.py)
def build_features(df, ctx):
    df = df.copy()
    df["team"] = df.team.replace(TEAM_FIX)
    df["opp"] = df.opp.replace(TEAM_FIX)
    df["grp"] = df.pos
    df["salk"] = df.salary / 1000.0
    df["proj"] = df.proj.clip(lower=0).fillna(0)
    parts = []
    for _, s in df.groupby("slate_id", sort=False):
        season, week = int(s.season.iloc[0]), int(s.week.iloc[0])
        s = s.copy()
        pf = ctx.player_feats(season, week, s.player_id.unique())
        s = s.join(pf, on="player_id")
        tt = s[s.pos != "DST"].groupby("team").team_total.median()
        s["team_total"] = s.team.map(tt).fillna(s.team_total)
        s["opp_total"] = s.opp.map(tt)
        s["opp_total"] = s.opp_total.fillna(s.game_total - s.team_total)
        s["spread"] = s.team_total - s.opp_total
        s["tt_rank"] = s.groupby("pos").team_total.rank(pct=True)
        s["gt_rank"] = s.game_total.rank(pct=True)
        if ctx.prior_salary is not None:
            ps = ctx.prior_salary[(ctx.prior_salary.season == season) & (ctx.prior_salary.week < week)]
            ps = ps.sort_values("week").groupby("player_id").tail(1).set_index("player_id")
            s["sal_prev"] = s.player_id.map(ps.salary)
            s["wk_since_prev"] = week - s.player_id.map(ps.week)
        else:
            s["sal_prev"] = np.nan
            s["wk_since_prev"] = np.nan
        s["sal_chg"] = ((s.salary - s.sal_prev) / 1000.0).fillna(0.0)
        s["has_prev_sal"] = s.sal_prev.notna().astype(float)
        if ctx.lag_own is not None:
            lo = ctx.lag_own[(ctx.lag_own.season == season) & (ctx.lag_own.week == week - 1)].set_index("player_id")
            s["lag_own"] = s.player_id.map(lo.own)
            s["lag_own_avail"] = float(len(lo) > 0)
        else:
            s["lag_own"] = np.nan
            s["lag_own_avail"] = 0.0
        s["l_lag_own"] = np.log1p(s.lag_own.fillna(0.0))
        ts = ctx.team_share(season, week)
        pool_ids = set(s.loc[s.in_pool, "player_id"])
        if len(ts):
            ts = ts[ts.position.isin(["RB", "WR", "TE", "QB"])].copy()
            ts["g2"] = np.where(ts.position == "RB", "RB", np.where(ts.position == "QB", "QB", "REC"))
            per = ts.groupby(["team", "g2", "player_id"]).usage.mean().reset_index()
            tot = per.groupby(["team", "g2"]).usage.sum()
            per["share"] = per.usage / per.set_index(["team", "g2"]).index.map(tot).values
            per = per[per.team.isin(set(s.team))]
            per["absent"] = ~per.player_id.isin(pool_ids)
            vac = per[per.absent].groupby(["team", "g2"]).share.sum()
            s["g2"] = np.where(s.pos == "RB", "RB", np.where(s.pos == "QB", "QB", np.where(s.pos == "DST", "DST", "REC")))
            s["vacated"] = [vac.get((a, b), 0.0) for a, b in zip(s.team, s.g2)]
            ms = per.set_index("player_id").share
            s["my_share"] = s.player_id.map(ms[~ms.index.duplicated()]).fillna(0.0)
        else:
            s["vacated"] = 0.0
            s["my_share"] = 0.0
        s.loc[s.pos == "DST", ["vacated", "my_share"]] = 0.0
        dfe = ctx.dst_feats(season, week, list(set(s.team) | set(s.opp.dropna())))
        s["dst_sk"] = s.team.map(dfe.sk_pg)
        s["opp_sa"] = s.opp.map(dfe.sa_pg)
        s["pressure"] = (s.dst_sk.fillna(dfe.sk_pg.mean()) + s.opp_sa.fillna(dfe.sa_pg.mean()))
        parts.append(s)
    df = pd.concat(parts)
    p = df.in_pool & (df.proj > 0)
    df["val"] = np.where(p, df.proj / df.salk.clip(lower=1), 0.0)
    key = [df.slate_id, df.grp]
    for c in ["proj", "val", "salk", "team_total", "pressure"]:
        x = df[c].where(p)
        df[c + "_rk"] = x.groupby(key).rank(ascending=False, method="min")
        df[c + "_lrk"] = np.log(df[c + "_rk"].fillna(99))
        mu = x.groupby(key).transform("mean")
        sd = x.groupby(key).transform("std").replace(0, np.nan)
        df[c + "_z"] = ((x - mu) / sd).fillna(-3)
        df[c + "_gap"] = (x.groupby(key).transform("max") - x).fillna(10)
    df["n_grp"] = p.groupby(key).transform("sum")
    df["n_games"] = df.groupby("slate_id").team.transform("nunique") / 2
    dkavg = df.ytd_ppg.where(df.ytd_gp >= 1, df.prev_ppg)
    df["dkavg"] = dkavg.fillna(0.0)
    df["pubv"] = (df.dkavg / df.salk.clip(lower=1)).clip(upper=15)
    df["pubv_rk"] = df.pubv.where(p & (df.pos != "DST")).groupby(key).rank(ascending=False)
    df["pubv_lrk"] = np.log(df.pubv_rk.fillna(99))
    df["last_val"] = (df.last_dk.fillna(0) / df.salk.clip(lower=1)).clip(-2, 10)
    df["last_val_lrk"] = np.log(df.last_val.where(p & (df.pos != "DST")).groupby(key).rank(ascending=False).fillna(99))
    df["prev_rank"] = df.prev_rank.fillna(150)
    df["l_prev_rank"] = np.log(df.prev_rank.clip(lower=1))
    df["prev_ppg"] = df.prev_ppg.fillna(0.0)
    df["ytd_gp"] = df.ytd_gp.fillna(0.0)
    df["p3_usage"] = df.p3_usage.fillna(0.0)
    df["cv"] = (df.sigma.fillna(0) / df.proj.clip(lower=.5)).clip(upper=5)
    for c in ["l_exp", "l_est"]:
        if c not in df:
            df[c] = np.nan
        df[c] = df[c].fillna(-5.8)
    df["cheap"] = (df.salary <= 4500).astype(float)
    df["min_sal"] = (df.salk_rk == df.groupby(key).salk_rk.transform("max")).astype(float)
    for g in GROUPS:
        df["is_" + g] = (df.grp == g).astype(float)
    df["wk1"] = (df.week == 1).astype(float)
    return df


def dst_features(D):
    D = D[D.pos == "DST"].copy()
    D["in_pool"] = D.in_pool & (D.proj > 0)
    g = D.groupby("slate_id")
    D["opp_rk"] = g.opp_total.rank(pct=True)
    D["fav"] = (D.spread > 0).astype(float)
    D["proj_rk"] = g.proj.rank(ascending=False, pct=True)
    D["pres_rk"] = g.pressure.rank(pct=True)
    D["viable"] = (((D.opp_rk <= .4) & (D.fav > 0)) | (D.proj_rk <= .25)) & (D.pres_rk > 1 / 3)
    D["viable_f"] = D.viable.astype(float)
    D["vsal_rk"] = D.salary.where(D.viable).groupby(D.slate_id).rank(method="min")
    D["cheapest_viable"] = (D.vsal_rk == 1).astype(float)
    D["vsal_lrk"] = np.log(D.vsal_rk.fillna(20))
    D["proj_gap1"] = g.proj.transform("max") - D.proj
    D["opp_gap"] = D.opp_total - g.opp_total.transform("min")
    return D


# ----------------------------------------------------------------------------- scoring
def _groups(df):
    return pd.factorize(df.slate_id.astype(str) + "|" + df.grp.astype(str))[0]


def _softmax(F, gid, mask):
    F = np.where(mask, F, -np.inf)
    m = pd.Series(F).groupby(gid).transform("max").to_numpy()
    e = np.where(mask, np.exp(F - np.where(np.isfinite(m), m, 0)), 0.0)
    s = pd.Series(e).groupby(gid).transform("sum").to_numpy()
    return np.where(s > 0, e / np.where(s > 0, s, 1), 0.0)


def allocate(df, F, budgets, cap=CAP):
    mask = (df.in_pool & (df.proj > 0)).to_numpy()
    gid = _groups(df)
    s = _softmax(F, gid, mask)
    out = np.zeros(len(df))
    b = df.grp.map(budgets).fillna(0).to_numpy()
    for g in np.unique(gid):
        ix = np.where(gid == g)[0]
        r = s[ix]
        rem = b[ix[0]]
        free = r > 0
        o = np.zeros(len(ix))
        for _ in range(10):
            tot = r[free].sum()
            if tot <= 0 or rem <= 0:
                break
            trial = np.where(free, r / tot * rem, 0)
            over = free & (trial > cap)
            if not over.any():
                o = np.where(free, trial, o)
                break
            o = np.where(over, cap, o)
            rem -= cap * over.sum()
            free &= ~over
        out[ix] = o
    return out


def _design(df, feats):
    X = df[feats].astype(float).to_numpy()
    return np.where(np.isfinite(X), X, 0.0)


def score_linear(F, art):
    X = _design(F, art["features"])
    pos = F[[f"is_{g}" for g in art.get("pos_interaction_order", GROUPS)]].to_numpy()
    X = np.column_stack([X] + [X * pos[:, [k]] for k in range(pos.shape[1])])
    Z = (X - np.asarray(art["mu"])) / np.asarray(art["sd"])
    return Z @ np.asarray(art["b"])


def score_dst(D, art):
    Z = (_design(D, art["features"]) - np.asarray(art["mu"])) / np.asarray(art["sd"])
    return Z @ np.asarray(art["b"])


# ----------------------------------------------------------------------------- inference entry
def to_frame(scored, feats, season, week, slate_id="live"):
    """Map a pipeline frame (+ ownership_model.build_features output) to the v2 input schema."""
    pos = scored["position"].astype(str).where(~scored["position"].astype(str).isin(["D", "DEF"]), "DST")
    opp = scored["opponent"].astype(str).str.replace(r"^(@|vs)\s*", "", regex=True).str.strip() \
        if "opponent" in scored.columns else pd.Series(np.nan, index=scored.index)
    proj = pd.to_numeric(scored["final_projection"], errors="coerce").fillna(0.0)
    return pd.DataFrame({
        "slate_id": slate_id, "season": int(season), "week": int(week),
        "player_id": scored["player_id"].astype(str), "pos": pos, "team": scored["team"].astype(str), "opp": opp,
        "salary": pd.to_numeric(scored["salary"], errors="coerce").astype(float),
        "proj": proj,
        "sigma": pd.to_numeric(scored["sigma"], errors="coerce") if "sigma" in scored.columns else 0.0,
        "team_total": pd.to_numeric(scored.get("implied_total"), errors="coerce"),
        "game_total": pd.to_numeric(scored.get("over_under"), errors="coerce"),
        "in_pool": proj > 0,
        "l_exp": feats["l_exp"].to_numpy(float), "l_est": feats["l_est"].to_numpy(float),
    }, index=scored.index)


def predict_v2(frame, ctx, lin, dst, live_pred=None, alpha=FFC_BLEND_ALPHA):
    """frame: to_frame() output (one or more slates). live_pred: live FFC-model %, aligned to frame,
    or None for no blend. Returns (final, v2_only) numpy arrays aligned to frame; rows outside
    QB/RB/WR/TE/DST are NaN (caller keeps the old number)."""
    F = build_features(frame, ctx)
    F = F.loc[frame.index] if F.index.is_unique else F
    Fs = score_linear(F, lin)
    budgets = lin["budgets"]
    v2_only = allocate(F, Fs, budgets, cap=lin.get("cap", CAP))
    if live_pred is not None:
        lf = np.log(np.maximum(np.asarray(live_pred, float), .05))
        final = allocate(F, alpha * Fs + (1 - alpha) * lf, budgets, cap=lin.get("cap", CAP))
    else:
        final = v2_only.copy()
    # DST group: v2 DST model
    D = dst_features(F)
    if len(D):
        Dd = D.assign(grp="DST")
        pd_ = allocate(Dd, score_dst(Dd, dst), {"DST": float(dst.get("budget", 100.0))},
                       cap=lin.get("cap", CAP))
        pos_ix = F.index.get_indexer(D.index)
        final[pos_ix] = pd_
        v2_only[pos_ix] = pd_
    other = ~F.pos.isin(GROUPS).to_numpy()
    final[other] = np.nan
    v2_only[other] = np.nan
    return final, v2_only


def refine_v2(scored, feats, live_new, ffc_used, site, season, week):
    """Called by ownership_model.refine_ownership. Returns (final, v2_only) Series on scored.index."""
    lin, dst = load_artifacts(site)
    if lin is None:
        raise RuntimeError("ownership v2 artifacts missing (data/ownership_v2_dk_{linear,dst}.json)")
    season = int(season) if season is not None else infer_season()
    week = int(week)
    if not 1 <= week <= 22:
        raise RuntimeError(f"week {week} out of range for v2 features")
    sc = scored.reset_index(drop=True)
    fe = feats.reset_index(drop=True)
    frame = to_frame(sc, fe, season, week)
    ctx = Ctx(load_stats(season, week), load_prior_salary(site, season, week), load_lag_own(site, season))
    live = np.asarray(live_new, float) if ffc_used else None
    final, v2_only = predict_v2(frame, ctx, lin, dst, live)
    return (pd.Series(final, index=scored.index), pd.Series(v2_only, index=scored.index))
