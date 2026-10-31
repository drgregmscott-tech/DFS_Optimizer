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


def load_salary_and_teams(site: str) -> tuple[dict[str, dict], list[str]]:
    path = latest(f"output/final_projections_{site}_{site}_classic_wk*_main_*.csv")
    if not path:
        return {}, []
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    info = {r["player_id"]: r for r in rows}
    teams = sorted({r["team"] for r in rows if r.get("team")})
    return info, teams


def candidates_by_position(season: int, week: int, site: str,
                            top_n: int = 5) -> dict[str, list[dict]]:
    """Returns {pos: [top_n candidate dicts]} for one site, ranked by
    pts/$1000 efficiency. Factored out 2026-10-31 so
    probe_ai_chat_weekly_questions.py can fan out NAMED questions onto
    these exact candidates instead of asking the chat an open "what's
    cheap value" question -- per 2026-10-31 feedback, open fringe-value
    questions have been the weakest-performing category all session;
    named ones (same pattern as the B/C injury questions) have been the
    strongest."""
    p = json.loads(WRW_TE_PARAMS.read_text(encoding="utf-8"))
    salary_info, teams = load_salary_and_teams(site)
    if not teams:
        return {}
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
        floor = THRESHOLDS[(site, pos)]
        pool = [x for x in rows if x["pos"] == pos and x["sal"] < floor]
        # Ranked by points-per-$1000 efficiency -- what the optimizer
        # actually uses -- not raw usage. Caught live 2026-10-30: a
        # usage-only ranking missed real plays (Flournoy) that score
        # well on efficiency despite modest target share (yards/TD rate
        # matter too), which looked like a false "blind spot" until
        # checked against real built lineups.
        pool.sort(key=lambda x: -x["eff"])
        out[pos] = pool[:top_n]
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
