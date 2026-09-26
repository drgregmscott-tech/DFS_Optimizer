"""Exhaustive DK showdown lineup enumeration + max-entropy (IPF) field model. No FC data here."""
from itertools import combinations
from functools import lru_cache
import numpy as np
CAP = 50000

@lru_cache(None)
def combos(n):
    return np.array(list(combinations(range(n), 5)), dtype=np.int16)

def enumerate_game(g):
    """g: DataFrame one row per player (flex sal/proj/act, Team, pos). Returns dict of per-lineup arrays.
    Lineup = CPT index c (1.5x sal/proj/act) + 5 distinct FLEX indices; cap 50k; both teams."""
    n = len(g); sal = g.sal.to_numpy(float); proj = g.proj.to_numpy(float); act = g.act.to_numpy(float)
    t = (g.Team.to_numpy() == g.Team.iloc[0]).astype(np.int8)
    out = {k: [] for k in ("cpt", "flex", "sal", "proj", "act", "nteam0")}
    C = combos(n - 1)
    for c in range(n):
        others = np.delete(np.arange(n), c)
        F = others[C]
        s = 1.5 * sal[c] + sal[F].sum(1)
        tt = t[c] + t[F].sum(1)
        ok = (s <= CAP) & (tt >= 1) & (tt <= 5)
        F = F[ok]
        out["cpt"].append(np.full(len(F), c, np.int16)); out["flex"].append(F.astype(np.int16))
        out["sal"].append(s[ok].astype(np.float32)); out["nteam0"].append(tt[ok].astype(np.int8))
        out["proj"].append((1.5 * proj[c] + proj[F].sum(1)).astype(np.float32))
        out["act"].append((1.5 * act[c] + act[F].sum(1)).astype(np.float32))
    return {k: np.concatenate(v) for k, v in out.items()}

def ipf_field(L, cpt_t, flex_t, logprior=None, iters=40):
    """Max-entropy lineup distribution matching CPT marginals cpt_t (sum 1) and FLEX marginals flex_t (sum 5)
    over enumerated lineups, times exp(logprior). Returns normalized weights."""
    n = len(cpt_t); a = np.log(np.maximum(cpt_t, 1e-6)); b = np.log(np.maximum(flex_t, 1e-6))
    lp = np.zeros(len(L["cpt"])) if logprior is None else logprior
    for _ in range(iters):
        z = lp + a[L["cpt"]] + b[L["flex"]].sum(1); z -= z.max(); w = np.exp(z); w /= w.sum()
        mc = np.bincount(L["cpt"], w, n)
        a += np.log(np.maximum(cpt_t, 1e-9) / np.maximum(mc, 1e-12)) * (cpt_t > 0)
        z = lp + a[L["cpt"]] + b[L["flex"]].sum(1); z -= z.max(); w = np.exp(z); w /= w.sum()
        mf = sum(np.bincount(L["flex"][:, j], w, n) for j in range(5))
        b += np.log(np.maximum(flex_t, 1e-9) / np.maximum(mf, 1e-12)) * (flex_t > 0)
    z = lp + a[L["cpt"]] + b[L["flex"]].sum(1); z -= z.max(); w = np.exp(z); w /= w.sum()
    mc = np.bincount(L["cpt"], w, n); mf = sum(np.bincount(L["flex"][:, j], w, n) for j in range(5))
    err = max(np.abs(mc - cpt_t).max(), np.abs(mf - flex_t).max())
    return w, err

def field_percentile(score, act, w):
    """share of field (weights w) strictly beaten + half ties."""
    return float(w[act < score].sum() + 0.5 * w[act == score].sum())

def wquantile(x, w, q):
    o = np.argsort(x); cw = np.cumsum(w[o]); return float(x[o][np.searchsorted(cw, q)])
