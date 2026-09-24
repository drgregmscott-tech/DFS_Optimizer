"""Score multi-season backtest arms against real DK points.

Actuals: data/rotoguru_actuals_dk_{season}.csv (real DK scoring, every pool
player, DNP = 0), joined on RotoGuru gid == salary ID (site_player_id).
Cross-check: r = .998 vs nflverse PPR + DK bonuses on 2019 wk6.

Populations
  played : skill player has an nflverse weekly_stats row that week (i.e. was
           active and recorded a stat), or is a DST. Mimics production, where
           OUT/inactive players are zeroed by status news the backtest lacks.
  all    : every pool player with final_projection > 0 (inactives score 0).
Both require final_projection > 0.

Metrics (per season x position and pooled): n, bias (proj - actual), MAE,
RMSE, Pearson, within-slate x position Spearman (mean over season-week x
position groups), top-N (mean actual of the projection top-N per
week x position; N = QB 12, RB 24, WR 36, TE 12, DST 12) and top-N hit rate
(share of projection top-N inside actual top-N), p10/p90 coverage.

Out-of-sample labels per season (shipped artifacts):
  volume_prior_dk.json, statline_variance.json : fit 2014-2021 -> in-sample everywhere
  projection_stack_dk.json                    : fit 2020-2021 -> OOS 2014-2019
  sigma_recalibration_dk.json, dst_model.json : fit 2014-2017 -> OOS 2018-2021

Usage:
  python analysis/backtest_multi/evaluate.py --arms baseline matchup_restored
  (first arm is the reference for paired week-clustered bootstrap deltas)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
TOPN = {"QB": 12, "RB": 24, "WR": 36, "TE": 12, "DST": 12}
SKILL = ["QB", "RB", "WR", "TE"]


def oos_label(season: int) -> str:
    stack = "stackOOS" if season <= 2019 else "stackIS"
    sig = "sigmaOOS" if season >= 2018 else "sigmaIS"
    return f"{stack},{sig},priorIS,varIS"


_ACT, _PLAYED = {}, {}


def actuals(season: int) -> pd.DataFrame:
    if season not in _ACT:
        a = pd.read_csv(REPO / "data" / f"rotoguru_actuals_dk_{season}.csv")
        a["site_player_id"] = a["gid"].astype(str)
        _ACT[season] = a[["week", "site_player_id", "actual_points"]].drop_duplicates(
            ["week", "site_player_id"])
        ws = pd.read_parquet(REPO / "data" / f"weekly_stats_{season}.parquet",
                             columns=["player_id", "week", "season_type"])
        ws = ws[ws["season_type"] == "REG"]
        _PLAYED[season] = set(zip(ws["player_id"], ws["week"]))
    return _ACT[season]


def load_arm(arm: str) -> pd.DataFrame:
    files = sorted((OUT / "proj" / arm).glob(f"proj_{arm}_dk_*_wk*.csv"))
    if not files:
        raise SystemExit(f"no projections for arm {arm}")
    frames = []
    for f in files:
        d = pd.read_csv(f, dtype={"site_player_id": str, "player_id": str},
                        usecols=lambda c: c in {
                            "season", "week", "player_id", "player_name", "position", "team",
                            "salary", "site_player_id", "final_projection", "engine_projection",
                            "statline_p10", "statline_p90", "sigma", "stack_delta"}
                        or c.startswith("proj_"))
        # Data defect: RotoGuru salary matching can give two pool rows the same
        # gsis id (2014 wk2: Alex Smith QB KC + TE CIN), and the build then
        # emits cross-multiplied duplicate rows. Drop every row of such an id.
        dup = d.duplicated(["site_player_id"], keep=False) | d.duplicated(["player_id", "position"], keep=False)
        if dup.any():
            print(f"NOTE {f.name}: dropped {int(dup.sum())} rows with duplicated ids "
                  f"({sorted(d.loc[dup, 'player_name'].unique())})")
            d = d[~dup]
        season = int(d["season"].iloc[0])
        d = d.merge(actuals(season), on=["week", "site_player_id"], how="left")
        d["actual_points"] = d["actual_points"].fillna(0.0)
        played = _PLAYED[season]
        d["played"] = [(p, w) in played for p, w in zip(d["player_id"], d["week"])]
        d.loc[d["position"] == "DST", "played"] = True
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["arm"] = arm
    return df


def metrics(d: pd.DataFrame) -> dict:
    e = d["final_projection"] - d["actual_points"]
    out = {"n": len(d), "weeks": d.groupby(["season", "week"]).ngroups,
           "bias": e.mean(), "MAE": e.abs().mean(), "RMSE": float(np.sqrt((e ** 2).mean())),
           "pearson": d["final_projection"].corr(d["actual_points"])}
    sp, tn, hit = [], [], []
    for (_, _, pos), g in d.groupby(["season", "week", "position"]):
        if len(g) >= 5:
            sp.append(g["final_projection"].corr(g["actual_points"], method="spearman"))
        n = TOPN.get(pos, 12)
        if len(g) >= 2 * n:
            top = g.nlargest(n, "final_projection")
            tn.append(top["actual_points"].mean())
            hit.append(top.index.isin(g.nlargest(n, "actual_points").index).mean())
    out["spearman_wxp"] = float(np.nanmean(sp)) if sp else np.nan
    out["topN_actual"] = float(np.mean(tn)) if tn else np.nan
    out["topN_hit"] = float(np.mean(hit)) if hit else np.nan
    if "statline_p10" in d and d["statline_p10"].notna().any():
        q = d[d["statline_p10"].notna() & d["statline_p90"].notna()]
        out["below_p10"] = (q["actual_points"] < q["statline_p10"]).mean()
        out["above_p90"] = (q["actual_points"] > q["statline_p90"]).mean()
    return out


def table(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    rows = []
    for k, g in df.groupby(by):
        k = k if isinstance(k, tuple) else (k,)
        rows.append({**dict(zip(by, k)), **metrics(g)})
    return pd.DataFrame(rows)


def paired_delta(ref: pd.DataFrame, alt: pd.DataFrame, pos=None, seasons=None, B=2000, seed=7):
    """alt - ref for MAE, Pearson (pooled) and within-slate Spearman, on the
    intersection of rows; 95% CI from a bootstrap over season-weeks."""
    key = ["season", "week", "site_player_id"]
    m = ref.merge(alt[key + ["final_projection"]], on=key, suffixes=("", "_alt"))
    m = m[(m["final_projection"] > 0) & (m["final_projection_alt"] > 0)]
    if pos:
        m = m[m["position"].isin(pos)]
    if seasons:
        m = m[m["season"].isin(seasons)]
    m["ae_ref"] = (m["final_projection"] - m["actual_points"]).abs()
    m["ae_alt"] = (m["final_projection_alt"] - m["actual_points"]).abs()
    wk = []
    for (s, w), g in m.groupby(["season", "week"]):
        sp_r, sp_a = [], []
        for _, gp in g.groupby("position"):
            if len(gp) >= 5:
                sp_r.append(gp["final_projection"].corr(gp["actual_points"], method="spearman"))
                sp_a.append(gp["final_projection_alt"].corr(gp["actual_points"], method="spearman"))
        wk.append({"n": len(g), "dae": (g["ae_alt"] - g["ae_ref"]).sum(),
                   "dsp": np.nanmean(np.array(sp_a) - np.array(sp_r)) if sp_r else np.nan})
    wk = pd.DataFrame(wk)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(wk), size=(B, len(wk)))
    dmae_b = wk["dae"].to_numpy()[idx].sum(1) / wk["n"].to_numpy()[idx].sum(1)
    dsp_b = np.nanmean(wk["dsp"].to_numpy()[idx], axis=1)
    return {"n": len(m), "weeks": len(wk),
            "dMAE": wk["dae"].sum() / wk["n"].sum(),
            "dMAE_ci": (np.percentile(dmae_b, 2.5), np.percentile(dmae_b, 97.5)),
            "dPearson": m["final_projection_alt"].corr(m["actual_points"]) - m["final_projection"].corr(m["actual_points"]),
            "dSpearman_wxp": np.nanmean(wk["dsp"]),
            "dSpearman_ci": (np.percentile(dsp_b, 2.5), np.percentile(dsp_b, 97.5)),
            "dBias": (m["final_projection_alt"] - m["final_projection"]).mean()}


def fmt(t: pd.DataFrame) -> str:
    return t.to_string(index=False, float_format=lambda x: f"{x:.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=["baseline"])
    ap.add_argument("--pop", default="played", choices=["played", "all"])
    a = ap.parse_args()
    lines = []
    arms = {}
    for arm in a.arms:
        df = load_arm(arm)
        arms[arm] = df
        ev = df[df["final_projection"] > 0]
        if a.pop == "played":
            ev = ev[ev["played"]]
        skill = ev[ev["position"].isin(SKILL)]
        lines.append(f"\n===== arm={arm} pop={a.pop} =====")
        lines.append("-- skill pooled --\n" + fmt(table(skill.assign(all="skill"), ["all"])))
        lines.append("-- by position --\n" + fmt(table(ev, ["position"])))
        bs = table(skill, ["season"])
        bs["oos"] = bs["season"].map(oos_label)
        lines.append("-- skill by season --\n" + fmt(bs))
        lines.append("-- skill, stack-OOS 2014-2019 vs stack-IS 2020-2021 --\n" + fmt(
            table(skill.assign(window=np.where(skill["season"] <= 2019, "2014-19", "2020-21")), ["window"])))
        lines.append("-- by season x position --\n" + fmt(table(ev, ["season", "position"])))
        table(ev, ["season", "position"]).to_csv(OUT / f"metrics_{arm}_{a.pop}.csv", index=False)
    ref = a.arms[0]
    for arm in a.arms[1:]:
        r = arms[ref]
        al = arms[arm]
        if a.pop == "played":
            r = r[r["played"]]
        lines.append(f"\n===== paired {arm} minus {ref} (pop={a.pop}; negative dMAE = {arm} better) =====")
        for label, pos, seas in [("skill all", SKILL, None), ("QB", ["QB"], None), ("RB", ["RB"], None),
                                 ("WR", ["WR"], None), ("TE", ["TE"], None), ("DST", ["DST"], None),
                                 ("skill 2014-19", SKILL, list(range(2014, 2020))),
                                 ("skill 2020-21", SKILL, [2020, 2021])]:
            d = paired_delta(r, al, pos, seas)
            lines.append(f"{label:14s} n={d['n']:6d} wks={d['weeks']:3d} dMAE={d['dMAE']:+.3f} "
                         f"[{d['dMAE_ci'][0]:+.3f},{d['dMAE_ci'][1]:+.3f}] dPearson={d['dPearson']:+.4f} "
                         f"dSpearman_wxp={d['dSpearman_wxp']:+.4f} [{d['dSpearman_ci'][0]:+.4f},{d['dSpearman_ci'][1]:+.4f}] "
                         f"dProj={d['dBias']:+.3f}")
        for s in sorted(r["season"].unique()):
            d = paired_delta(r, al, SKILL, [s])
            lines.append(f"  skill {s} n={d['n']:5d} dMAE={d['dMAE']:+.3f} [{d['dMAE_ci'][0]:+.3f},{d['dMAE_ci'][1]:+.3f}] "
                         f"dSpearman_wxp={d['dSpearman_wxp']:+.4f}")
    text = "\n".join(lines)
    (OUT / f"eval_{'_vs_'.join(a.arms)}_{a.pop}.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
