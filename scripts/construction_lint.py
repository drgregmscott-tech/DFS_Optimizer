"""Pre-lock construction lint (WK3 postmortem parking lot, 2026-09-29).

READ-ONLY. Never changes optimizer behavior or any file except the optional
--out CSV. For every lineup in an optimizer output CSV, prints which
documented construction rules the lineup violates, so rules that are only
written down (SHOWDOWN_RULES.md, WK3_ROOT_CAUSE_FINDINGS.md, WK2_POSTMORTEM.md,
HANDOFF_classic_construction_replay.md, checklist §5) are visible at build
time. Design and rule-by-rule rationale: WK3_CONSTRUCTION_RULE_AUDIT.md §4.

Each flag carries a severity:
  backstop - rule is already enforced by a preset/flag; firing means the
             build did not use that preset (or a lock/override beat it)
  warn     - Supported-or-close evidence, not enforced; look before lock
  info     - Weak / context-dependent / preference; a prompt, not a verdict

Usage:
  python scripts/construction_lint.py output/lineups_multi_dk_<slate>.csv
      [--pool output/final_projections_dk_<slate>.csv] [--contest se|gpp]
      [--out lint.csv]
Format (classic vs Showdown) is detected from the CPT roster slot. --pool is
needed only for the ownership- and DST-price-tier checks (auto-guessed from
the lineup filename when omitted). --contest only changes the chalk-CPT check.
"""
import argparse
import os
import re
import sys

import pandas as pd

PUNT_MAX = 4000          # Phase 2 definition (wk3_postmortem_phase2.py)
QB_PRICE_WATCH = 6000    # Phase 2: cashing-field avg QB ~$5,850
SD_CHEAP_TIER = (600, 1000)
PASS_CATCHERS = {"WR", "TE"}


def _guess_pool(lineup_path):
    base = os.path.basename(lineup_path)
    m = re.match(r"lineups_multi_(.+?)\.csv$", base) or re.match(r"lineups_(.+?)\.csv$", base)
    if not m:
        return None
    stem = m.group(1)
    d = os.path.dirname(lineup_path) or "."
    cands = [os.path.join(d, f"final_projections_{stem}.csv")]
    # strip a trailing _<client_id> suffix
    cands.append(os.path.join(d, "final_projections_" + re.sub(r"_[^_]+$", "", stem) + ".csv"))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def _flag(out, lid, rule, sev, evidence, msg):
    out.append(dict(lineup_id=lid, rule=rule, severity=sev, evidence=evidence, detail=msg))


def lint_showdown(lu, pool, contest):
    out = []
    dsts = own_cpt = None
    if pool is not None:
        p = pool.copy()
        if "roster_role" in p.columns:
            dsts = p[(p["position"] == "DST") & (p["roster_role"].astype(str).str.upper() == "FLEX")]
        else:
            dsts = p[p["position"] == "DST"]
        if "estimated_ownership_pct" in p.columns and "roster_role" in p.columns:
            c = p[p["roster_role"].astype(str).str.upper() == "CPT"]
            own_cpt = dict(zip(c["player_id"], c["estimated_ownership_pct"]))
    top_cpt = max(own_cpt, key=own_cpt.get) if own_cpt else None

    for lid, g in lu.groupby("lineup_id", sort=False):
        cpt = g[g["roster_slot"].astype(str).str.upper() == "CPT"]
        flex = g[g["roster_slot"].astype(str).str.upper() != "CPT"]
        if cpt.empty:
            continue
        c = cpt.iloc[0]
        cpos, cteam = c["position"], c["team"]

        # Rule 3 backstop: K/DST captain
        if cpos in ("K", "DST"):
            sev = "backstop" if cpos == "DST" else "warn"
            _flag(out, lid, "SD3_cpt_k_dst", sev, "Supported (DST) / Weak (K)",
                  f"{cpos} captain {c['player_name']}")
        # Rule 13 backstop: WR/TE captain without own QB in FLEX
        if cpos in PASS_CATCHERS and not ((flex["position"] == "QB") & (flex["team"] == cteam)).any():
            _flag(out, lid, "SD13_cpt_wrte_no_qb", "backstop", "Supported",
                  f"{cpos} captain {c['player_name']} with no {cteam} QB in FLEX")
        # Rule 12 backstop: $600-1k FLEX tier
        cheap = flex[(flex["salary"] >= SD_CHEAP_TIER[0]) & (flex["salary"] <= SD_CHEAP_TIER[1])]
        for _, r in cheap.iterrows():
            _flag(out, lid, "SD12_cheap_tier", "backstop", "Weak-to-Supported (SE) / Supported (GPP)",
                  f"{r['player_name']} ${int(r['salary'])} in the $600-1k tier")
        # Stack-depth backstop: QB captain with >2 same-team FLEX
        if cpos == "QB":
            n_same = int((flex["team"] == cteam).sum())
            if n_same > 2:
                _flag(out, lid, "SD_stack_depth", "backstop", "Weak-to-Supported",
                      f"QB captain with {n_same} same-team FLEX (cap 2)")
        # Rule 5: kicker count
        nk = int((g["position"] == "K").sum())
        if nk > 1:
            _flag(out, lid, "SD5_two_kickers", "info", "Weak (CI spans 0)", f"{nk} kickers")
        # Rule 7: 4-2 with captain's team heavy
        counts = g["team"].value_counts()
        if len(counts) == 2 and sorted(counts.tolist()) == [2, 4] and counts.idxmax() == cteam:
            _flag(out, lid, "SD7_split_cpt_heavy", "warn", "Supported (mild, -1.2 to -1.6 cash)",
                  f"4-2 split with captain's team ({cteam}) on the heavy side")
        # Rule 6: expensive DST
        d = g[g["position"] == "DST"]
        if not d.empty and dsts is not None and len(dsts) >= 2:
            if int(d.iloc[0]["salary"]) >= int(dsts["salary"].max()) and dsts["salary"].nunique() > 1:
                _flag(out, lid, "SD6_expensive_dst", "info", "Weak (direction confirmed n=142)",
                      f"{d.iloc[0]['player_name']} is the more expensive DST (${int(d.iloc[0]['salary'])})")
        # Rule 8: chalk-CPT tier (modeled ownership -- corr 0.56 with real field)
        if own_cpt and c["player_id"] in own_cpt:
            o = float(own_cpt[c["player_id"]])
            if contest == "gpp" and o < 5:
                _flag(out, lid, "SD8_low_owned_cpt", "info", "Supported on realized own; modeled own weak",
                      f"captain modeled {o:.1f}% (<5%)")
            if contest == "se" and c["player_id"] == top_cpt:
                _flag(out, lid, "SD8_top_chalk_cpt_se", "info", "Supported on realized own; modeled own weak",
                      f"captain is the single most-owned CPT (modeled {o:.1f}%)")
    return out


def lint_classic(lu, pool):
    out = []
    for lid, g in lu.groupby("lineup_id", sort=False):
        qbs = g[g["position"] == "QB"]
        qb = qbs.iloc[0] if not qbs.empty else None
        # §5 item: 2+ same-team pass catchers with no QB of that team
        pc = g[g["position"].isin(PASS_CATCHERS)]
        for team, n in pc["team"].value_counts().items():
            if n >= 2 and (qb is None or qb["team"] != team):
                _flag(out, lid, "CL_pc_pair_no_qb", "info", "User preference (checklist §5), untested",
                      f"{n} {team} pass-catchers without {team} QB")
        # Decision #56 backstop: skill player vs rostered DST
        d = g[g["position"] == "DST"]
        if not d.empty:
            dteam = d.iloc[0]["team"]
            vs = g[(g["position"] != "DST") & (g["opponent"] == dteam)]
            for _, r in vs.iterrows():
                _flag(out, lid, "CL_skill_vs_own_dst", "backstop", "Decision #56 (default-on)",
                      f"{r['player_name']} faces rostered DST {dteam}")
        if qb is not None:
            # Stack depth (Phase 2 Step 2; replay stack=2 recommendation)
            n_stack = int(((g["team"] == qb["team"]) & g["position"].isin({"RB", "WR", "TE"})).sum())
            if n_stack < 2:
                _flag(out, lid, "CL_stack_depth_lt2", "info",
                      "Directional (Phase 2 +3.7pt QB+2, n small; WK2 said stack 2 worse)",
                      f"QB+{n_stack} ({qb['player_name']})")
            # Bring-back
            if not (g["team"] == qb["opponent"]).any():
                _flag(out, lid, "CL_no_bringback", "info", "Mixed (replay: recommend; WK2: neutral)",
                      f"no {qb['opponent']} player opposite {qb['player_name']}")
            # QB price (Phase 2 / Step 4e)
            if int(qb["salary"]) > QB_PRICE_WATCH:
                _flag(out, lid, "CL_qb_price", "info", "Directional (Phase 2, 3 wks)",
                      f"QB ${int(qb['salary'])} > ${QB_PRICE_WATCH} (cashing-field avg ~$5,850)")
        # Punts (Phase 2 Step 2: 0 punts -8.9pt)
        nd = g[g["position"] != "DST"]
        if int(((nd["salary"] > 0) & (nd["salary"] <= PUNT_MAX)).sum()) == 0:
            _flag(out, lid, "CL_zero_punts", "warn", "Directional (Phase 2 field lift -8.9pt, real field)",
                  f"no non-DST player <= ${PUNT_MAX}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lineups")
    ap.add_argument("--pool", default=None)
    ap.add_argument("--contest", choices=["se", "gpp"], default="gpp")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    lu = pd.read_csv(a.lineups)
    pool_path = a.pool or _guess_pool(a.lineups)
    pool = pd.read_csv(pool_path) if pool_path and os.path.exists(pool_path) else None
    is_sd = (lu["roster_slot"].astype(str).str.upper() == "CPT").any()
    flags = lint_showdown(lu, pool, a.contest) if is_sd else lint_classic(lu, pool)

    n = lu["lineup_id"].nunique()
    print(f"[construction_lint] {'showdown' if is_sd else 'classic'}: {n} lineups, "
          f"pool={'none' if pool is None else os.path.basename(pool_path)}")
    if not flags:
        print("  no flags")
        return 0
    df = pd.DataFrame(flags)
    summ = df.groupby(["rule", "severity", "evidence"])["lineup_id"].nunique().reset_index(name="lineups")
    summ["share"] = (summ["lineups"] / n).map("{:.0%}".format)
    print(summ.to_string(index=False))
    if a.out:
        df.to_csv(a.out, index=False)
        print(f"  per-lineup flags -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
