"""
ecr_blend.py
============

Opt-in blend of FantasyPros expert-consensus weekly position ranks (ECR) into
the DK classic RB (and optionally TE) projections. OFF by default: nothing here
runs unless build_projections_statline.py is given --ecr-blend-rb / --ecr-blend-te
greater than 0.

WHY
---
analysis/proj_ecr/ecr_report.md (2026-09-25). On the leak-audited 2020-21 backtest
(weights and rank->points maps chosen on the training season only) blending ECR
into the shipped projection improved within-slate x position Spearman for RB in
both folds (+.015 to +.025, CIs exclude 0) and on live 2026 Wk1-2 (+.117, n=67,
too small to trust the size). WR failed the top-N bar, QB is worse than ours, TE is
weak. Roughly a third of the larger historical gain is ECR knowing who is inactive.
The historical engine has depth charts / injury status stubbed, so the live gain is
probably smaller than the backtest gain. It has NOT been shown to win more lineups.

HOW
---
    final = (1 - w) * final + w * map(ecr)      (only where final > 0)

map() is a monotone rank->expected-DK-points curve per position fit on 2020-21
(config/ecr_pts_map_dk.csv, np.interp on the ECR value). statline_p10/p90 shift by
the same delta (clipped at 0), the way the projection stack does.

INPUT
-----
DynastyProcess files/fp_latest_weekly.csv (pages ppr-rb / ppr-te), scraped a couple
of times a day. Cached in data/ecr/. The fantasypros_id -> gsis_id crosswalk is
DynastyProcess db_playerids.csv (slimmed and cached in data/ecr/).

SAFETY RULES
------------
- A player is blended only if ECR has him, his game kicks off AFTER now, and that
  kickoff is within 8 days of the ECR scrape (right week).
- The ECR file must have been scraped within 3 days of now, else the whole blend is
  skipped with a WARNING.
- Players not in ECR, players whose projection is already 0 (OUT / no game) and
  players whose game has started are left exactly as they were. status_check.py apply
  runs after the build and stays authoritative for OUT/DOUBTFUL players.
- Any failure (network, format, missing artifact) = projections unchanged, never an
  error. The caller wraps this in try/except as well.
- No name fallback on the id join (it matched 0 rows historically).

AUDIT
-----
data/ecr_blend/ecr_blend_{slate_id}.csv (per player) and ..._summary.json (per
build) are written whenever the blend is attempted.
"""

from __future__ import annotations

import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "ecr"
AUDIT_DIR = ROOT / "data" / "ecr_blend"
PTS_MAP_PATH = ROOT / "config" / "ecr_pts_map_dk.csv"

ECR_URL = "https://github.com/dynastyprocess/data/raw/master/files/fp_latest_weekly.csv"
IDS_URL = "https://github.com/dynastyprocess/data/raw/master/files/db_playerids.csv"
ECR_PAGES = {"RB": "ppr-rb", "TE": "ppr-te"}

MAX_SCRAPE_AGE_DAYS = 3
KICKOFF_WINDOW_S = 8 * 86400
IDS_CACHE_MAX_AGE_S = 7 * 86400
_HEADERS = {"User-Agent": "dfs-optimizer/ecr-blend"}


def _download(url: str):
    r = requests.get(url, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    return r.content, r.headers.get("ETag", "")


def _norm_id(s: pd.Series) -> pd.Series:
    """FantasyPros ids arrive as ints in one file and '17298.0' strings in the other."""
    return pd.to_numeric(s, errors="coerce").astype("Int64").astype(str)


def load_crosswalk() -> pd.DataFrame:
    """fantasypros_id -> gsis_id. A stale cache is fine (ids do not change)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / "playerids_slim.csv"
    if p.exists() and time.time() - p.stat().st_mtime < IDS_CACHE_MAX_AGE_S:
        return pd.read_csv(p, dtype=str)
    try:
        content, _ = _download(IDS_URL)
        raw = pd.read_csv(io.BytesIO(content), usecols=["fantasypros_id", "gsis_id"], dtype=str)
        slim = raw.dropna().copy()
        slim["fantasypros_id"] = _norm_id(slim["fantasypros_id"])
        slim = slim.drop_duplicates()
        slim.to_csv(p, index=False)
        return slim
    except Exception:
        if p.exists():
            return pd.read_csv(p, dtype=str)
        raise


def load_ecr():
    """Returns (dataframe, etag, source). Falls back to the cache if the fetch fails
    (the freshness rule in apply_blend still decides whether it is usable)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / "fp_latest_weekly.csv"
    etag, source = "", "fetched"
    try:
        content, etag = _download(ECR_URL)
        p.write_bytes(content)
    except Exception as exc:  # noqa: BLE001
        if not p.exists():
            raise
        source = f"cache after {type(exc).__name__}"
    return pd.read_csv(p), etag, source


def _strip_opp(s):
    return re.sub(r"^(vs\.?|at|@)\s*", "", str(s), flags=re.I).strip().upper()


def apply_blend(df: pd.DataFrame, weights: dict, slate_id: str, now: datetime | None = None,
                ecr_df: pd.DataFrame | None = None, crosswalk: pd.DataFrame | None = None,
                pts_map: pd.DataFrame | None = None):
    """Blend ECR into df's final_projection / statline_p10 / statline_p90 in place of a copy.

    weights: {"RB": 0.5, "TE": 0.0}. Returns (df, summary). ecr_df / crosswalk / pts_map
    can be injected (tests); otherwise they are loaded.
    """
    now = now or datetime.now(timezone.utc)
    now_ts = now.timestamp()
    active = {p: float(w) for p, w in weights.items() if p in ECR_PAGES and w and float(w) > 0}
    summary = {"slate_id": slate_id, "weights": active, "built_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "status": "not_run"}
    if not active:
        return df, summary

    etag, source = "", "injected"
    if ecr_df is None:
        ecr_df, etag, source = load_ecr()
    if crosswalk is None:
        crosswalk = load_crosswalk()
    if pts_map is None:
        pts_map = pd.read_csv(PTS_MAP_PATH)
    summary.update({"ecr_source": source, "ecr_etag": etag})

    scrape = pd.to_datetime(ecr_df["scrape_date"], errors="coerce").max()
    summary["ecr_scrape_date"] = None if pd.isna(scrape) else str(scrape.date())
    if pd.isna(scrape) or abs((now.date() - scrape.date()).days) > MAX_SCRAPE_AGE_DAYS:
        summary["status"] = "skipped_stale_ecr"
        print(f"WARNING: ECR file scrape_date {summary['ecr_scrape_date']} is not within "
              f"{MAX_SCRAPE_AGE_DAYS} days of now; ECR blend skipped.")
        _write_audit(summary, [], slate_id)
        return df, summary
    scrape_ts = scrape.tz_localize("UTC").timestamp()

    df = df.copy()
    crosswalk = crosswalk.copy()
    crosswalk["fantasypros_id"] = _norm_id(crosswalk["fantasypros_id"])
    audit = []
    n_blended = 0
    for pos, w in active.items():
        page = ECR_PAGES[pos]
        e = ecr_df.loc[ecr_df["page"] == page,
                       ["fantasypros_id", "ecr", "player_game_kickoff_ts", "player_opponent"]].copy()
        e["fantasypros_id"] = _norm_id(e["fantasypros_id"])
        e = (e.merge(crosswalk, on="fantasypros_id", how="left").rename(columns={"gsis_id": "player_id"})
              .dropna(subset=["player_id"]).drop_duplicates("player_id"))
        m = (pts_map.loc[pts_map["position"] == pos].groupby("ecr", as_index=False)["exp_pts"].mean()
             .sort_values("ecr"))
        xs, ys = m["ecr"].to_numpy(float), m["exp_pts"].to_numpy(float)

        mask = (df["position"].astype(str) == pos) & (df["final_projection"] > 0)
        cols = ["player_id", "player_name", "team", "opponent", "final_projection"]
        sub = df.loc[mask, cols].reset_index().rename(columns={"index": "_ix"})
        sub = sub.merge(e, on="player_id", how="left")
        has = sub["ecr"].notna()
        sub["ecr_pts"] = np.interp(sub["ecr"].astype(float), xs, ys)
        ko = pd.to_numeric(sub["player_game_kickoff_ts"], errors="coerce")
        future = ko > now_ts
        in_window = ko <= scrape_ts + KICKOFF_WINDOW_S
        ok = has & future & in_window
        sub["status"] = np.where(ok, "blended", np.where(~has, "no_ecr",
                                 np.where(~future, "kickoff_passed", "outside_week")))
        sub["pre"] = sub["final_projection"]
        sub["post"] = sub["pre"]
        sub.loc[ok, "post"] = (1.0 - w) * sub.loc[ok, "pre"] + w * sub.loc[ok, "ecr_pts"]
        sub["delta"] = sub["post"] - sub["pre"]
        sub["weight"] = w
        sub["position"] = pos
        sub["opp_match"] = [(_strip_opp(a) == str(b).strip().upper()) if pd.notna(a) else None
                            for a, b in zip(sub["player_opponent"], sub["opponent"])]

        if ok.any():
            ix = sub.loc[ok, "_ix"].to_numpy()
            d = sub.loc[ok, "delta"].to_numpy(float)
            df.loc[ix, "final_projection"] = sub.loc[ok, "post"].to_numpy(float)
            for c in ("statline_p10", "statline_p90"):
                if c in df.columns:
                    df.loc[ix, c] = np.clip(df.loc[ix, c].to_numpy(float) + d, 0.0, None)
        n_blended += int(ok.sum())
        big = sub["pre"] > 8
        summary[f"{pos}_players"] = int(len(sub))
        summary[f"{pos}_blended"] = int(ok.sum())
        summary[f"{pos}_match_rate_proj_gt8"] = (round(float(has[big].mean()), 3) if big.any() else None)
        summary[f"{pos}_skipped"] = {k: int(v) for k, v in sub.loc[~ok, "status"].value_counts().items()}
        if ok.any():
            summary[f"{pos}_mean_delta"] = round(float(sub.loc[ok, "delta"].mean()), 3)
            summary[f"{pos}_mean_abs_delta"] = round(float(sub.loc[ok, "delta"].abs().mean()), 3)
            j = sub.loc[ok, "delta"].abs().idxmax()
            summary[f"{pos}_largest_move"] = f"{sub.loc[j, 'player_name']} {sub.loc[j, 'pre']:.1f}->{sub.loc[j, 'post']:.1f}"
        audit.append(sub[["position", "player_id", "player_name", "team", "opponent", "player_opponent",
                          "opp_match", "ecr", "ecr_pts", "pre", "post", "delta", "status", "weight"]])
    summary["n_blended"] = n_blended
    summary["status"] = "applied" if n_blended else "no_players_blended"
    _write_audit(summary, audit, slate_id)
    return df, summary


def _write_audit(summary: dict, audit: list, slate_id: str) -> None:
    try:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        if audit:
            pd.concat(audit, ignore_index=True).to_csv(AUDIT_DIR / f"ecr_blend_{slate_id}.csv", index=False)
        (AUDIT_DIR / f"ecr_blend_{slate_id}_summary.json").write_text(json.dumps(summary, indent=2))
    except Exception as exc:  # noqa: BLE001 -- the audit is never allowed to break a build
        print(f"WARNING: could not write ECR blend audit ({type(exc).__name__}: {exc}).")


def describe(summary: dict) -> str:
    if summary.get("status") != "applied":
        return f"ECR blend: {summary.get('status')}"
    parts = []
    for pos in summary["weights"]:
        parts.append(f"{pos} w={summary['weights'][pos]:g}: blended {summary.get(pos + '_blended')}/"
                     f"{summary.get(pos + '_players')} (match {summary.get(pos + '_match_rate_proj_gt8')} of proj>8), "
                     f"mean delta {summary.get(pos + '_mean_delta')}, largest {summary.get(pos + '_largest_move')}")
    return "ECR blend applied (scrape " + str(summary.get("ecr_scrape_date")) + "): " + "; ".join(parts)
