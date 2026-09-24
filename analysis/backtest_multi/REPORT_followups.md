# Follow-up verdicts (2026-09-24). DK 2014-2021, n=40,720 skill player-weeks, 95% CIs resample weeks, props off.
| # | Item | Verdict | Key numbers |
|---|---|---|---|
| 1 | Post-stack level correction | REJECT | Every variant worsens MAE OOS (additive fit 2014-19/test 2020-21 +0.141 [+0.129,+0.155]; LOSO +0.085). Bias depends on projection size (RB <10 pts -1.2..-1.5, >15 pts +0.6..+0.9), not a level shift. |
| 2 | p10 calibration | SHIP (default on, `--no-p10-calibration` reverts) | Per-position max(0,a+b*proj) fit 2014-21; LOSO share below p10 10.4% vs 16.7%. Agent-reported pinball gain -0.112; p10_pinball_ci output shows -0.066 [-0.074,-0.057], 8/8 seasons, but RB only 5/8 and CI spans 0 (-0.007) - RB gain unproven. Dart threshold stays 1.0, but which players get flagged changes (22->21 flags; 14 dropped incl. Kelce/LaPorta/Kincaid/Bateman, 13 new cheap TE/WR). |
| 3 | QB rush volume | REJECT (opt-in `qb_rush_scale`=1.0) | QB rush historically over-projected +0.15/QB; x1.45 worsens MAE +0.0055. |
| 4 | Floor-share (H) | REJECT (opt-in `floor_share_fix`) | MAE +0.0028 [+0.0020,+0.0037], ranking unchanged. |
| 5 | LOSO refit of prior/variance | Measurement | Only ~0.002 MAE of baseline accuracy is in-sample. |
| 6 | Moved-QB / Murray | Not testable historically | Moved starters n=31 under-projected -3.95 pts; historical QB depth charts are a week stale. Check vs Murray wk3 live. |
Files: scripts/build_projections_statline.py, statline_model.py, fit_statline_variance.py (all default-preserving except p10 calibration); analysis/backtest_multi/* (followups.py, p10_*.py, hist_depth.py, diff_2026_slate.py). Retest: see followups.py subcommands level|sigma|qbrush|darts, p10_qr.py, test_default_preserved.py.
