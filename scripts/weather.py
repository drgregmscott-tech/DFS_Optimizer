"""
weather.py  (v2 -- research-based)
==================================

Game-day weather adjustment. See WEATHER_RESEARCH.md for the sources, the
numbers, and how each constant below was derived. Short version: every knot
is an average of (a) published studies and (b) our own nflverse 2013-2025
outdoor games (scripts/probe_weather_wind_study.py, probe_weather_rain_study.py).

Pulls an hourly forecast per outdoor stadium from Open-Meteo (free, no key),
averages it over the game window (kickoff .. kickoff+3h), and converts it
into per-team multipliers:

  pass_eff_factor  -- pass + receiving efficiency (yd and TD rates); wind,
                      rain and temperature, combined multiplicatively
  pass_vol_factor  -- pass attempts / targets (wind only: rain and cold do
                      not measurably change play-calling)
  rush_vol_factor  -- carries (wind only; the volume the passing game gives up)
  kicker_factor    -- FG production (Showdown pools only)

Position handling: within the passing chain (QB, WR, TE, RB receiving) the
data does NOT support a reliable position split -- catches are the QB's
yards, so they fall together. The real split is passing vs rushing: rushing
gains volume as passing loses it. Rushing efficiency is left neutral (our
data: yards per carry flat across wind/rain bins).

MARKET_SHARE: Vegas totals already price part of the weather. Our data: the
total drops ~0.9 pts calm -> 15-19 mph while actual scoring drops ~3.1, i.e.
the market prices ~30% of wind. Since vegas_factor is applied separately,
only the un-priced share is applied here (wind/rain 70%; temperature 30%,
because totals already track cold nearly fully).

Fail-safe: any fetch problem, missing kickoff, or indoor stadium -> factors
of exactly 1.0 for that game.

CLI (run by refresh_data.yml's shared_pull):
    python scripts/weather.py --season 2026 --week 2
writes data/weather_{season}_wk{week}.csv (one row per team per game).
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Piecewise-linear knots: (x, fractional change). Flat beyond the end knots.
# Effective wind = (1-gust_weight)*sustained + gust_weight*gust, in mph.
WIND_PASS_EFF = [(8, 0.0), (12, -0.015), (17, -0.045), (22, -0.08), (25, -0.14), (30, -0.16)]
WIND_PASS_VOL = [(10, 0.0), (12, -0.005), (17, -0.015), (22, -0.05), (25, -0.062), (30, -0.07)]
WIND_RUSH_VOL = [(10, 0.0), (12, 0.005), (17, 0.02), (22, 0.06), (25, 0.07), (30, 0.08)]
# Rain: expected mm/hr over the game window.
RAIN_PASS_EFF = [(0.0, 0.0), (0.15, -0.01), (0.5, -0.03), (1.0, -0.05), (2.0, -0.06)]
# Temperature (F). Flat 0 across 55-85.
TEMP_PASS_EFF = [(20, -0.07), (30, -0.04), (40, -0.02), (55, 0.0), (85, 0.0), (95, -0.015)]
# Kickers (literature only -- our own FG data is selection-biased, see WEATHER_RESEARCH.md).
WIND_KICKER = [(10, 0.0), (15, -0.03), (20, -0.07), (25, -0.10)]
RAIN_KICKER = [(0.0, 0.0), (0.5, -0.02), (1.0, -0.04)]

WEATHER_CONFIG = {
    "wind_gust_weight": 0.15,
    "market_share_wind": 0.7,
    "market_share_rain": 0.7,
    "market_share_temp": 0.3,
    # Precip amount is used in full at >=50% forecast probability, scaled down below.
    "rain_prob_full": 50.0,
    "max_pass_eff_penalty": 0.20,
    "game_window_hours": 3,
}

# Home-team -> (lat, lon) of the stadium. Keys are nflverse abbreviations.
STADIUMS = {
    "ARI": (33.5276, -112.2626), "ATL": (33.7554, -84.4009), "BAL": (39.2780, -76.6227),
    "BUF": (42.7738, -78.7870), "CAR": (35.2258, -80.8528), "CHI": (41.8623, -87.6167),
    "CIN": (39.0955, -84.5161), "CLE": (41.5061, -81.6995), "DAL": (32.7473, -97.0945),
    "DEN": (39.7439, -105.0201), "DET": (42.3400, -83.0456), "GB": (44.5013, -88.0622),
    "HOU": (29.6847, -95.4107), "IND": (39.7601, -86.1639), "JAX": (30.3239, -81.6373),
    "KC": (39.0489, -94.4839), "LV": (36.0909, -115.1833), "LAC": (33.9535, -118.3392),
    "LA": (33.9535, -118.3392), "MIA": (25.9580, -80.2389), "MIN": (44.9735, -93.2575),
    "NE": (42.0909, -71.2643), "NO": (29.9511, -90.0812), "NYG": (40.8135, -74.0745),
    "NYJ": (40.8135, -74.0745), "PHI": (39.9008, -75.1675), "PIT": (40.4468, -80.0158),
    "SF": (37.4032, -121.9700), "SEA": (47.5952, -122.3316), "TB": (27.9759, -82.5033),
    "TEN": (36.1665, -86.7713), "WAS": (38.9076, -76.8645),
}

# Fixed domes and retractable roofs. Retractables are treated as indoor
# (conservative: no adjustment) since the roof status isn't knowable in
# advance and they're usually closed in bad weather.
INDOOR_HOMES = {"ARI", "ATL", "DAL", "DET", "HOU", "IND", "LV", "LAC", "LA", "MIN", "NO"}

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
COLUMNS = ["team", "opponent", "home_team", "kickoff_utc", "indoor", "wind_mph",
           "gust_mph", "precip_mm_hr", "precip_prob", "temp_f",
           "pass_eff_factor", "pass_vol_factor", "rush_vol_factor", "kicker_factor",
           "note", "fetched_utc"]
NEUTRAL = {"pass_eff_factor": 1.0, "pass_vol_factor": 1.0, "rush_vol_factor": 1.0,
           "kicker_factor": 1.0}


def _interp(x, knots):
    xs, ys = zip(*knots)
    return float(np.interp(x, xs, ys))


def compute_factors(wind, gust, precip_mm_hr, precip_prob, temp_f, cfg=WEATHER_CONFIG):
    """Pure function: forecast summary -> dict of the four multipliers."""
    eff_wind = (1 - cfg["wind_gust_weight"]) * wind + cfg["wind_gust_weight"] * gust
    rain = precip_mm_hr * min(1.0, precip_prob / cfg["rain_prob_full"])
    w_eff = _interp(eff_wind, WIND_PASS_EFF) * cfg["market_share_wind"]
    r_eff = _interp(rain, RAIN_PASS_EFF) * cfg["market_share_rain"]
    t_eff = _interp(temp_f, TEMP_PASS_EFF) * cfg["market_share_temp"]
    pass_eff = max(1.0 - cfg["max_pass_eff_penalty"], (1 + w_eff) * (1 + r_eff) * (1 + t_eff))
    k = ((1 + _interp(eff_wind, WIND_KICKER) * cfg["market_share_wind"])
         * (1 + _interp(rain, RAIN_KICKER) * cfg["market_share_rain"]))
    return {
        "pass_eff_factor": round(pass_eff, 4),
        "pass_vol_factor": round(1 + _interp(eff_wind, WIND_PASS_VOL) * cfg["market_share_wind"], 4),
        "rush_vol_factor": round(1 + _interp(eff_wind, WIND_RUSH_VOL) * cfg["market_share_wind"], 4),
        "kicker_factor": round(k, 4),
    }


def _kickoff_utc(gameday, gametime):
    """nflverse gameday (YYYY-MM-DD) + gametime (HH:MM, US Eastern) -> UTC."""
    if not gameday or not gametime or pd.isna(gameday) or pd.isna(gametime):
        return None
    naive = datetime.strptime(f"{gameday} {gametime}", "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)


def _get_with_retry(url, params, tries=4, timeout=20):
    """Open-Meteo occasionally resets connections; retry before giving up
    (a give-up just means that one game runs neutral)."""
    for i in range(tries):
        try:
            return requests.get(url, params=params, timeout=timeout)
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def _fetch_window(lat, lon, start_utc, hours):
    end_utc = start_utc + timedelta(hours=hours)
    resp = _get_with_retry(OPEN_METEO_URL, params=dict(
        latitude=lat, longitude=lon, wind_speed_unit="mph", temperature_unit="fahrenheit",
        hourly="temperature_2m,precipitation_probability,precipitation,wind_speed_10m,wind_gusts_10m",
        timezone="UTC", start_date=start_utc.strftime("%Y-%m-%d"),
        end_date=end_utc.strftime("%Y-%m-%d")), timeout=20)
    resp.raise_for_status()
    h = pd.DataFrame(resp.json()["hourly"])
    h["time"] = pd.to_datetime(h["time"]).dt.tz_localize("UTC")
    win = h[(h["time"] >= start_utc.replace(minute=0, second=0, microsecond=0)) & (h["time"] <= end_utc)]
    if win.empty:
        raise ValueError("forecast window empty")
    return win


def build_weather(season: int, week: int) -> pd.DataFrame:
    sched = pd.read_parquet(DATA_DIR / f"schedules_{season}.parquet")
    games = sched[(sched["week"] == week) & (sched["game_type"] == "REG")]
    now = datetime.now(timezone.utc)
    rows = []
    for g in games.itertuples():
        base = dict(home_team=g.home_team, kickoff_utc=None, indoor=False, wind_mph=None,
                    gust_mph=None, precip_mm_hr=None, precip_prob=None, temp_f=None,
                    note="", fetched_utc=now.isoformat(), **NEUTRAL)
        kick = _kickoff_utc(g.gameday, g.gametime)
        roof = str(getattr(g, "roof", "") or "").lower()
        if kick is not None:
            base["kickoff_utc"] = kick.isoformat()
        if g.home_team in INDOOR_HOMES or roof in ("dome", "closed"):
            base.update(indoor=True, note="indoor/retractable -- neutral")
        elif kick is None or g.home_team not in STADIUMS:
            base["note"] = "no kickoff/stadium -- neutral"
        else:
            try:
                win = _fetch_window(*STADIUMS[g.home_team], kick, WEATHER_CONFIG["game_window_hours"])
                wind, gust = win["wind_speed_10m"].mean(), win["wind_gusts_10m"].mean()
                precip, prob = win["precipitation"].mean(), win["precipitation_probability"].mean()
                temp = win["temperature_2m"].mean()
                base.update(wind_mph=round(wind, 1), gust_mph=round(gust, 1),
                            precip_mm_hr=round(precip, 2), precip_prob=round(prob, 0),
                            temp_f=round(temp, 1),
                            **compute_factors(wind, gust, precip, prob, temp))
            except Exception as e:  # fail-safe: never let weather break a slate
                base["note"] = f"forecast failed ({type(e).__name__}) -- neutral"
                print(f"WARNING: weather fetch failed for {g.away_team}@{g.home_team}: {e}", file=sys.stderr)
        for team, opp in ((g.home_team, g.away_team), (g.away_team, g.home_team)):
            rows.append({**base, "team": team, "opponent": opp})
    return pd.DataFrame(rows, columns=COLUMNS)


def load_weather_factors(season: int, week: int) -> pd.DataFrame:
    """Per-team factors from the committed pull; empty frame if none exists
    (-> every player neutral 1.0)."""
    path = DATA_DIR / f"weather_{season}_wk{week}.csv"
    if not path.exists():
        print(f"NOTE: {path.name} not found -- weather adjustment skipped (all 1.0).", file=sys.stderr)
        return pd.DataFrame(columns=["team", *NEUTRAL])
    return pd.read_csv(path)[["team", *NEUTRAL]]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    args = ap.parse_args()
    df = build_weather(args.season, args.week)
    out = DATA_DIR / f"weather_{args.season}_wk{args.week}.csv"
    df.to_csv(out, index=False)
    adj = df[(df.pass_eff_factor < 1.0) | (df.rush_vol_factor > 1.0)].drop_duplicates("home_team")
    print(f"Wrote {out} ({len(df)} team-game rows; {len(adj)} game(s) with a weather adjustment).")
    for r in adj.itertuples():
        print(f"  game at {r.home_team}: wind {r.wind_mph}/gust {r.gust_mph} mph, precip {r.precip_mm_hr} mm/hr "
              f"@ {r.precip_prob}%, {r.temp_f}F -> pass eff x{r.pass_eff_factor}, pass vol x{r.pass_vol_factor}, "
              f"rush vol x{r.rush_vol_factor}, K x{r.kicker_factor}")


if __name__ == "__main__":
    main()
