"""Weekly projection/ownership accuracy tracker (standing post-slate cadence; WK4_POSTMORTEM_CHECKLIST item 3).

Flags drift for a human to look at. It never changes a projection, a config, or anything in output/ --
parallel in spirit to scripts/grade_construction_week.py (item 2), which does the same thing for construction
rules. Run it after each week's DK contest results are logged, read the report, decide by hand whether a
PERSISTENT flag is worth its own postmortem item. Nothing here auto-applies a fix.

Why a tracker and not an automatic recurring refit: analysis/recal_vs_spotadjust/RESULTS.md (2026-10-05) found
that every fix which mattered in Wk1-4 was a bug, a static bias already visible across all 5 years of FC
history, or a missing mechanism -- never a coefficient that drifted week to week and needed in-season data to
spot. Walk-forward tests there showed weekly coefficient refits for DST, the RB/WR/TE stack, and the ownership
model either do nothing (DST: in-season data gets ~0 optimal weight) or actively hurt (ownership: weekly recal
makes chalk sizing worse; stack: window-refit coefficients bounce on noise). A tracker that flags the same
drift a human would eventually find, on the same week or sooner, was the piece worth shipping.

What it does:
  - Auto-discovers every played slate from data/contest_results/dk_*_full.csv (classic + showdown), matching
    scripts/grade_construction_week.py's filename convention. No per-week hardcoding needed.
  - For each slate, reads output/final_projections_dk_<sid>.csv (current committed version -- same convention
    as grade_construction_week.py) and merges it against the contest's %Drafted/FPTS table by normalized name
    (+ roster role for showdown CPT/FLEX), same matching rule as analysis/wk4_postmortem/grade_wk4.py.
  - Builds one long player-level frame across every week played so far this season.
  - MODEL-VERSION WINDOW: finds the most recent commit date among the governing config files (below). Any
    slate whose final_projections file was last committed before that date is still shown per-week, but
    excluded from the season-to-date PERSISTENT trend calc -- otherwise a bias that a fix already shipped for
    keeps re-raising the same flag. Printed explicitly so you can see which weeks are "current era."
  - Flags, using the thresholds fit in analysis/recal_vs_spotadjust/ (grade_accuracy_week_proto.py):
      PERSISTENT  current-era season-to-date |bias| >= MATERIAL and |z| >= 2.5, >= 2 weeks, same sign in
                  >= 2/3 of weeks -- the "real drift" signature (this is what the DST v2 fix looked like).
      WEEK        this week alone is >= 3 SD out -- worth a look, not a fix by itself.

Usage (from repo root):
  python scripts/grade_accuracy_week.py --week 4
  python scripts/grade_accuracy_week.py --week 4 --through 4   # pool season-to-date only through week 4

Writes report.txt + segments.csv + players.csv to analysis/weekly_accuracy_review/out/wk<N>/ (gitignored).

Caveat: this reads output/final_projections_dk_<sid>.csv as currently committed, not a git-show-at-lock
snapshot -- if a slate's file was touched again after lock (see MULTI_SESSION_CONCURRENCY_GAP.md), this grades
whatever is committed now. Fine for a flags-only diagnostic; re-derive from git history if a flagged number
needs to be load-bearing for a real decision.
"""
import argparse
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CR = ROOT / "data" / "contest_results"
OUT_BASE = ROOT / "analysis" / "weekly_accuracy_review" / "out"
FN = re.compile(r"^dk_(classic|showdown)_wk(\d+)_(.+?)_(\d{2}[A-Za-z]{3}\d{4})(?:_(mme|se3max))?_full\.csv$")

MATERIAL = {"proj": 0.75, "own": 1.5}  # DK pts / ownership pts; below this it would not move a lineup
Z_PERSIST, Z_WEEK = 2.5, 3.0

# Governing config files: if one of these changed more recently than a slate's projections were built,
# that slate reflects an old model version and is excluded from the current-era trend calc.
GOVERNING_CONFIGS = [
    "data/projection_stack_dk.json",
    "data/dst_recal_v2.json",
    "data/qb_recal_config.json",
    "data/ownership_model_dk.json",
    "data/ownership_model_dk_ffc.json",
    "data/ownership_model_showdown_dk.json",
    "data/sigma_recalibration_dk.json",
]


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def last_commit_date(rel_path):
    out = git("log", "-1", "--format=%cI", "--", rel_path)
    return pd.Timestamp(out) if out else None


def norm(s):
    s = str(s).lower()
    s = re.sub(r"[.'’]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(s.split())


def discover_slates():
    """One row per played slate, preferring se3max > mme > plain when a slate has more than one contest
    export (same projections, just graded against one contest type to avoid double-weighting a slate)."""
    cands = {}
    for f in sorted(CR.glob("dk_*_full.csv")):
        m = FN.match(f.name)
        if not m:
            continue
        fmt, week, label, date, variant = m.groups()
        sid = f"dk_{fmt}_wk{week}_{label}_{date}"
        rank = {"se3max": 0, "mme": 1, None: 2}[variant]
        if sid not in cands or rank < cands[sid][0]:
            cands[sid] = (rank, f, fmt, int(week), label, date)
    rows = [dict(sid=sid, file=f, fmt=fmt, week=week, label=label, date=date)
            for sid, (rank, f, fmt, week, label, date) in cands.items()]
    return sorted(rows, key=lambda r: (r["week"], r["sid"]))


def actual_table(f, fmt):
    d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
    t = d[["Player", "Roster Position", "%Drafted", "FPTS"]].dropna(subset=["Player"]).copy()
    t["own"] = t["%Drafted"].astype(str).str.rstrip("%").astype(float)
    t["k"] = t.Player.map(norm)
    if fmt == "classic":
        g = t.groupby("k").agg(player=("Player", "first"), own=("own", "sum"), fpts=("FPTS", "first")).reset_index()
        g["role"] = ""
    else:
        g = t.groupby(["k", "Roster Position"]).agg(player=("Player", "first"), own=("own", "sum"),
                                                      fpts=("FPTS", "first")).reset_index()
        g = g.rename(columns={"Roster Position": "role"})
    return g


def load_slate(row):
    rel = f"output/final_projections_dk_{row['sid']}.csv"
    p_path = ROOT / rel
    if not p_path.exists():
        return None, None, None
    p = pd.read_csv(p_path)
    p = p[p.position.isin(["QB", "RB", "WR", "TE", "DST"])].copy()
    p["k"] = p.player_name.map(norm)
    # Full-pool model-side ownership sum by position, BEFORE the inner join below drops it -- used by
    # budget() so an undrafted-backup tail (real ownership ~0, genuinely absent from the contest export,
    # not matchable) doesn't make the model total look short. See WK4_POSTMORTEM_CHECKLIST.md Parking Lot
    # ("grade_accuracy_week.py's budget() table reports a phantom QB ownership gap", 2026-10-06).
    full_own_by_pos = (p.groupby("position").estimated_ownership_pct.sum().to_dict()
                        if row["fmt"] == "classic" else None)
    a = actual_table(row["file"], row["fmt"])
    if row["fmt"] == "classic":
        m = a.merge(p.drop_duplicates("k")[["k", "position", "salary", "final_projection",
                                             "estimated_ownership_pct"]], on="k", how="inner")
    else:
        p["role"] = p["roster_role"]
        m = a.merge(p[["k", "role", "position", "salary", "final_projection", "estimated_ownership_pct"]],
                    on=["k", "role"], how="inner")
        m = m[m.role == "FLEX"].copy()  # grade points/ownership on the FLEX scale; CPT is a multiplier of it
    m["sid"] = row["sid"]
    m["week"] = row["week"]
    m["fmt"] = row["fmt"]
    m["slate"] = f"{row['label']}_{row['date']}"
    return m, last_commit_date(rel), full_own_by_pos


def build_frame(through_week):
    rows, proj_dates, full_own = [], {}, {}
    for row in discover_slates():
        if row["week"] > through_week:
            continue
        m, pdate, fo = load_slate(row)
        if m is None:
            print(f"skip {row['sid']} (no final_projections file)")
            continue
        rows.append(m)
        proj_dates[row["sid"]] = pdate
        if fo is not None:
            full_own[row["sid"]] = fo
    if not rows:
        raise SystemExit("No played slates with both a contest export and a final_projections file found.")
    F = pd.concat(rows, ignore_index=True)
    F = F[F.final_projection.notna()].copy()
    return F, proj_dates, full_own


def tier(r):
    if r.position in ("DST", "K"):
        return r.position
    if r.salary >= 7000:
        return f"{r.position} $7k+"
    if r.salary < 4500:
        return f"{r.position} <$4.5k"
    return f"{r.position} mid"


def current_era(F, proj_dates):
    """Mark which rows were built under the config version currently live. If NOTHING graded so far in a
    given FORMAT (classic vs showdown) was built under it (e.g. only a showdown file got rebuilt right after
    a fix, as happened 2026-10-05 when only ATL/NO was rebuilt and classic wk4 wasn't touched), fall back to
    treating that format's weeks as current -- an empty trend table for that format is worse than one that
    includes a stale week, and a later run will have a real current-era week to anchor on. The fallback is
    per-format, not global: one format having a current-era row must not hide the other format's rows."""
    changed = [d for d in (last_commit_date(c) for c in GOVERNING_CONFIGS) if d is not None]
    if not changed:
        return F.assign(current_era=True), None, {}
    era_start = max(changed)
    F = F.copy()
    F["current_era"] = F.sid.map(lambda s: (proj_dates.get(s) is not None) and (proj_dates[s] >= era_start))
    fell_back = {}
    for fmt, idx in F.groupby("fmt").groups.items():
        if F.loc[idx, "current_era"].any():
            fell_back[fmt] = False
        else:
            F.loc[idx, "current_era"] = True
            fell_back[fmt] = True
    return F, era_start, fell_back


def seg_stats(d, pcol, acol):
    e = d[pcol] - d[acol]
    n = len(d)
    if n < 8:
        return None
    return dict(n=n, bias=e.mean(), mae=e.abs().mean(), sd=e.std(ddof=1),
                corr=np.corrcoef(d[pcol], d[acol])[0, 1] if d[pcol].std() > 0 else np.nan,
                wk_signs=d.groupby("week").apply(lambda g: np.sign((g[pcol] - g[acol]).mean())).tolist())


def report(F, week, kind, pcol, acol, segs):
    rows = []
    trend_pool = F[F.current_era] if "current_era" in F.columns else F
    trend_groups = dict(trend_pool.groupby(segs).__iter__())
    for seg_key, d in F.groupby(segs):
        d_trend = trend_groups.get(seg_key, d.iloc[0:0])
        seg = seg_key if isinstance(seg_key, str) else " / ".join(map(str, seg_key))
        sd = seg_stats(d_trend[d_trend.week <= week], pcol, acol)
        wk = seg_stats(d[d.week == week], pcol, acol)
        if sd is None:
            continue
        nwk = len(sd["wk_signs"])
        z = sd["bias"] / (sd["sd"] / np.sqrt(sd["n"])) if sd["sd"] > 0 else 0.0
        same = max(sd["wk_signs"].count(1.0), sd["wk_signs"].count(-1.0)) / nwk
        flag = ""
        if nwk >= 2 and abs(sd["bias"]) >= MATERIAL[kind] and abs(z) >= Z_PERSIST and same >= 2 / 3:
            flag = "PERSISTENT"
        elif wk is not None and abs(wk["bias"]) >= MATERIAL[kind] and \
                abs(wk["bias"] / (wk["sd"] / np.sqrt(wk["n"]))) >= Z_WEEK:
            flag = "WEEK"
        rows.append(dict(segment=seg, n_trend=sd["n"], weeks_trend=nwk, bias_trend=round(sd["bias"], 2),
                         z_trend=round(z, 1), same_sign=f"{same:.0%}",
                         bias_wk=round(wk["bias"], 2) if wk else np.nan,
                         mae_wk=round(wk["mae"], 2) if wk else np.nan,
                         corr_wk=round(wk["corr"], 3) if wk else np.nan, flag=flag))
    return pd.DataFrame(rows)


def salary_edge(F, week):
    out = []
    for (w, fmt), d in F[F.week <= week].groupby(["week", "fmt"]):
        if len(d) < 8 or d.salary.std() == 0:
            continue
        sal_fit = np.polyval(np.polyfit(d.salary, d.fpts, 1), d.salary)
        out.append(dict(week=w, fmt=fmt, corr_ours=np.corrcoef(d.final_projection, d.fpts)[0, 1],
                        corr_salary=np.corrcoef(sal_fit, d.fpts)[0, 1]))
    o = pd.DataFrame(out)
    if len(o):
        o["edge"] = o.corr_ours - o.corr_salary
    return o.round(3)


def chalk(F, week):
    out = []
    for (w, slate), d in F[(F.week <= week) & (F.fmt == "classic")].groupby(["week", "slate"]):
        top = d[d.own >= 20]
        if not len(top):
            continue
        top10 = set(d.nlargest(10, "own").player)
        ours10 = set(d.nlargest(10, "estimated_ownership_pct").player)
        out.append(dict(week=w, slate=slate, n_chalk=len(top), real_mean=top.own.mean(),
                        ours_mean=top.estimated_ownership_pct.mean(), top10_overlap=len(top10 & ours10) / 10))
    return pd.DataFrame(out).round(2)


def budget(F, week, full_own):
    """Real side: summed from the matched (inner-joined) rows -- the real contest export omits players who
    drew literal 0% ownership, so virtually every nonzero-owned real player already has a match and this is
    already the true real total. Model side: summed from the FULL per-slate output file (full_own), not the
    matched rows -- our model legitimately spreads a few points per slate across undrafted backups that have
    no real-side counterpart to match against, and summing only the matched rows made the model total look
    short by exactly that undrafted-backup mass (see WK4_POSTMORTEM_CHECKLIST.md Parking Lot, 2026-10-06)."""
    d = F[(F.week == week) & (F.fmt == "classic")]
    b = d.groupby(["slate", "sid", "position"])["own"].sum().reset_index()
    b["estimated_ownership_pct"] = [full_own.get(sid, {}).get(pos, np.nan) for sid, pos in zip(b.sid, b.position)]
    b["gap"] = b.estimated_ownership_pct - b.own
    return b.drop(columns="sid").round(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True, help="grade this week's slates")
    ap.add_argument("--through", type=int, default=None, help="pool season-to-date only through this week "
                                                                "(default: --week)")
    a = ap.parse_args()
    through = a.through or a.week

    F, proj_dates, full_own = build_frame(through)
    F, era_start, fell_back = current_era(F, proj_dates)
    F["tier"] = F.apply(tier, axis=1)
    C = F[F.fmt == "classic"]
    O = C[C.estimated_ownership_pct.notna() & C.own.notna()]

    out_dir = OUT_BASE / f"wk{a.week}"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 200)

    lines = []
    def p(s=""):
        print(s)
        lines.append(str(s))

    p(f"##### Accuracy tracker -- 2026 through week {a.week} (current output/ vs real DK contest results) #####")
    if era_start is not None:
        p(f"Governing config last changed: {era_start.date()}.")
        for fmt in sorted(F.fmt.unique()):
            d = F[F.fmt == fmt]
            if fell_back.get(fmt):
                p(f"  {fmt}: no graded {fmt} week was built after that, so falling back to treating all "
                  f"{fmt} weeks as current era this run. A real post-fix {fmt} week will anchor the window "
                  f"starting next time this is run.")
            else:
                current_weeks = sorted(d[d.current_era].week.unique().tolist())
                stale_weeks = sorted(d[~d.current_era].week.unique().tolist())
                p(f"  {fmt}: current-era weeks (used for PERSISTENT trend): {current_weeks}. "
                  f"Pre-current-model weeks (shown per-week only): {stale_weeks or 'none'}.")
    p("\n== projections, classic, by position ==")
    p(report(C, a.week, "proj", "final_projection", "fpts", "position").to_string(index=False))
    p("\n== projections, classic, by position x salary tier ==")
    p(report(C, a.week, "proj", "final_projection", "fpts", "tier").to_string(index=False))
    sd_f = F[F.fmt == "showdown"]
    if len(sd_f):
        p("\n== projections, showdown (FLEX scale), by position ==")
        p(report(sd_f, a.week, "proj", "final_projection", "fpts", "position").to_string(index=False))
    p("\n== projection edge over salary-only baseline (corr) ==")
    p(salary_edge(F, a.week).to_string(index=False))
    if len(O):
        p("\n== ownership, classic, by position x salary tier ==")
        p(report(O, a.week, "own", "estimated_ownership_pct", "own", "tier").to_string(index=False))
        p("\n== chalk sizing (classic, real own >= 20%) and top-10 overlap ==")
        p(chalk(O, a.week).to_string(index=False))
        p(f"\n== week {a.week} ownership budget by position (sum of ours vs real, classic) ==")
        p(budget(O, a.week, full_own).to_string(index=False))
    p("\nFlags are a trigger to open a postmortem item, not a diagnosis. Any fix gets tested on 2021-25 "
      "held-out history before shipping (see SUBAGENT_BRIEF.md). This tool changes nothing on its own.")

    (out_dir / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    F.to_csv(out_dir / "players.csv", index=False)
    print(f"\nWrote {out_dir / 'report.txt'} and {out_dir / 'players.csv'}")


if __name__ == "__main__":
    main()
