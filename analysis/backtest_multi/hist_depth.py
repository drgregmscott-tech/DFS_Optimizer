"""Leak-free historical depth-chart loader for the 2014-2021 backtest.

Source: nflverse weekly depth charts (free release asset
https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_{season}.parquet),
cached in analysis/backtest_multi/cache/depth_charts/ (never data/).

LEAK RULE: for target (season, week) each team's chart is its latest REG
chart with week STRICTLY < target week. nflverse's week-W chart is released
around week W but its exact timestamp relative to kickoff is not recorded, so
week W itself is not used. This is conservative: in-week injuries/promotions
of week W are invisible (as they would be to a Tuesday build).

Output matches statline_model.load_depth_chart(): [player_id, team, position,
depth_rank], QB/RB/WR/TE only. Rank convention: sequential within
(team, position) ordered by depth_team (the NFL chart lists two WR1s, so the
starters get 1 and 2, as in the 2026 ESPN snapshot where WR ranks are 1..n).

  python analysis/backtest_multi/hist_depth.py download   # fetch 2014-2021
  python analysis/backtest_multi/hist_depth.py check 2019 6
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache" / "depth_charts"
URL = "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_{s}.parquet"
POS_MAP = {"QB": "QB", "RB": "RB", "HB": "RB", "WR": "WR", "LWR": "WR", "RWR": "WR", "SWR": "WR", "TE": "TE"}
TEAM_CANON = {"OAK": "LV", "SD": "LAC", "SDG": "LAC", "STL": "LA", "LAR": "LA", "LVR": "LV",
              "WSH": "WAS", "JAC": "JAX", "GNB": "GB", "NOR": "NO", "NOS": "NO"}
_CACHE: dict[int, pd.DataFrame] = {}


def download(seasons=range(2014, 2022)):
    CACHE.mkdir(parents=True, exist_ok=True)
    for s in seasons:
        dest = CACHE / f"depth_charts_{s}.parquet"
        if not dest.exists():
            urllib.request.urlretrieve(URL.format(s=s), dest)
        print(dest, dest.stat().st_size)


def _season(season: int) -> pd.DataFrame:
    if season not in _CACHE:
        d = pd.read_parquet(CACHE / f"depth_charts_{season}.parquet")
        d = d[(d["game_type"] == "REG") & (d["formation"] == "Offense")].copy()
        d["pos"] = d["depth_position"].astype(str).str.strip().map(POS_MAP)
        d = d[d["pos"].notna() & d["gsis_id"].notna()]
        d["week"] = d["week"].astype(int)
        d["depth_team"] = pd.to_numeric(d["depth_team"], errors="coerce")
        d["team"] = d["club_code"].map(lambda t: TEAM_CANON.get(t, t))
        _CACHE[season] = d.reset_index(drop=True)
    return _CACHE[season]


def load_depth_chart_asof(season: int, week: int) -> pd.DataFrame:
    d = _season(season)
    d = d[d["week"] < week]
    if d.empty:
        return pd.DataFrame(columns=["player_id", "team", "position", "depth_rank"])
    last = d.groupby("team")["week"].transform("max")
    d = d[d["week"] == last].copy()
    d = d.sort_values(["team", "pos", "depth_team"], kind="stable")
    d = d.drop_duplicates(["team", "pos", "gsis_id"])        # player listed twice -> best slot
    d["depth_rank"] = d.groupby(["team", "pos"]).cumcount() + 1
    out = d.drop(columns=["position"]).rename(columns={"gsis_id": "player_id", "pos": "position"})
    out = out.sort_values("depth_rank").drop_duplicates(["player_id"])   # one row per player
    return out[["player_id", "team", "position", "depth_rank"]].reset_index(drop=True)


if __name__ == "__main__":
    if sys.argv[1] == "download":
        download()
    else:
        s, w = int(sys.argv[2]), int(sys.argv[3])
        dc = load_depth_chart_asof(s, w)
        print(len(dc), dc.groupby("position").size().to_dict())
        print(dc[dc["team"] == dc["team"].iloc[0]].sort_values(["position", "depth_rank"]).to_string())
