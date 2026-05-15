"""
Google Sheets backend for daily settlement data.
Falls back to local Excel when credentials are not configured.

Schema: one row per (trade_date, expiry_code, market)
  trade_date   — YYYY-MM-DD the settlement was for
  expiry_code  — e.g. "JUL26", "SEP26", "DEC26"
  market       — "KC" (Arabica, ¢/lb) or "RC" (Robusta, USD/MT)
  settlement   — closing settlement price
  change       — day-over-day change
  high         — session high
  low          — session low
  last         — last traded price
  open_interest
  rc_cents_lb  — RC converted to ¢/lb (KC rows only carry this blank)
  spread_clb   — KC settlement − RC_cents_lb for the same expiry & date
"""

import pandas as pd
import streamlit as st
from pathlib import Path

# ── Column schema ─────────────────────────────────────────────────────────────
COLUMNS = [
    "trade_date",    # YYYY-MM-DD
    "expiry_code",   # JUL26 / SEP26 / DEC26 etc.
    "market",        # KC or RC
    "settlement",
    "change",
    "high",
    "low",
    "last",
    "open_interest",
    "rc_cents_lb",   # only populated for RC rows (conversion)
    "spread_clb",    # KC − RC in ¢/lb (populated on KC rows after RC is saved)
    "notes",
]

SHEET_NAME = "Settlements"
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
LOCAL_XLS  = DATA_DIR / "settlements.xlsx"
DATA_DIR.mkdir(exist_ok=True)

KC_TO_MT = 22.0462   # multiply ¢/lb × 22.0462 = USD/MT  →  divide USD/MT to get ¢/lb


# ── Credential helpers ────────────────────────────────────────────────────────

def _has_sheets_config() -> bool:
    try:
        _ = st.secrets["gcp_service_account"]
        _ = st.secrets["SHEET_ID"]
        return True
    except (KeyError, FileNotFoundError):
        return False


@st.cache_resource(ttl=3600)
def _get_gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=scopes
    )
    return gspread.authorize(creds)


def _get_worksheet():
    client   = _get_gspread_client()
    sheet_id = st.secrets["SHEET_ID"]
    wb       = client.open_by_key(sheet_id)
    try:
        ws = wb.worksheet(SHEET_NAME)
    except Exception:
        ws = wb.add_worksheet(title=SHEET_NAME, rows=5000, cols=len(COLUMNS))
        ws.append_row(COLUMNS)
    return ws


# ── Public API ────────────────────────────────────────────────────────────────

def load_settlements() -> pd.DataFrame:
    if _has_sheets_config():
        return _load_from_sheets()
    return _load_from_excel()


def upsert_settlement(row: dict):
    """Insert or overwrite one row keyed on (trade_date, expiry_code, market)."""
    if _has_sheets_config():
        _upsert_sheets(row)
    else:
        _upsert_excel(row)


def delete_settlement(trade_date: str, expiry_code: str, market: str):
    if _has_sheets_config():
        _delete_sheets(trade_date, expiry_code, market)
    else:
        _delete_excel(trade_date, expiry_code, market)


def backend_label() -> str:
    return "Google Sheets" if _has_sheets_config() else "Local Excel"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_key(row: dict) -> tuple:
    return (str(row.get("trade_date", ""))[:10],
            str(row.get("expiry_code", "")),
            str(row.get("market", "")))


def _clean(row: dict) -> dict:
    """Ensure every COLUMNS key exists and None/NaN → empty string."""
    out = {}
    for c in COLUMNS:
        v = row.get(c, "")
        if v is None or (isinstance(v, float) and pd.isna(v)):
            v = ""
        out[c] = v
    return out


# ── Google Sheets implementation ──────────────────────────────────────────────

def _load_from_sheets() -> pd.DataFrame:
    try:
        ws      = _get_worksheet()
        records = ws.get_all_records()
        if not records:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(records)
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        for col in ["settlement","change","high","low","last","open_interest","rc_cents_lb","spread_clb"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as e:
        st.warning(f"Sheets read error: {e}")
        return pd.DataFrame(columns=COLUMNS)


def _upsert_sheets(row: dict):
    try:
        ws       = _get_worksheet()
        records  = ws.get_all_records()
        key      = _row_key(row)
        row_copy = _clean(row)
        if isinstance(row_copy["trade_date"], pd.Timestamp):
            row_copy["trade_date"] = row_copy["trade_date"].strftime("%Y-%m-%d")

        match_idx = None
        for i, rec in enumerate(records):
            rk = (str(rec.get("trade_date",""))[:10],
                  str(rec.get("expiry_code","")),
                  str(rec.get("market","")))
            if rk == key:
                match_idx = i + 2
                break

        ordered = [str(row_copy.get(c, "")) for c in COLUMNS]
        if match_idx:
            ws.update(f"A{match_idx}", [ordered])
        else:
            ws.append_row(ordered)
    except Exception as e:
        st.error(f"Sheets write error: {e}")


def _delete_sheets(trade_date: str, expiry_code: str, market: str):
    try:
        ws      = _get_worksheet()
        records = ws.get_all_records()
        key     = (str(trade_date)[:10], str(expiry_code), str(market))
        for i, rec in enumerate(records):
            rk = (str(rec.get("trade_date",""))[:10],
                  str(rec.get("expiry_code","")),
                  str(rec.get("market","")))
            if rk == key:
                ws.delete_rows(i + 2)
                break
    except Exception as e:
        st.error(f"Sheets delete error: {e}")


# ── Local Excel implementation ────────────────────────────────────────────────

def _init_excel():
    if LOCAL_XLS.exists():
        return
    pd.DataFrame(columns=COLUMNS).to_excel(LOCAL_XLS, sheet_name=SHEET_NAME, index=False)


def _load_from_excel() -> pd.DataFrame:
    _init_excel()
    try:
        df = pd.read_excel(LOCAL_XLS, sheet_name=SHEET_NAME)
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        for col in ["settlement","change","high","low","last","open_interest","rc_cents_lb","spread_clb"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame(columns=COLUMNS)


def _upsert_excel(row: dict):
    _init_excel()
    df  = _load_from_excel()
    key = _row_key(row)

    mask = (
        (df["trade_date"].dt.strftime("%Y-%m-%d") == key[0]) &
        (df["expiry_code"] == key[1]) &
        (df["market"]      == key[2])
    )
    new_row = pd.DataFrame([_clean(row)])
    new_row["trade_date"] = pd.to_datetime(new_row["trade_date"], errors="coerce")

    if mask.any():
        df = df[~mask]
    df = pd.concat([df, new_row], ignore_index=True)
    df = df.sort_values(["trade_date", "expiry_code", "market"]).reset_index(drop=True)
    with pd.ExcelWriter(LOCAL_XLS, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=SHEET_NAME, index=False)


def _delete_excel(trade_date: str, expiry_code: str, market: str):
    df   = _load_from_excel()
    key  = (str(trade_date)[:10], str(expiry_code), str(market))
    mask = (
        (df["trade_date"].dt.strftime("%Y-%m-%d") == key[0]) &
        (df["expiry_code"] == key[1]) &
        (df["market"]      == key[2])
    )
    df = df[~mask].reset_index(drop=True)
    with pd.ExcelWriter(LOCAL_XLS, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=SHEET_NAME, index=False)


# ── Legacy shim — keeps Weekly Price History page working ─────────────────────
# The old load_prices / save_row API pointed at a different schema.
# These are kept so the history page doesn't break; they read from the same file.

def load_prices() -> pd.DataFrame:
    return load_settlements()

def save_row(row: dict):
    pass  # legacy no-op; entry page now uses upsert_settlement

def delete_row(*args):
    pass
