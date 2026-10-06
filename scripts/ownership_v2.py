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


# 2026-09-30 (analysis/wrte_chalk_root_cause): coefficients refit on the TRUE slate pool (the 2021-25 training
# frame used to include ~25% off-slate players, which flattened v2 and under-sized chalk). Select with
# DFS_OWN_V2_COEF=truepool | current. Missing candidate files fall back to the current artifacts.
V2_COEF_DEFAULT = "current"


def v2_coef_choice():
    v = os.environ.get("DFS_OWN_V2_COEF", V2_COEF_DEFAULT).strip().lower()
    return "truepool" if v == "truepool" else "current"


# 2026-10-05 QB attempts share (analysis/wk4_postmortem/qb_share_refit/RESULTS.md): the QB `my_share` feature was
# carries+targets averaged over games PLAYED / the team's other QBs' same average (last 3 team games), so one game of
# backup kneel-downs got equal weight to a real start (Lawrence read .47 in Wk4 because Mullens had 3 kneel carries,
# costing him ~35-40% of his modeled ownership; Darnold/Kyler hit the same way). With the switch on, QB my_share =
# the QB's passing attempts summed over the team's last-3-game window / the team's QB attempts summed (same window,
# same pre-lock rule), and the linear coefficients come from data/ownership_v2_{site}_linear_qbatt.json, refit on
# 2021-25 with that feature (same frame/pool as the current artifact). The feature follows the artifact
# (lin["qb_share"] == "attempts"), so the feature and its coefficients can never be mixed. Missing artifact = no-op.
# Switch: DFS_OWN_V2_QB_ATT_SHARE=1 (default 0 = off).
# HOLD (2026-10-05): 2026 is clearly better held-out (QB starter corr wk1-3 .684->.728, wk4 .351->.570, 10/12 slates),
# but 2021-25 leave-one-season-out with the refit is slightly WORSE (QB starter corr .663->.656, QB CE 2.866->2.886,
# worse in 4 of 5 seasons, better on only 25/86 slates). Fails the "history not worse" bar, so it stays off.
QB_ATT_SHARE_DEFAULT = "0"


def qb_att_share_enabled():
    return os.environ.get("DFS_OWN_V2_QB_ATT_SHARE", QB_ATT_SHARE_DEFAULT).strip().lower() not in (
        "0", "false", "off", "no", "")


# 2026-10-05 QB min-attempts floor (analysis/wk4_postmortem/qb_share_refit/minsnap/RESULTS.md): narrower fix for the same
# bug as QB_ATT_SHARE above. Keeps the OLD QB my_share (carries+targets averaged over games played / sum of the team's
# QBs' same averages, last 3 team games), but a QB's game only counts if he threw >= QB_SHARE_MIN_ATT passes. A backup's
# kneel-down/garbage-time game no longer counts as a "game"; a QB with no counted game in the window gets my_share 0.
# Shipped coefficients are reused (no artifact change). Only QB my_share changes; vacated and other groups untouched.
# Switch: DFS_OWN_V2_QB_SHARE_MINSNAP=1 (default 0 = off); threshold via DFS_OWN_V2_QB_SHARE_MIN_ATT (default 10).
# Ignored when the QB_ATT_SHARE artifact is active (that feature replaces this one).
# HOLD (2026-10-05): 2026 better (QB starter corr wk1-3 .684->.716, wk4 .351->.525, shipped coefs) but 2021-25 worse:
# shipped coefs .682->.642 (in-sample), LOSO refit .663->.655 (QB CE 2.866->2.884, worse in 4/5 seasons, 25/86 slates
# better). K=5/15 the same. Not a rare case in history: 24% of starter-slates move, mostly backup-kneel games on
# BUF/KC/SF-type teams, and the old diluted read predicted those starters well (actual 5.6%, old 5.7%, floored 7.6%).
QB_SHARE_MINSNAP_DEFAULT = "0"
QB_SHARE_MIN_ATT = 10


def qb_share_minsnap_enabled():
    return os.environ.get("DFS_OWN_V2_QB_SHARE_MINSNAP", QB_SHARE_MINSNAP_DEFAULT).strip().lower() not in (
        "0", "false", "off", "no", "")


def qb_share_min_att():
    try:
        return float(os.environ.get("DFS_OWN_V2_QB_SHARE_MIN_ATT", QB_SHARE_MIN_ATT))
    except ValueError:
        return float(QB_SHARE_MIN_ATT)


def load_artifacts(site="dk"):
    lp, dp = linear_path(site), dst_path(site)
    if v2_coef_choice() == "truepool":
        tl, td = DATA_DIR / f"ownership_v2_{site}_linear_truepool.json", DATA_DIR / f"ownership_v2_{site}_dst_truepool.json"
        if tl.exists() and td.exists():
            lp, dp = tl, td
    elif qb_att_share_enabled():
        ql = DATA_DIR / f"ownership_v2_{site}_linear_qbatt.json"
        if ql.exists():
            lp = ql
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
                "attempts", "def_sacks", "sacks_suffered", "opponent_team"]
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


def qb_att_share(ts):
    """ts: Ctx.team_share() rows. Per QB: passing attempts summed over his team's last-3-game window / the team's QB
    attempts summed over the same window. Series indexed by player_id (first team wins for a traded QB, matching
    my_share). Empty when there are no attempts."""
    if not len(ts) or "attempts" not in ts:
        return pd.Series(dtype=float)
    q = ts[ts.position == "QB"]
    a = q.assign(attempts=q.attempts.fillna(0)).groupby(["team", "player_id"]).attempts.sum()
    tot = a.groupby(level="team").transform("sum")
    sh = (a / tot.where(tot > 0)).dropna().reset_index(level="team", drop=True)
    return sh[~sh.index.duplicated()]


def qb_share_minsnap(ts, min_att):
    """ts: Ctx.team_share() rows. The old QB my_share (carries+targets mean over games / team QBs' sum of means),
    counting only games where the QB threw >= min_att passes. Series indexed by player_id; QBs with no counted game are
    absent (caller maps them to 0). None when attempts are unavailable (caller keeps the old value = fail-safe no-op)."""
    if not len(ts) or "attempts" not in ts:
        return None
    q = ts[(ts.position == "QB") & (ts.attempts.fillna(0) >= min_att)]
    per = q.groupby(["team", "player_id"]).usage.mean()
    tot = per.groupby(level="team").transform("sum")
    sh = (per / tot.where(tot > 0)).fillna(0.0).reset_index(level="team", drop=True)
    return sh[~sh.index.duplicated()]


# ----------------------------------------------------------------------------- features (port of analysis/ownership_v2/common.py)
def build_features(df, ctx, qb_att=False, qb_minsnap=None):
    """qb_att=True: QB my_share = passing-attempt share (see QB_ATT_SHARE_DEFAULT). Only valid with an artifact fit on
    that feature (lin["qb_share"] == "attempts"); predict_v2 sets it from the artifact.
    qb_minsnap=<min attempts>: old QB my_share but only counting games with >= that many pass attempts (see
    QB_SHARE_MINSNAP_DEFAULT). None/0 = off. Ignored when qb_att is on."""
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
            if qb_att:
                qb = s.pos == "QB"
                s.loc[qb, "my_share"] = s.loc[qb, "player_id"].map(qb_att_share(ts)).fillna(s.loc[qb, "my_share"])
            elif qb_minsnap:
                ms2 = qb_share_minsnap(ts, qb_minsnap)
                if ms2 is not None:
                    qb = s.pos == "QB"
                    s.loc[qb, "my_share"] = s.loc[qb, "player_id"].map(ms2).fillna(0.0)
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


# 2026-09-30 teammate-OUT bump (analysis/wrte_chalk_root_cause/RESULTS.md): the field gives WR/TE whose teammates
# are OUT a usage bump that our score under-weights (2026 teammate-OUT 15%+ chalk: real 26.6, shipped 17.6).
# final WR/TE log-score += VAC_BUMP_K * vacated, re-allocated to the same group budgets. `vacated` is the share of
# the team's recent receiving usage (nflverse, prior weeks) held by teammates NOT in the pool; the pool is
# final_projection > 0, i.e. after the build zeroes OUT/DOUBTFUL -- the same status set the projection uses.
# Switch: DFS_OWN_VAC_BUMP=0. Any failure = no-op.
VAC_BUMP_K = 1.0
LAST_AUDIT = {}


def vac_bump_enabled():
    return os.environ.get("DFS_OWN_VAC_BUMP", "1").strip().lower() not in ("0", "false", "off", "no")


def apply_vac_bump(F, final, k=None, cap=CAP):
    """Returns (bumped final, audit array of bumped-minus-before; 0 where untouched). Fail-safe: on any problem
    returns the input unchanged."""
    k = VAC_BUMP_K if k is None else k
    try:
        vac = pd.to_numeric(F["vacated"], errors="coerce").fillna(0.0).clip(0, 1).to_numpy()
        wr = F.pos.isin(["WR", "TE"]).to_numpy()
        base = np.asarray(final, float)
        ok = np.isfinite(base)
        if not (wr & ok & (vac > 0)).any() or k == 0:
            return base, np.zeros(len(base))
        Fsc = np.log(np.maximum(np.where(ok, base, 0.0), .05)) + k * vac * wr
        sub = F[wr & ok]
        bud = pd.Series(base[wr & ok], index=sub.index).groupby([sub.slate_id, sub.grp]).sum()
        out = base.copy()
        for (sid, g), ix in sub.groupby([sub.slate_id, sub.grp]).indices.items():
            rows = np.where(wr & ok)[0][ix]
            out[rows] = allocate(F.iloc[rows], Fsc[rows], {g: float(bud[(sid, g)])}, cap=cap)
        if not np.all(np.isfinite(out[wr & ok])):
            return base, np.zeros(len(base))
        return out, np.where(wr & ok, out - base, 0.0)
    except Exception:  # noqa: BLE001 -- the bump must never break a build
        return np.asarray(final, float), np.zeros(len(final))


# 2026-09-30 chalk-size candidate (analysis/chalk_size_fix/RESULTS.md): every model predicts real 20%+ chalk at
# about half; raw FFC sizes chalk about right but ranks worse. For skill players raw FFC ranks in the slate's top
# CHALK_N, final log-score = (1-b)*log(final) + b*log(raw FFC); every group is re-allocated to its own current
# budget (same convention as the vac bump). Switch: DFS_OWN_CHALK_FFC=1 (default 0 = off). Params from
# data/ownership_v2_chalk.candidate-2026-09-30.json when present. Any failure = no-op.
CHALK_FFC_DEFAULT = "0"
CHALK_PARAMS_PATH = DATA_DIR / "ownership_v2_chalk.candidate-2026-09-30.json"
CHALK_N, CHALK_B = 15, 0.5


def chalk_ffc_enabled():
    return os.environ.get("DFS_OWN_CHALK_FFC", CHALK_FFC_DEFAULT).strip().lower() not in ("0", "false", "off", "no", "")


def chalk_params():
    try:
        with open(CHALK_PARAMS_PATH, encoding="utf-8-sig") as f:
            p = json.load(f)
        return int(p["n"]), float(p["b"])
    except Exception:  # noqa: BLE001
        return CHALK_N, CHALK_B


def apply_chalk_ffc(F, final, raw_ffc, n=None, b=None, cap=CAP):
    """Returns (pulled final, audit array of pulled-minus-before). Fail-safe: input unchanged on any problem."""
    if n is None or b is None:
        n0, b0 = chalk_params()
        n = n0 if n is None else n
        b = b0 if b is None else b
    try:
        base = np.asarray(final, float)
        ffc = pd.to_numeric(pd.Series(np.asarray(raw_ffc, float)), errors="coerce").to_numpy()
        skill = F.pos.isin(["QB", "RB", "WR", "TE"]).to_numpy()
        ok = np.isfinite(base) & skill
        if b == 0 or n <= 0 or not (ok & np.isfinite(ffc) & (ffc > 0)).any():
            return base, np.zeros(len(base))
        top = np.zeros(len(base), bool)
        for _, ix in F[ok].groupby("slate_id").indices.items():
            rows = np.where(ok)[0][ix]
            f = np.where(np.isfinite(ffc[rows]), ffc[rows], -1.0)
            r = rows[np.argsort(-f, kind="stable")[:n]]
            top[r[ffc[r] > 0]] = True
        lb = np.log(np.maximum(np.where(ok, base, 0.0), .05))
        Fsc = np.where(top, (1 - b) * lb + b * np.log(np.maximum(np.nan_to_num(ffc), .05)), lb)
        sub = F[ok]
        bud = pd.Series(base[ok], index=sub.index).groupby([sub.slate_id, sub.grp]).sum()
        out = base.copy()
        for (sid, g), ix in sub.groupby([sub.slate_id, sub.grp]).indices.items():
            rows = np.where(ok)[0][ix]
            out[rows] = allocate(F.iloc[rows], Fsc[rows], {g: float(bud[(sid, g)])}, cap=cap)
        if not np.all(np.isfinite(out[ok])):
            return base, np.zeros(len(base))
        return out, np.where(ok, out - base, 0.0)
    except Exception:  # noqa: BLE001 -- must never break a build
        return np.asarray(final, float), np.zeros(len(final))


# 2026-10-01 chalk-size fix v2, SEGMENTED (analysis/chalk_size_fix_v2/RESULTS.md): the broad pull above helped
# cheap WR/TE catch rate but raided budget from real mega-chalk (worse $7k+ bias30) in 1 of 3 weeks. Restricting
# the FFC pull to salary < CHALK_SEG_SAL_THRESH and freezing already-shipped mega-chalk (>= CHALK_SEG_FREEZE_PCT)
# out of the group re-allocation was the only segment that lifted cheap WR/TE catch20 (.58 -> .75 pooled wk1-3)
# with $7k+ bias30 unchanged in every week. (n, b) = (15, 0.5) chosen by in-training MAE over all of wk1-3 (no
# wk4 data exists yet to hold out) -- re-verify against Wk4 once results land before changing these params.
# Switch: DFS_OWN_CHALK_FFC_SEG=1 (default 1 = on, shipped 2026-10-05 after passing its first held-out week,
# Wk4: corr .900->.909, cheap WR/TE chalk-catch 63%->100% on all 3 classic slates, $7k+ unaffected --
# see analysis/wk4_postmortem/RESULTS.md). Mutually exclusive with the broad DFS_OWN_CHALK_FFC switch above
# (segmented takes precedence if both are set). Any failure = no-op. DFS_OWN_CHALK_FFC_SEG=0 to disable.
CHALK_SEG_FFC_DEFAULT = "1"
CHALK_SEG_PARAMS_PATH = DATA_DIR / "ownership_v2_chalk_seg.candidate-2026-10-01.json"
CHALK_SEG_N, CHALK_SEG_B = 15, 0.5
CHALK_SEG_SAL_THRESH = 5500.0
CHALK_SEG_FREEZE_PCT = 25.0


def chalk_ffc_seg_enabled():
    return os.environ.get("DFS_OWN_CHALK_FFC_SEG", CHALK_SEG_FFC_DEFAULT).strip().lower() not in (
        "0", "false", "off", "no", "")


def chalk_seg_params():
    try:
        with open(CHALK_SEG_PARAMS_PATH, encoding="utf-8-sig") as f:
            p = json.load(f)
        return (int(p["n"]), float(p["b"]), float(p["sal_thresh"]), float(p["freeze_pct"]))
    except Exception:  # noqa: BLE001
        return CHALK_SEG_N, CHALK_SEG_B, CHALK_SEG_SAL_THRESH, CHALK_SEG_FREEZE_PCT


def apply_chalk_ffc_seg(F, final, raw_ffc, n=None, b=None, sal_thresh=None, freeze_pct=None, cap=CAP,
                        exclude_qb=False):
    """Segmented variant of apply_chalk_ffc(): the FFC pull only hits slate-top-N players that ALSO have
    salary < sal_thresh, and rows already shipped >= freeze_pct are frozen out of the re-allocation so the
    pull cannot raid real mega-chalk. exclude_qb=True: QBs keep their top-N slots (so RB/WR/TE output is
    unchanged) but are never hit -- used when the QB-own-cut pass below handles QBs. Returns (pulled final,
    audit array). Fail-safe: input unchanged on any problem."""
    n0, b0, s0, f0 = chalk_seg_params()
    n = n0 if n is None else n
    b = b0 if b is None else b
    sal_thresh = s0 if sal_thresh is None else sal_thresh
    freeze_pct = f0 if freeze_pct is None else freeze_pct
    try:
        base = np.asarray(final, float)
        ffc = pd.to_numeric(pd.Series(np.asarray(raw_ffc, float)), errors="coerce").to_numpy()
        sal = pd.to_numeric(F["salary"], errors="coerce").to_numpy()
        skill = F.pos.isin(["QB", "RB", "WR", "TE"]).to_numpy()
        ok = np.isfinite(base) & skill
        if b == 0 or n <= 0 or not (ok & np.isfinite(ffc) & (ffc > 0)).any():
            return base, np.zeros(len(base))
        mask = sal < sal_thresh
        if exclude_qb:
            mask &= ~F.pos.eq("QB").to_numpy()
        freeze = base >= freeze_pct
        top = np.zeros(len(base), bool)
        for _, ix in F[ok].groupby("slate_id").indices.items():
            rows = np.where(ok)[0][ix]
            f = np.where(np.isfinite(ffc[rows]), ffc[rows], -1.0)
            r = rows[np.argsort(-f, kind="stable")[:n]]
            top[r[ffc[r] > 0]] = True
        hit = top & mask
        if not hit.any():
            return base, np.zeros(len(base))
        frz = freeze & ~hit
        lb = np.log(np.maximum(np.where(ok, base, 0.0), .05))
        Fsc = np.where(hit, (1 - b) * lb + b * np.log(np.maximum(np.nan_to_num(ffc), .05)), lb)
        al = ok & ~frz
        sub = F[al]
        out = base.copy()
        for (sid, g), ix in sub.groupby([sub.slate_id, sub.grp]).indices.items():
            rows = np.where(al)[0][ix]
            grp_all = ok & (F.slate_id.to_numpy() == sid) & (F.grp.to_numpy() == g)
            if not hit[rows].any():
                continue
            bud = base[grp_all].sum() - base[grp_all & frz].sum()
            out[rows] = allocate(F.iloc[rows], Fsc[rows], {g: float(bud)}, cap=cap)
        if not np.all(np.isfinite(out[ok])):
            return base, np.zeros(len(base))
        return out, np.where(ok, out - base, 0.0)
    except Exception:  # noqa: BLE001 -- must never break a build
        return np.asarray(final, float), np.zeros(len(final))


# 2026-10-06 QB own-cut for the chalk-seg pull (analysis/wk4_postmortem/qb_chalk_lawrence/RESULTS.md): the seg pull
# above is structurally blind to QBs -- chalk QBs cost $5.5-7k (fail the $5,500 gate) and a 20% QB ranks below the
# slate's top-15 FFC because RB/WR/TE chalk fills those slots (Lawrence 16th on wk4_main, Darnold 16th on wk4_aft).
# This pass gives QBs their own cut: the slate's top QB_CUT_K QBs by raw FFC, no salary gate, same b / freeze as seg,
# re-allocated inside the QB budget only. RB/WR/TE are untouched by construction. 2026 12 classic slates: QB MAE
# better on 11/12, QB corr .815->.843, real-12%+ QB bias -4.8->-3.9; wins 3 of 4 leave-one-week-out weeks. Switch:
# DFS_OWN_CHALK_QB_CUT=<k> (default 3 = on, shipped 2026-10-06; 0 = off). Only runs with the seg switch on. Any
# failure = no-op. Re-grade after Wk5 (analysis/wk4_postmortem/qb_chalk_lawrence/RESULTS.md) -- sample is 2026-only
# (FFC doesn't exist in history) and still only 12 slates.
CHALK_QB_CUT_DEFAULT = "3"


def chalk_qb_cut_k():
    try:
        return max(0, int(os.environ.get("DFS_OWN_CHALK_QB_CUT", CHALK_QB_CUT_DEFAULT).strip() or 0))
    except ValueError:
        return 0


def apply_chalk_ffc_qb_cut(F, final, raw_ffc, k=None, cap=CAP):
    """QB-only FFC pull for the slate's top-k QBs by raw FFC. Returns (pulled final, audit delta)."""
    k = chalk_qb_cut_k() if k is None else k
    base = np.asarray(final, float)
    try:
        qb = F.pos.eq("QB").to_numpy() & np.isfinite(base)
        if k <= 0 or not qb.any():
            return base, np.zeros(len(base))
        _, b, _, fz = chalk_seg_params()
        Q = F[qb].copy()
        Q["salary"] = 0.0  # no salary gate for QBs
        qo, _ = apply_chalk_ffc_seg(Q, base[qb].copy(), np.asarray(raw_ffc, float)[qb], n=k, b=b,
                                    sal_thresh=1.0, freeze_pct=fz, cap=cap)
        out = base.copy()
        out[qb] = qo
        if not np.all(np.isfinite(out[qb])):
            return base, np.zeros(len(base))
        return out, out - base
    except Exception:  # noqa: BLE001 -- must never break a build
        return base, np.zeros(len(base))


# 2026-09-30 chalk-temperature candidate (analysis/chalk_temperature/RESULTS.md): the v2 distribution is "too flat at
# the top" (real 30%+ players predicted ~20). Sharpen each position group's shares: new_i ∝ final_i ** gamma
# (= softmax temperature 1/gamma on the log-share), re-allocated to the SAME group total with the usual CAP
# water-fill. No new data. Switch/param: env DFS_OWN_CHALK_TEMP=<gamma>; unset/1.0 = no-op. Any failure = no-op.
# NO SHIP (2026-09-30): fixes catch-rate/bias direction in all 5 history seasons but costs correlation every
# season and overshoots $7k+ on live 2026 (already near-calibrated there via the FFC blend). Off by default.
CHALK_TEMP_DEFAULT = 1.0


def chalk_temp_gamma():
    try:
        return float(os.environ.get("DFS_OWN_CHALK_TEMP", CHALK_TEMP_DEFAULT))
    except ValueError:
        return CHALK_TEMP_DEFAULT


def apply_chalk_temp(F, final, gamma=None, cap=CAP, groups=None):
    """Returns (sharpened final, audit delta). Groups default to skill groups (QB/RB/WR/TE; DST untouched)."""
    gamma = chalk_temp_gamma() if gamma is None else gamma
    base = np.asarray(final, float)
    try:
        if gamma == 1.0:
            return base, np.zeros(len(base))
        groups = [g for g in GROUPS if g != "DST"] if groups is None else groups
        sel = (F.grp.isin(groups).to_numpy() & np.isfinite(base) & (base > 0))
        if not sel.any():
            return base, np.zeros(len(base))
        Fsc = gamma * np.log(np.maximum(np.where(sel, base, 1.0), 1e-3))
        sub = F[sel]
        bud = pd.Series(base[sel], index=sub.index).groupby([sub.slate_id.to_numpy(), sub.grp.to_numpy()]).sum()
        out = base.copy()
        rows_all = np.where(sel)[0]
        for (sid, g), ix in sub.groupby([sub.slate_id.to_numpy(), sub.grp.to_numpy()]).indices.items():
            rows = rows_all[ix]
            out[rows] = allocate(F.iloc[rows], Fsc[rows], {g: float(bud[(sid, g)])}, cap=cap)
        if not np.all(np.isfinite(out[sel])):
            return base, np.zeros(len(base))
        return out, out - base
    except Exception:  # noqa: BLE001
        return base, np.zeros(len(base))


# 2026-10-05 adaptive FFC blend (analysis/wk4_postmortem/ffc_adaptive_blend/, local): per-row alpha that leans harder
# on our v2 number the more v2 and the live FFC model disagree, d = log(v2_only%) - log(live%) (d<0 = FFC side higher):
#   a_i = min(1, a0 + kH*max(-d,0) + kL*max(d,0)),  score = a_i*log(v2_only%) + (1-a_i)*log(live%)
# (log(v2_only%) in place of raw Fs so per-row alphas stay in the same units). Tested leave-one-week-out on all 12
# 2026 DK classic slates (wk1-4), symmetric and asymmetric, with d vs the live FFC model AND vs raw FFC:
# NO SHIP -- never beat the flat 0.45 held out (pooled corr .894 -> .889/.888, MAE 1.088 -> 1.095); with d vs raw
# FFC every fold picked zero slope. Off by default. Switch: DFS_OWN_FFC_ADAPTIVE=1; params via
# DFS_OWN_FFC_ADAPTIVE_PARAMS="a0,kH,kL" (default = in-sample best 0.45,0,0.15). Bad params / any failure = flat blend.
FFC_ADAPTIVE_DEFAULT = "0"
FFC_ADAPTIVE_PARAMS = (0.45, 0.0, 0.15)


def ffc_adaptive_enabled():
    return os.environ.get("DFS_OWN_FFC_ADAPTIVE", FFC_ADAPTIVE_DEFAULT).strip().lower() not in (
        "0", "false", "off", "no", "")


def ffc_adaptive_params():
    try:
        raw = os.environ.get("DFS_OWN_FFC_ADAPTIVE_PARAMS", "").strip()
        a0, kh, kl = (float(x) for x in raw.split(",")) if raw else FFC_ADAPTIVE_PARAMS
        if not (0 <= a0 <= 1 and kh >= 0 and kl >= 0 and all(np.isfinite([a0, kh, kl]))):
            return None
        return a0, kh, kl
    except Exception:  # noqa: BLE001
        return None


def adaptive_blend_score(v2_only, live_pred, params=None):
    """Per-row adaptive log-blend score (see block comment). Returns (score, alpha array) or None on any problem
    (caller then uses the flat blend)."""
    try:
        p = ffc_adaptive_params() if params is None else params
        if p is None:
            return None
        a0, kh, kl = p
        lv2 = np.log(np.maximum(np.asarray(v2_only, float), .05))
        lf = np.log(np.maximum(np.asarray(live_pred, float), .05))
        d = lv2 - lf
        a = np.minimum(1.0, a0 + kh * np.maximum(-d, 0) + kl * np.maximum(d, 0))
        sc = a * lv2 + (1 - a) * lf
        if not np.all(np.isfinite(sc)):
            return None
        return sc, a
    except Exception:  # noqa: BLE001
        return None


def predict_v2(frame, ctx, lin, dst, live_pred=None, alpha=FFC_BLEND_ALPHA, vac_k=None, raw_ffc=None):
    """frame: to_frame() output (one or more slates). live_pred: live FFC-model %, aligned to frame,
    or None for no blend. Returns (final, v2_only) numpy arrays aligned to frame; rows outside
    QB/RB/WR/TE/DST are NaN (caller keeps the old number)."""
    qb_att = lin.get("qb_share") == "attempts"
    F = build_features(frame, ctx, qb_att=qb_att,
                       qb_minsnap=qb_share_min_att() if (not qb_att and qb_share_minsnap_enabled()) else None)
    F = F.loc[frame.index] if F.index.is_unique else F
    Fs = score_linear(F, lin)
    budgets = lin["budgets"]
    v2_only = allocate(F, Fs, budgets, cap=lin.get("cap", CAP))
    ad = adaptive_blend_score(v2_only, live_pred) if (live_pred is not None and ffc_adaptive_enabled()) else None
    if ad is not None:
        final = allocate(F, ad[0], budgets, cap=lin.get("cap", CAP))
    elif live_pred is not None:
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
    LAST_AUDIT.clear()
    if ad is not None:
        LAST_AUDIT["own_ffc_alpha"] = ad[1]
    if vac_bump_enabled() and (vac_k is None or vac_k != 0):
        final, bump = apply_vac_bump(F, final, vac_k, cap=lin.get("cap", CAP))
        LAST_AUDIT["own_vac_bump"] = bump
        LAST_AUDIT["own_vacated"] = pd.to_numeric(F["vacated"], errors="coerce").fillna(0.0).to_numpy()
    if raw_ffc is not None and chalk_ffc_seg_enabled():
        qk = chalk_qb_cut_k()
        final, pull = apply_chalk_ffc_seg(F, final, raw_ffc, cap=lin.get("cap", CAP), exclude_qb=qk > 0)
        LAST_AUDIT["own_chalk_ffc_seg"] = pull
        if qk > 0:
            final, qpull = apply_chalk_ffc_qb_cut(F, final, raw_ffc, k=qk, cap=lin.get("cap", CAP))
            LAST_AUDIT["own_chalk_qb_cut"] = qpull
    elif raw_ffc is not None and chalk_ffc_enabled():
        final, pull = apply_chalk_ffc(F, final, raw_ffc, cap=lin.get("cap", CAP))
        LAST_AUDIT["own_chalk_ffc"] = pull
    if chalk_temp_gamma() != 1.0:
        final, dtemp = apply_chalk_temp(F, final, cap=lin.get("cap", CAP))
        LAST_AUDIT["own_chalk_temp"] = dtemp
    other = ~F.pos.isin(GROUPS).to_numpy()
    final[other] = np.nan
    v2_only[other] = np.nan
    return final, v2_only


def loud_warn(msg):
    """Fallback/missing-input warning (CI-parity 2026-09-29). Always to stderr; on GitHub Actions also a
    ::warning:: annotation so it shows on the run summary. Off: env DFS_LOUD_FALLBACKS=0 (plain stderr line)."""
    import sys
    print(f"WARNING: {msg}", file=sys.stderr)
    if (os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("DFS_LOUD_FALLBACKS", "1").strip().lower() not in ("0", "false", "off", "no")):
        print(f"::warning title=DFS fallback::{msg}", flush=True)


def _check_v2_inputs(stats, prior_sal, lag_own, season, week):
    """Warn (never change behavior) when v2's week-(N-1) inputs are missing/partial: v2 then runs on stale features."""
    if week < 2:
        return
    prev = week - 1
    n_prev = int(((stats.season == season) & (stats.week == prev)).sum()) if stats is not None else 0
    if n_prev < 500:  # a full NFL week is ~1,100 rows; a Thursday-only pull is ~70
        loud_warn(f"ownership v2: weekly_stats_{season} has only {n_prev} rows for week {prev} (full week ~1,100) -- "
                  f"last week's stats not fully ingested; v2 uses stale form/usage features. "
                  f"Run scripts/ingest_historical.py --season {season}.")
    if prior_sal is None or not ((prior_sal.season == season) & (prior_sal.week == prev)).any():
        loud_warn(f"ownership v2: no output/final_projections_*_classic_wk{prev}_* file -- prior-week salary features missing.")
    if lag_own is None or not ((lag_own.season == season) & (lag_own.week == prev)).any():
        loud_warn(f"ownership v2: data/ownership_actual_log.csv has no {season} wk{prev} main-slate rows -- "
                  f"lagged-ownership feature missing (run scripts/log_ownership.py).")


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
    stats = load_stats(season, week)
    prior_sal = load_prior_salary(site, season, week)
    lag_own = load_lag_own(site, season)
    _check_v2_inputs(stats, prior_sal, lag_own, season, week)
    ctx = Ctx(stats, prior_sal, lag_own)
    live =np.asarray(live_new, float) if ffc_used else None
    raw = pd.to_numeric(sc["ffc_own_pct"], errors="coerce").to_numpy() \
        if (ffc_used and "ffc_own_pct" in sc.columns) else None
    final, v2_only = predict_v2(frame, ctx, lin, dst, live, raw_ffc=raw)
    return (pd.Series(final, index=scored.index), pd.Series(v2_only, index=scored.index))
