# Weather adjustment: research basis (v2, 2026-09-20)

`scripts/weather.py` constants are derived from (a) published analyses and (b) our own
nflverse data (outdoor/open-roof regular-season games, 2013-2021 + 2024-2025; 2022-23
weekly stats are not in the repo). Reproduce with `scripts/probe_weather_wind_study.py` and
`scripts/probe_weather_rain_study.py` (rain uses Open-Meteo archive precipitation over each
game's 3h window). All own-data figures are relative to each team's/player's own season mean.

## Wind (own data, sustained mph; n games = 450 / 906 / 444 / 174 / 55)
| Wind | Pass yds | YPA | Pass att | Carries | Rush yds | Pass rate |
|---|---|---|---|---|---|---|
| 0-4 | 1.039 | 1.023 | 1.016 | 0.986 | 0.977 | 1.014 |
| 5-9 (baseline) | 1.005 | 1.004 | 1.001 | 0.998 | 1.007 | 1.002 |
| 10-14 | 0.985 | 0.992 | 0.993 | 1.005 | 0.998 | 0.994 |
| 15-19 | 0.939 | 0.956 | 0.985 | 1.018 | 1.006 | 0.984 |
| 20+ | 0.915 | 0.953 | 0.955 | 1.061 | 1.073 | 0.953 |

Player level (points vs own mean, 15-19 / 20+): QB 0.915 / 0.917, WR 0.951 / 0.966 (yards
0.943 / 0.908 with targets ~flat), TE 0.945 / 0.777 (noisy, n~114), RB 0.941 / 1.043.
Yards per carry is flat in wind. Kicker FG% shows no decline in our data (attempt selection),
so kicker effects come from the literature only.

**Published:** completion% 60.3 -> 54.7 and ANY/A 5.79 -> 4.62 at 20+ mph vs <10, INT rate
flat, TD% 4.29 -> 3.58 (Spax, nflverse-based 1985-2016); PFF: 5-10 mph -0.7% comp / -0.13 YPA,
10+ mph -1.8% / -0.30 YPA (n=5,736 high-wind attempts), no clear TD/INT effect; Advanced NFL
Stats / Yahoo: pass decline 10-15 ~ 15-20, then 1.5-2x larger at 20+, teams swap ~5 passes for
runs per game above 20 mph; FantasyLife (11-yr nflverse + Open-Meteo): 25+ mph YPA -17.9%, pass
rate -6.2%, aDOT only -6.9% (QBs keep throwing deep); FG% 83.8 (<10) -> ~80 (15-20) -> ~77 (20+).
Consensus: negligible below ~10 mph, steady decline 10-20, sharp break at 20+.

## Rain (own data, calm <10 mph & >45F to isolate; team pass yds vs dry)
| 3h precip | n team-games | Pass yds | YPA | Pass att | Carries |
|---|---|---|---|---|---|
| dry | 1592 | 1.031 | 1.019 | 1.012 | 0.989 |
| <=1 mm | 242 | 1.010 (-2%) | 1.015 | 0.998 | 1.006 |
| 1-3 mm | 106 | 0.980 (-5%) | 0.995 | 0.992 | 0.978 |
| >3 mm | 62 | 0.967 (-6%) | 0.963 | 1.002 | 1.004 |

Rain lowers efficiency but does NOT change pass rate or carries (unlike wind). QB points
0.91 at >=1 mm; WR 0.93 / 0.94. **Published:** the widely repeated "-12% passing production in
rain" (Sharp Football, Yahoo) is confounded with wind/cold/snow; Spax's 1985-2016 study found
rain minimal. Isolated, we measure -2% to -6%, so v2 uses -1% / -3% / -5% / -6% knots.

## Temperature (own data, YPA vs 55-85F): <25F 0.938, 25-40 0.970, 40-55 0.993, >85 0.999.
Literature: 25-55F ~-5%, <25 or >85F ~-8% (small samples at extremes). Dome teams show no
extra wind penalty; the cold effect is real, not a wind proxy.

## Market overlap (why v2 applies only 70% of wind/rain)
Actual total - Vegas total: 0-4 mph +1.2, 5-9 +0.6, 10-14 -1.3, 15-19 -1.5. Total scoring falls
~3.1 pts calm -> 15-19 mph but the posted total falls only ~0.9 (~30% priced). Since vegas_factor
already carries that, weather applies the un-priced 70%. Temperature is priced almost fully
(totals track cold), so it gets 30%.

## Position conclusions
- Passing chain (QB, WR, TE, RB receiving): move together; the data does not support a reliable
  WR vs TE split (samples too small; TE 20+ is noisy). Same efficiency + volume factor.
- Rushing: gains volume, efficiency unchanged. Kickers: literature-based, Showdown only.
- DST: no adjustment (no reliable evidence found).
