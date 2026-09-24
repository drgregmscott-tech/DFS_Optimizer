"""
prelock_check.py -- READ-ONLY pre-lock sanity report for classic slates.

Reads (never writes) the files the Sunday pipeline produces and prints a
PASS / WARN / FAIL report per slate:

  1  freshness        projections build time vs salary / status / vegas / props /
                      weather / FFC inputs (anything newer than the build = rebuild)
  2  props            snapshot exists, age, whether the build used it (audit file),
                      top movers (>15%) old -> new projection vs the pre-props build
  3  injuries         OUT/Doubtful still projected > 0, Questionable list, status
                      pulls NEWER than the build that change a player's status
  4  QB outliers      starters with pass att > 38, proj < 14 or > 30, model vs
                      public (DFF/WinWithOdds) gaps (moved-QB / Murray check)
  5  DST sanity       projection range, DSTs vs high-implied offenses, cheap-viable list
  6  p10 / darts      calibrated statline_p10 present (DK), dart list under the
                      current vs calibrated p10 (threshold 1.0)
  7  value outliers   cheap high-value and expensive low-value players
  8  ownership        per-position sums vs expected, OUT players still owned, top-10 chalk
  9  vegas / weather  projection implied totals vs latest vegas pull, wind > 15 mph, domes
 10  lock table       per-game kickoff UTC / CDT (late-swap windows)

Usage (from repo root):
    python analysis/prelock/prelock_check.py                       # all wk3 classic slates
    python analysis/prelock/prelock_check.py --slate-id dk_classic_wk3_main_27Sep2026
    python analysis/prelock/prelock_check.py --week 2 --as-of 2026-09-20T16:30:00Z   # replay wk2

Exit code: 2 if any FAIL, 1 if any WARN, else 0.  No network calls, no writes.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "output"
DATA = REPO / "data"
CDT = timedelta(hours=-5)          # US Central Daylight Time (valid through 2026-11-01)

DART_THRESHOLD = 1.0               # data/optimizer_presets.json mme_gpp dart-floor-threshold
MOVER_PCT = 0.15
QB_ATT_MAX, QB_LO, QB_HI = 38.0, 14.0, 30.0
WIND_MPH = 15.0

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


# ---------------------------------------------------------------- helpers
class Report:
    def __init__(self):
        self.counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "INFO": 0}

    def line(self, level, msg):
        self.counts[level] += 1
        print(f"  [{level}] {msg}")

    def table(self, df, indent="      "):
        if df is None or len(df) == 0:
            return
        txt = df.to_string(index=False)
        print("\n".join(indent + ln for ln in txt.splitlines()))


def utc(ts):
    if ts is None or (isinstance(ts, float) and np.isnan(ts)):
        return None
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert("UTC").to_pydatetime()


def fmt(dt):
    if dt is None:
        return "n/a"
    return f"{dt:%a %m-%d %H:%M}Z ({(dt + CDT):%H:%M} CDT)"


def git(*args):
    try:
        r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def file_time(path: Path):
    """Best 'last written' time for a file: local mtime if the working copy is
    modified/untracked, else its last commit time (a git checkout gives every
    file the same mtime, so mtime alone is meaningless for committed files)."""
    if not path.exists():
        return None
    rel = path.relative_to(REPO).as_posix()
    status = git("status", "--porcelain", "--", rel).strip()
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    if status:
        return mtime
    c = git("log", "-1", "--format=%cI", "--", rel).strip()
    return utc(c) if c else mtime


def file_history(path: Path):
    rel = path.relative_to(REPO).as_posix()
    out = []
    for ln in git("log", "--format=%H %cI %s", "--", rel).splitlines():
        sha, ts, *msg = ln.split(" ", 2)
        out.append((sha, utc(ts), msg[0] if msg else ""))
    return out  # newest first


def git_csv(sha, path: Path):
    txt = git("show", f"{sha}:{path.relative_to(REPO).as_posix()}")
    return pd.read_csv(StringIO(txt)) if txt else None


def norm_name(s):
    s = str(s).lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", s)
    return re.sub(r"[^a-z]", "", s)


def load_p10_coefs():
    src = (REPO / "scripts" / "build_projections_statline.py").read_text(encoding="utf-8")
    m = re.search(r"P10_QR_DK\s*=\s*(\{.*?\})\s*\n\s*\n", src, re.S)
    if not m:
        return None
    body = m.group(1)
    coefs = {}
    for pos, a, b in re.findall(r'"(\w+)":\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)', body):
        coefs[pos] = (float(a), float(b))
    return coefs or None


def find_salary(slate_id, week):
    for p in (DATA / "raw_salaries" / f"{slate_id}.csv",
              DATA / "raw_salaries" / "26_27_Season_Salary_Archives" / f"Week_{week}" / f"{slate_id}.csv"):
        if p.exists():
            return p
    return None


def latest_status_file(week, as_of):
    best = None
    for p in OUT.glob(f"player_status_{week}_*.csv"):
        m = re.search(r"_(\d{8}_\d{6})\.csv$", p.name)
        if not m:
            continue
        ts = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        if ts <= as_of and (best is None or ts > best[0]):
            best = (ts, p)
    return best


def latest_vegas_file(week, teams, as_of):
    best = None
    for p in OUT.glob(f"vegas_implied_totals_*wk{week}_*.csv"):
        t = file_time(p)
        if t is None or t > as_of:
            continue
        try:
            v = pd.read_csv(p)
        except Exception:  # noqa: BLE001
            continue
        cover = len(set(v["team"]) & teams) / max(1, len(teams))
        if cover < 0.8:
            continue
        if best is None or t > best[0]:
            best = (t, p, v)
    return best


# ---------------------------------------------------------------- per-slate check
def check_slate(s, as_of, rep: Report, verbose: bool):
    sid, site, week = s["slate_id"], s["site"], int(s["week"])
    lock = utc(s["lock_time_utc"])
    print("=" * 100)
    print(f"{sid}   site={site}  lock={fmt(lock)}  as-of={fmt(as_of)}  "
          f"({(lock - as_of).total_seconds() / 3600:+.1f} h to lock)")
    print("=" * 100)
    proj_path = OUT / f"final_projections_{site}_{sid}.csv"
    if not proj_path.exists():
        rep.line("FAIL", f"no projections file {proj_path.name}")
        return
    df = pd.read_csv(proj_path)
    build_t = file_time(proj_path)
    dk = site == "dk"

    # ---------------- 1 freshness
    print("\n-- 1. Freshness")
    inputs = {}
    sal = find_salary(sid, week)
    inputs["salary"] = file_time(sal) if sal else None
    st = latest_status_file(week, as_of)
    inputs["status pull"] = st[0] if st else None
    teams = set(df["team"].dropna())
    vg = latest_vegas_file(week, teams, as_of)
    inputs["vegas pull"] = vg[0] if vg else None
    props_path = DATA / "props" / f"props_{sid}.csv"
    props_t = None
    if props_path.exists():
        try:
            props_t = utc(datetime.strptime(pd.read_csv(props_path, usecols=["pulled_at"], nrows=1)
                                            ["pulled_at"].iloc[0], "%Y%m%dT%H%M%SZ"))
        except Exception:  # noqa: BLE001
            props_t = file_time(props_path)
    inputs["props pull"] = props_t
    wx_path = DATA / f"weather_{s.get('season', 2026)}_wk{week}.csv"
    wx = pd.read_csv(wx_path) if wx_path.exists() else None
    inputs["weather"] = utc(wx["fetched_utc"].max()) if wx is not None and "fetched_utc" in wx else None
    ffc = DATA / "ownership_public" / f"ffc_dk_{sid}.csv"
    if dk:
        inputs["FFC ownership"] = file_time(ffc) if ffc.exists() else None
    last_msg = (file_history(proj_path) or [(None, None, "uncommitted")])[0][2]
    print(f"      last commit touching it: {last_msg[:90]}")
    if "light_vegas_refresh" in last_msg:
        rep.line("WARN", "latest projections commit came from a light_vegas_refresh (rebuild WITHOUT status apply)")
    print(f"      projections built/committed: {fmt(build_t)}   "
          f"age at as-of: {(as_of - build_t).total_seconds() / 3600:.1f} h")
    newer = []
    for k, t in inputs.items():
        flag = ""
        if t is not None and build_t is not None and t > build_t + timedelta(minutes=2):
            flag = "  <-- NEWER than build"
            newer.append(k)
        print(f"      {k:15s} {fmt(t)}{flag}")
    if build_t and build_t > as_of + timedelta(minutes=2):
        rep.line("INFO", "projections file was (re)built AFTER --as-of (replay of a past slate): freshness "
                         "comparisons below are not meaningful for that week")
    if sal is None:
        rep.line("FAIL", "salary file not found in data/raw_salaries (download from site + ingest_salaries.py)")
    if newer:
        rep.line("WARN", f"inputs newer than the projections build: {', '.join(newer)} -> rebuild "
                         f"(the next full refresh, or local build_projections_statline.py + status_check apply)")
    else:
        rep.line("PASS", "no input is newer than the projections build")
    if build_t and (as_of - build_t) > timedelta(hours=8) and lock > as_of:
        rep.line("WARN", "projections are more than 8 h old")

    # ---------------- 2 props
    print("\n-- 2. Props anchor")
    audit = DATA / "props" / f"audit_{sid}.csv"
    if not props_path.exists():
        if site == "fd":
            rep.line("INFO", "no props for FD: props_auto.py only pulls DK slates -> FD build is ENGINE ONLY "
                             "(compare with the matching DK slate's movers by hand)")
        else:
            rep.line("WARN", f"no props snapshot {props_path.name} (auto-pull happens ~100 min before lock, "
                             f"16:00Z full refresh for a 17:00Z lock) -> build is engine only")
    else:
        age_build = (build_t - props_t).total_seconds() / 3600 if build_t and props_t else None
        used = (audit.exists() and props_t is not None and build_t is not None
                and props_t <= build_t + timedelta(minutes=2) and age_build is not None and age_build <= 72)
        rep.line("PASS" if used else "WARN",
                 f"props {props_path.name} pulled {fmt(props_t)}; build {'USED' if used else 'did NOT use'} it"
                 + ("" if used else " (build older than the pull, >72h old, or no audit file) -> rebuild"))
        if audit.exists():
            a = pd.read_csv(audit)
            n_m = int(a.get("props_matched", pd.Series(dtype=bool)).fillna(False).astype(bool).sum())
            print(f"      audit: {n_m} players matched to market lines")
    # movers vs the last build before the props pull (or the previous build)
    hist = file_history(proj_path)
    base_sha, base_label = None, ""
    if props_t is not None:
        prior = [h for h in hist if h[1] < props_t]
        if prior:
            base_sha, base_label = prior[0][0], f"last build before props pull ({fmt(prior[0][1])})"
    if base_sha is None and hist:
        modified = bool(git("status", "--porcelain", "--", proj_path.relative_to(REPO).as_posix()).strip())
        pick = hist[0] if modified else (hist[1] if len(hist) > 1 else None)
        if pick:
            base_sha, base_label = pick[0], f"previous committed build ({fmt(pick[1])})"
    if base_sha:
        old = git_csv(base_sha, proj_path)
        if old is not None and "final_projection" in old:
            m = df[["player_id", "player_name", "position", "team", "salary", "final_projection"]].merge(
                old[["player_id", "final_projection"]].rename(columns={"final_projection": "old"}),
                on="player_id", how="left")
            m["chg"] = (m["final_projection"] - m["old"]) / m["old"].clip(lower=1.0)
            mv = m[(m[["old", "final_projection"]].max(axis=1) >= 5) & (m["chg"].abs() > MOVER_PCT)]
            mv = mv.reindex(mv["chg"].abs().sort_values(ascending=False).index)
            print(f"      movers >15% vs {base_label}: {len(mv)}")
            out = mv.head(25).assign(old=lambda x: x.old.round(1), new=lambda x: x.final_projection.round(1),
                                     pct=lambda x: (100 * x.chg).round(0))
            rep.table(out[["player_name", "position", "team", "salary", "old", "new", "pct"]])

    # ---------------- 3 injuries
    print("\n-- 3. Injury / status coverage")
    fp = df["final_projection"].fillna(0)
    if "injury_status" not in df.columns:
        rep.line("FAIL", "no injury_status column: status_check.py apply did NOT run on this build (a "
                         "light_vegas_refresh rebuild re-projects everyone and skips status) -> OUT players "
                         "are projected again. Fix: trigger a full refresh (workflow_dispatch) or run "
                         "status_check.py apply locally (see checklist)")
    ist = df.get("injury_status", pd.Series("ACTIVE", index=df.index)).fillna("ACTIVE").str.upper()
    bad = df[(ist == "OUT") & (fp > 0)]
    if "injury_status" in df.columns:
        rep.line("FAIL" if len(bad) else "PASS", f"OUT players (per build) still projected > 0: {len(bad)}")
    rep.table(bad[["player_name", "position", "team", "salary", "final_projection"]].head(15))
    dbt = df[(ist == "DOUBTFUL") & (fp > 0)]
    if len(dbt):
        rep.line("WARN", f"DOUBTFUL players still projected > 0 (exclude unless news says playing): {len(dbt)}")
        rep.table(dbt[["player_name", "position", "team", "salary", "final_projection"]])
    q = df[(ist == "QUESTIONABLE") & (fp >= 5)].sort_values("final_projection", ascending=False)
    rep.line("WARN" if len(q) else "PASS",
             f"QUESTIONABLE and projected >= 5: {len(q)} (confirm active ~90 min before kickoff; "
             f"late-game Qs are late-swap risks)")
    rep.table(q[[c for c in ["player_name", "position", "team", "salary", "final_projection", "injury_raw_status"]
                 if c in q.columns]].head(20))
    if st:
        sdf = pd.read_csv(st[1])
        m = df[["player_id", "player_name", "team", "position", "final_projection"]].assign(
            proj_status=ist.values).merge(sdf[["player_id", "status", "raw_status"]], on="player_id", how="inner")
        m["status"] = m["status"].fillna("ACTIVE").astype(str)
        hard = m[(m["status"].str.upper() == "OUT") & (m["final_projection"] > 0)]
        rep.line("FAIL" if len(hard) else "PASS",
                 f"players OUT in the latest status pull but projected > 0: {len(hard)}")
        rep.table(hard.sort_values("final_projection", ascending=False)
                  [["player_name", "team", "position", "final_projection", "raw_status"]].round(1).head(12))
        diff = m[(m["status"].str.upper() != m["proj_status"]) & (m["final_projection"] > 0)
                 & m["status"].str.upper().isin(["OUT", "DOUBTFUL", "QUESTIONABLE"])]
        rep.line("WARN" if len(diff) else "PASS",
                 f"latest status pull {st[1].name}: {len(diff)} projected player(s) whose status differs "
                 f"from the build")
        rep.table(diff[["player_name", "team", "position", "final_projection", "proj_status", "status",
                        "raw_status"]].head(20))
    else:
        rep.line("WARN", f"no player_status_{week}_*.csv found at or before as-of")
    if sal:
        raw = pd.read_csv(sal, encoding="utf-8-sig")
        col = "Status" if "Status" in raw.columns else ("Injury Indicator" if "Injury Indicator" in raw.columns else None)
        if col:
            tagged = raw[raw[col].fillna("").astype(str).str.strip().isin(["O", "OUT", "IR", "D", "Out"])]
            print(f"      site salary file tags O/IR/D on {len(tagged)} players (snapshot at download time)")
    rep.line("INFO", "official inactives post ~90 min before each kickoff (11:30Z for 13:00 ET games; "
                     "14:35Z-ish for 16:05/16:25 ET) -- not in any file yet; check news")

    # ---------------- 4 QBs
    print("\n-- 4. QB outliers (team's top-projected QB = presumed starter)")
    qb = df[(df["position"] == "QB") & (fp > 0)].sort_values("final_projection", ascending=False)
    starters = qb.groupby("team").head(1).copy()
    pubs = load_public(site, sid)
    if pubs is not None:
        starters["key"] = starters["player_name"].map(norm_name) + "|" + starters["team"]
        starters = starters.merge(pubs, on="key", how="left")
    flags = starters[(starters["proj_pass_att"] > QB_ATT_MAX) | (starters["final_projection"] < QB_LO)
                     | (starters["final_projection"] > QB_HI)
                     | (starters.get("pub_mean", pd.Series(np.nan, index=starters.index)).notna()
                        & ((starters["final_projection"] - starters.get("pub_mean", 0)).abs() >= 4))]
    rep.line("WARN" if len(flags) else "PASS", f"QB starters flagged: {len(flags)} of {len(starters)}")
    cols = ["player_name", "team", "salary", "final_projection", "proj_pass_att", "proj_rush_att"] + \
           [c for c in ("pub_mean", "pub_src") if c in starters]
    show = flags[cols].copy()
    for c in ("final_projection", "proj_pass_att", "proj_rush_att", "pub_mean"):
        if c in show:
            show[c] = show[c].round(1)
    rep.table(show)
    mur = starters[starters["player_name"].str.contains("Murray", na=False) & (starters["team"] == "MIN")]
    if len(mur):
        r = mur.iloc[0]
        print(f"      Murray (MIN) note: model {r.final_projection:.1f}; market/WWO ~17.2 on 09-24. "
              f"Moved starters under-projected -3.95 pts (n=31, REPORT_followups.md #6).")
    if pubs is not None:
        top = df[fp >= 12].copy()
        top["key"] = top["player_name"].map(norm_name) + "|" + top["team"]
        top = top.merge(pubs, on="key", how="left")
        top = top[top["pub_mean"].notna()]
        top["gap"] = top["final_projection"] - top["pub_mean"]
        big = top[(top["gap"].abs() >= np.maximum(4, 0.25 * top["pub_mean"]))].sort_values("gap")
        rep.line("INFO", f"non-QB/QB players (proj >= 12) with model vs public gap >= max(4, 25%): {len(big)} "
                         f"(model-only conviction; public = mean of DFF/WWO)")
        rep.table(big[["player_name", "position", "team", "salary", "final_projection", "pub_mean",
                       "gap"]].round(1).head(15))

    # ---------------- 5 DST
    print("\n-- 5. DST sanity")
    dpos = df["position"].isin(["DST", "D", "DEF"])
    dst = df[dpos].copy()
    if len(dst):
        opp_it = df.drop_duplicates("team").set_index("team")["implied_total"]
        dst["opp_implied"] = dst["opponent"].map(opp_it)
        dst["val"] = dst["final_projection"] / (dst["salary"] / 1000)
        neg = dst[dst["final_projection"] <= 0]
        lo, hi = dst["final_projection"].min(), dst["final_projection"].max()
        ok = len(neg) == 0 and hi < 15 and lo > 2
        rep.line("PASS" if ok else "WARN",
                 f"{len(dst)} DSTs, proj {lo:.1f}-{hi:.1f}; zero/neg: {len(neg)}")
        cheap_cut = dst["salary"].quantile(0.5)
        viable = dst[(dst["salary"] <= cheap_cut) & (dst["opp_implied"] <= 21.5)].sort_values("val", ascending=False)
        risky = dst[dst["opp_implied"] >= 26].sort_values("final_projection", ascending=False)
        print("      cheap-and-believable (salary <= median, opp implied <= 21.5), by value:")
        rep.table(viable[["player_name", "salary", "opponent", "opp_implied", "final_projection", "val"]]
                  .round(2).head(6))
        if len(risky):
            print("      blow-up risk (opp implied >= 26) -- avoid in cash:")
            rep.table(risky[["player_name", "salary", "opponent", "opp_implied", "final_projection"]].round(1))

    # ---------------- 6 p10 / darts
    print("\n-- 6. p10 calibration / dart list")
    coefs = load_p10_coefs()
    skill = df["position"].isin(["QB", "RB", "WR", "TE"]) & (df["sigma"] > 0) & (fp > 0)
    if "statline_p10" not in df:
        rep.line("FAIL", "statline_p10 missing (build without --sigma-recalibration?) -> MME dart cap errors out")
    elif dk and coefs:
        ab = df.loc[skill, "position"].map(coefs)
        calib = (ab.map(lambda t: t[0]) + ab.map(lambda t: t[1]) * df.loc[skill, "final_projection"]).clip(lower=0)
        match = (calib - df.loc[skill, "statline_p10"]).abs() < 0.05
        share = match.mean() if len(match) else 0
        if share > 0.95:
            rep.line("PASS", f"statline_p10 is the calibrated QR p10 for {share:.0%} of skill players")
        else:
            rep.line("WARN", f"statline_p10 is NOT calibrated ({share:.0%} match): this build predates commit "
                             f"7ec55c5 -> next rebuild changes p10 and the MME dart list")
        cur = df.loc[skill & (df["statline_p10"] < DART_THRESHOLD)]
        new_p10 = pd.Series(np.nan, index=df.index)
        new_p10.loc[calib.index] = calib
        newd = df.loc[skill & (new_p10 < DART_THRESHOLD)]
        added = newd[~newd["player_id"].isin(cur["player_id"])]
        dropped = cur[~cur["player_id"].isin(newd["player_id"])]
        # Only players the optimizer might realistically roster.
        rel = lambda x: x[x["final_projection"] >= 3].sort_values("final_projection", ascending=False)  # noqa: E731
        print(f"      darts (p10 < {DART_THRESHOLD}, proj >= 3): current {len(rel(cur))}, "
              f"calibrated {len(rel(newd))}; newly flagged {len(rel(added))}, no longer flagged {len(rel(dropped))}")
        print("      (the optimizer exempts the stacked team from the dart cap; not modelled here)")
        if len(rel(added)):
            print("      newly flagged under calibrated p10:")
            rep.table(rel(added)[["player_name", "position", "team", "salary", "final_projection"]].round(1).head(15))
        if len(rel(dropped)):
            print("      no longer flagged:")
            rep.table(rel(dropped)[["player_name", "position", "team", "salary", "final_projection"]].round(1).head(15))
    else:
        rep.line("INFO", "FD: statline_p10 is the MC value (calibration is DK-classic only)")

    # ---------------- 7 value
    print("\n-- 7. Salary vs projection value outliers")
    v = df[(fp > 0) & ~dpos].copy()
    v["val"] = v["final_projection"] / (v["salary"] / 1000)
    cheap_max = 4500 if dk else 5500
    exp_min = 7000 if dk else 8000
    out_rows = []
    for pos, g in v.groupby("position"):
        hi_q, lo_q = g["val"].quantile(0.9), g.loc[g["salary"] >= exp_min, "val"].quantile(0.25) if (g["salary"] >= exp_min).any() else np.nan
        c = g[(g["salary"] <= cheap_max) & (g["val"] >= max(hi_q, 2.8 if dk else 2.2))]
        out_rows.append(c.assign(kind="cheap-high"))
        if np.isfinite(lo_q):
            e = g[(g["salary"] >= exp_min) & (g["val"] <= lo_q)]
            out_rows.append(e.assign(kind="exp-low"))
    vo = pd.concat(out_rows) if out_rows else pd.DataFrame()
    if len(vo):
        vo = vo.sort_values(["kind", "val"], ascending=[True, False])
        rep.line("INFO", f"{(vo.kind == 'cheap-high').sum()} cheap high-value, {(vo.kind == 'exp-low').sum()} "
                         f"expensive low-value (verify role/news for each cheap one before relying on it)")
        rep.table(vo[[c for c in ["kind", "player_name", "position", "team", "salary", "final_projection", "val",
                                  "injury_status"] if c in vo.columns]].round(2).head(25))

    # ---------------- 8 ownership
    print("\n-- 8. Ownership sanity")
    if "estimated_ownership_pct" in df:
        own = df["estimated_ownership_pct"].fillna(0)
        by = own.groupby(df["position"]).sum().round(0)
        tot = own.sum()
        exp_tot = 900.0
        ok = abs(tot - exp_tot) < 15
        rep.line("PASS" if ok else "WARN", f"ownership sum {tot:.0f} (expect ~{exp_tot:.0f} = 9 slots x 100); "
                                           f"by pos {by.to_dict()}")
        stale = df[(ist == "OUT") & (own > 0.5)]
        rep.line("WARN" if len(stale) else "PASS", f"OUT players carrying > 0.5% ownership: {len(stale)}")
        rep.table(stale[["player_name", "team", "estimated_ownership_pct"]].round(1).head(10))
        chalk = df[fp > 0].sort_values("estimated_ownership_pct", ascending=False).head(10).copy()
        chalk["val"] = chalk["final_projection"] / (chalk["salary"] / 1000)
        cols = ["player_name", "position", "team", "salary", "final_projection", "val", "estimated_ownership_pct"]
        if "ffc_own_pct" in chalk:
            cols.append("ffc_own_pct")
        print("      top-10 chalk (model):")
        rep.table(chalk[cols].round(1))
        if dk and "ffc_own_pct" not in df:
            rep.line("WARN", "no ffc_own_pct column: build did not use FFC public ownership")
    else:
        rep.line("WARN", "no estimated_ownership_pct column")

    # ---------------- 9 vegas / weather
    print("\n-- 9. Vegas / weather")
    if vg:
        vt, vp, vdf = vg
        cmp = df.drop_duplicates("team")[["team", "implied_total"]].merge(
            vdf.drop_duplicates("team")[["team", "implied_total"]].rename(columns={"implied_total": "vegas_now"}),
            on="team", how="left")
        cmp["d"] = cmp["vegas_now"] - cmp["implied_total"]
        moved = cmp[cmp["d"].abs() >= 1.0].sort_values("d")
        rep.line("WARN" if len(moved) else "PASS",
                 f"latest vegas pull {vp.name} ({fmt(vt)}): {len(moved)} team implied totals moved >= 1 pt "
                 f"vs the build")
        rep.table(moved.round(2))
        missing = cmp[cmp["vegas_now"].isna()]["team"].tolist()
        if missing:
            rep.line("WARN", f"teams missing from the latest vegas pull: {missing}")
    else:
        rep.line("WARN", "no vegas_implied_totals file covering this slate")
    if wx is not None:
        w = wx[wx["team"].isin(teams)].drop_duplicates("home_team")
        windy = w[(w["wind_mph"] >= WIND_MPH) & (~w["indoor"].astype(bool))]
        dome = w[w["indoor"].astype(bool)]
        wet = w[(w["precip_prob"].fillna(0) >= 0.5) & (w["precip_mm_hr"].fillna(0) >= 1) & (~w["indoor"].astype(bool))]
        age = (as_of - inputs["weather"]).total_seconds() / 3600 if inputs["weather"] else None
        rep.line("WARN" if (age is None or age > 12) else "PASS",
                 f"weather fetched {fmt(inputs['weather'])} ({age:.0f} h before as-of)" if age is not None
                 else "weather fetch time unknown")
        rep.line("WARN" if len(windy) else "PASS", f"outdoor games with wind >= {WIND_MPH:.0f} mph: {len(windy)}")
        rep.table(windy[["home_team", "team", "opponent", "wind_mph", "gust_mph", "pass_eff_factor"]])
        if len(wet):
            rep.line("INFO", f"heavy rain likely: {', '.join(wet['home_team'])}")
        print(f"      domes/indoor: {', '.join(sorted(dome['home_team']))}")
    else:
        rep.line("WARN", f"no weather file {wx_path.name}")

    # ---------------- 10 lock table
    print("\n-- 10. Lock / late-swap table")
    ko = None
    if wx is not None:
        ko = wx[wx["team"].isin(teams)][["home_team", "team", "opponent", "kickoff_utc"]]
        ko = ko[ko["team"] == ko["home_team"]]
    if ko is not None and len(ko):
        ko = ko.assign(k=pd.to_datetime(ko["kickoff_utc"], utc=True))
        n_by_team = df[fp > 0].groupby("team").size()
        rows = []
        for k, g in ko.groupby("k"):
            games = ", ".join(f"{r.opponent}@{r.home_team}" for r in g.itertuples())
            n = int(sum(n_by_team.get(t, 0) + n_by_team.get(o, 0) for t, o in zip(g.team, g.opponent)))
            rows.append({"kickoff_utc": f"{k:%H:%M}", "cdt": f"{(k + CDT):%H:%M}", "n_games": len(g),
                         "players_proj>0": n, "games": games})
        rep.table(pd.DataFrame(rows))
        if len(rows) > 1:
            rep.line("INFO", "late swap: players in later windows stay swappable until their own kickoff "
                             "(DK and FD both allow late swap on classic)")
    else:
        rep.line("WARN", "no kickoff times available (weather file missing)")


def load_public(site, sid):
    frames = []
    d = DATA / "projections_public"
    f1 = d / f"dff_{site}_{sid}.csv"
    if f1.exists():
        x = pd.read_csv(f1)
        frames.append(pd.DataFrame({"key": x["player"].map(norm_name) + "|" + x["team"],
                                    "p": pd.to_numeric(x["ppg_proj"], errors="coerce"), "src": "DFF"}))
    f2 = d / f"wwo_{site}_{sid}.csv"
    if f2.exists():
        x = pd.read_csv(f2)
        frames.append(pd.DataFrame({"key": x["player"].map(norm_name) + "|" + x["team"],
                                    "p": pd.to_numeric(x["projection"], errors="coerce"), "src": "WWO"}))
    if not frames:
        return None
    a = pd.concat(frames).dropna()
    g = a.groupby("key").agg(pub_mean=("p", "mean"), pub_src=("src", lambda s: "+".join(sorted(set(s)))))
    return g.reset_index()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slate-id", action="append", help="repeatable; default = all classic slates of --week")
    ap.add_argument("--week", type=int, default=3)
    ap.add_argument("--as-of", default=None, help="ISO UTC clock override (default now), e.g. 2026-09-20T16:30:00Z")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    as_of = utc(args.as_of) if args.as_of else datetime.now(timezone.utc)
    cfg = json.loads((DATA / "current_slate.json").read_text())
    slates = [s for s in cfg["slates"] if s.get("format") == "classic"]
    if args.slate_id:
        want = set(args.slate_id)
        slates = [s for s in slates if s["slate_id"] in want]
        missing = want - {s["slate_id"] for s in slates}
        for m in missing:
            print(f"[FAIL] {m} is not a classic slate in data/current_slate.json")
    else:
        slates = [s for s in slates if int(s["week"]) == args.week]
    rep = Report()
    for s in slates:
        try:
            check_slate(s, as_of, rep, args.verbose)
        except Exception as exc:  # noqa: BLE001 -- a report must never die mid-way
            rep.line("FAIL", f"check crashed for {s['slate_id']}: {type(exc).__name__}: {exc}")
        print()
    c = rep.counts
    print(f"SUMMARY: {c['FAIL']} FAIL, {c['WARN']} WARN, {c['PASS']} PASS, {c['INFO']} INFO "
          f"across {len(slates)} slate(s)")
    sys.exit(2 if c["FAIL"] else (1 if c["WARN"] else 0))


if __name__ == "__main__":
    main()
