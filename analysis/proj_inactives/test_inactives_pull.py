"""Offline tests for scripts/inactives_pull.py (no network; temp dirs). Run: python analysis/proj_inactives/test_inactives_pull.py"""
import os, sys, tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
import inactives_pull as ip  # noqa: E402


def setup(age_h=1):
    d = Path(tempfile.mkdtemp())
    ip.OUTPUT_DIR, ip.LOG_DIR = d / "output", d / "logs"
    ip.OUTPUT_DIR.mkdir()
    ts = (datetime.now(timezone.utc) - timedelta(hours=age_h)).strftime("%Y%m%d_%H%M%S")
    pd.DataFrame([["00-1", "A One", "BUF", "RB", "QUESTIONABLE", "Questionable", "x", "auto_exact"],
                  ["00-2", "B Two", "BUF", "WR", "ACTIVE", None, None, "auto_exact"],
                  ["00-3", "C Three", "BUF", "QB", "OUT", "Out", "x", "auto_exact"]],
                 columns=["player_id", "player_name", "team", "position", "status", "raw_status",
                          "last_updated", "match_method"]).to_csv(ip.OUTPUT_DIR / f"player_status_3_{ts}.csv", index=False)
    return SimpleNamespace(season=2026, week=3, teams=None, max_base_age_hours=6.0, dry_run=False)


def fake(rows):
    ip.collect = lambda *a, **k: (pd.DataFrame(rows), [("e", "BUF", "ok", len(rows))])
    ip.map_to_player_id = lambda f, s: f.assign(player_id=f.espn_id.map({"1": "00-1", "3": "00-3", "9": None}),
                                                match_method="espn_id")


r = lambda i, n: {"espn_id": i, "player_name": n, "espn_position": "RB", "team": "BUF", "event_id": "e"}
# 1: Q -> OUT, OUT stays, unmatched skipped, ACTIVE untouched
a = setup(); fake([r("1", "A One"), r("3", "C Three"), r("9", "Nobody")]); ip.run(a)
outs = sorted(ip.OUTPUT_DIR.glob("player_status_3_*.csv"))
assert len(outs) == 2, outs
new = pd.read_csv(outs[-1]).set_index("player_id")
assert new.loc["00-1", "status"] == "OUT" and new.loc["00-2", "status"] == "ACTIVE" and new.loc["00-3", "status"] == "OUT"
lg = pd.read_csv(next(ip.LOG_DIR.glob("inactives_3_*.csv")))
assert set(lg.action) == {"set_out", "already_out", "unmatched_skipped"}, lg.action
# 2: nothing changed -> no new status file (no re-stamping)
a = setup(); fake([r("3", "C Three")]); ip.run(a)
assert len(list(ip.OUTPUT_DIR.glob("player_status_3_*.csv"))) == 1
# 3: stale base -> no-op
a = setup(age_h=10); fake([r("1", "A One")]); ip.run(a)
assert len(list(ip.OUTPUT_DIR.glob("player_status_3_*.csv"))) == 1
# 4: nothing posted -> no-op
a = setup(); fake([]); ip.run(a)
assert len(list(ip.OUTPUT_DIR.glob("player_status_3_*.csv"))) == 1
# 5: exception -> main() exits 0, base untouched
a = setup()
def boom(*a, **k): raise RuntimeError("network down")
ip.collect = boom
sys.argv = ["x", "--season", "2026", "--week", "3"]
try:
    ip.main()
except SystemExit as e:
    assert e.code == 0
assert len(list(ip.OUTPUT_DIR.glob("player_status_3_*.csv"))) == 1
# 6: sanity gate on game roster
ip._get = lambda url: {"entries": [{"didNotPlay": False}] * 55}
assert ip.game_inactives("e", "2")[0].startswith("insane")
ip._get = lambda url: None
assert ip.game_inactives("e", "2")[0] == "not_posted"
print("ALL TESTS PASSED")
