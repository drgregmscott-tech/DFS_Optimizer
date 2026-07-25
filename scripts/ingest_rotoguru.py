"""
ingest_rotoguru.py
===================

Historical DFS salary + actual-points ingest, from RotoGuru.

Purpose: this project has real 2025 NFL OUTCOMES (weekly_stats parquet) but
zero real historical SALARY files -- DK/FD publish no API and the "Export to
CSV" button only ever gives you the CURRENT slate. Without historical
salaries there is no salary cap, so no legal roster, so no lineup, so no
lineup-level backtest and no salary-vs-points baseline curve. RotoGuru is a
free archive that closes exactly that gap.

Emits, per season:
  1. `data/raw_salaries/rotoguru_{site}_{season}_wk{week}.csv`
       One file per week, shaped to MIMIC that site's own real salary export
       (see decision #2). Feed straight into ingest_salaries.py.
  2. `data/rotoguru_actuals_{site}_{season}.csv`
       Actual DFS points per player per week. This is the scoring truth the
       backtest harness grades lineups against, and RotoGuru gives it to us
       in the same response as the salaries, so it would be wasteful to
       throw it away.

COVERAGE, VERIFIED LIVE 2026-07-25 (not assumed -- checked before building):
  DraftKings 2014-2021. FanDuel 2011-2021. Yahoo 2017-2021.
  There is NO data for 2022 or later. Do not plan around getting it here.

Design decisions, numbered per this project's convention. #1 is the one that
matters most; the rest follow from it or from the upstream contract.

  1. HARD YEAR/WEEK ASSERTION -- RotoGuru fails SILENTLY on an
     out-of-range year. Verified directly: requesting `year=2024` returned
     2021 data, with the header reading "2021", the `year` parameter
     dropped from the redirect URL entirely, and byte-identical rows to a
     no-year request (Mahomes 36.28 at $8,100 in both). It does not 404, it
     does not warn -- it serves the newest season it has and looks like a
     success.

     A naive loop over 2021-2025 would therefore collect the 2021 file five
     times and cheerfully report five seasons ingested. That is precisely
     the silent-corruption class this project has been bitten by twice
     already (duplicate player_id silently corrupting merged projections;
     an empty Cloudflare secret reporting "Success!"). So: every response's
     own `Year` and `Week` columns are checked against what was requested,
     and a mismatch is a hard SystemExit naming both values -- never a
     warning, never a skip.

  2. OUTPUT SHAPE = MIMIC THE SITE'S OWN EXPORT, don't invent a schema.
     The obvious-looking alternative is for this script to do its own
     nflverse player matching and emit `salaries_{site}_{slate_id}.csv`
     directly. Rejected: ingest_salaries.py already owns a 5-stage matcher
     (exact / position-equivalents / name_mapping.csv override / team-
     abbrev normalization / unique-name fallback) plus unmatched-player
     logging. Reimplementing that here would create a second matching
     implementation to drift out of sync -- the exact failure mode
     SITE_CONFIGS exists to prevent.

     So this script's output is a *raw-export lookalike*, and matching
     stays in one place:

         python3 scripts/ingest_rotoguru.py --site dk --season 2021
         python3 scripts/ingest_salaries.py --site dk --season 2021 \
             --raw data/raw_salaries/rotoguru_dk_2021_wk10.csv \
             --slate-id rotoguru_wk10

     This turned out to be nearly free: 32 of RotoGuru's 33 team
     abbreviations (`kan`, `gnb`, `nwe`, `tam`, `sfo`, `lvr`, `jac`, and
     `oak`) were already in ingest_salaries.py's BASE_TEAM_ABBREV_MAP. The
     `OAK -> LV` entry even happens to fix a real inconsistency inside
     RotoGuru's own data: 2021 week 1 lists Lamar Jackson as `bal @ oak`
     while listing Josh Jacobs as `lvr`, so the Raiders appear under two
     abbreviations in the same file.

     ONE was missing, and only real data found it -- see decision #11.

 11. `nor` WAS NOT IN THE MAP, AND THE FAILURE WAS SILENT. Validating all
     33 RotoGuru abbreviations against the real 32-team set in
     weekly_stats_2021.parquet turned up exactly one miss:
     BASE_TEAM_ABBREV_MAP had `"NOS": "NO"` but not `"NOR": "NO"`, and
     RotoGuru uses `nor`. Nothing errored. What actually happened:
       a. Every New Orleans SKILL player still matched, but fell through
          from the exact-match stage to `auto_fallback_team_mismatch` at
          MEDIUM confidence (verified on real data: Kamara, Juwan Johnson,
          Lil'Jordan Humphrey).
       b. The DEFENSE row came out as player_id `DST_NOR` with
          normalized_team `NOR`, which can never match the Vegas file's
          `NO`. build_dst_projections() would therefore find no game for
          New Orleans, treat it as a bye, and force final_projection to
          0.0 -- every week, for one team, with no error anywhere.
     Fixed at the canonical location (BASE_TEAM_ABBREV_MAP), not patched
     locally, because the gap affects ANY source that writes `NOR`, not
     just RotoGuru. Purely additive -- no site export currently sends it.

     Consequence for this module: `team` and `opponent` are normalized
     HERE, in tidy_season(), by calling ingest_salaries.py's own
     normalize_team() -- reuse, not a second implementation. Done early
     rather than left raw because the actuals file's `opponent` column is
     a join key for the backtest harness, and raw `oak` vs `lvr` would
     silently split the Raiders across two codes there. Safe because
     normalize_team() is idempotent, so ingest_salaries.py re-normalizing
     the emitted TeamAbbrev is a no-op.

  3. `ID` COLUMN = RotoGuru's GID, AND IT IS NOT THE SITE'S REAL ID.
     ingest_salaries.py needs `site_id_col` ("ID" on DK, "Id" on FD)
     because Session 7.3's "Download Lineups for Import" feature has to
     write DK's own numeric ID -- DK's bulk upload rejects name-only
     entries. RotoGuru has no DK ID, but it does have a GID that is stable
     per player across weeks and seasons (Mahomes is 1523 throughout), so
     it satisfies every downstream join.

     FLAGGED LOUDLY, because this is a real trap: a lineup built from
     RotoGuru-sourced salaries can NEVER be uploaded to DK or FD. The IDs
     are RotoGuru's, not the site's. That's harmless for backtesting (you
     don't upload a 2021 lineup) but it must not be mistaken for a live
     salary file. Every emitted file therefore carries an
     `id_source=rotoguru_gid` column so a downstream consumer can tell,
     and the filename is prefixed `rotoguru_`.

  4. `AvgPointsPerGame` IS DERIVED, WITH THE SAME LOOKAHEAD GUARD AS
     SESSION 2.1. Real DK exports carry a season-to-date average, which
     build_projections.py's build_dst_projections() depends on as the ONLY
     real historical signal for a team defense (that script's decision
     #5a). RotoGuru has no such column, but it has the weekly points to
     compute one.

     Computed as the mean of that player's points over weeks strictly
     BEFORE the target week, same season. Weeks 1..N-1 only -- identical
     cutoff logic to projections_baseline.py, for the same reason:
     including the target week's own points would leak the outcome being
     projected into its own input, and DST projections are built directly
     off this column.

     A player with no prior week is written as BLANK, not 0.0. "We have no
     evidence yet" and "we measured zero" are different claims, and
     build_projections.py already applies its own documented .fillna(0.0)
     to this column -- so writing a real 0.0 here would silently
     impersonate a measurement.

  5. `N/A` SALARIES ARE EXCLUDED, NOT COERCED. RotoGuru writes a literal
     "N/A" salary for players who scored but weren't on that week's slate
     (2021 week 1: Danny Amendola 14.4 pts, Chris Hogan 8.0 pts -- both
     N/A). In the semi-colon feed these arrive as an empty field, which
     `pd.to_numeric` would happily turn into NaN and a careless fillna
     would turn into 0. A $0 player is catastrophic in an optimizer: it is
     free points, and the solver will take all of them, every time.
     These rows are dropped from the salary file, counted, and printed.
     Their POINTS are still kept in the actuals file -- they really did
     score; they just weren't purchasable.

  6. NAME RESHAPE, NOT NAME MATCHING. RotoGuru writes "Last, First" with
     the generational suffix attached to the last name ("Mahomes II,
     Patrick", "Shenault Jr., Laviska", "St. Brown, Amon-Ra", "Ruggs III,
     Henry"). Split on the FIRST comma and swap -> "Patrick Mahomes II".
     No further cleanup here: ingest_salaries.py's normalize_name() already
     lowercases, strips punctuation, and drops suffixes from its SUFFIXES
     set, and doing any of that twice risks the two implementations
     disagreeing. Expect some rows to land in that script's unmatched log
     on the first run for a season -- that is the system working as
     designed, and the fix is a row in data/name_mapping.csv, exactly as
     for a real export.

  7. DEFENSE ROWS. RotoGuru uses position `Def` and a city-style name
     ("Arizona", "New York J", "New York G", "LA Rams", "Las Vegas"), with
     GIDs 7001-7032. Position is mapped to each site's own label via
     SITE_CONFIGS[site]["defense_position_values"] rather than hardcoding
     "DST" -- DK uses DST, FD uses D/DEF, and that difference already has
     a canonical home. The city name is passed through UNCHANGED and is
     deliberately not used for matching: the `Team` column already carries
     the real team code, so defense matching never depends on parsing
     "New York J" correctly.

  8. NO SLATE FILTERING HERE. RotoGuru states on every page that its
     salaries "typically reflect only 'all week (Thurs-Mon)' slates" and
     that single-game contest salaries differ and are not reported. So the
     pool this produces is a FULL-WEEK pool, wider than the Sunday-only
     Classic main slate actually played. That is a real caveat, and it is
     deliberately NOT corrected here: this script's job is to be a
     faithful mirror of the source. Narrowing to a Sunday main slate needs
     schedules_{season}.parquet, which the backtest harness will already
     have loaded -- so it belongs there, once, rather than being half-
     applied in two places.

  9. RESPONSES ARE CACHED TO DISK. Raw HTML is written to
     `data/raw_salaries/.rotoguru_cache/` and reused on re-run unless
     --no-cache is passed. A full 8-season two-site pull is ~270 requests
     against a small volunteer-run site; re-running the parser during
     development should not re-hit it. Requests are also rate-limited
     (--sleep, default 2.0s) for the same reason. Please leave this on.

 10. PLAYOFF WEEKS DON'T EXIST UPSTREAM. RotoGuru states it does not
     produce NFL stats or salaries for playoff weeks. Harmless -- this
     whole pipeline is REG-season only (projections_baseline.py /
     projections_matchup.py both exclude POST) -- but it means weeks are
     capped at 17 for 2014-2020 and 18 from 2021 on, which is why
     --weeks defaults to the season-aware range rather than a constant.

Usage:
    python3 scripts/ingest_rotoguru.py --site dk --season 2021
    python3 scripts/ingest_rotoguru.py --site dk --season 2014 2015 2016
    python3 scripts/ingest_rotoguru.py --site fd --season 2021 --weeks 1 2 3
"""

import argparse
import html
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import SITE_CONFIGS, normalize_team  # noqa: E402 -- decisions #7/#11: per-site defense labels and team normalization both live there, not here

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RAW_SALARY_DIR = DATA_DIR / "raw_salaries"
CACHE_DIR = RAW_SALARY_DIR / ".rotoguru_cache"

BASE_URL = "http://rotoguru1.com/cgi-bin/fyday.pl"

# Decision #1 / coverage note. Verified live 2026-07-25 by reading the
# "Available DFS history" list on the page itself. Requesting outside this
# range does NOT error -- it silently serves the newest season available,
# which is why the per-response Year assertion in parse_scsv() exists.
SITE_COVERAGE = {
    "dk": (2014, 2021),
    "fd": (2011, 2021),
}

# RotoGuru's own game keys.
SITE_GAME_KEY = {"dk": "dk", "fd": "fd"}

# Decision #10 -- 17-game regular season began in 2021.
def regular_season_weeks(season: int) -> list[int]:
    return list(range(1, 19)) if season >= 2021 else list(range(1, 18))


# ---------------------------------------------------------------------------
# Step 1: Fetch (cached, rate-limited) -- decision #9
# ---------------------------------------------------------------------------

def fetch_week_html(site: str, season: int, week: int, sleep: float,
                    use_cache: bool = True) -> str:
    cache_path = CACHE_DIR / f"{site}_{season}_wk{week}.html"
    if use_cache and cache_path.exists():
        return cache_path.read_text(encoding="utf-8", errors="replace")

    params = {
        "game": SITE_GAME_KEY[site],
        "scsv": "1",
        "week": str(week),
        "year": str(season),
    }
    resp = requests.get(BASE_URL, params=params, timeout=30)
    if resp.status_code != 200:
        raise SystemExit(
            f"RotoGuru returned HTTP {resp.status_code} for "
            f"site={site} season={season} week={week}. URL: {resp.url}"
        )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(resp.text, encoding="utf-8")
    time.sleep(sleep)
    return resp.text


# ---------------------------------------------------------------------------
# Step 2: Parse the semi-colon block + ASSERT year/week -- decision #1
# ---------------------------------------------------------------------------

PRE_RE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.DOTALL | re.IGNORECASE)


def parse_scsv(page_html: str, site: str, season: int, week: int) -> pd.DataFrame:
    """Extract the semi-colon delimited table and hard-fail if the response
    is not actually the season/week that was asked for (decision #1)."""
    blocks = PRE_RE.findall(page_html)
    scsv_block = None
    for block in blocks:
        text = html.unescape(re.sub(r"<[^>]+>", "", block)).strip()
        if text.lower().startswith("week;year;"):
            scsv_block = text
            break

    if scsv_block is None:
        raise SystemExit(
            f"Could not find a semi-colon delimited <pre> block for site={site} "
            f"season={season} week={week}. RotoGuru's page layout may have "
            f"changed, or scsv=1 was dropped from the request. Inspect the "
            f"cached HTML at {CACHE_DIR / f'{site}_{season}_wk{week}.html'} "
            f"before changing this parser."
        )

    lines = [ln for ln in scsv_block.splitlines() if ln.strip()]
    header = [h.strip() for h in lines[0].split(";")]
    rows = [ln.split(";") for ln in lines[1:]]
    rows = [r for r in rows if len(r) == len(header)]

    if not rows:
        raise SystemExit(
            f"Semi-colon block for site={site} season={season} week={week} "
            f"parsed to zero data rows (header was: {header}). Not treating "
            f"this as an empty week -- a real empty week should still return "
            f"a header with no rows only for weeks that were never played."
        )

    df = pd.DataFrame(rows, columns=header)

    # --- DECISION #1: the assertion this whole module exists to get right ---
    returned_years = sorted(set(df["Year"].astype(str).str.strip()))
    returned_weeks = sorted(set(df["Week"].astype(str).str.strip()))

    if returned_years != [str(season)]:
        raise SystemExit(
            f"YEAR MISMATCH -- refusing to ingest.\n"
            f"  Requested season: {season}\n"
            f"  Response contains Year: {returned_years}\n"
            f"RotoGuru silently serves its newest available season when the "
            f"requested year is out of range (verified: year=2024 returns "
            f"2021 data with no error). Coverage for '{site}' is "
            f"{SITE_COVERAGE[site][0]}-{SITE_COVERAGE[site][1]}. Do NOT "
            f"'fix' this by relaxing the check -- the data would be wrong."
        )

    if returned_weeks != [str(week)]:
        raise SystemExit(
            f"WEEK MISMATCH -- refusing to ingest.\n"
            f"  Requested week: {week}\n"
            f"  Response contains Week: {returned_weeks}\n"
            f"Same silent-fallback risk as the year check above."
        )

    return df


# ---------------------------------------------------------------------------
# Step 3: Normalize into a tidy per-season frame
# ---------------------------------------------------------------------------

def _points_col(header: list[str]) -> str:
    """RotoGuru names the points/salary columns per game ('DK points',
    'FD points'). Read them from the header rather than hardcoding, so a
    site key change fails loudly at the lookup instead of silently picking
    the wrong column."""
    for col in header:
        if col.lower().endswith("points"):
            return col
    raise SystemExit(f"No '*points' column found in RotoGuru header: {header}")


def _salary_col(header: list[str]) -> str:
    for col in header:
        if col.lower().endswith("salary"):
            return col
    raise SystemExit(f"No '*salary' column found in RotoGuru header: {header}")


def reshape_name(raw: str) -> str:
    """Decision #6: 'Mahomes II, Patrick' -> 'Patrick Mahomes II'.
    Defenses have no comma ('Arizona') and pass through unchanged."""
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    if "," not in raw:
        return raw
    last, first = raw.split(",", 1)
    return f"{first.strip()} {last.strip()}".strip()


def tidy_season(frames: dict[int, pd.DataFrame], site: str) -> pd.DataFrame:
    """Concatenate per-week frames into one tidy season frame."""
    tidy = []
    for week, df in sorted(frames.items()):
        header = list(df.columns)
        pts_col, sal_col = _points_col(header), _salary_col(header)

        out = pd.DataFrame({
            "week": pd.to_numeric(df["Week"], errors="raise").astype(int),
            "season": pd.to_numeric(df["Year"], errors="raise").astype(int),
            "gid": df["GID"].astype(str).str.strip(),
            "name": df["Name"].map(reshape_name),
            "rotoguru_position": df["Pos"].astype(str).str.strip(),
            # Decision #11 -- normalized here via ingest_salaries.py's own
            # normalize_team(), not a local copy. Safe to do this early
            # because normalize_team is idempotent (a value already in
            # nflverse form maps to itself), so ingest_salaries.py
            # re-normalizing the emitted TeamAbbrev is a no-op.
            "team": df["Team"].map(lambda t: normalize_team(t, site)),
            "home_away": df["h/a"].astype(str).str.strip(),
            "opponent": df["Oppt"].map(lambda t: normalize_team(t, site)),
            "actual_points": pd.to_numeric(df[pts_col], errors="coerce"),
            # Decision #5: blank/"N/A" salary -> NaN here, EXCLUDED later.
            "salary": pd.to_numeric(
                df[sal_col].astype(str).str.replace(r"[$,]", "", regex=True).str.strip(),
                errors="coerce",
            ),
        })
        tidy.append(out)

    season_df = pd.concat(tidy, ignore_index=True)

    n_bad_points = season_df["actual_points"].isna().sum()
    if n_bad_points:
        raise SystemExit(
            f"{n_bad_points} row(s) had an unparseable actual-points value. "
            f"Points are the scoring truth for the backtest harness -- not "
            f"silently dropping or zero-filling them. Inspect the cached HTML."
        )

    return season_df


# ---------------------------------------------------------------------------
# Step 4: Emit a per-week file shaped like the site's own export -- decision #2
# ---------------------------------------------------------------------------

def derive_avg_points(season_df: pd.DataFrame, week: int) -> pd.Series:
    """Decision #4: season-to-date average from weeks STRICTLY BEFORE the
    target week. Same lookahead cutoff as projections_baseline.py."""
    prior = season_df[season_df["week"] < week]
    if prior.empty:
        return pd.Series(dtype=float)
    return prior.groupby("gid")["actual_points"].mean()


def write_week_file(season_df: pd.DataFrame, site: str, season: int,
                    week: int, out_dir: Path) -> tuple[Path, int, int]:
    cfg = SITE_CONFIGS[site]
    defense_label = sorted(cfg["defense_position_values"])[0]  # decision #7

    wk = season_df[season_df["week"] == week].copy()
    if wk.empty:
        raise SystemExit(f"No rows for site={site} season={season} week={week}.")

    # Decision #5 -- drop unpurchasable rows, count them, never zero-fill.
    n_total = len(wk)
    no_salary = wk["salary"].isna()
    n_dropped = int(no_salary.sum())
    wk = wk[~no_salary].copy()

    # Decision #7 -- 'Def' -> this site's own defense label.
    wk["position_out"] = wk["rotoguru_position"].where(
        wk["rotoguru_position"].str.lower() != "def", defense_label
    )

    # Decision #4 -- derived, lookahead-guarded, BLANK when unavailable.
    avg = derive_avg_points(season_df, week)
    wk["avg_points"] = wk["gid"].map(avg)

    if site == "dk":
        out = pd.DataFrame({
            "Name": wk["name"],
            "Position": wk["position_out"],
            "TeamAbbrev": wk["team"],
            "Salary": wk["salary"].astype(int),
            "ID": wk["gid"],
            "Roster Position": wk["position_out"],
            "Game Info": wk["team"] + "@" + wk["opponent"],
            "AvgPointsPerGame": wk["avg_points"],
        })
    else:
        out = pd.DataFrame({
            "Position": wk["position_out"],
            "Team": wk["team"],
            "Salary": wk["salary"].astype(int),
            "Id": wk["gid"],
            "Nickname": wk["name"],
            "First Name": wk["name"].str.split().str[0],
            "Last Name": wk["name"].str.split().str[1:].str.join(" "),
            "Opponent": wk["opponent"],
            # Emitted as AvgPointsPerGame, not FD's real "FPPG" -- see the
            # FD note in this module's closing comment block.
            "AvgPointsPerGame": wk["avg_points"],
        })

    # Decision #3 -- make the non-real-ID provenance impossible to miss.
    out["id_source"] = "rotoguru_gid"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"rotoguru_{site}_{season}_wk{week}.csv"
    out.to_csv(out_path, index=False)
    return out_path, n_total, n_dropped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def ingest_season(site: str, season: int, weeks: list[int], sleep: float,
                  use_cache: bool, out_dir: Path) -> pd.DataFrame:
    lo, hi = SITE_COVERAGE[site]
    if not (lo <= season <= hi):
        raise SystemExit(
            f"Season {season} is outside RotoGuru's verified coverage for "
            f"'{site}' ({lo}-{hi}). Refusing to request it: RotoGuru does "
            f"NOT error on an out-of-range year, it silently returns its "
            f"newest season, so a request here would look like it worked "
            f"and give you {hi} data labelled {season}."
        )

    frames = {}
    for week in weeks:
        page = fetch_week_html(site, season, week, sleep, use_cache)
        frames[week] = parse_scsv(page, site, season, week)
        print(f"  [{site} {season}] week {week}: {len(frames[week])} rows")

    season_df = tidy_season(frames, site)

    total_dropped = 0
    for week in weeks:
        path, n_total, n_dropped = write_week_file(
            season_df, site, season, week, out_dir
        )
        total_dropped += n_dropped
        note = f"  ({n_dropped} row(s) dropped: no salary)" if n_dropped else ""
        print(f"  wrote {path.name}: {n_total - n_dropped} players{note}")

    if total_dropped:
        print(f"  NOTE: {total_dropped} player-week row(s) had no salary "
              f"(scored, but not on that week's slate). Excluded from the "
              f"salary files, retained in the actuals file. See decision #5.")

    actuals_path = DATA_DIR / f"rotoguru_actuals_{site}_{season}.csv"
    season_df.to_csv(actuals_path, index=False)
    print(f"  wrote {actuals_path.relative_to(REPO_ROOT)} "
          f"({len(season_df)} player-weeks, scoring truth for the harness)")

    return season_df


def main():
    parser = argparse.ArgumentParser(
        description="Ingest historical DFS salaries + actual points from RotoGuru."
    )
    parser.add_argument("--site", required=True, choices=["dk", "fd"])
    parser.add_argument("--season", type=int, nargs="+", required=True,
                        help="One or more seasons, e.g. --season 2021 or --season 2019 2020 2021")
    parser.add_argument("--weeks", type=int, nargs="+", default=None,
                        help="Specific weeks (default: full REG season for that year)")
    parser.add_argument("--sleep", type=float, default=2.0,
                        help="Seconds between requests (default 2.0 -- please don't lower this)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Re-fetch even if a cached response exists")
    parser.add_argument("--out-dir", default=str(RAW_SALARY_DIR))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    lo, hi = SITE_COVERAGE[args.site]
    print(f"RotoGuru coverage for {SITE_CONFIGS[args.site]['label']}: {lo}-{hi} "
          f"(verified live 2026-07-25; nothing after {hi} exists)")

    for season in args.season:
        weeks = args.weeks if args.weeks else regular_season_weeks(season)
        print(f"\n=== {SITE_CONFIGS[args.site]['label']} {season} "
              f"(weeks {weeks[0]}-{weeks[-1]}) ===")
        ingest_season(args.site, season, weeks, args.sleep,
                      not args.no_cache, out_dir)

    print("\nNext step -- run each week through the existing matcher "
          "(decision #2), e.g.:")
    s0 = args.season[0]
    w0 = (args.weeks or regular_season_weeks(s0))[0]
    print(f"  python3 scripts/ingest_salaries.py --site {args.site} "
          f"--season {s0} \\\n"
          f"      --raw data/raw_salaries/rotoguru_{args.site}_{s0}_wk{w0}.csv \\\n"
          f"      --slate-id rotoguru_wk{w0}")
    print(f"  (requires data/weekly_stats_{s0}.parquet -- run "
          f"ingest_historical.py --season {s0} first if you haven't)")


if __name__ == "__main__":
    main()
