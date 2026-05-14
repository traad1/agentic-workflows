"""
Google Sheets backend for weekly price data.
Falls back to local Excel when credentials are not configured.
"""

import json
import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import datetime

# ── Column schema (order matters — must match sheet header row) ───────────────
COLUMNS = [
    "week_of",          # ISO date string YYYY-MM-DD (Monday of the week)
    "day",              # Monday–Friday
    "session",          # Open / Settlement
    "kc_cents_lb",      # Arabica KC ¢/lb
    "rc_usd_mt",        # Robusta RC USD/MT
    "rc_cents_lb",      # RC converted to ¢/lb
    "spread_cents_lb",  # KC − RC_cents_lb
    "notes",
]

SHEET_NAME   = "Weekly Prices"
BASE_DIR     = Path(__file__).parent
DATA_DIR     = BASE_DIR / "data"
LOCAL_XLS    = DATA_DIR / "weekly_prices.xlsx"
DATA_DIR.mkdir(exist_ok=True)

# ── Credential helpers ────────────────────────────────────────────────────────

def _has_sheets_config() -> bool:
    """True when Streamlit secrets contain the service account block."""
    try:
        _ = st.secrets["gcp_service_account"]
        _ = st.secrets["SHEET_ID"]
        return True
    except (KeyError, FileNotFoundError):
        return False


@st.cache_resource(ttl=3600)
def _get_gspread_client():
    """Return an authenticated gspread client using Streamlit secrets."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=scopes,
    )
    return gspread.authorize(creds)


def _get_worksheet():
    """Open (or create) the Weekly Prices worksheet."""
    client   = _get_gspread_client()
    sheet_id = st.secrets["SHEET_ID"]
    wb       = client.open_by_key(sheet_id)
    try:
        ws = wb.worksheet(SHEET_NAME)
    except Exception:
        ws = wb.add_worksheet(title=SHEET_NAME, rows=2000, cols=len(COLUMNS))
        ws.append_row(COLUMNS)
    return ws


# ── Public API ────────────────────────────────────────────────────────────────

def load_prices() -> pd.DataFrame:
    """Load all weekly price rows. Uses Sheets when configured, else local Excel."""
    if _has_sheets_config():
        return _load_from_sheets()
    return _load_from_excel()


def save_row(row: dict):
    """Upsert a row by (week_of, day, session)."""
    if _has_sheets_config():
        _save_to_sheets(row)
    else:
        _save_to_excel(row)


def delete_row(week_of, day, session):
    """Delete a specific row."""
    if _has_sheets_config():
        _delete_from_sheets(week_of, day, session)
    else:
        _delete_from_excel(week_of, day, session)


def backend_label() -> str:
    if _has_sheets_config():
        return "Google Sheets"
    return "Local Excel"


# ── Google Sheets implementation ──────────────────────────────────────────────

def _load_from_sheets() -> pd.DataFrame:
    try:
        ws      = _get_worksheet()
        records = ws.get_all_records()
        if not records:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(records)
        df["week_of"] = pd.to_datetime(df["week_of"], errors="coerce")
        for col in ["kc_cents_lb", "rc_usd_mt", "rc_cents_lb", "spread_cents_lb"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as e:
        st.warning(f"Sheets read error: {e}")
        return pd.DataFrame(columns=COLUMNS)


def _save_to_sheets(row: dict):
    try:
        ws      = _get_worksheet()
        records = ws.get_all_records()
        week_str = pd.Timestamp(row["week_of"]).strftime("%Y-%m-%d")
        row_copy = dict(row)
        row_copy["week_of"] = week_str
        # Sanitise None → ""
        for k in row_copy:
            if row_copy[k] is None or (isinstance(row_copy[k], float) and pd.isna(row_copy[k])):
                row_copy[k] = ""

        # Find existing row index (1-based + 1 for header = data row)
        match_idx = None
        for i, rec in enumerate(records):
            if (str(rec.get("week_of", "")).startswith(week_str[:10]) and
                    rec.get("day") == row["day"] and
                    rec.get("session") == row["session"]):
                match_idx = i + 2  # 1-based, +1 for header row
                break

        ordered = [str(row_copy.get(c, "")) for c in COLUMNS]
        if match_idx:
            ws.update(f"A{match_idx}", [ordered])
        else:
            ws.append_row(ordered)

        # Clear load cache so next read reflects the write
        _load_from_sheets.clear() if hasattr(_load_from_sheets, "clear") else None
    except Exception as e:
        st.error(f"Sheets write error: {e}")


def _delete_from_sheets(week_of, day, session):
    try:
        ws       = _get_worksheet()
        records  = ws.get_all_records()
        week_str = pd.Timestamp(week_of).strftime("%Y-%m-%d")
        for i, rec in enumerate(records):
            if (str(rec.get("week_of", "")).startswith(week_str[:10]) and
                    rec.get("day") == day and
                    rec.get("session") == session):
                ws.delete_rows(i + 2)
                break
    except Exception as e:
        st.error(f"Sheets delete error: {e}")


# ── Local Excel implementation (unchanged from v1.0) ─────────────────────────

def _init_excel():
    if LOCAL_XLS.exists():
        return
    df = pd.DataFrame(columns=COLUMNS)
    with pd.ExcelWriter(LOCAL_XLS, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=SHEET_NAME, index=False)


def _load_from_excel() -> pd.DataFrame:
    _init_excel()
    try:
        df = pd.read_excel(LOCAL_XLS, sheet_name=SHEET_NAME, dtype={"week_of": str})
        df["week_of"] = pd.to_datetime(df["week_of"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame(columns=COLUMNS)


def _save_to_excel(row: dict):
    _init_excel()
    df = _load_from_excel()
    mask = (
        (df["week_of"] == row["week_of"]) &
        (df["day"]     == row["day"])     &
        (df["session"] == row["session"])
    )
    if mask.any():
        for col, val in row.items():
            df.loc[mask, col] = val
    else:
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df = df.sort_values(["week_of", "day", "session"]).reset_index(drop=True)
    with pd.ExcelWriter(LOCAL_XLS, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=SHEET_NAME, index=False)


def _delete_from_excel(week_of, day, session):
    df = _load_from_excel()
    mask = (
        (df["week_of"] == pd.Timestamp(week_of)) &
        (df["day"]     == day)                    &
        (df["session"] == session)
    )
    df = df[~mask].reset_index(drop=True)
    with pd.ExcelWriter(LOCAL_XLS, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=SHEET_NAME, index=False)
