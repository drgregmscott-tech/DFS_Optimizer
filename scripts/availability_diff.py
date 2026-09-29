"""PROTOTYPE (not wired into production): multi-source availability diff.

Pulls current skill-player status from two free, no-login, machine-readable sources and diffs them against the
newest pipeline status file (output/player_status_{week}_*.csv written by status_check.py pull):
  * ESPN team roster endpoint (same one status_check.py uses) -> injuries[].status + date
  * Sleeper /v1/players/nfl (public, no token; docs ask for <= ~1 call/day on this 5MB endpoint, so the
    response is cached for --sleeper-max-age-hours, default 6) -> injury_status, status, team
Joins are by ID via nflverse weekly_rosters (espn_id, sleeper_id -> gsis_id); no name matching.
Writes analysis/inactives/live/availability_diff_{week}_{utcts}.csv; touches nothing else.
Rows flagged when any two sources disagree on OUT-ish vs not, or Q/D vs ACTIVE.

Usage: python scripts/availability_diff.py --season 2026 --week 4 [--teams BUF,CAR]
"""
import argparse, glob, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd, requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from status_check import ESPN_TEAM_IDS, STATUS_MAP, fetch_team_roster  # noqa: E402

LIVE = ROOT / "analysis" / "inactives" / "live"
SK = {"QB", "RB", "WR", "TE", "FB"}
SLEEPER_MAP = {"out": "OUT", "ir": "OUT", "pup": "OUT", "sus": "OUT", "cov": "OUT", "na": "OUT", "dnr": "OUT",
               "doubtful": "DOUBTFUL", "questionable": "QUESTIONABLE", "probable": "ACTIVE"}


def espn_pull(teams):
    rows = []
    for ab, tid in teams.items():
        try:
            js = fetch_team_roster(tid)
        except Exception as e:  # noqa: BLE001
            print(f"ESPN {ab} failed: {e}", file=sys.stderr); continue
        for g in js.get("athletes", []):
            for p in g.get("items", []):
                if (p.get("position") or {}).get("abbreviation") not in SK:
                    continue
                inj = sorted(p.get("injuries") or [], key=lambda i: i.get("date", ""))
                raw = inj[-1].get("status", "") if inj else ""
                rows.append({"espn_id": str(p.get("id")), "espn_name": p.get("fullName"),
                             "espn_status": STATUS_MAP.get(raw.lower(), raw.upper()) if raw else "ACTIVE",
                             "espn_raw": raw, "espn_date": inj[-1].get("date") if inj else None})
    return pd.DataFrame(rows)


def sleeper_pull(max_age_h):
    LIVE.mkdir(parents=True, exist_ok=True)
    cache = LIVE / "sleeper_players_cache.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < max_age_h * 3600:
        data = json.loads(cache.read_text(encoding="utf-8"))
        print(f"Sleeper: using cache ({(time.time()-cache.stat().st_mtime)/3600:.1f}h old)")
    else:
        r = requests.get("https://api.sleeper.app/v1/players/nfl", timeout=60)
        r.raise_for_status(); data = r.json()
        cache.write_text(json.dumps(data), encoding="utf-8")
    rows = []
    for sid, p in data.items():
        if p.get("position") not in SK or not p.get("team"):
            continue
        inj = (p.get("injury_status") or "").strip()
        st = (p.get("status") or "").strip()
        s = SLEEPER_MAP.get(inj.lower(), "ACTIVE" if not inj else inj.upper())
        if st.lower().startswith(("injured reserve", "physically unable", "inactive", "suspended", "non football")):
            s = "OUT"
        rows.append({"sleeper_id": str(sid), "sleeper_name": p.get("full_name"), "sleeper_team": p.get("team"),
                     "sleeper_status": s, "sleeper_raw": f"{inj}|{st}", "sleeper_news_updated": p.get("news_updated")})
    return pd.DataFrame(rows)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--season", type=int, required=True); a.add_argument("--week", type=int, required=True)
    a.add_argument("--teams"); a.add_argument("--sleeper-max-age-hours", type=float, default=6)
    x = a.parse_args()
    teams = ESPN_TEAM_IDS if not x.teams else {k: v for k, v in ESPN_TEAM_IDS.items() if k in x.teams.upper().split(",")}
    ro = pd.read_parquet(ROOT / "data" / f"weekly_rosters_{x.season}.parquet",
                         columns=["gsis_id", "espn_id", "sleeper_id", "full_name", "team", "position", "week"])
    ro = ro.sort_values("week").drop_duplicates("gsis_id", keep="last")
    ro["espn_id"] = ro.espn_id.astype(str).str.replace(r"\.0$", "", regex=True)
    ro["sleeper_id"] = ro.sleeper_id.astype(str).str.replace(r"\.0$", "", regex=True)
    e = espn_pull(teams); s = sleeper_pull(x.sleeper_max_age_hours)
    df = ro[ro.position.isin(SK)].merge(e, on="espn_id", how="left").merge(s, on="sleeper_id", how="left")
    df = df[df.espn_status.notna() | df.sleeper_status.notna()]
    files = sorted(glob.glob(str(ROOT / "output" / f"player_status_{x.week}_*.csv")))
    if files:
        base = pd.read_csv(files[-1], dtype={"player_id": str})[["player_id", "status"]].rename(
            columns={"player_id": "gsis_id", "status": "pipeline_status"})
        df = df.merge(base, on="gsis_id", how="left")
        print(f"pipeline base: {os.path.basename(files[-1])}")
    else:
        df["pipeline_status"] = None; print("no pipeline status file for this week; diff is ESPN vs Sleeper only")
    def cls(v):
        return None if pd.isna(v) else ("OUT" if v in ("OUT", "DOUBTFUL") else ("Q" if v == "QUESTIONABLE" else "ACT"))
    c = df[["espn_status", "sleeper_status", "pipeline_status"]].apply(lambda col: col.map(cls))
    df["disagree"] = c.apply(lambda r: len(set(r.dropna())) > 1, axis=1)
    df["any_out"] = (c == "OUT").any(axis=1)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    LIVE.mkdir(parents=True, exist_ok=True)
    outp = LIVE / f"availability_diff_{x.week}_{ts}.csv"
    df.sort_values(["disagree", "any_out"], ascending=False).to_csv(outp, index=False)
    d = df[df.disagree]
    print(f"rows {len(df)}; ESPN matched {df.espn_status.notna().sum()}, Sleeper matched {df.sleeper_status.notna().sum()}; "
          f"disagreements {len(d)}")
    print(d[["full_name", "team", "position", "espn_raw", "sleeper_raw", "pipeline_status"]].head(40).to_string(index=False))
    print(f"wrote {outp}")


if __name__ == "__main__":
    main()
