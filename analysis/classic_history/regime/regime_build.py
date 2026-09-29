"""gmscott81 regime-change study, step 1: re-parse ONLY the classic contests gmscott81 entered.

Reuses lineup_study_build.parse() unchanged (source-patched in memory to also return gmscott81's roster
player indices). Writes raw-derived caches to data/fc_history/derived/classic_regime/ (gitignored, never commit).
Week/season metadata fallbacks are skipped ({}): the few metadata-less players get position from roster slot
and salary from the cap bound, exactly as the main build does when no metadata exists.

    python analysis/classic_history/regime/regime_build.py
"""
import os, sys, glob, types
from multiprocessing import Pool
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CH = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(CH))
DER = os.path.join(ROOT, "data", "fc_history", "derived", "classic_regime")

src = open(os.path.join(CH, "lineup_study_build.py"), encoding="utf-8").read()
src = src.replace("    return ent, pl, qa\n",
                  "    qa['_meM'] = M[is_me].tolist(); qa['_ids'] = ids\n    return ent, pl, qa\n", 1)
lsb = types.ModuleType("lsb"); lsb.__file__ = os.path.join(CH, "lineup_study_build.py")
exec(compile(src, lsb.__file__, "exec"), lsb.__dict__)

KEEP = ["rank", "points", "payout_c", "is_me", "own_sum", "proj_sum", "proj_ok", "qb_own", "qb_own_rank",
        "n_top5own", "n_lt2own", "sal_used", "stack_rec", "bb", "punts", "studs", "dupes", "max_team"]


def work(f):
    base = os.path.basename(f)[:-8]
    ent, pl, qa = lsb.parse(f, {}, {}, {})
    ent[KEEP].to_parquet(os.path.join(DER, "entries", base + ".parquet"), index=False)
    pl = pl[["pid", "pos", "team", "sal", "proj", "fp", "own", "own_cash", "proj_own"]].copy()
    pl.to_parquet(os.path.join(DER, "players", base + ".parquet"), index=False)
    ids = qa.pop("_ids"); meM = qa.pop("_meM")
    rows = [{"file": base, "entry": k, "slot": s, "pid": ids[i]} for k, r in enumerate(meM) for s, i in enumerate(r)]
    print(base, len(ent), int(ent.is_me.sum()), flush=True)
    return rows


def main():
    qa = pd.read_csv(os.path.join(CH, "out", "cl_qa.csv"))
    files = qa.loc[qa.me_entries > 0, "file"].tolist()
    paths = [os.path.join(lsb.SRC, f) for f in files]
    for d in ("entries", "players"):
        os.makedirs(os.path.join(DER, d), exist_ok=True)
    with Pool(int(os.environ.get("NPROC", "6"))) as p:
        res = p.map(work, paths)
    pd.DataFrame([r for rr in res for r in rr]).to_parquet(os.path.join(DER, "me_rosters.parquet"), index=False)


if __name__ == "__main__":
    main()
