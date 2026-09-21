"""
showdown_field.py -- simulated DK Showdown field from CPT/FLEX ownership.

Each simulated entry = 1 CPT (1.5x salary/points) + 5 distinct FLEX, cap
$50,000, at least one player from each team. Candidates are drawn from the
ownership vectors, filtered by the cap / team rule, and the draw weights are
re-tuned (iterative proportional fitting) so the ACCEPTED lineups reproduce the
target CPT and FLEX ownership. Optional `split_target` (share of lineups with
k players from the CPT's team, k=1..5) reweights lineups to a target team split.
"""
import numpy as np
import pandas as pd

CAP_SALARY = 50000
MIN_SALARY = 48500  # real entries: median ~49.7k, 10th pct ~48.4-48.8k (wk1/wk2); 48.5k matched score quantiles within ~1 pt
N_FLEX = 5


def _draw(wc, wf, n, rng, exclude_self=True):
    m = len(wc)
    cpt = rng.choice(m, size=n, p=wc / wc.sum())
    keys = np.log(wf)[None, :] + rng.gumbel(size=(n, m))
    keys[np.arange(n), cpt] = -np.inf  # a player cannot be CPT and FLEX
    flex = np.argpartition(-keys, N_FLEX, axis=1)[:, :N_FLEX]
    return cpt, flex


def simulate_field(sal_flex, team, cpt_own, flex_own, n=20000, seed=0, iters=10, batch=150000,
                   split_target=None, min_salary=MIN_SALARY):
    """sal_flex: FLEX salaries (CPT = 1.5x). team: team label per player.
    cpt_own/flex_own: % ownership (CPT sums ~100, FLEX ~500).
    Returns (cpt_idx[n], flex_idx[n,5], weights[n]) of accepted lineups."""
    rng = np.random.default_rng(seed)
    sal = np.asarray(sal_flex, float)
    team = np.asarray(team)
    tid = pd.factorize(team)[0]
    m = len(sal)
    tc = np.maximum(np.asarray(cpt_own, float), 1e-4) / 100.0
    tf = np.maximum(np.asarray(flex_own, float), 1e-4) / 100.0
    wc, wf = tc.copy(), tf.copy()
    best = (np.inf, wc.copy(), wf.copy())
    for it in range(iters + 1):
        cpt, flex = _draw(wc, wf, batch, rng)
        tot = 1.5 * sal[cpt] + sal[flex].sum(axis=1)
        same = (tid[flex] == tid[cpt][:, None]).all(axis=1)
        ok = (tot <= CAP_SALARY) & (tot >= min_salary) & ~same
        if ok.sum() < 2000:  # weights drifted to an (almost) infeasible corner: go back to the best so far
            wc, wf = best[1].copy(), best[2].copy()
            cpt, flex = _draw(wc, wf, batch, rng)
            tot = 1.5 * sal[cpt] + sal[flex].sum(axis=1)
            same = (tid[flex] == tid[cpt][:, None]).all(axis=1)
            ok = (tot <= CAP_SALARY) & (tot >= min_salary) & ~same
            cpt, flex = cpt[ok], flex[ok]
            w = np.ones(len(cpt))
            break
        cpt, flex = cpt[ok], flex[ok]
        w = np.ones(len(cpt))
        if split_target is not None:
            k = np.clip((tid[flex] == tid[cpt][:, None]).sum(axis=1) + 1, 1, 5)
            share = np.bincount(k, minlength=6)[1:6] / len(k)
            ratio = np.where(share > 0, np.asarray(split_target) / np.maximum(share, 1e-9), 0)
            w = ratio[k - 1]
        obs_c = np.bincount(cpt, weights=w, minlength=m) / w.sum()
        obs_f = np.bincount(flex.ravel(), weights=np.repeat(w, N_FLEX), minlength=m) / w.sum()
        err = np.abs(obs_c - tc).sum() + np.abs(obs_f - tf).sum() / N_FLEX
        if err < best[0]:
            best = (err, wc.copy(), wf.copy())
        if it == iters:
            break
        wc = wc * np.clip(tc / np.maximum(obs_c, 1e-4), 0.5, 2.0) ** 0.6
        wf = wf * np.clip(tf / np.maximum(obs_f, 1e-4), 0.5, 2.0) ** 0.6
    idx = rng.choice(len(cpt), size=n, replace=True, p=w / w.sum())
    return cpt[idx], flex[idx]


def score_lineups(cpt, flex, pts_flex):
    p = np.asarray(pts_flex, float)
    return 1.5 * p[cpt] + p[flex].sum(axis=1)


def marginals(cpt, flex, m):
    n = len(cpt)
    return np.bincount(cpt, minlength=m) / n * 100, np.bincount(flex.ravel(), minlength=m) / n * 100
