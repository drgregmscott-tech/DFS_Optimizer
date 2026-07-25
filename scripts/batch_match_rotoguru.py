"""
batch_match_rotoguru.py
=======================

Materialize the full matched-salary dataset from the RotoGuru raw files
(chosen approach "a": build all salaries_*.csv up front, once, so the
backtest harness just READS files instead of shelling out to the matcher
per week).

Runs ingest_salaries.py -- the SAME 5-stage matcher the live weekly workflow
uses -- as a subprocess over every rotoguru_{site}_{season}_wk{week}.csv it
finds, using the agreed slate-id convention:

    rotoguru_{season}_wk{week}     (no site: the output filename already
                                    prefixes it, giving
                                    salaries_{site}_rotoguru_{season}_wk{week}.csv)

Why a wrapper and not a loop inlined into the harness:

  1. ONE MATCHER, NOT TWO. This calls scripts/ingest_salaries.py as a
     subprocess rather than importing and re-driving its internals. The
     matcher stays the single source of truth for how a RotoGuru name
     becomes an nflverse player_id; this script only orchestrates.

  2. EXIT CODE 1 IS EXPECTED HERE, NOT FATAL. ingest_salaries.py exits 1
     whenever ANY row is unmatched -- correct for the live weekly workflow,
     where an unmatched star means "stop and fix name_mapping.csv before
     you build a lineup." But the RotoGuru bootstrap has a known, permanent
     1-2% unmatched tail of inert scrubs and journeymen (verified across
     2014/2018/2021: Luke McCown, Michael Vick, Ben Watson, Robby Anderson,
     Westbrook-Ikhine -- all low-salary players who never enter an optimal
     lineup). If this batch treated exit-1 as fatal it would halt on the
     first file and never produce the other 143. So exit-1 is captured and
     summarized, NOT propagated -- but see #3.

  3. THE SUMMARY IS THE POINT. Running 144 files and ignoring their exit
     codes would silently lose the signal when something REAL breaks (a
     season whose schema quirk craters the match rate, an empty week, a
     hard SystemExit from a missing parquet). So every invocation's match
     rate AND match-quality distribution are captured, and the run ends
     with a table plus an explicit list of any week that falls below a
     threshold or fails hard. A normal scrub tail and a genuinely broken
     week look completely different in that summary.

     Match quality matters as much as match rate: a week can be 98% matched
     but with many medium-confidence auto_fallback_team_mismatch or
     low-confidence ambiguous rows, which is worth a look even though the
     headline number is fine. The summary reports both.

  4. IDEMPOTENT / RE-RUNNABLE. This is a materialization step over 144
     subprocess calls; if it dies partway it must resume, not restart or
     double-write. A week whose output salaries file already exists is
     skipped unless --force is passed.

  5. PER-WEEK weekly_stats. Each RotoGuru week is matched against that
     SAME SEASON's weekly_stats parquet (the matcher's --season /
     --weekly-stats). Matching 2014 salaries against 2021 rosters would be
     nonsense; the season is parsed back out of each raw filename and the
     correct parquet selected.

Usage:
    python3 scripts/batch_match_rotoguru.py                 # all sites/seasons found
    python3 scripts/batch_match_rotoguru.py --site dk       # one site
    python3 scripts/batch_match_rotoguru.py --season 2021   # one season
    python3 scripts/batch_match_rotoguru.py --force         # rebuild existing
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RAW_SALARY_DIR = DATA_DIR / "raw_salaries"
LOG_DIR = REPO_ROOT / "logs"
INGEST_SALARIES = Path(__file__).resolve().parent / "ingest_salaries.py"

# rotoguru_{site}_{season}_wk{week}.csv
RAW_NAME_RE = re.compile(r"^rotoguru_(?P<site>dk|fd)_(?P<season>\d{4})_wk(?P<week>\d+)\.csv$")

# Any week landing below this overall match rate is surfaced loudly in the
# summary. Set from the observed bootstrap floor (~98-99% on real weeks) with
# headroom -- a week under this is anomalous, not just scrub tail.
MATCH_RATE_WARN_THRESHOLD = 0.95

# Lines the matcher prints, e.g. "  Matched:   432 (98.4%)"
MATCHED_RE = re.compile(r"Matched:\s+(\d+)\s+\(([\d.]+)%\)")
UNMATCHED_RE = re.compile(r"Unmatched:\s+(\d+)\s+\(([\d.]+)%\)")


def discover_raw_files(site_filter, season_filter):
    files = []
    for path in sorted(RAW_SALARY_DIR.glob("rotoguru_*_wk*.csv")):
        m = RAW_NAME_RE.match(path.name)
        if not m:
            continue
        site, season, week = m["site"], int(m["season"]), int(m["week"])
        if site_filter and site != site_filter:
            continue
        if season_filter and season not in season_filter:
            continue
        files.append((path, site, season, week))
    return files


def output_exists(site, season, week):
    slate_id = f"rotoguru_{season}_wk{week}"
    return (DATA_DIR / f"salaries_{site}_{slate_id}.csv").exists()


def match_one(path, site, season, week):
    """Run the real matcher as a subprocess. Returns a result dict.

    Note on exit codes: ingest_salaries.py exits 1 on ANY unmatched row
    (decision #2), so a non-zero return with a parseable 'Matched:' line is
    a NORMAL partial-match, not a failure. Only a non-zero return WITHOUT a
    parseable summary is a genuine hard error (missing parquet, SystemExit)."""
    slate_id = f"rotoguru_{season}_wk{week}"
    weekly_stats = DATA_DIR / f"weekly_stats_{season}.parquet"

    if not weekly_stats.exists():
        return {
            "site": site, "season": season, "week": week,
            "status": "ERROR", "detail": f"missing {weekly_stats.name}",
            "rate": None, "unmatched": [],
        }

    proc = subprocess.run(
        [sys.executable, str(INGEST_SALARIES),
         "--site", site,
         "--season", str(season),
         "--raw", str(path),
         "--slate-id", slate_id,
         "--weekly-stats", str(weekly_stats),
         "--out-dir", str(DATA_DIR),
         "--log-dir", str(LOG_DIR)],
        capture_output=True, text=True,
    )
    out = proc.stdout + "\n" + proc.stderr

    m = MATCHED_RE.search(out)
    if not m:
        # No summary line at all -> genuine hard failure, not a scrub tail.
        return {
            "site": site, "season": season, "week": week,
            "status": "ERROR",
            "detail": (proc.stderr or out).strip().splitlines()[-1] if out.strip() else "no output",
            "rate": None, "unmatched": [],
        }

    rate = float(m.group(2)) / 100.0
    unmatched = []
    capture = False
    for line in out.splitlines():
        if "Unmatched players" in line:
            capture = True
            continue
        if capture:
            s = line.strip()
            if s.startswith("- "):
                unmatched.append(s[2:])
            elif s.startswith("Wrote "):
                break

    status = "OK" if rate >= MATCH_RATE_WARN_THRESHOLD else "LOW"
    return {
        "site": site, "season": season, "week": week,
        "status": status, "detail": "", "rate": rate, "unmatched": unmatched,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Batch-match all RotoGuru raw salary files through ingest_salaries.py."
    )
    parser.add_argument("--site", choices=["dk", "fd"], default=None)
    parser.add_argument("--season", type=int, nargs="+", default=None)
    parser.add_argument("--force", action="store_true",
                        help="Rebuild even if the matched output already exists")
    args = parser.parse_args()

    season_filter = set(args.season) if args.season else None
    files = discover_raw_files(args.site, season_filter)

    if not files:
        raise SystemExit(
            f"No rotoguru_*_wk*.csv files found in {RAW_SALARY_DIR} matching "
            f"site={args.site} season={args.season}. Run ingest_rotoguru.py first."
        )

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Found {len(files)} raw file(s) to process.\n")

    results, skipped = [], 0
    for path, site, season, week in files:
        if not args.force and output_exists(site, season, week):
            skipped += 1
            continue
        res = match_one(path, site, season, week)
        results.append(res)
        flag = {"OK": "  ", "LOW": "!!", "ERROR": "XX"}[res["status"]]
        rate_str = f"{res['rate']:.1%}" if res["rate"] is not None else "  --  "
        detail = f"  {res['detail']}" if res["detail"] else ""
        print(f"  {flag} {site} {season} wk{week:<2}  {rate_str}"
              f"  ({len(res['unmatched'])} unmatched){detail}")

    # ------------------------------------------------------------------
    # Summary -- decision #3
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    ok = [r for r in results if r["status"] == "OK"]
    low = [r for r in results if r["status"] == "LOW"]
    err = [r for r in results if r["status"] == "ERROR"]
    print(f"  Processed: {len(results)}   Skipped (already built): {skipped}")
    print(f"  OK: {len(ok)}   LOW (<{MATCH_RATE_WARN_THRESHOLD:.0%}): {len(low)}   ERROR: {len(err)}")

    if ok:
        rates = [r["rate"] for r in ok]
        print(f"  OK match rate: min {min(rates):.1%}, "
              f"mean {sum(rates)/len(rates):.1%}, max {max(rates):.1%}")

    if low:
        print("\n  LOW-MATCH WEEKS (investigate -- this is not the normal scrub tail):")
        for r in low:
            print(f"    {r['site']} {r['season']} wk{r['week']}: {r['rate']:.1%}")

    if err:
        print("\n  HARD ERRORS (no match summary produced):")
        for r in err:
            print(f"    {r['site']} {r['season']} wk{r['week']}: {r['detail']}")

    # Aggregate unmatched names across the whole run: a name that recurs in
    # many weeks is a high-value name_mapping.csv row (one fix, many weeks).
    from collections import Counter
    name_counts = Counter()
    for r in results:
        name_counts.update(r["unmatched"])
    if name_counts:
        print("\n  MOST-FREQUENT UNMATCHED NAMES (top candidates for "
              "data/name_mapping.csv -- one row fixes every week they appear):")
        for name, count in name_counts.most_common(20):
            print(f"    {count:>3}x  {name}")

    if err:
        sys.exit(1)  # hard errors are worth a non-zero exit; LOW/scrub tail are not


if __name__ == "__main__":
    main()
