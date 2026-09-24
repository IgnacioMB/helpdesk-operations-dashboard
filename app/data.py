"""Loading layer for the dashboard.

The clean ticket table is produced by `data_cleaning.ipynb` and is the only file
that has to be maintained. Everything under data/clean/derived is recomputed by
pipeline/build.py, which runs automatically if those files are missing.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pandas as pd
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLEAN_DIR = ROOT / "data" / "clean"
CLEAN = CLEAN_DIR / "tickets_clean.csv"
DERIVED = CLEAN_DIR / "derived"
ISSUES = CLEAN_DIR / "data_quality_issues.csv"

BOOL_COLS = ["has_accepted_refund", "has_out_of_pocket_refund",
             "is_weekend", "resolved_same_day", "is_repeat_contact_booking"]


def _ensure_built() -> None:
    """Rebuild the derived layer whenever it is older than the clean table.

    Checking existence alone is not enough: re-running the cleaning notebook leaves the
    aggregates in place but out of date, and the dashboard would serve them without
    complaint. Comparing mtimes means the derived files can never be behind their source.
    """
    if not CLEAN.exists():
        raise SystemExit(
            f"{CLEAN} is missing. Run data_cleaning.ipynb to produce it.")
    stamp = DERIVED / "headline_kpis.json"
    if not stamp.exists() or stamp.stat().st_mtime < CLEAN.stat().st_mtime:
        subprocess.run([sys.executable, str(ROOT / "pipeline" / "build.py")], check=True)


def clean_mtime() -> float:
    """Cache key: a new clean table must invalidate whatever is already loaded."""
    return CLEAN.stat().st_mtime if CLEAN.exists() else 0.0


@st.cache_data(show_spinner="Loading helpdesk data…")
def load(_source_mtime: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    # _source_mtime is not used in the body - it is here so that a refreshed clean file
    # produces a different cache key and the frame is re-read instead of served stale.
    _ensure_built()
    df = pd.read_csv(CLEAN, parse_dates=["created_at", "resolved_at",
                                         "created_date", "resolved_date"])
    # read_csv turns the nullable booleans back into object/float - restore them
    for c in BOOL_COLS:
        df[c] = df[c].map({True: True, False: False, "True": True, "False": False,
                           1: True, 1.0: True, 0: False, 0.0: False}).astype("boolean")
    issues = pd.read_csv(ISSUES)
    head = json.loads((DERIVED / "headline_kpis.json").read_text())
    return df, issues, head
