"""
weather.py
==========

Game-day weather adjustment (added 2026-09-20 -- the pipeline previously had
no weather input at all; nflverse's own temp/wind columns are only filled in
AFTER a game, so they can't be used for a forecast).

Pulls an hourly forecast per outdoor stadium from Open-Meteo (free, no key),
averages it over the game window (kickoff .. kickoff+3h), and converts it
into three per-team multipliers:

  pass_factor   -- scales pass and receiving efficiency (yd + TD rates)
  rush_factor   -- scales rushing efficiency (small lift when passing suffers)
  kicker_factor -- scales kicker projections (Showdown pools only)

DEFAULTS ARE DELIBERATELY CONSERVATIVE. There is no weather data in the
backtest to calibrate against, so every constant below is judgment, chosen so
a genuinely bad game moves a passer a few percent, not a lot. All are in one
block (WEATHER_CONFIG) so they can be retuned in one place once there's
in-season evidence. Efficiency-only, matching statline_model decision #10
(the market factor scales efficiency, not volume).

Fail-safe: any fetch problem, missing kickoff, or indoor stadium -> factors
of exactly 1.0 for that game. A weather outage can never zero or distort a
slate; it just falls back to "no adjustment", which is today's behavior.

CLI (run by refresh_data.yml's shared_pull):
    python scripts/weather.py --season 2026 --week 2
writes data/weather_{season}_wk{week}.csv (one row per team per game).
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

WEATHER_CONFIG = {
    # Effective wind = 0.7*sustained + 0.3*gust. Penalty starts at 12 mph.
    "wind_gust_weight": 0.3,
    "wind_threshold_mph": 12.0,
    "wind_pass_penalty_per_mph": 0.006,
    # Rain: penalty scales with mean mm/hr over the window, capped, then
    # weighted by the mean precipitation probability.
    "rain_pass_penalty_per_mm_hr": 0.02,
    "rain_pass_penalty_cap": 0.04,
    # Total pass-efficiency penalty is capped no matter how bad it gets.
    "max_pass_penalty": 0.10,
    # Rushing gets this share of the pass penalty back as a lift (capped).
    "rush_lift_share": 0.4,
    "max_rush_lift": 0.03,
    # Kickers: wind matters more than for passers.
    "kicker_wind_threshold_mph": 10.0,
    "kicker_wind_penalty_per_mph": 0.008,
    "kicker_rain_share": 0.5,
    "max_kicker_penalty": 0.10,
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
           "pass_factor", "rush_factor", "kicker_factor", "note", "fetched_utc"]


def compute_factors(wind, gust, precip_mm_hr, precip_prob, cfg=WEATHER_CONFIG):
    """Pure function: forecast summary -> (pass, rush, kicker) multipliers."""
    eff_wind = (1 - cfg["wind_gust_weight"]) * wind + cfg["wind_gust_weight"] * gust
    wind_pen = max(0.0, eff_wind - cfg["wind_threshold_mph"]) * cfg["wind_pass_penalty_per_mph"]
    rain_pen = (min(cfg["rain_pass_penalty_cap"], cfg["rain_pass_penalty_per_mm_hr"] * precip_mm_hr)
                * (precip_prob / 100.0))
    pass_pen = min(cfg["max_pass_penalty"], wind_pen + rain_pen)
    rush_lift = min(cfg["max_rush_lift"], cfg["rush_lift_share"] * pass_pen)
    k_wind = max(0.0, eff_wind - cfg["kicker_wind_threshold_mph"]) * cfg["kicker_wind_penalty_per_mph"]
    k_pen = min(cfg["max_kicker_penalty"], k_wind + cfg["kicker_rain_share"] * rain_pen)
    return round(1.0 - pass_pen, 4), round(1.0 + rush_lift, 4), round(1.0 - k_pen, 4)


def _kickoff_utc(gameday, gametime):
    """nflverse gameday (YYYY-MM-DD) + gametime (HH:MM, US Eastern) -> UTC."""
    if not gameday or not gametime or pd.isna(gameday) or pd.isna(gametime):
        return None
    naive = datetime.strptime(f"{gameday} {gametime}", "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)


def _fetch_window(lat, lon, start_utc, hours):
    end_utc = start_utc + timedelta(hours=hours)
    resp = requests.get(OPEN_METEO_URL, params=dict(
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
                    pass_factor=1.0, rush_factor=1.0, kicker_factor=1.0, note="",
                    fetched_utc=now.isoformat())
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
                pf, rf, kf = compute_factors(wind, gust, precip, prob)
                base.update(wind_mph=round(wind, 1), gust_mph=round(gust, 1),
                            precip_mm_hr=round(precip, 2), precip_prob=round(prob, 0),
                            temp_f=round(win["temperature_2m"].mean(), 1),
                            pass_factor=pf, rush_factor=rf, kicker_factor=kf)
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
        return pd.DataFrame(columns=["team", "pass_factor", "rush_factor", "kicker_factor"])
    return pd.read_csv(path)[["team", "pass_factor", "rush_factor", "kicker_factor"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    args = ap.parse_args()
    df = build_weather(args.season, args.week)
    out = DATA_DIR / f"weather_{args.season}_wk{args.week}.csv"
    df.to_csv(out, index=False)
    adj = df[(df.pass_factor < 1.0) | (df.rush_factor > 1.0)].drop_duplicates("home_team")
    print(f"Wrote {out} ({len(df)} team-game rows; {len(adj)} game(s) with a weather adjustment).")
    for r in adj.itertuples():
        print(f"  game at {r.home_team}: wind {r.wind_mph}/gust {r.gust_mph} mph, "
              f"precip {r.precip_mm_hr} mm/hr @ {r.precip_prob}% -> pass x{r.pass_factor}, rush x{r.rush_factor}, K x{r.kicker_factor}")


if __name__ == "__main__":
    main()
