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
    ours = {norm_key(n, s) for n, s in zip(sal[name_col], sal["salary"])}

    best = None
    for num, label in list_slates(args.site):
        t = fetch_table(num)
        if t.empty or "proj_own" not in t.columns:
            print(f"  {label:35s} (id {num}): empty table, skipped")
            continue
        t = t[t["proj_own"] > 0]
        if t.empty:
            continue
        overlap = len({norm_key(n, s) for n, s in zip(t["player"], t["salary"])} & ours)
        # A smaller slate's top-50 (e.g. Early Only) is a subset of a bigger
        # slate's pool, so raw overlap can tie -- break ties on the slate name
        # in our slate_id (main / early / afternoon).
        kw = next((k for k in ("main", "early", "afternoon") if k in args.slate_id.lower()), None)
        bonus = 0.5 if kw and kw in label.lower() else 0.0
        print(f"  {label:35s} (id {num}): {overlap}/{len(t)} players match {args.slate_id}")
        if best is None or overlap + bonus > best[4]:
            best = (overlap, num, label, t, overlap + bonus)
        time.sleep(0.6)

    if best is None or best[0] < MIN_OVERLAP:
        raise SystemExit(f"No FFC slate matched {args.slate_id} (best overlap "
                         f"{0 if best is None else best[0]} < {MIN_OVERLAP}). Nothing saved.")
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    out = public_path(args.site, args.slate_id)
    best[3].to_csv(out, index=False)
    print(f"Saved {len(best[3])} rows from '{best[2]}' (id {best[1]}, overlap {best[0]}) -> {out}")


if __name__ == "__main__":
    main()
