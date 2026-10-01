"""
ingest_public_ownership.py
==========================

Pulls Fantasy Football Calculator's FREE projected DFS ownership table
(https://fantasyfootballcalculator.com/dfs/ownership) for one of OUR slates and
saves it to data/ownership_public/ffc_{site}_{slate_id}.csv.

WHY (2026-09-23 ownership review): it is the one outside signal that fixes the
layered ownership model's biggest misses (cheap-crowd plays like Mayer/Jones/
Schultz). Added as a feature, leave-one-week-out on the 6 real wk1/wk2 DK
slates: corr 0.676 -> 0.764, MAE 6.75 -> 6.05, chalk bias -6.8 -> -4.1, misses
>12 pts 31 -> 23, and every slate improved. See ownership_model.py.

HOW: the page lists the CURRENT week's slates (dropdown, static HTML) and each
slate's table is server-rendered at /dfs/ownership/slate/{id} (top 50 players:
salary, projected %, low-high range). The page does not say which of our slates
each corresponds to, so every listed slate is fetched and the best match to
data/salaries_{site}_{slate_id}.csv (by normalized name + salary) is kept.

    python scripts/ingest_public_ownership.py --site dk --slate-id dk_classic_wk3_main_27Sep2026

Run it AFTER ingest_salaries.py and as close to lock as you can (projections
move), then re-run the projection build. Never required: without the file the
ownership model uses its pub_val-only artifact.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
PUBLIC_DIR = DATA_DIR / "ownership_public"
BASE = "https://fantasyfootballcalculator.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (personal DFS research; low volume)"}
SITE_LABEL = {"dk": "DraftKings", "fd": "FanDuel"}
MIN_OVERLAP = 25          # of the table's 50 players, must match our slate by name+salary
# Table-selection fix (2026-10-01): a smaller slate's top-50 (e.g. Early Only) is a SUBSET
# of a bigger slate's pool, so raw name+salary overlap alone can pick the wrong table --
# on wk3 main, the early table out-matched the real main table (44 vs 43) and got saved,
# silently dropping every afternoon-game player from "main"'s ownership for 4 days straight.
# Fix: pick by TEAM COVERAGE first (how many of our slate's teams the matched players span),
# overlap+bonus only as a tie-break. Off: DFS_FFC_PICK_BY_COVERAGE=0 (old overlap-only logic).
MIN_TEAM_COVERAGE = 0.70  # loud warning if the saved table covers fewer than this share of teams
COVERAGE_MARGIN = 0.80    # reject a table if another candidate covers teams*this much better


def pick_by_coverage_enabled() -> bool:
    return os.environ.get("DFS_FFC_PICK_BY_COVERAGE", "1").strip().lower() not in ("0", "false", "off", "no")


def norm_key(name, salary) -> str:
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", str(name).lower())
    return re.sub(r"[^a-z]", "", n) + str(int(salary))


def public_path(site: str, slate_id: str) -> Path:
    return PUBLIC_DIR / f"ffc_{site}_{slate_id}.csv"


def list_slates(site: str) -> list:
    r = requests.get(f"{BASE}/dfs/ownership", headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for opt in soup.select("select option"):
        val, label = opt.get("value"), opt.get_text(strip=True)
        if val and label.startswith(SITE_LABEL[site]):
            out.append((int(val), label))
    return out


def fetch_table(slate_num: int) -> pd.DataFrame:
    r = requests.get(f"{BASE}/dfs/ownership/slate/{slate_num}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    rows = []
    for tr in soup.select("tr")[1:]:
        c = [x.get_text(" ", strip=True) for x in tr.find_all(["td", "th"])]
        if len(c) < 3:
            continue
        rng = re.findall(r"[\d.]+", c[3]) if len(c) > 3 else []
        rows.append({
            "player": c[0],
            "salary": int(re.sub(r"\D", "", c[1]) or 0),
            "proj_own": float(c[2].rstrip("%")),
            "lo": float(rng[0]) if len(rng) > 0 else None,
            "hi": float(rng[1]) if len(rng) > 1 else None,
        })
    return pd.DataFrame(rows)


def load_public(site: str, slate_id: str):
    """Saved table as a {normalized name+salary key -> proj_own} dict, or None."""
    p = public_path(site, slate_id)
    if not p.exists():
        return None
    t = pd.read_csv(p)
    return {norm_key(n, s): float(o) for n, s, o in zip(t["player"], t["salary"], t["proj_own"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", choices=["dk", "fd"], default="dk")
    ap.add_argument("--slate-id", required=True)
    args = ap.parse_args()

    sal = pd.read_csv(DATA_DIR / f"salaries_{args.site}_{args.slate_id}.csv")
    name_col = "name" if "name" in sal.columns else "Name"
    team_col = "normalized_team" if "normalized_team" in sal.columns else "TeamAbbrev"
    key_to_team = {norm_key(n, s): tm for n, s, tm in zip(sal[name_col], sal["salary"], sal[team_col])}
    ours = set(key_to_team)
    our_teams = set(sal[team_col].dropna())
    use_coverage = pick_by_coverage_enabled()

    candidates = []
    kw = next((k for k in ("main", "early", "afternoon") if k in args.slate_id.lower()), None)
    for num, label in list_slates(args.site):
        t = fetch_table(num)
        if t.empty or "proj_own" not in t.columns:
            print(f"  {label:35s} (id {num}): empty table, skipped")
            continue
        t = t[t["proj_own"] > 0]
        if t.empty:
            continue
        matched = {norm_key(n, s) for n, s in zip(t["player"], t["salary"])} & ours
        overlap = len(matched)
        teams = {key_to_team[k] for k in matched}
        coverage = len(teams) / len(our_teams) if our_teams else 0.0
        # A smaller slate's top-50 (e.g. Early Only) is a subset of a bigger slate's
        # pool, so raw overlap alone can tie or even beat the real match -- break
        # ties on the slate name in our slate_id (main / early / afternoon).
        bonus = 0.5 if kw and kw in label.lower() else 0.0
        print(f"  {label:35s} (id {num}): {overlap}/{len(t)} players match, "
              f"{len(teams)}/{len(our_teams)} teams covered ({coverage:.0%})")
        candidates.append({"num": num, "label": label, "t": t, "overlap": overlap,
                            "score": overlap + bonus, "coverage": coverage})
        time.sleep(0.6)

    if not candidates:
        raise SystemExit(f"No FFC slate matched {args.slate_id} (no candidates). Nothing saved.")

    if use_coverage:
        best_coverage = max(c["coverage"] for c in candidates)
        viable = [c for c in candidates if c["coverage"] >= best_coverage * COVERAGE_MARGIN]
        best = max(viable, key=lambda c: c["score"])
    else:
        best = max(candidates, key=lambda c: c["score"])

    if best["overlap"] < MIN_OVERLAP:
        raise SystemExit(f"No FFC slate matched {args.slate_id} (best overlap "
                         f"{best['overlap']} < {MIN_OVERLAP}). Nothing saved.")
    if best["coverage"] < MIN_TEAM_COVERAGE:
        print(f"WARNING: saved FFC table for {args.slate_id} covers only "
              f"{best['coverage']:.0%} of this slate's teams ({best['label']}, id {best['num']}) "
              f"-- likely a partial/wrong-slate match.", file=sys.stderr)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    out = public_path(args.site, args.slate_id)
    best["t"].to_csv(out, index=False)
    print(f"Saved {len(best['t'])} rows from '{best['label']}' (id {best['num']}, "
          f"overlap {best['overlap']}, team coverage {best['coverage']:.0%}) -> {out}")


if __name__ == "__main__":
    main()
