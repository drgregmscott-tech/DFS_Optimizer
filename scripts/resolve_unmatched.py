"""
resolve_unmatched.py
====================

Propose data/name_mapping.csv rows for the RECURRING unmatched names that
the batch match surfaced -- the real, rosterable players (Robbie Anderson,
Gabe Davis, ...) who miss the nflverse join in every week due to one
systematic name discrepancy, as distinct from the inert scrub tail.

TWO PHASES, because a wrong player_id is worse than an unmatched player.
An unmatched player is simply absent from the pool; a MISmapped player_id
silently attributes one player's salary to another player's outcomes, which
corrupts every backtest that touches that week with no error. So this tool
never writes a mapping from a guess:

  Phase 1 (default) -- PROPOSE. Reads the unmatched logs, aggregates names
    by frequency, and for each looks up candidate player_ids in the
    weekly_stats parquets by (nickname-aware name) + team + position, then
    prints a proposal table with the EVIDENCE (matched display name, team,
    position, seasons seen, games) for you to eyeball. Writes nothing.

  Phase 2 (--write) -- COMMIT. Re-runs the same lookup and appends only the
    UNAMBIGUOUS single-candidate resolutions to data/name_mapping.csv, in
    that file's exact 6-column schema. Anything with zero or multiple
    candidates is skipped and listed for manual handling -- never
    auto-resolved.

Matching strategy, in order of confidence:
  1. Nickname-aware exact: RotoGuru's normalized name, with common
     first-name nicknames expanded bidirectionally (Gabriel<->Gabe,
     Robby<->Robbie, Michael<->Mike, Olabisi<->Bisi, ...), matched against
     the reference normalized name. This is what catches the Gabe Davis
     class, where plain substring fails (gabriel davis vs gabe davis share
     no substring).
  2. Subset-token: every token of the RotoGuru name appears in the
     reference name. Catches suffix growth (Nick Westbrook ->
     Nick Westbrook-Ikhine) and (Deonte Harris -> Deonte Harty is NOT this
     -- that's a real surname change and will show zero candidates, which
     is correct: it needs a human, see below).

  A name is only auto-written when the union of both strategies yields
  exactly ONE player_id. Team and position are attached as confirming
  evidence but deliberately NOT required to match -- a player can change
  teams between the RotoGuru row and their most-recent nflverse row, and
  requiring a team match would re-introduce the exact team-drift miss we're
  trying to resolve.

IMPORTANT -- this reads EVERY weekly_stats_{season}.parquet present, so run
it only after ingest_historical.py has pulled all the seasons you intend to
back-test. A name that resolves to one player in 2021 but a different
player in 2016 would show as MULTIPLE candidates and be skipped for manual
review -- which is the safe outcome.

Usage:
    python3 scripts/resolve_unmatched.py                 # propose (dry run)
    python3 scripts/resolve_unmatched.py --top 12        # only the N most frequent
    python3 scripts/resolve_unmatched.py --write         # commit unambiguous rows
    python3 scripts/resolve_unmatched.py --min-count 5   # ignore names seen <5x
"""

import argparse
import csv
import glob
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
LOG_DIR = REPO_ROOT / "logs"
NAME_MAPPING = DATA_DIR / "name_mapping.csv"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import normalize_name  # noqa: E402 -- one normalizer, shared

# Bidirectional first-name nicknames. Expanded both ways at lookup, so only
# one direction needs listing here. Kept deliberately small and hand-curated
# -- this is a resolver for a known list of ~12 names, not a general
# nickname engine, and an over-broad map risks a false single-candidate.
NICKNAMES = {
    "gabriel": "gabe",
    "robby": "robbie",
    "michael": "mike",
    "olabisi": "bisi",
    "dwayne": "dee",
    "joshua": "josh",
    "benjamin": "ben",
    "matthew": "matt",
    "christopher": "chris",
    "nicholas": "nick",
}


# Surname CHANGES that no fuzzy rule can (or should) reach -- a player whose
# nflverse display name shares no surname with the RotoGuru name, because
# nflverse retroactively applied a legal name change across ALL their
# historical rows. These are the residue that correctly lands in NO
# CANDIDATE: verified BY HAND, player_id confirmed against the parquet, and
# written through the same validated path as the auto-resolved names so they
# get the same schema and idempotency guarantees. Never let a fuzzy rule
# invent one of these -- "Anderson" -> "Chosen" is not a nickname.
#
# Each entry verified 2026 against real weekly_stats parquets:
#   Robby Anderson  -> 00-0032688  nflverse "Robbie Chosen" (legal name change 2022,
#                                   applied retroactively to his 2016-2021 rows)
#   Deonte Harris   -> 00-0035215  nflverse "Deonte Harty" (surname change)
MANUAL_ALIASES = {
    # normalized RotoGuru name -> (player_id, nflverse display name for the note)
    "robby anderson": ("00-0032688", "Robbie Chosen"),
    "deonte harris": ("00-0035215", "Deonte Harty"),
}


def first_name_variants(token: str) -> set[str]:
    out = {token}
    if token in NICKNAMES:
        out.add(NICKNAMES[token])
    for k, v in NICKNAMES.items():
        if v == token:
            out.add(k)
    return out


def load_reference() -> pd.DataFrame:
    paths = sorted(glob.glob(str(DATA_DIR / "weekly_stats_*.parquet")))
    if not paths:
        raise SystemExit(
            f"No weekly_stats_*.parquet in {DATA_DIR}. Run ingest_historical.py first."
        )
    frames = []
    for p in paths:
        d = pd.read_parquet(
            p, columns=["player_id", "player_display_name", "position", "team", "season", "week"]
        )
        frames.append(d)
    ref = pd.concat(frames, ignore_index=True)
    ref = ref.dropna(subset=["player_id", "player_display_name", "position"])
    ref["norm"] = ref["player_display_name"].map(normalize_name)
    return ref


def collect_unmatched() -> Counter:
    """Aggregate unmatched player names across every unmatched log, weighted
    by how many weeks each appears in."""
    logs = sorted(LOG_DIR.glob("unmatched_salaries_*.csv"))
    if not logs:
        raise SystemExit(
            f"No unmatched_salaries_*.csv in {LOG_DIR}. Run batch_match_rotoguru.py first."
        )
    counter = Counter()
    for log in logs:
        try:
            df = pd.read_csv(log)
        except Exception:
            continue
        if "name" not in df.columns:
            continue
        # Defenses never have an nflverse id and are matched separately; skip.
        col_pos = "position_upper" if "position_upper" in df.columns else None
        for _, row in df.iterrows():
            if col_pos and str(row[col_pos]).upper() in {"DST", "DEF", "D"}:
                continue
            counter[str(row["name"]).strip()] += 1
    return counter


def find_candidates(name: str, ref: pd.DataFrame) -> pd.DataFrame:
    n = normalize_name(name)
    parts = n.split()
    if not parts:
        return ref.iloc[0:0]

    firsts = first_name_variants(parts[0])
    last = " ".join(parts[1:])
    nickname_norms = {f"{f} {last}".strip() for f in firsts}

    exact = ref[ref["norm"].isin(nickname_norms)]
    subset = ref[ref["norm"].apply(lambda x: all(p in x for p in parts))]

    cand = pd.concat([exact, subset]).drop_duplicates("player_id")
    return cand


def summarize_candidate(pid: str, cand_rows: pd.DataFrame) -> dict:
    sub = cand_rows[cand_rows["player_id"] == pid]
    seasons = sorted(sub["season"].unique())
    return {
        "player_id": pid,
        "display_name": sub["player_display_name"].iloc[0],
        "position": sub["position"].iloc[0],
        "teams": sorted(sub["team"].dropna().unique()),
        "seasons": f"{seasons[0]}-{seasons[-1]}" if len(seasons) > 1 else str(seasons[0]),
        "games": len(sub),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Propose (and optionally write) name_mapping.csv rows for recurring unmatched names."
    )
    parser.add_argument("--top", type=int, default=None,
                        help="Only consider the N most frequent unmatched names")
    parser.add_argument("--min-count", type=int, default=1,
                        help="Ignore names appearing in fewer than this many weeks")
    parser.add_argument("--site", default="dk",
                        help="Which site's mapping rows to write (name_mapping.csv is keyed by site)")
    parser.add_argument("--write", action="store_true",
                        help="Append unambiguous resolutions to name_mapping.csv (default: dry run)")
    args = parser.parse_args()

    ref = load_reference()
    counter = collect_unmatched()

    ranked = [(name, c) for name, c in counter.most_common() if c >= args.min_count]
    if args.top:
        ranked = ranked[:args.top]

    print(f"Reference: {ref['player_id'].nunique()} unique players across "
          f"{ref['season'].nunique()} season(s).")
    print(f"Considering {len(ranked)} unmatched name(s)"
          f"{f' (top {args.top})' if args.top else ''}"
          f"{f', seen >= {args.min_count}x' if args.min_count > 1 else ''}.\n")

    resolved, ambiguous, none = [], [], []
    manual_used = []
    for name, count in ranked:
        # Manually-verified surname changes win over any fuzzy result --
        # these were confirmed by hand against the parquet (see MANUAL_ALIASES).
        alias = MANUAL_ALIASES.get(normalize_name(name))
        if alias:
            pid, disp = alias
            sub = ref[ref["player_id"] == pid]
            if sub.empty:
                # ID not in the loaded seasons -- surface it rather than
                # writing a player_id we can't confirm is present.
                none.append((name, count))
                continue
            seasons = sorted(sub["season"].unique())
            info = {
                "player_id": pid,
                "display_name": disp,
                "position": sub["position"].iloc[0],
                "teams": sorted(sub["team"].dropna().unique()),
                "seasons": f"{seasons[0]}-{seasons[-1]}" if len(seasons) > 1 else str(seasons[0]),
                "games": len(sub),
            }
            resolved.append((name, count, info))
            manual_used.append(name)
            continue

        cand = find_candidates(name, ref)
        pids = cand["player_id"].unique()
        if len(pids) == 1:
            info = summarize_candidate(pids[0], cand)
            resolved.append((name, count, info))
        elif len(pids) == 0:
            none.append((name, count))
        else:
            ambiguous.append((name, count, [summarize_candidate(p, cand) for p in pids]))

    print("=" * 70)
    print(f"RESOLVED (single candidate -- safe to write): {len(resolved)}")
    print("=" * 70)
    for name, count, info in resolved:
        tag = "  [manual alias]" if name in manual_used else ""
        print(f"  {count:>4}x  {name:24s} -> {info['player_id']}  "
              f"{info['display_name']} ({info['position']}, "
              f"{'/'.join(info['teams'][:3])}, {info['seasons']}, {info['games']}g){tag}")

    if ambiguous:
        print("\n" + "=" * 70)
        print(f"AMBIGUOUS (multiple candidates -- NOT written, resolve by hand): {len(ambiguous)}")
        print("=" * 70)
        for name, count, infos in ambiguous:
            print(f"  {count:>4}x  {name}")
            for info in infos:
                print(f"           - {info['player_id']}  {info['display_name']} "
                      f"({info['position']}, {'/'.join(info['teams'][:3])}, {info['seasons']})")

    if none:
        print("\n" + "=" * 70)
        print(f"NO CANDIDATE (real surname change or genuine scrub -- skipped): {len(none)}")
        print("=" * 70)
        print("  These need a human: a changed surname (e.g. Deonte Harris -> Harty)")
        print("  won't fuzzy-match, and a true scrub simply has no nflverse row worth mapping.")
        for name, count in none:
            print(f"  {count:>4}x  {name}")

    if not args.write:
        print(f"\n[DRY RUN] Nothing written. Re-run with --write to append the "
              f"{len(resolved)} resolved row(s) to {NAME_MAPPING.name}.")
        return

    # ---- Phase 2: write via UPSERT, not blind append ----
    # The earlier bug: idempotency was keyed on (site, source_name,
    # player_id). A stale team-KEYED row and the corrected team-AGNOSTIC row
    # for the same player share that key, so the corrected row was silently
    # skipped and the stale row -- which only fires on ONE of the player's
    # teams -- survived. That's how Robby Anderson stayed 93x unmatched
    # after "mapping" him: his CAR row resolved his CAR weeks and missed
    # every other team.
    #
    # Fix: the write is an UPSERT keyed on (site, source_name). A new
    # resolution for a name REPLACES any prior row for that same name+site,
    # rather than being blocked by it. Rows for OTHER names/sites are
    # preserved untouched. The whole file is rewritten once, so a stale row
    # can't linger.
    if NAME_MAPPING.exists() and NAME_MAPPING.stat().st_size > 0:
        prior = pd.read_csv(NAME_MAPPING)
    else:
        prior = pd.DataFrame(
            columns=["site", "source_name", "source_team",
                     "source_position", "player_id", "notes"]
        )

    # Normalize NaN teams to empty string so the file is unambiguous.
    if "source_team" in prior.columns:
        prior["source_team"] = prior["source_team"].fillna("").astype(str).str.strip()

    new_rows = []
    for name, count, info in resolved:
        new_rows.append({
            "site": args.site,
            "source_name": name,
            # Deliberately BLANK: these are name-variant / surname-change
            # rows carrying an explicit player_id, so they must apply in
            # EVERY week regardless of which team the player was on that
            # week. A team here would re-introduce the multi-team miss this
            # whole pass exists to fix. The matcher treats blank source_team
            # as "any team" (name-keyed override).
            "source_team": "",
            "source_position": info["position"],
            "player_id": info["player_id"],
            "notes": f"auto-resolved from RotoGuru unmatched ({count} weeks); "
                     f"{info['display_name']} in nflverse; team-agnostic",
        })
    new_df = pd.DataFrame(new_rows)

    # Drop any prior rows that these new ones supersede (same site+name),
    # then concatenate. Everything else in the file is left as-is.
    superseded = set(zip(new_df["site"], new_df["source_name"]))
    keep_mask = ~prior.apply(
        lambda r: (str(r["site"]), str(r["source_name"])) in superseded, axis=1
    ) if len(prior) else pd.Series([], dtype=bool)
    kept = prior[keep_mask] if len(prior) else prior

    n_replaced = len(prior) - len(kept) if len(prior) else 0
    combined = pd.concat([kept, new_df], ignore_index=True)
    combined.to_csv(NAME_MAPPING, index=False)

    print(f"\nWrote {NAME_MAPPING} -- {len(new_df)} row(s) for site '{args.site}'"
          f"{f' ({n_replaced} stale row(s) replaced)' if n_replaced else ''}, "
          f"{len(kept)} unrelated row(s) preserved.")
    print("Next: re-run the batch matcher to lift the affected weeks:")
    print("  python3 scripts/batch_match_rotoguru.py --force")
    return

if __name__ == "__main__":
    main()
