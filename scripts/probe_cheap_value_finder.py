"""Data-driven cheap-value finder -- built 2026-10-30 to answer "are we
reliably finding the cheap players with real opportunity" directly from
our own trailing usage data, instead of asking a chat model to guess at
salaries it has repeatedly told us it doesn't reliably know (see
AI_PROBE_QUESTION_TEMPLATES.md and the 2026-10-30 session discussion).

Uses the same _wrw_trailing_usage() the vacancy-redistribution mechanisms
are built on (probe_team_usage_rank.py's single-team version, extended to
scan every team on the slate at once), joined against this week's REAL
salary from our own DK/FD files -- no guessing, no stale web data.

Usage:
    python3 scripts/probe_cheap_value_finder.py
    python3 scripts/probe_cheap_value_finder.py --season 2026 --week 8
"""
import argparse
import csv
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from statline_model import _wrw_trailing_usage, WRW_TE_PARAMS  # noqa: E402
import json

THRESHOLDS = {
    ("dk", "WR"): 4500, ("fd", "WR"): 6000,
    ("dk", "RB"): 6000, ("fd", "RB"): 7000,
    ("dk", "TE"): 4500, ("fd", "TE"): 5500,
}


def latest(pattern: str) -> str | None:
    c = glob.glob(pattern)
    return max(c, key=os.path.getmtime) if c else None


def dedup_cpt_flex(rows: list[dict]) -> list[dict]:
    """Showdown slates carry each player as two rows (roster_role CPT and
    FLEX, CPT salary = 1.5x FLEX, same player_id). Collapse to one row per
    player, preferring the FLEX row since it carries the real/base salary
    -- CPT's inflated price isn't a second distinct player or a floor
    worth checking separately. Classic rows have no roster_role duplicate
    and pass through unchanged."""
    by_id: dict[str, dict] = {}
    for r in rows:
        pid = r.get("player_id")
        role = r.get("roster_role")
        if pid not in by_id or role == "FLEX":
            by_id[pid] = r
    return list(by_id.values())


def load_salary_and_teams(site: str, slate_path: str | None = None
                           ) -> tuple[dict[str, dict], list[str]]:
    path = slate_path or latest(f"output/final_projections_{site}_{site}_classic_wk*_main_*.csv")
    if not path:
        return {}, []
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows = dedup_cpt_flex(rows)
    info = {r["player_id"]: r for r in rows}
    teams = sorted({r["team"] for r in rows if r.get("team")})
    return info, teams


def candidates_by_position(season: int, week: int, site: str,
                            top_n: int = 5, slate_path: str | None = None,
                            team_filter: list[str] | None = None,
                            thresholds: dict[str, float] | None = None,
                            min_proj: float = 0.0
                            ) -> dict[str, list[dict]]:
    """Returns {pos: [top_n candidate dicts]} for one site, ranked by
    pts/$1000 efficiency. Factored out 2026-10-31 so
    probe_ai_chat_weekly_questions.py can fan out NAMED questions onto
    these exact candidates instead of asking the chat an open "what's
    cheap value" question -- per 2026-10-31 feedback, open fringe-value
    questions have been the weakest-performing category all session;
    named ones (same pattern as the B/C injury questions) have been the
    strongest.

    slate_path, added for showdown (2026-11-05): classic auto-glob can't
    find a showdown file (different filename shape, no "_main_"), so the
    caller passes the exact file it already resolved instead of this
    function guessing a second time. team_filter scopes the candidate
    pool to a showdown slate's 2 teams instead of every team on the slate.
    thresholds overrides the default classic THRESHOLDS per position
    (showdown's smaller, cheaper pool needs its own floors). min_proj
    drops players below an absolute projection floor before ranking by
    pts/$1000 efficiency -- needed for showdown (2026-11-05): that ratio
    blows up for a $200 scrub with a ~1pt projection, so an efficiency-only
    rank can put real noise ahead of real candidates when the pool is
    this cheap. Classic's floors never go low enough to need this, so it
    defaults to 0 (no-op) there.
    """
    p = json.loads(WRW_TE_PARAMS.read_text(encoding="utf-8"))
    salary_info, teams = load_salary_and_teams(site, slate_path=slate_path)
    if not teams:
        return {}
    if team_filter:
        teams = [t for t in teams if t in team_filter]
    ag, tvr = _wrw_trailing_usage(season, week, teams, p)
    if ag is None or ag.empty:
        return {}

    rows = []
    for (team, pid), r in ag.iterrows():
        info = salary_info.get(pid)
        if not info or not info.get("salary"):
            continue
        status = (info.get("injury_status") or "").upper()
        if status == "OUT":
            # Trailing usage is built from games BEFORE this week, so an
            # OUT player's pre-injury usage still shows up here even
            # though he's not playing. Caught live 2026-10-30: Davante
            # Adams topped the DK WR list despite being out 6-10 weeks.
            continue
        sal = float(info["salary"])
        pos = r["pos"]
        if pos not in ("WR", "RB", "TE"):
            continue
        team_vol = tvr.loc[team] if team in tvr.index else None
        if team_vol is None:
            continue
        tgt_pg = r["sh_tgt"] * float(team_vol["ttgt"])
        car_pg = r["sh_car"] * float(team_vol["tcar"])
        touches_pg = tgt_pg + car_pg
        proj = float(info.get("final_projection") or 0.0)
        eff = proj / sal * 1000 if sal else 0.0
        rows.append({
            "name": info["player_name"], "pos": pos, "team": team,
            "sal": sal, "tgt_pg": tgt_pg, "touches_pg": touches_pg,
            "sh_tgt": r["sh_tgt"], "implied": info.get("implied_total", ""),
            "status": status, "proj": proj, "eff": eff,
        })

    out: dict[str, list[dict]] = {}
    for pos in ("WR", "RB", "TE"):
        floor = thresholds[pos] if thresholds else THRESHOLDS[(site, pos)]
        pool = [x for x in rows if x["pos"] == pos and x["sal"] < floor and x["proj"] >= min_proj]
        # Ranked by points-per-$1000 efficiency -- what the optimizer
        # actually uses -- not raw usage. Caught live 2026-10-30: a
        # usage-only ranking missed real plays (Flournoy) that score
        # well on efficiency despite modest target share (yards/TD rate
        # matter too), which looked like a false "blind spot" until
        # checked against real built lineups.
        pool.sort(key=lambda x: -x["eff"])
        out[pos] = pool[:top_n]
    return out


def latest_lineup_pool(slate_token: str) -> str | None:
    """slate_token is a final_projections filename with the
    'final_projections_' prefix and '.csv' suffix stripped (e.g.
    'dk_dk_classic_wk9_main_08Nov2026') -- finds the matching
    lineups_multi_<token>_*.csv from the real 100-lineup build, if one
    exists yet. Added 2026-11-07."""
    return latest(f"output/lineups_multi_{slate_token}_*.csv")


def build_pool_candidates(lineup_csv_path: str, site: str,
                           exclude_names: set[str] | None = None,
                           thresholds: dict[str, float] | None = None
                           ) -> dict[str, list[dict]]:
    """Distinct cheap WR/RB/TE actually rostered somewhere in the real
    built lineup pool, grouped by position. Added 2026-11-07 per user
    feedback: `candidates_by_position()`'s top-N-by-efficiency list is a
    *proxy* for what the solver will pick -- a real salary-saver can rank
    outside that cutoff and never get asked about, which is exactly the
    gap between the probe's output and the actual 100-lineup build the
    user was describing. This reads what the solver ACTUALLY picked
    instead of re-guessing it, so nothing real can fall outside a top-N
    window. It's additive to candidates_by_position, not a replacement --
    the user explicitly wants to keep the existing fringe-value question
    category as-is and just stop missing names that don't make that list.

    Deliberately membership-only: no count of how many of the 100
    lineups include a player, no percentage. That's the lineup-pool
    exposure metric that was already ruled out as a cross-check signal
    (see feedback_ai_probe_crosscheck_not_exposure memory, 2026-10-31) --
    exposure is a read on the solver's combinatorics across the whole
    pool, not on whether one player's own projection is right, so it must
    never decide a verdict. But "did the solver actually use him anywhere
    in a real build" is a different question -- it only decides who gets
    ASKED about, never whether the answer is correct. That's still judged
    purely from season_avg/recent_form/matchup_factor/vegas_factor, same
    as every other candidate.
    """
    with open(lineup_csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    exclude_names = exclude_names or set()
    seen: dict[str, dict] = {}
    for r in rows:
        pos = r.get("position")
        if pos not in ("WR", "RB", "TE"):
            continue
        name = r.get("player_name")
        if not name or name in exclude_names or name in seen:
            continue
        try:
            sal = float(r.get("salary") or 0)
        except ValueError:
            continue
        floor = (thresholds or THRESHOLDS).get((site, pos), 0)
        if sal <= 0 or sal >= floor:
            continue
        seen[name] = {
            "name": name, "pos": pos, "team": r.get("team"), "sal": sal,
            "proj": float(r.get("projection") or 0.0),
        }
    out: dict[str, list[dict]] = {"WR": [], "RB": [], "TE": []}
    for v in seen.values():
        out[v["pos"]].append(v)
    for pos in out:
        out[pos].sort(key=lambda x: x["sal"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--week", type=int, default=8)
    args = ap.parse_args()

    for site in ("dk", "fd"):
        by_pos = candidates_by_position(args.season, args.week, site)
        if not by_pos:
            print(f"No {site.upper()} classic main slate / usage data found -- skipping.")
            continue
        print(f"\n{'='*70}\n{site.upper()} cheap value finder (wk{args.week})\n{'='*70}")
        for pos in ("WR", "RB", "TE"):
            floor = THRESHOLDS[(site, pos)]
            usage_metric = "touches_pg" if pos == "RB" else "tgt_pg"
            print(f"\n-- {pos} under ${floor:,} ({site.upper()}), by pts/$1k efficiency --")
            for x in by_pos[pos]:
                flag = f" [{x['status']}]" if x['status'] and x['status'] != "ACTIVE" else ""
                print(f"  {x['name']:22s} {x['team']:4s} ${x['sal']:>6,.0f}  "
                      f"proj={x['proj']:5.1f}  eff={x['eff']:5.2f}  "
                      f"{usage_metric}={x[usage_metric]:5.1f}  tgt_share={x['sh_tgt']:5.1%}  "
                      f"implied_total={x['implied']}{flag}")


if __name__ == "__main__":
    main()
