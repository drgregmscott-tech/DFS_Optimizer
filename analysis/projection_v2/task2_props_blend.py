"""Task 2b: props-implied receiving blend weight for WR/TE, 2026 wk3 (the only slates with props audits).
No FC data. Engine-only and market stat means come from data/props/audit_*.csv (written at build time).
Candidate: cand(w) = final_projection + (RP_w - RP_final), RP = rec + 0.1*rec_yd + 6*rec_td,
RP_w = (1-w)*RP_engine + w*RP_market. w=weight on market; final already contains the live anchor.
"""
import io, subprocess
from pathlib import Path
import numpy as np, pandas as pd

R = Path(__file__).resolve().parents[2]
rng = np.random.default_rng(0)


def load():
    out = []
    for sub in ["main", "early", "afternoon"]:
        o = pd.read_csv(io.StringIO(subprocess.run(["git", "-C", str(R), "show", f"HEAD:output/final_projections_dk_dk_classic_wk3_{sub}_27Sep2026.csv"],
                                                   capture_output=True, text=True, encoding="utf-8", check=True).stdout), dtype={"player_id": str})
        a = pd.read_csv(R / f"data/props/audit_dk_classic_wk3_{sub}_27Sep2026.csv", dtype={"player_id": str})
        r = pd.read_csv(R / f"data/results_raw_dk_2026_wk3_{sub}.csv"); r["player_name"] = r.player_name.str.strip()
        m = o[o.position.isin(["WR", "TE"])].merge(a.drop(columns=["player_name", "position", "team"]), on="player_id").merge(r, on="player_name")
        m = m[m.props_matched.astype(bool) & m.props_rec_market.notna() & m.props_recyd_market.notna()]
        m["sub"] = sub
        out.append(m)
    d = pd.concat(out, ignore_index=True)
    td_m = d.props_td_market.fillna(d.props_td_engine)
    d["rp_eng"] = d.props_rec_engine + .1 * d.props_recyd_engine + 6 * d.props_td_engine.fillna(d.proj_rec_td)
    d["rp_mkt"] = d.props_rec_market + .1 * d.props_recyd_market + 6 * td_m
    d["rp_fin"] = d.proj_rec + .1 * d.proj_rec_yd + 6 * d.proj_rec_td
    d["w_live"] = ((d.rp_fin - d.rp_eng) / (d.rp_mkt - d.rp_eng)).where((d.rp_mkt - d.rp_eng).abs() > 1)
    return d


def main():
    d = load()
    d = d[d.actual_fpts.notna()]
    print(f"WR/TE with props matched & actual: {len(d)}  per slate {d['sub'].value_counts().to_dict()}")
    print(f"effective live anchor weight implied by final file (median over |mkt-eng|>1): {d.w_live.median():.2f}")
    ws = np.round(np.arange(0, 1.01, .1), 1)
    rows = []
    for w in ws:
        c = d.final_projection + ((1 - w) * d.rp_eng + w * d.rp_mkt - d.rp_fin)
        for sub, g in d.assign(c=c).groupby("sub"):
            rows.append((w, sub, (g.c - g.actual_fpts).abs().mean(), np.corrcoef(g.c, g.actual_fpts)[0, 1]))
        rows.append((w, "ALL", (c - d.actual_fpts).abs().mean(), np.corrcoef(c, d.actual_fpts)[0, 1]))
    T = pd.DataFrame(rows, columns=["w", "sub", "mae", "corr"]).pivot(index="w", columns="sub")
    print(T.round(3).to_string())
    # bootstrap best w and MAE gain of w*=best vs current final (players resampled)
    best = []
    gains = []
    for _ in range(1000):
        b = d.sample(len(d), replace=True, random_state=int(rng.integers(1e9)))
        maes = [((b.final_projection + ((1 - w) * b.rp_eng + w * b.rp_mkt - b.rp_fin)) - b.actual_fpts).abs().mean() for w in ws]
        best.append(ws[int(np.argmin(maes))])
        gains.append((b.final_projection - b.actual_fpts).abs().mean() - maes[list(ws).index(1.0)])
    best = np.array(best)
    print(f"bootstrap argmin-MAE w: median {np.median(best):.1f}, 80% interval [{np.quantile(best,.1):.1f},{np.quantile(best,.9):.1f}]")
    print(f"MAE gain final -> w=1.0: mean {np.mean(gains):+.3f}, 95% [{np.quantile(gains,.025):+.3f},{np.quantile(gains,.975):+.3f}]")
    cheap = d[d.salary < 5500]
    for w in [0.0, 0.5, 1.0]:
        c = cheap.final_projection + ((1 - w) * cheap.rp_eng + w * cheap.rp_mkt - cheap.rp_fin)
        print(f"cheap <5.5k n={len(cheap)} w={w}: MAE {(c-cheap.actual_fpts).abs().mean():.3f} corr {np.corrcoef(c,cheap.actual_fpts)[0,1]:.3f}  (final MAE {(cheap.final_projection-cheap.actual_fpts).abs().mean():.3f})")


if __name__ == "__main__":
    main()
