"""Ownership v2: shared feature builder, within-group softmax model (+ gradient boosting), metrics.

No FC data in this file. Every feature here is computable pre-lock from our own inputs:
salary file, our projection/sigma, Vegas totals, nflverse weekly stats of PRIOR games,
prior-week DK salary, prior-week realized ownership (our contest-results log), schedule.

Model: for each (slate, position group) the predicted ownership is
    own_i = budget_g * softmax(F)_i,  water-filled at CAP
F = linear(X) [+ boosted trees].  Fit = cross-entropy between target shares and softmax shares
(Plackett-Luce first-choice / multinomial with fractional counts), Newton boosting for trees.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import spearmanr

R = Path(__file__).resolve().parents[2]
GROUPS = ["QB", "RB", "WR", "TE", "DST"]
CAP = 75.0
TEAM_FIX = {"JAC": "JAX", "LAR": "LA", "LVR": "LV", "WSH": "WAS"}


# ----------------------------------------------------------------------------- lookups
def dk_points(w):
    p = (w.passing_yards.fillna(0) * .04 + w.passing_tds.fillna(0) * 4 - w.passing_interceptions.fillna(0)
         + w.rushing_yards.fillna(0) * .1 + w.rushing_tds.fillna(0) * 6 + w.receptions.fillna(0)
         + w.receiving_yards.fillna(0) * .1 + w.receiving_tds.fillna(0) * 6
         + 3 * (w.passing_yards.fillna(0) >= 300) + 3 * (w.rushing_yards.fillna(0) >= 100)
         + 3 * (w.receiving_yards.fillna(0) >= 100)
         - w[["sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"]].fillna(0).sum(1)
         + 2 * w[["passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions"]].fillna(0).sum(1))
    return p


def load_stats(seasons=range(2019, 2027)):
    cols = None
    out = []
    for s in seasons:
        f = R / f"data/weekly_stats_{s}.parquet"
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
    a = pd.concat(out, ignore_index=True)
    a["opponent_team"] = a.opponent_team.replace(TEAM_FIX)
    a["t"] = a.season * 100 + a.week
    return a.sort_values(["player_id", "t"])


class Ctx:
    """Pre-lock lookup tables. Every query for (season, week) only uses rows with t < season*100+week."""

    def __init__(self, stats, prior_salary=None, lag_own=None):
        self.st = stats
        self.prior_salary = prior_salary  # df season, week, player_id, salary (any earlier week in season)
        self.lag_own = lag_own            # df season, week, player_id, own (main slate realized)
        # season-level player summaries
        g = stats.groupby(["player_id", "season"])
        ss = g.agg(ppg=("dk", "mean"), tot=("dk", "sum"), gp=("dk", "size"), pos=("position", "last")).reset_index()
        ss["pos_rank"] = ss.groupby(["season", "pos"]).tot.rank(ascending=False, method="min")
        self.season_sum = ss
        # team defense: sacks made per game and opponent's sacks allowed
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
        """Each player's share of his team's group usage over the team's last 3 games (prior)."""
        t = season * 100 + week
        st = self.st[(self.st.t < t) & (self.st.t >= t - 100)]  # within ~1 year
        st = st[st.season == season] if (st.season == season).any() else st[st.season == season - 1]
        lastw = st.groupby("team").t.apply(lambda x: sorted(x.unique())[-3:])
        rows = []
        for tm, ws in lastw.items():
            x = st[(st.team == tm) & st.t.isin(ws)]
            rows.append(x)
        return pd.concat(rows) if rows else st.iloc[:0]

    def dst_feats(self, season, week, teams):
        t = season * 100 + week
        tw = self.team_week[self.team_week.t < t]
        o = pd.DataFrame(index=pd.Index(teams, name="team"))
        last8 = tw.groupby("team").tail(8).groupby("team")
        o["sk_pg"] = last8.sk.mean()
        o["sa_pg"] = last8.sa.mean()  # sacks this team's QBs took (used for the opponent)
        return o


# ----------------------------------------------------------------------------- features
def build_features(df, ctx):
    """df: one or more slates. Required columns:
    slate_id, season, week, player_id, pos, team, opp, salary, proj, sigma, team_total, game_total, in_pool,
    l_exp, l_est (optional; NaN -> floor).  Returns df with feature columns appended."""
    df = df.copy()
    df["team"] = df.team.replace(TEAM_FIX)
    df["opp"] = df.opp.replace(TEAM_FIX)
    df["grp"] = df.pos
    df["salk"] = df.salary / 1000.0
    df["proj"] = df.proj.clip(lower=0).fillna(0)
    parts = []
    for sid, s in df.groupby("slate_id", sort=False):
        season, week = int(s.season.iloc[0]), int(s.week.iloc[0])
        s = s.copy()
        pf = ctx.player_feats(season, week, s.player_id.unique())
        s = s.join(pf, on="player_id")
        # teams / vegas (derived from skill rows so DST uses the same convention)
        tt = s[s.pos != "DST"].groupby("team").team_total.median()
        s["team_total"] = s.team.map(tt).fillna(s.team_total)
        s["opp_total"] = s.opp.map(tt)
        s["opp_total"] = s.opp_total.fillna(s.game_total - s.team_total)
        s["spread"] = s.team_total - s.opp_total
        s["tt_rank"] = s.groupby("pos").team_total.rank(pct=True)
        s["gt_rank"] = s.game_total.rank(pct=True)
        # prior salary
        if ctx.prior_salary is not None:
            ps = ctx.prior_salary[(ctx.prior_salary.season == season) & (ctx.prior_salary.week < week)]
            ps = ps.sort_values("week").groupby("player_id").tail(1).set_index("player_id")
            s["sal_prev"] = s.player_id.map(ps.salary)
            s["wk_since_prev"] = week - s.player_id.map(ps.week)
        else:
            s["sal_prev"] = np.nan; s["wk_since_prev"] = np.nan
        s["sal_chg"] = ((s.salary - s.sal_prev) / 1000.0).fillna(0.0)
        s["has_prev_sal"] = s.sal_prev.notna().astype(float)
        # prior-week realized ownership
        if ctx.lag_own is not None:
            lo = ctx.lag_own[(ctx.lag_own.season == season) & (ctx.lag_own.week == week - 1)].set_index("player_id")
            s["lag_own"] = s.player_id.map(lo.own)
            s["lag_own_avail"] = float(len(lo) > 0)
        else:
            s["lag_own"] = np.nan; s["lag_own_avail"] = 0.0
        s["l_lag_own"] = np.log1p(s.lag_own.fillna(0.0))
        # opportunity vacated: teammates (same group) with prior usage who are not in this slate's pool
        ts = ctx.team_share(season, week)
        pool_ids = set(s.loc[s.in_pool, "player_id"])
        if len(ts):
            ts = ts[ts.position.isin(["RB", "WR", "TE", "QB"])].copy()
            ts["g2"] = np.where(ts.position == "RB", "RB", np.where(ts.position == "QB", "QB", "REC"))
            per = ts.groupby(["team", "g2", "player_id"]).usage.mean().reset_index()
            tot = per.groupby(["team", "g2"]).usage.sum()
            per["share"] = per.usage / per.set_index(["team", "g2"]).index.map(tot).values
            # only teams on this slate; absent = not in pool (and not traded away: last team == team)
            slate_teams = set(s.team)
            per = per[per.team.isin(slate_teams)]
            per["absent"] = ~per.player_id.isin(pool_ids)
            vac = per[per.absent].groupby(["team", "g2"]).share.sum()
            s["g2"] = np.where(s.pos == "RB", "RB", np.where(s.pos == "QB", "QB", np.where(s.pos == "DST", "DST", "REC")))
            s["vacated"] = [vac.get((a, b), 0.0) for a, b in zip(s.team, s.g2)]
            ms = per.set_index("player_id").share
            s["my_share"] = s.player_id.map(ms[~ms.index.duplicated()]).fillna(0.0)
        else:
            s["vacated"] = 0.0; s["my_share"] = 0.0
        s.loc[s.pos == "DST", ["vacated", "my_share"]] = 0.0
        # DST pressure
        dfe = ctx.dst_feats(season, week, list(set(s.team) | set(s.opp.dropna())))
        s["dst_sk"] = s.team.map(dfe.sk_pg)
        s["opp_sa"] = s.opp.map(dfe.sa_pg)
        s["pressure"] = (s.dst_sk.fillna(dfe.sk_pg.mean()) + s.opp_sa.fillna(dfe.sa_pg.mean()))
        parts.append(s)
    df = pd.concat(parts)
    # within-slate/group relative features (pool only)
    p = df.in_pool & (df.proj > 0)
    df["val"] = np.where(p, df.proj / df.salk.clip(lower=1), 0.0)
    key = [df.slate_id, df.grp]
    for c in ["proj", "val", "salk", "team_total", "pressure"]:
        x = df[c].where(p)
        df[c + "_rk"] = x.groupby(key).rank(ascending=False, method="min")
        df[c + "_lrk"] = np.log(df[c + "_rk"].fillna(99))
        mu = x.groupby(key).transform("mean"); sd = x.groupby(key).transform("std").replace(0, np.nan)
        df[c + "_z"] = ((x - mu) / sd).fillna(-3)
        df[c + "_gap"] = (x.groupby(key).transform("max") - x).fillna(10)
    df["n_grp"] = p.groupby(key).transform("sum")
    df["n_games"] = df.groupby("slate_id").team.transform("nunique") / 2
    # public-value analogue (DK lobby AvgPPG / salary): season-to-date, falls back to last season
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


# feature families (used for ablation). all numeric columns created above.
FAM = {
    "price": ["salk", "salk_lrk", "salk_z", "cheap", "min_sal"],
    "our_proj": ["proj", "proj_lrk", "proj_z", "proj_gap", "val", "val_lrk", "val_z", "val_gap", "cv"],
    "optimizer": ["l_exp", "l_est"],
    "vegas": ["team_total", "opp_total", "spread", "game_total", "tt_rank", "gt_rank", "team_total_lrk"],
    "public_value": ["dkavg", "pubv", "pubv_lrk"],
    "recency": ["last_dk", "last_val", "last_val_lrk", "p3_dk"],
    "name": ["prev_ppg", "l_prev_rank", "ytd_gp"],
    "price_move": ["sal_chg", "has_prev_sal"],
    "lag_own": ["l_lag_own", "lag_own_avail"],
    "role": ["my_share", "p3_usage", "vacated"],
    "dst": ["pressure", "pressure_lrk", "dst_sk", "opp_sa"],
    "slate": ["n_grp", "n_games", "wk1"],
}
ALL = [c for v in FAM.values() for c in v]


def design(df, feats):
    X = df[feats].astype(float).to_numpy()
    X = np.where(np.isfinite(X), X, 0.0)
    pos = df[[f"is_{g}" for g in GROUPS]].to_numpy()
    return X, pos


# ----------------------------------------------------------------------------- softmax model
def _groups(df):
    return pd.factorize(df.slate_id.astype(str) + "|" + df.grp.astype(str))[0]


def _softmax(F, gid, mask):
    F = np.where(mask, F, -np.inf)
    m = pd.Series(F).groupby(gid).transform("max").to_numpy()
    e = np.where(mask, np.exp(F - np.where(np.isfinite(m), m, 0)), 0.0)
    s = pd.Series(e).groupby(gid).transform("sum").to_numpy()
    return np.where(s > 0, e / np.where(s > 0, s, 1), 0.0)


class Model:
    """Linear softmax (position-specific slopes via interactions) + optional Newton-boosted trees."""

    def __init__(self, feats, l2=1.0, trees=0, depth=3, lr=0.1, min_h=20.0, nbins=24, pos_inter=True, seed=0):
        self.feats, self.l2, self.trees, self.depth, self.lr = feats, l2, trees, depth, lr
        self.min_h, self.nbins, self.pos_inter = min_h, nbins, pos_inter

    def _X(self, df):
        X, pos = design(df, self.feats)
        if self.pos_inter:
            X = np.column_stack([X] + [X * pos[:, [k]] for k in range(pos.shape[1])])
        return X

    def fit(self, df, target):
        y = df[target].clip(lower=0).fillna(0).to_numpy(float)
        mask = (df.in_pool & (df.proj > 0)).to_numpy()
        gid = _groups(df)
        gs = pd.Series(y * mask).groupby(gid).transform("sum").to_numpy()
        t = np.where(gs > 0, y * mask / np.where(gs > 0, gs, 1), 0)
        w = gs / 100.0  # weight a group by its ownership mass
        X = self._X(df)
        self.mu = X[mask].mean(0); self.sd = X[mask].std(0); self.sd[self.sd == 0] = 1
        Z = (X - self.mu) / self.sd

        def f(b):
            F = Z @ b
            s = _softmax(F, gid, mask)
            ll = -(w * t * np.log(np.where(s > 0, s, 1))).sum() + self.l2 * (b @ b)
            gr = Z.T @ (w * (s - t)) + 2 * self.l2 * b
            return ll, gr
        self.b = minimize(f, np.zeros(Z.shape[1]), jac=True, method="L-BFGS-B", options={"maxiter": 800}).x
        self.budgets = (pd.Series(gs).groupby(df.grp.to_numpy()).mean()).to_dict() if False else \
            df.assign(_y=y * mask).groupby(["slate_id", "grp"])._y.sum().groupby("grp").mean().to_dict()
        self.forest = []
        if self.trees:
            Xt, _ = design(df, self.feats)
            Xt = np.column_stack([Xt, df[[f"is_{g}" for g in GROUPS]].to_numpy() @ np.arange(5)])
            self.edges = [np.unique(np.quantile(Xt[mask, j], np.linspace(0, 1, self.nbins + 1)[1:-1]))
                          for j in range(Xt.shape[1])]
            B = self._bin(Xt)
            F = Z @ self.b
            for _ in range(self.trees):
                s = _softmax(F, gid, mask)
                g = w * (s - t) * mask
                h = np.maximum(w * s * (1 - s), 1e-6) * mask
                tree = self._grow(B, g, h, np.where(mask)[0], 0)
                upd = self._apply(tree, B)
                F = F + self.lr * upd
                self.forest.append(tree)
        return self

    def _bin(self, X):
        return np.column_stack([np.searchsorted(e, X[:, j], side="right") for j, e in enumerate(self.edges)]).astype(np.int16)

    def _grow(self, B, g, h, idx, d):
        G, H = g[idx].sum(), h[idx].sum()
        leaf = {"v": -G / (H + 1.0)}
        if d >= self.depth or H < 2 * self.min_h:
            return leaf
        best = (0.0, None)
        base = G * G / (H + 1.0)
        for j in range(B.shape[1]):
            nb = self.nbins + 1
            gb = np.bincount(B[idx, j], weights=g[idx], minlength=nb)
            hb = np.bincount(B[idx, j], weights=h[idx], minlength=nb)
            gl, hl = np.cumsum(gb)[:-1], np.cumsum(hb)[:-1]
            gr, hr = G - gl, H - hl
            ok = (hl >= self.min_h) & (hr >= self.min_h)
            if not ok.any():
                continue
            gain = np.where(ok, gl ** 2 / (hl + 1) + gr ** 2 / (hr + 1) - base, -1)
            k = int(np.argmax(gain))
            if gain[k] > best[0]:
                best = (gain[k], (j, k))
        if best[1] is None:
            return leaf
        j, k = best[1]
        L = idx[B[idx, j] <= k]; Rr = idx[B[idx, j] > k]
        self.gain_log = getattr(self, "gain_log", {})
        self.gain_log[j] = self.gain_log.get(j, 0) + best[0]
        return {"j": j, "k": k, "l": self._grow(B, g, h, L, d + 1), "r": self._grow(B, g, h, Rr, d + 1)}

    def _apply(self, tree, B):
        out = np.zeros(len(B))
        stack = [(tree, np.arange(len(B)))]
        while stack:
            nd, ix = stack.pop()
            if "v" in nd:
                out[ix] = nd["v"]; continue
            m = B[ix, nd["j"]] <= nd["k"]
            stack.append((nd["l"], ix[m])); stack.append((nd["r"], ix[~m]))
        return out

    def score(self, df):
        Z = (self._X(df) - self.mu) / self.sd
        F = Z @ self.b
        if self.forest:
            Xt, _ = design(df, self.feats)
            Xt = np.column_stack([Xt, df[[f"is_{g}" for g in GROUPS]].to_numpy() @ np.arange(5)])
            B = self._bin(Xt)
            for tr in self.forest:
                F = F + self.lr * self._apply(tr, B)
        return F

    def predict(self, df, budgets=None, F=None):
        F = self.score(df) if F is None else F
        return allocate(df, F, budgets or self.budgets)

    def importance(self):
        names = self.feats + ["pos"]
        gl = getattr(self, "gain_log", {})
        tot = sum(gl.values()) or 1
        return pd.Series({names[j]: v / tot for j, v in gl.items()}).sort_values(ascending=False)


def allocate(df, F, budgets, cap=CAP):
    mask = (df.in_pool & (df.proj > 0)).to_numpy()
    gid = _groups(df)
    s = _softmax(F, gid, mask)
    out = np.zeros(len(df))
    b = df.grp.map(budgets).fillna(0).to_numpy()
    for g in np.unique(gid):
        ix = np.where(gid == g)[0]
        r = s[ix]; rem = b[ix[0]]; free = r > 0; o = np.zeros(len(ix))
        for _ in range(10):
            tot = r[free].sum()
            if tot <= 0 or rem <= 0:
                break
            trial = np.where(free, r / tot * rem, 0)
            over = free & (trial > cap)
            if not over.any():
                o = np.where(free, trial, o); break
            o = np.where(over, cap, o); rem -= cap * over.sum(); free &= ~over
        out[ix] = o
    return out


# ----------------------------------------------------------------------------- metrics
def metrics(df, pred, target):
    y = df[target].fillna(0).to_numpy(float); p = np.asarray(pred, float)
    o = {"n": len(y), "slates": df.slate_id.nunique()}
    o["corr"] = np.corrcoef(p, y)[0, 1]
    sp = [spearmanr(p[ix], y[ix])[0] for ix in df.groupby("slate_id").indices.values()]
    o["sp_slate"] = np.nanmean(sp)
    o["mae"] = np.abs(p - y).mean()
    hi = y >= 20
    o["catch20"] = (p[hi] >= 15).mean() if hi.any() else np.nan
    o["bias20"] = (p[hi] - y[hi]).mean() if hi.any() else np.nan
    pos = y > 0
    o["corr_pos"] = np.corrcoef(p[pos], y[pos])[0, 1]
    cw = pos & df.pos.isin(["WR", "TE"]).to_numpy() & (df.salary < 5500).to_numpy()
    o["corr_cheapWRTE"] = np.corrcoef(p[cw], y[cw])[0, 1]
    hi7 = (df.salary >= 7000).to_numpy() & (df.pos != "DST").to_numpy()
    o["corr_7k"] = np.corrcoef(p[hi7], y[hi7])[0, 1]
    # top-decile capture: of each slate's real top-10% (in pool-sized terms: top N/10 by real), share in pred top N/10
    cap_ = []
    for ix in df.groupby("slate_id").indices.values():
        k = max(1, int(round((y[ix] > 0).sum() / 10)))
        tr = set(ix[np.argsort(-y[ix])[:k]]); tp = set(ix[np.argsort(-p[ix])[:k]])
        cap_.append(len(tr & tp) / k)
    o["top10pct"] = np.mean(cap_)
    return o


def mtable(rows):
    t = pd.DataFrame(rows).T
    cols = ["slates", "corr", "sp_slate", "mae", "catch20", "bias20", "corr_pos", "corr_cheapWRTE", "corr_7k", "top10pct"]
    return t[[c for c in cols if c in t]].astype(float).round(3)
