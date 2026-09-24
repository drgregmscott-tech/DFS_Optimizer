"""
ingest_public_projections.py
============================

LOGS outside sites' free fantasy-point projections for one of OUR slates, so
they can be back-tested against real results later. DATA ONLY: nothing in the
projection build reads these files (2026-09-24 projections handoff, step E).

WHY NOW: both sources serve only the CURRENT week (no archive, verified
2026-09-24: DFF ignores week/date parameters). Every week not logged is lost
for good, and the blend/ensembling test needs several weeks of them.

SOURCES (public HTML only, robots.txt allows both pages):
  dff -- Daily Fantasy Fuel, https://www.dailyfantasyfuel.com/nfl/projections/{draftkings|fanduel}
         server-rendered; one <tr class="projections-listing"> per player with
         data- attributes (proj_score, ppg_proj, inj, starter_flag, depth_rank,
         opp_rank, l5/l10/szn avg, spread, ou). DK and FD.
  wwo -- WinWithOdds, https://www.winwithodds.com/dfs  (DK only; prop-derived,
         so likely correlated with our props anchor). The /dfs/download and
         /api/ endpoints are robots-disallowed and are NOT touched.

Each row is matched to our slate's salary file by normalized name; rows for
players not on our slate are dropped. Output:
    data/projections_public/{source}_{site}_{slate_id}.csv
Overwritten on every run (last pull before lock wins); fetched_at_utc records when.

    python scripts/ingest_public_projections.py --site dk --slate-id dk_classic_wk3_main_27Sep2026

Fail-safe: any failure (site down, layout change, too little overlap) prints a
message, saves nothing for that source, and the script still exits 0 unless
EVERY requested source failed -- so it can sit in the refresh workflow with
continue-on-error and never block a build.
"""

import argparse
import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUT_DIR = DATA_DIR / "projections_public"
HEADERS = {"User-Agent": "Mozilla/5.0 (personal DFS research; low volume)"}
DFF_URL = {"dk": "https://www.dailyfantasyfuel.com/nfl/projections/draftkings",
           "fd": "https://www.dailyfantasyfuel.com/nfl/projections/fanduel"}
WWO_URL = "https://www.winwithodds.com/dfs"
MIN_MATCH_FRAC = 0.25     # of OUR slate players found (DFF lists only ~450 relevant players, so not ~100%)
MIN_MATCH_ROWS = 20
WWO_HEADER = ["#", "Player Name", "Pos", "Team", "Game", "Salary", "Projection", "Value", "Slates"]


def norm_name(name) -> str:
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", str(name).lower())
    return re.sub(r"[^a-z]", "", n)


def out_path(source: str, site: str, slate_id: str) -> Path:
    return OUT_DIR / f"{source}_{site}_{slate_id}.csv"


def get(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=40)
    r.raise_for_status()
    return r.text


def fetch_dff(site: str) -> pd.DataFrame:
    text = get(DFF_URL[site])
    rows = []
    for m in re.finditer(r"<tr[^>]*projections-listing[^>]*>", text):
        attrs = {k: html.unescape(v) for k, v in re.findall(r'data-([a-z0-9_]+)\s*=\s*"([^"]*)"', m.group(0))}
        if "name" in attrs:
            rows.append(attrs)
    if len(rows) < 100:
        raise RuntimeError(f"DFF layout changed? only {len(rows)} listing rows parsed")
    df = pd.DataFrame(rows)
    for need in ("name", "pos", "team", "salary", "proj_score", "ppg_proj"):
        if need not in df.columns:
            raise RuntimeError(f"DFF layout changed? missing data-{need}")
    for c in ("salary", "proj_score", "ppg_proj", "value_proj", "l5_avg", "l10_avg", "szn_avg",
              "opp_rank", "spread", "ou", "starter_flag", "depth_rank"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.rename(columns={"name": "player"})


def fetch_wwo() -> pd.DataFrame:
    text = get(WWO_URL)
    heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", text, re.S)]
    if heads[:len(WWO_HEADER)] != WWO_HEADER:
        raise RuntimeError(f"WWO layout changed? headers {heads[:12]}")
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", text, re.S):
        c = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(c) == len(WWO_HEADER):
            rows.append(c)
    if len(rows) < 100:
        raise RuntimeError(f"WWO layout changed? only {len(rows)} rows parsed")
    df = pd.DataFrame(rows, columns=["rank", "player", "pos", "team", "game", "salary",
                                     "projection", "value", "wwo_slate_ids"])
    for c in ("salary", "projection", "value"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def our_players(site: str, slate_id: str) -> dict:
    """{normalized name -> our salary} for the slate (FLEX row salary for Showdown)."""
    sal = pd.read_csv(DATA_DIR / f"salaries_{site}_{slate_id}.csv")
    name_col = "name" if "name" in sal.columns else "Name"
    if "roster_role" in sal.columns:                       # Showdown: FLEX rows carry the base salary
        sal = sal[sal["roster_role"] == "FLEX"]
    return {norm_name(n): int(s) for n, s in zip(sal[name_col], sal["salary"])}


def match(df: pd.DataFrame, ours: dict) -> pd.DataFrame:
    df = df.copy()
    df["key"] = df["player"].map(norm_name)
    df = df[df["key"].isin(ours)].drop_duplicates("key")
    df["our_salary"] = df["key"].map(ours)
    df["salary_match"] = (df["salary"] == df["our_salary"]).astype(int)
    return df.drop(columns="key")


def run_source(source: str, site: str, slate_id: str, ours: dict) -> bool:
    try:
        if source == "dff":
            raw = fetch_dff(site)
        elif site != "dk":
            print("  wwo: DK only, skipped")
            return False
        else:
            raw = fetch_wwo()
        m = match(raw, ours)
        frac = len(m) / max(len(ours), 1)
        salary_ok = m["salary_match"].mean() if len(m) else 0.0
        print(f"  {source}: {len(raw)} rows pulled, {len(m)}/{len(ours)} of our slate matched "
              f"({frac:.0%}), salary agrees on {salary_ok:.0%}")
        # A big shortfall means wrong site/week or a layout change.
        if frac < MIN_MATCH_FRAC or len(m) < MIN_MATCH_ROWS:
            print(f"  {source}: match too small (need >= {MIN_MATCH_FRAC:.0%} and {MIN_MATCH_ROWS} rows) -- NOT saved")
            return False
        m.insert(0, "fetched_at_utc", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        p = out_path(source, site, slate_id)
        m.to_csv(p, index=False)
        print(f"  {source}: saved {len(m)} rows -> {p}")
        return True
    except Exception as e:                                   # noqa: BLE001 -- fail-safe by design
        print(f"  {source}: FAILED ({type(e).__name__}: {e}) -- nothing saved")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", choices=["dk", "fd"], default="dk")
    ap.add_argument("--slate-id", required=True)
    ap.add_argument("--sources", nargs="+", choices=["dff", "wwo"], default=["dff", "wwo"])
    args = ap.parse_args()
    ours = our_players(args.site, args.slate_id)
    ok = [run_source(s, args.site, args.slate_id, ours) for s in args.sources]
    if not any(ok):
        sys.exit("No public projection source could be logged.")


if __name__ == "__main__":
    main()
