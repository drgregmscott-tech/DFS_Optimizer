"""
fc_history_map.py -- map Fantasy Cruncher history players to our player_id (nflverse gsis) and validate
against our DK labels. Reads data/fc_history/derived/fc_master.csv (from fc_history_etl.py); writes
fc_master_mapped.csv, map_validation.csv, map_report.txt in the same git-ignored derived/ dir.

Match tiers (first hit wins), per (season, week, player) row:
  1 week   name_key + team + pos in that week's weekly_stats (played)
  2 season name_key + team (+pos) anywhere in that season's weekly_stats (inactive/DNP that week)
  3 global name_key+pos unique across all weekly_stats/rotoguru-known ids (also covers seasons with no local stats)
  4 name_mapping.csv (source_name, position)
DST rows map to team (id = 'DST_<TEAM>'). Labels: DK points computed from weekly_stats vs FC `score`, plus
RotoGuru actuals (real DK) for 2021.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from fc_history_etl import norm_name, OUT, ROOT

TEAM = {"JAC": "JAX", "LAR": "LA", "STL": "LA", "WSH": "WAS", "OAK": "LV", "SD": "LAC"}
tm = lambda s: s.map(lambda t: TEAM.get(t, t))


def dk_points(w):
    g = lambda c: w[c].fillna(0)
    p = (g("passing_yards") * .04 + g("passing_tds") * 4 - g("passing_interceptions") + g("rushing_yards") * .1
         + g("rushing_tds") * 6 + g("receptions") + g("receiving_yards") * .1 + g("receiving_tds") * 6
         - g("sack_fumbles_lost") - g("rushing_fumbles_lost") - g("receiving_fumbles_lost")
         + 2 * (g("passing_2pt_conversions") + g("rushing_2pt_conversions") + g("receiving_2pt_conversions"))
         + 6 * (g("special_teams_tds") + g("fumble_recovery_tds")))
    return p + 3 * ((g("passing_yards") >= 300) | (g("rushing_yards") >= 100) | (g("receiving_yards") >= 100))


def main():
    m = pd.read_csv(OUT / "fc_master.csv")
    m["team_n"] = tm(m.team)
    ws = []
    for f in sorted((ROOT / "data").glob("weekly_stats_*.parquet")):
        d = pd.read_parquet(f)
        d = d[d.season_type == "REG"]
        if len(d):
            ws.append(d)
    ws = pd.concat(ws)
    ws["name_key"] = ws.player_display_name.map(norm_name)
    ws["team_n"] = tm(ws.team)
    ws["dk_calc"] = dk_points(ws)
    ws["fc_season"] = ws.season.isin(m.season.unique())
    ws["position"] = ws.position.replace({"FB": "RB"})
    ws_all = ws  # all seasons kept here so players whose stats are outside the FC seasons still get an id; # any nflverse position: DK lists e.g. Taysom Hill QB / N'Keal Harry WR that nflverse has as TE
    ws = ws[ws.position.isin(["QB", "RB", "WR", "TE"])]
    wk = ws.drop_duplicates(["season", "week", "name_key", "team_n", "position"]).set_index(["season", "week", "name_key", "team_n", "position"]).player_id
    sn = ws.groupby(["season", "name_key", "team_n", "position"]).player_id.agg(lambda s: s.iloc[0] if s.nunique() == 1 else None)
    gl = ws.groupby(["name_key", "position"]).player_id.agg(lambda s: s.iloc[0] if s.nunique() == 1 else None)
    uniq = lambda s: s.iloc[0] if s.nunique() == 1 else None
    gl_np = ws_all.groupby("name_key").player_id.agg(uniq)
    sn_np = ws_all.groupby(["season", "name_key", "team_n"]).player_id.agg(uniq)
    ws_all = ws_all.assign(last=ws_all.name_key.str.split().str[-1], first=ws_all.name_key.str.split().str[0])
    fn = ws_all.groupby(["season", "last", "team_n"]).apply(lambda g: list(set(zip(g["first"], g.player_id))))
    al = pd.read_csv(ROOT / "data" / "fc_name_alias.csv"); al["k"] = al.fc_name.map(norm_name)
    ald = al.set_index("k").player_id
    nm = pd.read_csv(ROOT / "data" / "name_mapping.csv"); nm = nm[nm.site == "dk"]
    nm["k"] = nm.source_name.map(norm_name)
    nmd = nm.drop_duplicates(["k", "source_position"]).set_index(["k", "source_position"]).player_id

    def prefix(r):  # Chigoziem/Chig, Irv/Irvin: same season+team+last name, one first name is a prefix of the other
        parts = r.name_key.split()
        if len(parts) < 2:
            return None
        c = {pid for f, pid in fn.get((r.season, parts[-1], r.team_n), []) if f.startswith(parts[0][:3]) and (f.startswith(parts[0]) or parts[0].startswith(f))}
        return c.pop() if len(c) == 1 else None

    ids, tier = [], []
    for r in m.itertuples():
        if r.pos == "DST":
            ids.append(f"DST_{r.team_n}"); tier.append("dst"); continue
        if r.pos == "K":
            ids.append(None); tier.append("k_skip"); continue
        pid, t = None, "unmapped"
        for tname, look in (("0_alias", lambda: ald.get(r.name_key)),
                            ("1_week", lambda: wk.get((r.season, r.week, r.name_key, r.team_n, r.pos))),
                            ("2_season", lambda: sn.get((r.season, r.name_key, r.team_n, r.pos))),
                            ("3_global", lambda: gl.get((r.name_key, r.pos))),
                            ("4_namemap", lambda: nmd.get((r.name_key, r.pos))),
                            ("5_season_anypos", lambda: sn_np.get((r.season, r.name_key, r.team_n))),
                            ("6_name_only", lambda: gl_np.get(r.name_key)),
                            ("7_first_prefix", lambda: prefix(r))):
            v = look()
            if isinstance(v, str):
                pid, t = v, tname; break
        ids.append(pid); tier.append(t)
    m["player_id"], m["match_tier"] = ids, tier

    lab = ws_all[ws_all.fc_season][["season", "week", "player_id", "dk_calc"]].drop_duplicates(["season", "week", "player_id"])
    m = m.merge(lab, on=["season", "week", "player_id"], how="left")
    rg = pd.concat([pd.read_csv(f) for f in (ROOT / "data").glob("rotoguru_actuals_dk_20*.csv")])
    rg = rg[rg.season.isin(m.season.unique())]
    rg["name_key"] = rg.name.map(norm_name); rg["team_n"] = tm(rg.team)
    rg = rg.drop_duplicates(["season", "week", "name_key", "team_n"])[["season", "week", "name_key", "team_n", "actual_points"]]
    m = m.merge(rg.rename(columns={"actual_points": "rg_dk"}), on=["season", "week", "name_key", "team_n"], how="left")
    m.drop(columns="team_n").to_csv(OUT / "fc_master_mapped.csv", index=False)

    sk = m[m.pos.isin(["QB", "RB", "WR", "TE"])].copy()
    rep = ["FC history -> player_id map + DK label validation", ""]
    rep.append("skill rows by match tier per season (counts):")
    rep.append(sk.pivot_table(index="season", columns="match_tier", values="player", aggfunc="count", fill_value=0).to_string())
    played = sk[(sk.score.abs() > 0) | (sk.own_pct > 0)]
    um = played[played.player_id.isna()]
    rep.append(f"\nUnmapped skill rows: {len(sk[sk.player_id.isna()])}; of those with score!=0 or own>0: {len(um)}")
    rep.append(um.groupby(["season", "player", "team", "pos"]).size().sort_values(ascending=False).head(40).to_string())
    dup = m[m.player_id.notna()].duplicated(["source_file", "player_id"], keep=False)
    rep.append(f"\nSame player_id twice within one file: {int(dup.sum())} rows")
    rep.append(m[m.player_id.notna()][dup][["source_file", "player", "team", "pos", "player_id"]].head(15).to_string())
    val = []
    for label, col in (("nflverse-calc", "dk_calc"), ("rotoguru", "rg_dk")):
        v = sk[sk[col].notna()].copy()
        v["diff"] = (v.score - v[col]).abs()
        one = v.drop_duplicates(["season", "week", "player", "team"])
        rep.append(f"\nFC score vs {label}: rows {len(one)}; exact(<=0.15) {(one['diff']<=.15).mean():.1%}; "
                   f"<=1pt {(one['diff']<=1).mean():.1%}; median abs diff {one['diff'].median():.2f}")
        rep.append(one.groupby("season")["diff"].agg(n="size", exact=lambda s: (s <= .15).mean(), le1=lambda s: (s <= 1).mean()).round(3).to_string())
        bad = one[one["diff"] > 1].sort_values("diff", ascending=False)
        rep.append("worst 15:\n" + bad[["season", "week", "player", "team", "pos", "score", col, "diff", "match_tier"]].head(15).to_string(index=False))
        val.append(bad.assign(label=label))
    pd.concat(val).to_csv(OUT / "map_validation.csv", index=False)
    no_lab = sk[(sk.dk_calc.isna()) & (sk.rg_dk.isna())]
    rep.append(f"\nSkill rows with no label source at all (per season): {no_lab.groupby('season').size().to_dict()} of {sk.groupby('season').size().to_dict()}")
    (OUT / "map_report.txt").write_text("\n".join(rep) + "\n", encoding="utf-8")
    print("\n".join(rep))


main()
