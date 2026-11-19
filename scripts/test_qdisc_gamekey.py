"""Tests for the pre-inactives Questionable discount game key (status_check.py, D2 item d).

    python -m pytest scripts/test_qdisc_gamekey.py

Game key comes from the slate's own schedule (salary file Game Info), never the stamped `opponent`
(zero-projection rows carry BYE_OR_UNKNOWN). Unkeyable rows fail safe to resolved / no discount.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_check as sc  # noqa: E402

SCHED = sc._qdisc_schedule_from_games(
    ["BUF@NYJ 11/15/2026 01:00PM ET", "KC@ATL 11/15/2026 04:25PM ET"], "dk")


def _df():
    return pd.DataFrame({
        "player_name": ["inact_buf", "q_nyj", "q_kc", "q_bye"],
        "team": ["BUF", "NYJ", "KC", "ZZZ"],
        # BUF inactive row has a zero projection and the BYE sentinel, as in real data
        "opponent": ["BYE_OR_UNKNOWN", "BUF", "ATL", "BYE_OR_UNKNOWN"],
        "injury_status": ["OUT", "QUESTIONABLE", "QUESTIONABLE", "QUESTIONABLE"],
        "injury_raw_status": ["Inactive (gameday)", "Questionable", "Questionable", "Questionable"],
        "final_projection": [0.0, 10.0, 10.0, 10.0],
    })


def _resolved(df):
    gk = sc._qdisc_game_key(df, SCHED)
    m = df["injury_raw_status"] == sc.QDISC_GATE_RESOLVED_RAW
    return set(gk[m].dropna())


def test_a_bye_sentinel_inactive_closes_real_game():
    df = _df()
    assert _resolved(df) == {"BUF|NYJ"}
    out, n = sc.qdisc_apply(df.copy(), _resolved(df), SCHED)
    r = out.set_index("player_name")
    assert r.loc["q_nyj", "qdisc_gate_reason"] == "inactives_resolved"
    assert r.loc["q_nyj", "qdisc_factor"] == 1.0 and r.loc["q_nyj", "final_projection"] == 10.0


def test_b_unkeyed_row_fails_safe():
    df = _df()
    out, _ = sc.qdisc_apply(df.copy(), _resolved(df), SCHED)
    r = out.set_index("player_name").loc["q_bye"]
    assert r["qdisc_gate_reason"] == "unkeyed_resolved"
    assert r["qdisc_factor"] == 1.0 and r["final_projection"] == 10.0 and r["qdisc_applied"] == 0


def test_c_unresolved_game_discounted():
    df = _df()
    out, n = sc.qdisc_apply(df.copy(), _resolved(df), SCHED)
    r = out.set_index("player_name").loc["q_kc"]
    assert r["qdisc_gate_reason"] == "inactives_pending"
    assert r["qdisc_factor"] == sc.QDISC_K_PRE == 0.760
    assert abs(r["final_projection"] - 7.6) < 1e-9 and n == 1


def test_d_idempotent():
    df = _df()
    once, _ = sc.qdisc_apply(df.copy(), _resolved(df), SCHED)
    again, _ = sc.qdisc_restore(once.copy())
    twice, _ = sc.qdisc_apply(again, _resolved(df), SCHED)
    pd.testing.assert_frame_equal(once.reset_index(drop=True), twice.reset_index(drop=True))
