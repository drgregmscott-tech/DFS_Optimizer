"""Score a Showdown lineup file against the simulated field under correlated outcomes.

usage: python analysis/showdown_own/score_lineups.py <projections_csv> <lineups_csv> [n_sims]

Outcomes: points_i = max(0, proj_i + sigma_i * z_i), with
  z_i = a*G(game) + b*T(own offense) + noise         (skill / QB)
  kicker: 0.45*T(own offense) + noise
  DST:   -0.5*T(opposing offense) + noise
(a=0.2, b=0.45 => same-team skill corr ~0.24, opposing ~0.04). The field is the
ownership-weighted simulated field (scripts/showdown_field.py) built from the
projections file's estimated CPT/FLEX ownership. Reports, per lineup, the mean
field percentile and P(top 10% / 1% / 0.1%) across simulated slates: a
top-heavy proxy for GPP value, NOT a calibrated win probability (ownership is
an estimate, correlations are assumed).
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "scripts"))
import showdown_field as sf


def main(proj_csv, lineup_csv, n_sims=1500, n_field=20000, seed=11, dst_rho=-0.5, dst_sig_mult=1.0):
    P = pd.read_csv(proj_csv, dtype={"player_id": str})
    fl = P[P.roster_role == "FLEX"].reset_index(drop=True)
    cpt_own = fl.player_id.map(P[P.roster_role == "CPT"].set_index("player_id").estimated_ownership_pct).values
    c, f = sf.simulate_field(fl.salary.values, fl.team.values, cpt_own, fl.estimated_ownership_pct.values,
                             n=n_field, seed=seed)
    idx = {pid: i for i, pid in enumerate(fl.player_id)}
    teams = fl.team.unique().tolist()
    tix = fl.team.map({t: i for i, t in enumerate(teams)}).values
    opp = 1 - tix
    pos = fl.position.values
    proj = fl.final_projection.values
    sig = pd.to_numeric(fl.sigma, errors="coerce").fillna(pd.Series(proj * 0.6)).values
    m = len(fl)
    rng = np.random.default_rng(seed)
    L = pd.read_csv(lineup_csv, dtype={"player_id": str})
    lus = []
    for lid, g in L.groupby("lineup_id"):
        cp = idx[g[g.roster_role == "CPT"].player_id.iloc[0]]
        fx = [idx[x] for x in g[g.roster_role == "FLEX"].player_id]
        lus.append((lid, cp, fx))
    pct = {lid: [] for lid, _, _ in lus}
    for _ in range(n_sims):
        G = rng.normal(); T = rng.normal(size=2); e = rng.normal(size=m)
        z = 0.2 * G + 0.45 * T[tix] + np.sqrt(1 - 0.04 - 0.2025) * e
        isk = pos == "K"; isd = np.isin(pos, ["DST", "D", "DEF"])
        z = np.where(isk, 0.45 * T[tix] + np.sqrt(1 - 0.2025) * e, z)
        z = np.where(isd, dst_rho * T[opp] + np.sqrt(1 - dst_rho ** 2) * e, z)
        pts = np.maximum(0.0, proj + sig * np.where(isd, dst_sig_mult, 1.0) * z)
        field = 1.5 * pts[c] + pts[f].sum(axis=1)
        fs = np.sort(field)
        for lid, cp, fx in lus:
            sc = 1.5 * pts[cp] + pts[fx].sum()
            pct[lid].append(np.searchsorted(fs, sc) / len(fs))
    rows = []
    for lid, cp, fx in lus:
        p = np.array(pct[lid])
        g = L[L.lineup_id == lid]
        rows.append(dict(lineup=lid, cpt=fl.player_name[cp], proj=round(g.projection.sum(), 1),
                         mean_pct=round(p.mean() * 100, 1), top10=round((p >= .90).mean() * 100, 1),
                         top1=round((p >= .99).mean() * 100, 2), top01=round((p >= .999).mean() * 100, 2)))
    out = pd.DataFrame(rows).sort_values("top1", ascending=False)
    print(out.to_string(index=False))
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1500)
