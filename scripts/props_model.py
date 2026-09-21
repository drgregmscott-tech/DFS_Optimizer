"""
props_model.py
===============

Player-prop market lines -> expected stat-line means, and the "market anchor"
that blends those means into the stat-line engine's per-player inputs.

WHY (Week 2 2026 post-mortem, see WK2_POSTMORTEM.md): over 31 historical
weeks the engine beats salary, but in 2026 wk1-2 it was roughly tied, and the
one market signal we could test (DraftKings anytime-TD odds, 290 RB/WR/TE
player-weeks) explained more fantasy-point variance than the engine did
(R2 0.36 vs 0.29; engine + TD odds 0.36). Sportsbooks price role, injuries,
game script and matchup in ways our recency-weighted history cannot. Session
14.1 shelved props "pending real evidence"; this is built on that evidence.

THE MATH
--------
For every (player, market, book):

  1. Odds -> implied probability, then remove the book's margin. Two-sided
     markets (over/under) use the POWER method (find k with po^k + pu^k = 1),
     which handles lopsided prices better than simple normalization.
  2. Fit a distribution to (line, P(over)) and read off its MEAN (not the
     line -- lines sit near the median, and yardage is right-skewed):
       receptions / pass TDs : negative binomial (var/mean ~ 1.2, r = 20)
       receiving/rushing/passing yards: gamma, with a marginal coefficient of
         variation that falls with the mean. CV(mean) was measured on
         2019-25 nflverse player-games (mean of an 8-game rolling proxy,
         played games only): rec yds 0.73 -> 0.54 over means 29 -> 76,
         rush yds 0.66 -> 0.53, pass yds ~0.30. These marginals include a
         little mean-uncertainty, so they slightly over-state dispersion (and
         so slightly over-state the mean implied by an over-probability > 50%).
  3. Anytime TD is one-sided (only "Yes" is posted), so the margin cannot be
     read off the price. It is removed at the GAME level instead: the
     listed players' implied probabilities are scaled so they sum to the
     number of distinct TD scorers the Vegas total implies (falling back to
     a flat 1/1.15). Expected TDs = -ln(1 - p) (Poisson).
  4. Books are combined by taking the MEDIAN of the per-book implied means,
     which handles books posting different lines (63.5 vs 64.5) and
     outliers. A market needs >= MIN_BOOKS books, else it is ignored.

THE BLEND (apply_market_anchor)
--------------------------------
Per stat, target mean = w * market + (1 - w) * engine, with the market/engine
ratio clamped to [CLAMP_LO, CLAMP_HI]. The engine's per-player usage
parameters (volume, yards-per-unit, TD rate) are then re-solved so its own
Monte Carlo reproduces those target means; the engine's variance structure,
DK bonuses and teammate correlations all still apply. Players with no market
data are untouched. Every adjustment is written to audit columns.

Pure functions, no network access. props_ingest.py fetches; build_projections_
statline.py calls apply_market_anchor().
"""

import math
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

MIN_BOOKS = 2
DEFAULT_WEIGHT = 0.5
CLAMP_LO, CLAMP_HI = 0.5, 1.8
NB_R = 20.0          # receptions / pass TD dispersion (var = mu + mu^2/r)
DEFAULT_TD_VIG_DIVISOR = 1.15
FG_POINTS_PER_GAME = 10.0   # expected field-goal points per game, for the TD budget
SKILL_SCORER_COVERAGE = 0.93  # share of distinct TD scorers that are listed in the market

MARKET_KEYS = {
    "player_reception_yds": "rec_yd",
    "player_receptions": "rec",
    "player_rush_yds": "rush_yd",
    "player_pass_yds": "pass_yd",
    "player_pass_tds": "pass_td",
    "player_anytime_td": "anytime_td",
}


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def norm_name(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.lower().replace("'", "").replace(".", "").replace("-", " ")
    s = _SUFFIX.sub("", s)
    return " ".join(re.sub(r"[^a-z ]", " ", s).split())


# ---------------------------------------------------------------------------
# Odds -> probability
# ---------------------------------------------------------------------------

def american_to_prob(o: float) -> float:
    o = float(o)
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def power_devig(p_over: float, p_under: float) -> float:
    """No-vig P(over) via the power method: find k with po^k + pu^k = 1."""
    lo, hi = 0.3, 4.0
    for _ in range(80):
        k = 0.5 * (lo + hi)
        if p_over ** k + p_under ** k > 1.0:
            lo = k
        else:
            hi = k
    return p_over ** (0.5 * (lo + hi))


# ---------------------------------------------------------------------------
# Distributions (no scipy in this project's requirements)
# ---------------------------------------------------------------------------

def _gammaincc(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x) (Numerical Recipes)."""
    if x <= 0:
        return 1.0
    if x < a + 1.0:                      # series for P, return 1 - P
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(500):
            ap += 1.0
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-12:
                break
        return 1.0 - s * math.exp(-x + a * math.log(x) - math.lgamma(a))
    b = x + 1.0 - a                       # continued fraction for Q
    c = 1e300
    d = 1.0 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-12:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def yards_cv(kind: str, mean: float) -> float:
    m = max(float(mean), 1.0)
    if kind == "rec_yd":
        return float(np.clip(0.83 - 0.0037 * m, 0.45, 0.85))
    if kind == "rush_yd":
        return float(np.clip(0.77 - 0.0029 * m, 0.45, 0.85))
    if kind == "pass_yd":
        return 0.30
    return 0.6


def gamma_sf(x: float, mean: float, cv: float) -> float:
    """P(Y > x) for Y ~ Gamma with the given mean and coefficient of variation."""
    shape = 1.0 / (cv * cv)
    return _gammaincc(shape, x / (mean * cv * cv))


def mean_from_yards_line(kind: str, line: float, p_over: float) -> float:
    """Mean of the gamma whose P(Y > line) = p_over (CV depends on the mean)."""
    lo, hi = 1.0, max(6.0 * line, 50.0)
    for _ in range(80):
        mu = 0.5 * (lo + hi)
        if gamma_sf(line, mu, yards_cv(kind, mu)) < p_over:
            lo = mu
        else:
            hi = mu
    return 0.5 * (lo + hi)


def nb_sf_count(k: int, mu: float, r: float = NB_R) -> float:
    """P(X >= k) for X ~ NegBin(mean mu, size r)."""
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    q = r / (r + mu)
    lq, lp = math.log(q), math.log(mu / (r + mu))
    cdf = 0.0
    for j in range(k):
        cdf += math.exp(math.lgamma(j + r) - math.lgamma(r) - math.lgamma(j + 1) + r * lq + j * lp)
    return max(0.0, 1.0 - cdf)


def mean_from_count_line(line: float, p_over: float, r: float = NB_R) -> float:
    """Mean of the NB whose P(X > line) = p_over; line is x.5, so X >= line+0.5."""
    k = int(math.floor(line)) + 1
    lo, hi = 0.01, 12.0 if line < 12 else 60.0
    for _ in range(80):
        mu = 0.5 * (lo + hi)
        if nb_sf_count(k, mu, r) < p_over:
            lo = mu
        else:
            hi = mu
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# Market table -> per-player expected stats
# ---------------------------------------------------------------------------

def td_budget_scale(sum_implied: float, game_total: float | None) -> float:
    """Factor (<= 1) applied to every listed player's implied anytime-TD
    probability in a game so they sum to the distinct TD scorers the Vegas
    total implies."""
    if not sum_implied or sum_implied <= 0:
        return 1.0 / DEFAULT_TD_VIG_DIVISOR
    if game_total and game_total > 20:
        tds = max(game_total - FG_POINTS_PER_GAME, 10.0) / 7.0
        target = tds * 0.97 * SKILL_SCORER_COVERAGE
        return float(np.clip(target / sum_implied, 0.6, 1.0))
    return 1.0 / DEFAULT_TD_VIG_DIVISOR


def market_means(props: pd.DataFrame, game_totals: dict | None = None) -> pd.DataFrame:
    """props: normalized long table with columns event_id, home, away, player,
    market, line, side ('Over'/'Under'/'Yes'), price, book.
    game_totals: {event_id: over/under}. Returns one row per (event_id,
    player_key) with columns rec, rec_yd, rush_yd, pass_yd, pass_td (means),
    anytime_p (de-vigged probability) and n_books_<stat>."""
    if props is None or len(props) == 0:
        return pd.DataFrame()
    props = props.copy()
    props["pkey"] = props["player"].map(norm_name)
    props["stat"] = props["market"].map(MARKET_KEYS)
    props = props.dropna(subset=["stat", "price"])
    out = {}

    def slot(event, pkey, player):
        return out.setdefault((event, pkey), {"event_id": event, "player_key": pkey, "player": player})

    # two-sided markets
    two = props[props["stat"] != "anytime_td"]
    for (event, pkey, stat, book, line), g in two.groupby(["event_id", "pkey", "stat", "book", "line"]):
        sides = {r.side: american_to_prob(r.price) for r in g.itertuples()}
        if "Over" not in sides or "Under" not in sides:
            continue
        p_over = power_devig(sides["Over"], sides["Under"])
        p_over = float(np.clip(p_over, 0.03, 0.97))
        if stat in ("rec", "pass_td"):
            mu = mean_from_count_line(float(line), p_over)
        else:
            mu = mean_from_yards_line(stat, float(line), p_over)
        d = slot(event, pkey, g["player"].iloc[0])
        d.setdefault(f"_{stat}", []).append(mu)

    # one-sided anytime TD, de-vigged at the game level
    at = props[props["stat"] == "anytime_td"]
    for (event, book), g in at.groupby(["event_id", "book"]):
        pk = g.groupby("pkey").agg(price=("price", "first"), player=("player", "first"))
        p = pk["price"].map(american_to_prob)
        scale = td_budget_scale(float(p.sum()), (game_totals or {}).get(event))
        for key, val in p.items():
            d = slot(event, key, pk.loc[key, "player"])
            d.setdefault("_anytime_p", []).append(float(np.clip(val * scale, 0.005, 0.95)))

    rows = []
    for d in out.values():
        row = {"event_id": d["event_id"], "player_key": d["player_key"], "player": d["player"]}
        for stat in ("rec", "rec_yd", "rush_yd", "pass_yd", "pass_td", "anytime_p"):
            vals = d.get(f"_{stat}", [])
            row[stat] = float(np.median(vals)) if len(vals) >= MIN_BOOKS else np.nan
            row[f"n_books_{stat}"] = len(vals)
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Blend into the engine's per-player usage parameters
# ---------------------------------------------------------------------------

def _num(x, default=0.0):
    try:
        v = float(x)
        return default if not np.isfinite(v) else v
    except (TypeError, ValueError):
        return default


def _blend(engine_mean: float, market_mean: float, w: float) -> float:
    if not np.isfinite(market_mean) or engine_mean <= 1e-9:
        # No usable engine mean to ratio against: trust the market only when it is
        # clearly non-trivial, and still respect the weight.
        return w * market_mean + (1 - w) * engine_mean if np.isfinite(market_mean) else engine_mean
    target = w * market_mean + (1 - w) * engine_mean
    return float(np.clip(target, CLAMP_LO * engine_mean, CLAMP_HI * engine_mean))


def apply_market_anchor(df: pd.DataFrame, market: pd.DataFrame, variance: dict,
                        weight: float = DEFAULT_WEIGHT, verbose: bool = True) -> pd.DataFrame:
    """df: the engine's per-player frame just before simulate() (columns
    player_id, player_name, position, team, opponent, {pass,rush,recv}_mu /
    _yd_rate / _td_rate, catch_rate, market_factor, optional weather factors).
    market: output of market_means() with an added `team` column (the
    player's team, set by match_market_to_pool()). Returns df with adjusted
    usage parameters plus audit columns props_*."""
    df = df.copy()
    audit_cols = ["props_matched", "props_rec_engine", "props_rec_market", "props_recyd_engine",
                  "props_recyd_market", "props_rushyd_engine", "props_rushyd_market",
                  "props_passyd_engine", "props_passyd_market", "props_td_engine",
                  "props_td_market"]
    for c in audit_cols:
        df[c] = np.nan if c != "props_matched" else False
    if market is None or len(market) == 0:
        return df

    mk = market.set_index(["team", "player_key"])
    n_adj = 0
    for idx, row in df.iterrows():
        pos = row.get("position")
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        key = (row.get("team"), norm_name(row.get("player_name")))
        if key not in mk.index:
            continue
        m = mk.loc[key]
        if isinstance(m, pd.DataFrame):
            m = m.iloc[0]
        vpos = variance["positions"].get(pos, {})
        fac = _num(row.get("market_factor"), 1.0) or 1.0
        wx_vol_p = _num(row.get("pass_vol_factor"), 1.0) or 1.0
        wx_eff_p = _num(row.get("pass_eff_factor"), 1.0) or 1.0
        wx_vol_r = _num(row.get("rush_vol_factor"), 1.0) or 1.0
        cr = float(np.clip(_num(row.get("catch_rate"), vpos.get("catch_rate", 0.65)) or vpos.get("catch_rate", 0.65), 0.05, 1.0))
        touched = False

        # ---- receiving component (RB/WR/TE) --------------------------------
        if pos in ("RB", "WR", "TE"):
            tgt = _num(row.get("recv_mu")) * wx_vol_p
            ydr = _num(row.get("recv_yd_rate")) * fac * wx_eff_p
            tdr = _num(row.get("recv_td_rate")) * fac * wx_eff_p
            e_rec, e_ryd, e_rtd = tgt * cr, tgt * ydr, tgt * tdr
            att = _num(row.get("rush_mu")) * wx_vol_r
            rydr = _num(row.get("rush_yd_rate")) * fac
            rtdr = _num(row.get("rush_td_rate")) * fac
            e_rush_yd, e_rush_td = att * rydr, att * rtdr
            df.at[idx, "props_rec_engine"], df.at[idx, "props_recyd_engine"] = e_rec, e_ryd
            df.at[idx, "props_rushyd_engine"] = e_rush_yd
            df.at[idx, "props_td_engine"] = e_rtd + e_rush_td
            df.at[idx, "props_rec_market"], df.at[idx, "props_recyd_market"] = m.get("rec"), m.get("rec_yd")
            df.at[idx, "props_rushyd_market"] = m.get("rush_yd")

            new_tgt = tgt
            if np.isfinite(m.get("rec", np.nan)) and e_rec > 1e-9:
                new_tgt = _blend(e_rec, m["rec"], weight) / cr
                touched = True
            elif np.isfinite(m.get("rec_yd", np.nan)) and e_ryd > 1e-9:
                # receptions line missing: let yards drive volume, rate stays
                new_tgt = tgt * _blend(e_ryd, m["rec_yd"], weight) / e_ryd
                touched = True
            new_ydr = ydr
            if np.isfinite(m.get("rec_yd", np.nan)) and e_ryd > 1e-9 and new_tgt > 1e-9 and np.isfinite(m.get("rec", np.nan)):
                new_ydr = _blend(e_ryd, m["rec_yd"], weight) / new_tgt
                touched = True
            elif new_tgt > 1e-9:
                new_ydr = ydr                    # volume moved yards proportionally
            new_att, new_rydr = att, rydr
            if np.isfinite(m.get("rush_yd", np.nan)) and e_rush_yd > 1e-9:
                new_rydr = _blend(e_rush_yd, m["rush_yd"], weight) / max(att, 1e-9)
                touched = True
            # anytime TD: split the market total between receiving and rushing
            # by the engine's own ratio, then blend
            e_td = e_rtd + e_rush_td
            new_tdr, new_rtdr = tdr, rtdr
            if np.isfinite(m.get("anytime_p", np.nan)) and e_td > 1e-9:
                lam = -math.log(1.0 - float(m["anytime_p"]))
                df.at[idx, "props_td_market"] = lam
                tgt_td = _blend(e_td, lam, weight)
                ratio = tgt_td / e_td
                # rates scale so total expected TDs hit the blended target given
                # the (possibly changed) volumes
                new_tdr = tdr * ratio * (tgt / new_tgt if new_tgt > 1e-9 else 1.0)
                new_rtdr = rtdr * ratio * (att / new_att if new_att > 1e-9 else 1.0)
                touched = True
            df.at[idx, "recv_mu"] = new_tgt / wx_vol_p if wx_vol_p else new_tgt
            df.at[idx, "recv_yd_rate"] = new_ydr / (fac * wx_eff_p)
            df.at[idx, "recv_td_rate"] = new_tdr / (fac * wx_eff_p)
            df.at[idx, "rush_yd_rate"] = new_rydr / fac
            df.at[idx, "rush_td_rate"] = new_rtdr / fac

        # ---- QB ------------------------------------------------------------
        if pos == "QB":
            att = _num(row.get("pass_mu")) * wx_vol_p
            ydr = _num(row.get("pass_yd_rate")) * fac * wx_eff_p
            tdr = _num(row.get("pass_td_rate")) * fac * wx_eff_p
            e_pyd, e_ptd = att * ydr, att * tdr
            df.at[idx, "props_passyd_engine"], df.at[idx, "props_passyd_market"] = e_pyd, m.get("pass_yd")
            new_ydr, new_tdr = ydr, tdr
            if np.isfinite(m.get("pass_yd", np.nan)) and e_pyd > 1e-9:
                new_ydr = _blend(e_pyd, m["pass_yd"], weight) / max(att, 1e-9)
                touched = True
            if np.isfinite(m.get("pass_td", np.nan)) and e_ptd > 1e-9:
                new_tdr = _blend(e_ptd, m["pass_td"], weight) / max(att, 1e-9)
                touched = True
            df.at[idx, "pass_yd_rate"] = new_ydr / (fac * wx_eff_p)
            df.at[idx, "pass_td_rate"] = new_tdr / (fac * wx_eff_p)
            # QB anytime TD = rushing TDs only
            att_r = _num(row.get("rush_mu")) * wx_vol_r
            rtdr = _num(row.get("rush_td_rate")) * fac
            e_rtd = att_r * rtdr
            if np.isfinite(m.get("anytime_p", np.nan)) and e_rtd > 1e-9:
                lam = -math.log(1.0 - float(m["anytime_p"]))
                df.at[idx, "props_td_engine"], df.at[idx, "props_td_market"] = e_rtd, lam
                df.at[idx, "rush_td_rate"] = _blend(e_rtd, lam, weight) / max(att_r, 1e-9) / fac
                touched = True
        if touched:
            df.at[idx, "props_matched"] = True
            n_adj += 1
    if verbose:
        print(f"Props market anchor: adjusted {n_adj} player(s) at weight {weight:.2f} "
              f"(clamp {CLAMP_LO}-{CLAMP_HI}x of the engine mean).")
    return df


def match_market_to_pool(market: pd.DataFrame, events: pd.DataFrame, pool: pd.DataFrame) -> pd.DataFrame:
    """Attach `team` to market rows by name within each event's two teams.
    events: columns event_id, home_abbr, away_abbr. pool: engine frame with
    player_name, team. Ambiguous matches (same normalized name on both teams)
    are dropped rather than guessed."""
    if market is None or len(market) == 0:
        return market
    ev = events.set_index("event_id")
    by_team = {}
    for r in pool[["player_name", "team"]].itertuples(index=False):
        by_team.setdefault(r.team, set()).add(norm_name(r.player_name))
    rows, dropped = [], 0
    for r in market.itertuples(index=False):
        if r.event_id not in ev.index:
            continue
        teams = [ev.loc[r.event_id, "home_abbr"], ev.loc[r.event_id, "away_abbr"]]
        hits = [t for t in teams if r.player_key in by_team.get(t, ())]
        if len(hits) != 1:
            dropped += 1
            continue
        d = r._asdict()
        d["team"] = hits[0]
        rows.append(d)
    print(f"Props matching: {len(rows)} market player(s) matched to the pool, {dropped} unmatched/ambiguous dropped.")
    return pd.DataFrame(rows)
