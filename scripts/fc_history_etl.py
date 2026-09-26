"""
fc_history_etl.py
=================

Plain-Python ETL (no Claude, no network) for Fantasy Cruncher "Lineup Rewind" exports.

Reads every data/fc_history/{season}/fc_{site}_{season}_wk{WW}_{slate}_{contest}.csv, normalizes the
two export layouts (wide 78-column grouped header, narrow 27-column header) into one table and writes
QA output. It only standardizes -- no player-id mapping and no modeling (that is a separate step).

Outputs (all under data/fc_history/derived/, which is git-ignored; the repo is public and these are
subscription data -- never commit them):
    fc_master.csv     one row per player per file (columns below + file metadata)
    qa_files.csv      one row per file: rows, ownership totals, nulls, layout, warnings
    qa_report.txt     coverage by season, missing weeks, duplicates, unparsed names, flagged files
    etl_run.log       appended run log

Filename convention (from Greg's exports):
    fc_dk_2025_wk05_main_single_entry.csv   fc_dk_2026_wk01_main_mme.csv   fc_dk_2026_wk02_main_3max.csv
    showdown: fc_dk_{season}_wk{WW}_sd_{TEAMS}_{type}.csv (anything after wkNN is kept as `slate_raw`;
    a trailing _single_entry/_3max/_mme/_cash/_se is the contest type)

Facts this relies on (verified on the first five files, 2026-09-25): the header row is the row whose
first cell is "Player"; a wide file has a group row above it; FC Proj / Score / Salary are identical
across contests within a week; Own% is post-lock and contest specific.

Run:  python scripts/fc_history_etl.py
"""

from __future__ import annotations

import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "fc_history"
OUT = SRC / "derived"

FNAME = re.compile(r"^fc_(?P<site>dk|fd)_(?P<season>\d{4})_wk(?P<week>\d{1,2})_(?P<rest>.+)$", re.I)
CONTEST_TYPES = ("single_entry", "3max", "mme", "cash", "se")
COLS = {  # output name -> FC column name
    "player": "Player", "inj": "Inj", "pos": "Pos", "pdepth": "pDepth", "salary": "Salary", "team": "Team",
    "opp": "Opp", "vegas_pts": "VegasPts", "stdv": "STDV", "floor": "Floor", "ceiling": "Ceiling",
    "fc_proj": "FC Proj", "own_pct": "Own%", "score": "Score", "val": "Val",
}
NUMERIC = ["salary", "vegas_pts", "stdv", "floor", "ceiling", "fc_proj", "own_pct", "score", "val"]
EXPECTED_WEEKS = range(1, 19)


def norm_name(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_name(stem: str):
    m = FNAME.match(stem)
    if not m:
        return None
    rest = m.group("rest")
    contest = None
    low = rest.lower()
    for t in CONTEST_TYPES:
        if low == t or low.endswith("_" + t):
            contest = t
            rest = rest[: len(rest) - len(t) - 1] if low != t else ""
            break
    slate = rest or "unknown"
    kind = "showdown" if slate.lower().startswith(("sd", "showdown")) else "classic"
    return {"site": m.group("site").lower(), "season": int(m.group("season")), "week": int(m.group("week")),
            "slate_raw": slate, "slate_kind": kind, "contest": contest or "unknown"}


def load_file(path: Path):
    raw = pd.read_csv(path, header=None, dtype=str)
    hits = raw.index[raw.iloc[:, 0].astype(str).str.strip().eq("Player")]
    if len(hits) == 0:
        raise ValueError("no header row with 'Player' in the first column")
    h = int(hits[0])
    cols = [str(c).strip() if pd.notna(c) else "" for c in raw.iloc[h]]
    body = raw.iloc[h + 1:].copy()
    body.columns = range(len(cols))
    out = {}
    missing = []
    for key, name in COLS.items():
        idx = [i for i, c in enumerate(cols) if c == name]
        if idx:
            out[key] = body[idx[0]].astype(str).str.strip().replace({"nan": np.nan, "": np.nan})
        else:
            out[key] = pd.Series(np.nan, index=body.index)
            missing.append(name)
    df = pd.DataFrame(out)
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c].astype("string").str.rstrip("%"), errors="coerce")
    df = df[df["player"].notna()].reset_index(drop=True)
    df["name_key"] = df["player"].map(norm_name)
    return df, ("wide" if len(cols) > 40 else "narrow"), len(cols), missing


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    files = sorted(p for p in SRC.glob("*/*.csv") if p.parent.name.isdigit())
    log = [f"=== fc_history_etl {started:%Y-%m-%d %H:%M:%S}: {len(files)} file(s) under {SRC}"]
    if not files:
        log.append("No files found; nothing to do.")
        (OUT / "etl_run.log").open("a", encoding="utf-8").write("\n".join(log) + "\n")
        print("\n".join(log))
        return 1

    frames, qa, unparsed, errors = [], [], [], []
    for p in files:
        meta = parse_name(p.stem)
        if meta is None:
            unparsed.append(p.name)
            continue
        try:
            df, layout, ncols, missing = load_file(p)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{p.name}: {type(exc).__name__}: {exc}")
            continue
        for k, v in meta.items():
            df[k] = v
        df["layout"] = layout
        df["source_file"] = p.name
        frames.append(df)
        warns = []
        if missing:
            warns.append("missing columns: " + ",".join(missing))
        own_sum = float(df["own_pct"].sum())
        if meta["slate_kind"] == "classic" and not (850 <= own_sum <= 905):
            warns.append(f"classic ownership sums to {own_sum:.0f} (expected ~890-900)")
        if int((df["own_pct"] > 0).sum()) == 0:
            warns.append("no player has ownership > 0")
        if df["score"].notna().sum() == 0:
            warns.append("no actual scores")
        if df["fc_proj"].notna().sum() == 0:
            warns.append("no FC projections")
        by_pos = df.groupby("pos")["own_pct"].sum().round(0).to_dict()
        qa.append({**meta, "file": p.name, "layout": layout, "ncols": ncols, "rows": len(df),
                   "own_sum": round(own_sum, 1), "own_gt0": int((df["own_pct"] > 0).sum()),
                   "own_by_pos": str(by_pos), "score_null": int(df["score"].isna().sum()),
                   "fcproj_null": int(df["fc_proj"].isna().sum()), "salary_null": int(df["salary"].isna().sum()),
                   "warnings": "; ".join(warns)})

    if not frames:
        log.append("No parsable files.")
        log += ["UNPARSED: " + n for n in unparsed] + ["ERROR: " + e for e in errors]
        (OUT / "etl_run.log").open("a", encoding="utf-8").write("\n".join(log) + "\n")
        print("\n".join(log))
        return 1

    master = pd.concat(frames, ignore_index=True)
    qa_df = pd.DataFrame(qa)
    master.to_csv(OUT / "fc_master.csv", index=False)
    qa_df.to_csv(OUT / "qa_files.csv", index=False)

    rep = [f"FC history QA -- generated {started:%Y-%m-%d %H:%M:%S}",
           f"files parsed {len(qa_df)}  |  unparsed names {len(unparsed)}  |  read errors {len(errors)}  |  master rows {len(master)}", ""]
    classic = qa_df[qa_df.slate_kind == "classic"]
    rep.append("CLASSIC coverage (files per season x contest type):")
    rep.append(classic.pivot_table(index="season", columns="contest", values="file", aggfunc="count", fill_value=0).to_string())
    rep.append("")
    rep.append("Weeks with NO single-entry classic main file (expected 1-18, main slate):")
    se = classic[(classic.contest.isin(["single_entry", "se"])) & (classic.slate_raw.str.lower() == "main")]
    for season in sorted(qa_df.season.unique()):
        have = set(se[se.season == season].week)
        gap = [w for w in EXPECTED_WEEKS if w not in have]
        rep.append(f"  {season}: have {len(have)}, missing {gap}")
    sd = qa_df[qa_df.slate_kind == "showdown"]
    rep.append("")
    rep.append(f"SHOWDOWN files: {len(sd)}" + ("" if sd.empty else "  by season: " + str(sd.groupby('season').size().to_dict())))
    other = classic[~classic.slate_raw.str.lower().isin(["main"])]
    rep.append(f"CLASSIC non-main slates (early/afternoon/etc.): {len(other)}" + ("" if other.empty else "  " + str(other.groupby('slate_raw').size().to_dict())))
    dups = qa_df[qa_df.duplicated(["site", "season", "week", "slate_raw", "contest"], keep=False)]
    rep.append("")
    rep.append(f"DUPLICATE (site, season, week, slate, contest): {len(dups)} file(s)" + ("" if dups.empty else "\n  " + "\n  ".join(dups.file)))
    rep.append("")
    flagged = qa_df[qa_df.warnings != ""]
    rep.append(f"FLAGGED files: {len(flagged)}")
    for _, r in flagged.iterrows():
        rep.append(f"  {r.file}: {r.warnings}")
    if unparsed:
        rep.append("\nUNPARSED file names (rename to fc_{site}_{season}_wk{WW}_{slate}_{type}.csv):")
        rep += ["  " + n for n in unparsed]
    if errors:
        rep.append("\nREAD ERRORS:")
        rep += ["  " + e for e in errors]
    rep.append(f"\nlayouts: {qa_df.layout.value_counts().to_dict()}")
    (OUT / "qa_report.txt").write_text("\n".join(rep) + "\n", encoding="utf-8")

    log.append(f"parsed {len(qa_df)} files -> {len(master)} rows; flagged {len(flagged)}; unparsed {len(unparsed)}; errors {len(errors)}; "
               f"took {(datetime.now() - started).total_seconds():.1f}s")
    with (OUT / "etl_run.log").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(log) + "\n")
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
