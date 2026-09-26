"""Write the refit sigma_recalibration artifacts that go with the net-of-latent statline_variance.json (2026-09-26).
Research script; NO FC data in this file (reads the git-ignored FC-derived frames built by evaluate.py).
DK : a*raw^b per position refit (fit_sigma_recalibration.fit_position, 10 bins) on the 88-slate production-faithful
     rebuild with the NEW variance artifact, seasons 2021-2025, 2023-2025 rows double-weighted; DST entry kept as-is.
FD : no FD actuals here -> FD curve kept, `a` and sigma_fit_range rescaled by the measured per-position raw-sigma
     shrink (new/old raw MC sd, DK frames) so FD sigma is unchanged to first order.
Also prints the QR p90 = a + b*final per position (2021-25 fit, 2023+ double-weighted) -- NOT shipped (no consumer).
    python analysis/proj_variance/fit_recal_prod.py [--tag vol2021] [--write]
"""
import argparse, json, os, sys, copy
from datetime import date
import numpy as np, pandas as pd
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(R, "scripts")); sys.path.insert(0, os.path.dirname(__file__))
import evaluate as ev
OUT = os.path.join(R, "data/fc_history/derived/proj_variance")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", default="vol2021"); ap.add_argument("--base", default="cur")
    ap.add_argument("--write", action="store_true"); a = ap.parse_args()
    X = pd.read_parquet(os.path.join(OUT, f"frame_{a.tag}.parquet")); B = pd.read_parquet(os.path.join(OUT, f"frame_{a.base}.parquet"))
    tr = X[(X.season >= 2021) & (X.season <= 2025)]
    tr = pd.concat([tr, tr[tr.season >= 2023]])
    fits = ev.fit_recal(tr)
    old = json.load(open(os.path.join(R, "data/sigma_recalibration_dk.json")))
    new = copy.deepcopy(old)
    for p, e in fits.items():
        new["positions"][p] = e
        print(f"DK {p}: a {old['positions'][p]['a']:.4f} -> {e['a']:.4f}  b {old['positions'][p]['b']:.4f} -> {e['b']:.4f}  r2 {e['loglog_r2']:.3f}")
    new.update(fit_date=date.today().isoformat(), seasons=list(range(2021, 2026)), n_rows=int(len(tr)))
    new["notes"] = old["notes"] + (" 2026-09-26 REFIT (QB/RB/WR/TE; DST unchanged) against the net-of-latent statline_variance.json "
        "(yards double-count fix), on the 88-slate production-faithful DK main rebuild 2021-2025 with 2023-2025 rows double-weighted. "
        "Validation: analysis/proj_variance/. Previous artifact: data/sigma_recalibration_dk.json.bak-2026-09-26.")
    # measured raw-sigma shrink per position (same player-slates)
    k = ["season", "week", "player_id"]
    m = B[k + ["position", "pts_sd"]].merge(X[k + ["pts_sd"]], on=k, suffixes=("_o", "_n"))
    m = m[(m.pts_sd_o > 0) & (m.position != "DST")]
    ratio = (m.pts_sd_n / m.pts_sd_o).groupby(m.position).median()
    print("raw MC sd new/old median by position:", ratio.round(4).to_dict())
    fd_old = json.load(open(os.path.join(R, "data/sigma_recalibration_fd.json")))
    fd = copy.deepcopy(fd_old)
    for p, r in ratio.items():
        if p in fd["positions"]:
            e = fd["positions"][p]; e["a_before_2026_09_26"] = e["a"]
            e["a"] = round(e["a"] / r ** e["b"], 6)
            e["sigma_fit_range"] = [round(v * r, 4) for v in e["sigma_fit_range"]]
            print(f"FD {p}: a {e['a_before_2026_09_26']:.4f} -> {e['a']:.4f} (raw shrink {r:.3f}, b {e['b']:.3f})")
    fd["notes"] = fd_old["notes"] + (" 2026-09-26: `a` and sigma_fit_range rescaled by the measured raw-MC-sd shrink of the net-of-latent "
        "statline_variance.json so FD sigma is unchanged to first order (no FD refit; no FD actuals). Previous: *.bak-2026-09-26.")
    # QR p90 (report only)
    for p in ["QB", "RB", "WR", "TE"]:
        g = tr[tr.played & (tr.position == p)]
        c = ev.qr(g.final_projection.values, g.act.values, .9)
        print(f"QR p90 {p}: a {c[0]:+.4f} b {c[1]:.4f}")
    # effect on DK production sigma (2023+, same player-slates)
    S = X.copy(); S["sig_new"] = ev.apply_recal(S, new["positions"])
    e = B[k + ["position", "sigma"]].merge(S[k + ["sig_new"]], on=k); e = e[e.sigma > 0]
    print("DK sigma new/old (prod) median by position:", (e.sig_new / e.sigma).groupby(e.position).median().round(3).to_dict())
    if a.write:
        for f, obj in [("sigma_recalibration_dk.json", new), ("sigma_recalibration_fd.json", fd)]:
            json.dump(obj, open(os.path.join(R, "data", f), "w"), indent=1)
            print("wrote data/" + f)


if __name__ == "__main__":
    main()
