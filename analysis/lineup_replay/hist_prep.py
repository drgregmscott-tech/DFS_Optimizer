"""History lineup replay, step 1 (FC-DERIVED OUTPUTS -- DO NOT COMMIT builds/hist or hist_meta/).

For each 2022-25 DK classic main slate that has BOTH our regenerated pre-game projections
(data/fc_history/derived/ourproj/proj_{season}_wk{week}.csv, analysis/ownership_fc_refit/run_ourproj.py) AND a real
FC Lineup Study SE_dollar contest (data/fc_history/lineup_study/{season}wk{week}_SE_dollar_*.json.gz), writes three
optimizer-ready pools restricted to the contest's players:
  old : our history projection as generated (pre early-blend, pre QB recal)
  new : old + early-season salary blend (weeks 1,2,7+) + QB recal (wk3+), using the production functions/configs
        from scripts/build_projections_statline.py (imported, not edited)
  fc  : FC's own projection (fc_proj from data/fc_history/derived/fc_master_mapped.csv, single_entry main export) -- the commercial model, same pool, same optimizer
Ownership columns are ours in all three (SE presets use lambda 0, so ownership does not enter the solve).
Also writes hist_meta/{tag}.npz: the real field's points (desc), cash_amt by rank, entry fee, min-cash score, and
FC PlayerId -> actual DK points, for grading. Contests with broken FC projections (>25% of $5K+ skill players at 0 in FC's projection export fc_master_mapped)
are skipped entirely so all three arms run on the same slates.
"""
import glob
import gzip
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_projections_statline as bps  # noqa: E402

LS = REPO / "data" / "fc_history" / "lineup_study"
OP = REPO / "data" / "fc_history" / "derived" / "ourproj"
TEAM_FIX = {"JAC": "JAX", "LAR": "LA", "WSH": "WAS", "LVR": "LV"}


def norm(s):
    s = str(s).lower()
    s = re.sub(r"[.'’]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(s.split())


def main():
    (HERE / "hist_meta").mkdir(exist_ok=True)
    for v in ("old", "new", "fc"):
        (HERE / "builds" / "hist" / v).mkdir(parents=True, exist_ok=True)
    log = []
    global FCM
    FCM = pd.read_csv(REPO / "data/fc_history/derived/fc_master_mapped.csv", low_memory=False, dtype={"player_id": str})
    FCM = FCM[(FCM.contest == "single_entry") & (FCM.slate_kind == "classic") & (FCM.site == "dk")]
    for f in sorted(glob.glob(str(LS / "202[2-5]wk*_SE_dollar_*.json.gz"))):
        m = re.match(r"(\d{4})wk(\d+)_", Path(f).name)
        season, week = int(m.group(1)), int(m.group(2))
        opf = OP / f"proj_{season}_wk{week}.csv"
        if not opf.exists():
            continue
        d = json.load(gzip.open(f))
        P = pd.DataFrame(d["players"].values()).drop_duplicates("PlayerId")
        P["Team"] = P.Team.map(lambda t: TEAM_FIX.get(t, t))
        o = pd.read_csv(opf, dtype={"player_id": str, "site_player_id": str})
        o["k"] = o.player_name.map(norm)
        P["k"] = P.PlayerName.map(norm)
        # match: DST by team; skill by (name, salary), then (name, team)
        pd_ = P[P.SitePos == "DST"].set_index("Team").PlayerId.to_dict()
        ps = P[P.SitePos != "DST"]
        by_ns = {(k, s): i for k, s, i in zip(ps.k, ps.Salary, ps.PlayerId)}
        by_nt = {(k, t): i for k, t, i in zip(ps.k, ps.Team, ps.PlayerId)}
        fid = []
        for k, s, t, pos in zip(o.k, o.salary, o.team, o.position):
            fid.append(pd_.get(t) if pos == "DST" else by_ns.get((k, s), by_nt.get((k, t))))
        o["fc_pid"] = fid
        o = o[o.fc_pid.notna()].copy()
        o["fc_pid"] = o.fc_pid.astype(int)
        o = o.drop_duplicates("fc_pid")
        fm = FCM[(FCM.season == season) & (FCM.week == week)].drop_duplicates("player_id").set_index("player_id").fc_proj
        o["fc_proj"] = o.player_id.map(fm).fillna(0.0).clip(lower=0)
        sk = o[(o.position != "DST") & (o.salary >= 5000)]
        bad = (sk.fc_proj <= 0.05).mean()
        # coverage of the field's rostered players (by ownership) that we matched
        own = P.set_index("PlayerId").own.astype(float)
        cov = own[own.index.isin(o.fc_pid)].sum() / own.sum()
        tag = f"h{season}w{week:02d}"
        log.append(dict(tag=tag, n_pool=len(o), fc_zero_frac=round(bad, 3), own_coverage=round(cov, 3)))
        if bad > 0.25 or cov < 0.97:
            log[-1]["skipped"] = True
            continue
        # player_name := FC PlayerId string so lineups carry the grading key
        o["player_name"] = o.player_name + "#" + o.fc_pid.astype(str)
        o["no_real_game_this_week"] = False
        # Inactives proxy (history has no pre-lock status for our engine): zero our projection where FC's pre-lock
        # export projects 0 (FC's OUT/inactive), same as analysis/proj_lineup_level's "zFC" filter. Applied to old+new.
        o.loc[(o.fc_proj <= 0.05) & (o.position != "DST"), "final_projection"] = 0.0
        base = o.drop(columns=["k"])
        sid = f"hist_{tag}"
        base.drop(columns=["fc_pid", "fc_proj", "no_real_game_this_week"]).to_csv(
            HERE / "builds" / "hist" / "old" / f"final_projections_dk_{sid}.csv", index=False)
        n = base.copy()
        n = bps._apply_early_season_blend(n, week)
        n = bps._apply_qb_recal(n, week)
        n.loc[(n.fc_proj <= 0.05) & (n.position != "DST"), "final_projection"] = 0.0  # status apply runs after the build
        n.drop(columns=["fc_pid", "fc_proj", "no_real_game_this_week"]).to_csv(
            HERE / "builds" / "hist" / "new" / f"final_projections_dk_{sid}.csv", index=False)
        fcv = base.copy()
        fcv["final_projection"] = fcv.fc_proj
        fcv.drop(columns=["fc_pid", "fc_proj", "no_real_game_this_week"]).to_csv(
            HERE / "builds" / "hist" / "fc" / f"final_projections_dk_{sid}.csv", index=False)
        rows = d["rows"]
        pts = np.array([r[3] for r in rows], float)
        cash = np.array([r[4] or 0 for r in rows], float)
        order = np.argsort(-pts, kind="stable")
        lr = d["list_row"]
        fp = P.set_index("PlayerId").fantasy_points.astype(float)
        np.savez(HERE / "hist_meta" / f"{tag}.npz", pts=pts[order], cash=cash[order] / 100.0 if lr["cost"] and cash.max() > lr["prizepool"] * 2 else cash[order],
                 cost=float(lr["cost"]), mincash=float(lr.get("mincash_score") or 0), fp_ids=fp.index.values, fp=fp.values, own=P.set_index("PlayerId").own.astype(float).reindex(fp.index).values,
                 n_entrants=float(lr.get("total_entrants") or len(rows)))
    L = pd.DataFrame(log)
    L.to_csv(HERE / "hist_meta" / "prep_log.csv", index=False)
    print(L.to_string())
    print("kept", int((~L.get("skipped", pd.Series(False, index=L.index)).fillna(False).astype(bool)).sum()))


if __name__ == "__main__":
    main()
