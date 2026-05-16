import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from pathlib import Path
from sheets_backend import (
    load_prices, save_row, delete_row, backend_label,
    load_settlements, upsert_settlement, KC_TO_MT as _KC_TO_MT,
)

st.set_page_config(
    page_title="Vidya Coffee Terminal",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling: dark terminal theme ────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0a0e1a; color: #c8d0e0; }
    .stMetric { background-color: #111827; border: 1px solid #1e2d40; border-radius: 6px; padding: 12px; }
    .stMetric label { color: #6b7fa3 !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 1px; }
    .stMetric [data-testid="metric-container"] { color: #e2e8f0; }
    .block-container { padding-top: 1rem; }
    h1, h2, h3 { color: #e2e8f0; font-family: 'Courier New', monospace; }
    .stSidebar { background-color: #0d1117; }
    div[data-testid="stSidebarNav"] { background-color: #0d1117; }
    .terminal-header {
        background: linear-gradient(90deg, #0f2027, #203a43, #2c5364);
        padding: 10px 20px;
        border-radius: 6px;
        margin-bottom: 20px;
        font-family: 'Courier New', monospace;
        color: #00d4ff;
        font-size: 22px;
        font-weight: bold;
        letter-spacing: 2px;
    }
    .section-label {
        background-color: #1a2332;
        color: #00aaff;
        font-family: 'Courier New', monospace;
        font-size: 11px;
        letter-spacing: 2px;
        padding: 4px 10px;
        border-left: 3px solid #00aaff;
        margin-bottom: 8px;
    }
    .positive { color: #00e676; }
    .negative { color: #ff5252; }
    hr { border-color: #1e2d40; }
    div[data-testid="stNumberInput"] input { background-color: #111827; color: #e2e8f0; border: 1px solid #1e2d40; }
    div[data-testid="stDateInput"] input { background-color: #111827; color: #e2e8f0; border: 1px solid #1e2d40; }
    .stDataFrame { background-color: #0d1117; }
    thead tr th { background-color: #1a2332 !important; color: #00aaff !important; font-family: 'Courier New', monospace; }
    tbody tr:nth-child(even) { background-color: #0d1117; }
    tbody tr:nth-child(odd)  { background-color: #111827; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
TICKERS = {
    "Arabica (KC)":  "KC=F",
    "Robusta (RC)":  "RC=F",
    "BRL/USD":       "BRL=X",
    "USD Index":     "DX-Y.NYB",
    "Sugar #11":     "SB=F",
    "Crude Oil":     "CL=F",
}

TIMEFRAMES = {
    "1 Day":   "1d",
    "5 Days":  "5d",
    "1 Month": "1mo",
    "3 Months":"3mo",
    "1 Year":  "1y",
    "2 Years": "2y",
}

INTERVALS = {
    "1d":  "5m",
    "5d":  "30m",
    "1mo": "1h",
    "3mo": "1d",
    "1y":  "1d",
    "2y":  "1wk",
}

KC_TO_MT = 22.0462  # cents/lb → USD/MT

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# ── Market data helpers ───────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch(ticker: str, period: str) -> pd.DataFrame:
    interval = INTERVALS.get(period, "1d")
    df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

@st.cache_data(ttl=300)
def fetch_quote(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.fast_info
    try:
        price  = info.last_price
        prev   = info.previous_close
        change = price - prev
        pct    = (change / prev) * 100 if prev else 0
        return {"price": price, "change": change, "pct": pct, "prev": prev}
    except Exception:
        return {"price": None, "change": 0, "pct": 0, "prev": None}

def candlestick_chart(df: pd.DataFrame, title: str, color: str = "#00aaff") -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return fig
    has_ohlc = all(c in df.columns for c in ["Open", "High", "Low", "Close"])
    if has_ohlc:
        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"],
            low=df["Low"],   close=df["Close"],
            increasing_line_color="#00e676",
            decreasing_line_color="#ff5252",
            name=title,
        ))
    else:
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"],
                                  line=dict(color=color, width=1.5), name=title))
    if "Volume" in df.columns and df["Volume"].sum() > 0:
        fig.add_trace(go.Bar(x=df.index, y=df["Volume"],
                              marker_color="rgba(0,170,255,0.15)", name="Volume", yaxis="y2"))
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", showgrid=False,
                        tickfont=dict(color="#4a5568", size=9), showticklabels=False))
    fig.update_layout(
        title=dict(text=title, font=dict(color="#c8d0e0", size=13, family="Courier New")),
        paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117",
        font=dict(color="#c8d0e0"),
        xaxis=dict(gridcolor="#1a2332", showgrid=True, rangeslider=dict(visible=False)),
        yaxis=dict(gridcolor="#1a2332", showgrid=True, side="left"),
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        height=320,
    )
    return fig

def large_candle_chart(df: pd.DataFrame, title: str, *,
                        price_unit: str = "¢/lb",
                        accent_color: str = "#00aaff",
                        height: int = 520) -> go.Figure:
    """Full-width candle chart with MA20/MA50 overlays and a volume sub-panel."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                         row_heights=[0.78, 0.22], vertical_spacing=0.03)
    if df.empty:
        fig.update_layout(
            title=dict(text=title + " — no data", font=dict(color="#c8d0e0", size=15)),
            paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117", height=height,
        )
        return fig

    has_ohlc = all(c in df.columns for c in ["Open","High","Low","Close"])
    if has_ohlc:
        fig.add_trace(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"],
            increasing_line_color="#00e676",
            decreasing_line_color="#ff5252",
            increasing_fillcolor="#00e676",
            decreasing_fillcolor="#ff5252",
            name="Price",
            showlegend=False,
        ), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"],
                                  line=dict(color=accent_color, width=1.5),
                                  name="Close"), row=1, col=1)

    # Moving averages
    if "Close" in df.columns:
        if len(df) >= 20:
            ma20 = df["Close"].rolling(20).mean()
            fig.add_trace(go.Scatter(x=df.index, y=ma20,
                                      line=dict(color="#ffeb3b", width=1.2, dash="dot"),
                                      name="MA 20"), row=1, col=1)
        if len(df) >= 50:
            ma50 = df["Close"].rolling(50).mean()
            fig.add_trace(go.Scatter(x=df.index, y=ma50,
                                      line=dict(color="#ff9800", width=1.2, dash="dot"),
                                      name="MA 50"), row=1, col=1)

    # Volume
    if "Volume" in df.columns and df["Volume"].sum() > 0:
        vol_colors = []
        if has_ohlc:
            for o, c in zip(df["Open"], df["Close"]):
                vol_colors.append("rgba(0,230,118,0.45)" if c >= o else "rgba(255,82,82,0.45)")
        else:
            vol_colors = "rgba(0,170,255,0.4)"
        fig.add_trace(go.Bar(x=df.index, y=df["Volume"],
                              marker_color=vol_colors, name="Volume",
                              showlegend=False), row=2, col=1)

    fig.update_layout(
        title=dict(text=title, font=dict(color="#e2e8f0", size=16,
                                          family="Courier New"), x=0.01),
        paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117",
        font=dict(color="#c8d0e0"),
        xaxis=dict(gridcolor="#1a2332", showgrid=True, rangeslider=dict(visible=False)),
        xaxis2=dict(gridcolor="#1a2332", showgrid=True),
        yaxis=dict(gridcolor="#1a2332", showgrid=True, title=price_unit, side="right"),
        yaxis2=dict(gridcolor="#1a2332", showgrid=False, title="Vol", side="right",
                     tickfont=dict(size=9, color="#6b7fa3")),
        margin=dict(l=10, r=60, t=50, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h",
                     y=1.02, x=0.99, xanchor="right",
                     font=dict(size=11)),
        height=height,
        hovermode="x unified",
    )
    return fig


def line_chart(x, y, title: str, color: str = "#00aaff", height: int = 260) -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=x, y=y,
        line=dict(color=color, width=1.5),
        fill="tozeroy",
        fillcolor="rgba(0,170,255,0.05)",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(color="#c8d0e0", size=12, family="Courier New")),
        paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117",
        xaxis=dict(gridcolor="#1a2332", showgrid=True, rangeslider=dict(visible=False)),
        yaxis=dict(gridcolor="#1a2332", showgrid=True),
        margin=dict(l=10, r=10, t=35, b=10),
        height=height, font=dict(color="#c8d0e0"),
    )
    return fig

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ☕ VIDYA TERMINAL")
    st.markdown("---")
    page = st.radio(
        "Navigate",
        ["Market Overview", "Arabica Deep Dive", "Robusta Deep Dive",
         "Spreads & Correlations", "Basis Calculator",
         "Weekly Price Entry", "Daily Price History",
         "TradingView Charts"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    timeframe_label = st.selectbox("Timeframe", list(TIMEFRAMES.keys()), index=2)
    period = TIMEFRAMES[timeframe_label]
    st.markdown("---")
    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    _bl = backend_label()
    _bl_color = "#00e676" if _bl == "Google Sheets" else "#ffeb3b"
    st.markdown(
        f"<small style='color:{_bl_color}'>&#9679; {_bl}</small><br>"
        f"<small style='color:#4a5568'>Last update: {datetime.now().strftime('%H:%M:%S')}</small>",
        unsafe_allow_html=True,
    )

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div class="terminal-header">☕ VIDYA GLOBAL COFFEE TERMINAL &nbsp;|&nbsp; '
    f'<span style="font-size:14px;color:#a0aec0">{datetime.now().strftime("%Y-%m-%d %H:%M")}</span></div>',
    unsafe_allow_html=True,
)

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: MARKET OVERVIEW
# ═════════════════════════════════════════════════════════════════════════════
if page == "Market Overview":
    st.markdown('<div class="section-label">MARKET OVERVIEW — LIVE QUOTES</div>', unsafe_allow_html=True)

    cols = st.columns(len(TICKERS))
    for i, (name, ticker) in enumerate(TICKERS.items()):
        q = fetch_quote(ticker)
        with cols[i]:
            if q["price"] is not None:
                st.metric(label=name, value=f"{q['price']:.2f}",
                          delta=f"{q['change']:+.2f} ({q['pct']:+.2f}%)",
                          delta_color="normal" if q["change"] >= 0 else "inverse")
            else:
                st.metric(label=name, value="N/A", delta="--")

    st.markdown("---")

    # ── NY Arabica — full-width candle chart ──────────────────────────────────
    st.markdown('<div class="section-label">NY ARABICA — KC FUTURES (¢/lb)</div>', unsafe_allow_html=True)
    df_kc = fetch("KC=F", period)
    st.plotly_chart(
        large_candle_chart(df_kc,
                           f"Arabica Coffee — {timeframe_label}",
                           price_unit="¢/lb",
                           accent_color="#00aaff",
                           height=520),
        use_container_width=True,
    )

    st.markdown("---")

    # ── London Robusta — full-width candle chart ──────────────────────────────
    st.markdown('<div class="section-label">LONDON ROBUSTA — RC FUTURES (USD/MT)</div>', unsafe_allow_html=True)
    df_rc = fetch("RC=F", period)
    st.plotly_chart(
        large_candle_chart(df_rc,
                           f"Robusta Coffee — {timeframe_label}",
                           price_unit="USD/MT",
                           accent_color="#ff9800",
                           height=520),
        use_container_width=True,
    )

    st.markdown("---")

    # ── Macro context: BRL/USD and DXY ────────────────────────────────────────
    st.markdown('<div class="section-label">MACRO CONTEXT</div>', unsafe_allow_html=True)
    macro_l, macro_r = st.columns(2)
    with macro_l:
        df_brl = fetch("BRL=X", period)
        if not df_brl.empty:
            st.plotly_chart(line_chart(df_brl.index, df_brl["Close"],
                                        "BRL/USD Exchange Rate",
                                        color="#00e676", height=320),
                            use_container_width=True)
    with macro_r:
        df_dxy = fetch("DX-Y.NYB", period)
        if not df_dxy.empty:
            st.plotly_chart(line_chart(df_dxy.index, df_dxy["Close"],
                                        "USD Index (DXY)",
                                        color="#ff9800", height=320),
                            use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: ARABICA DEEP DIVE
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Arabica Deep Dive":
    st.markdown('<div class="section-label">ARABICA (KC=F) — ICE COFFEE C CONTRACT</div>', unsafe_allow_html=True)

    q = fetch_quote("KC=F")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Last Price (¢/lb)", f"{q['price']:.2f}" if q['price'] else "N/A",
                  delta=f"{q['change']:+.2f}" if q['price'] else None)
    with c2:
        st.metric("Prev Close", f"{q['prev']:.2f}" if q.get("prev") else "N/A")
    df_kc_1y = fetch("KC=F", "1y")
    with c3:
        if not df_kc_1y.empty:
            st.metric("52W High", f"{df_kc_1y['High'].max():.2f}")
    with c4:
        if not df_kc_1y.empty:
            st.metric("52W Low", f"{df_kc_1y['Low'].min():.2f}")

    st.markdown("---")
    df_kc = fetch("KC=F", period)
    if not df_kc.empty:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            row_heights=[0.75, 0.25], vertical_spacing=0.03)
        if all(c in df_kc.columns for c in ["Open","High","Low","Close"]):
            fig.add_trace(go.Candlestick(
                x=df_kc.index, open=df_kc["Open"], high=df_kc["High"],
                low=df_kc["Low"], close=df_kc["Close"],
                increasing_line_color="#00e676", decreasing_line_color="#ff5252", name="KC"),
                row=1, col=1)
        if len(df_kc) >= 20:
            fig.add_trace(go.Scatter(x=df_kc.index, y=df_kc["Close"].rolling(20).mean(),
                                     line=dict(color="#ffeb3b", width=1, dash="dot"), name="MA20"), row=1, col=1)
        if len(df_kc) >= 50:
            fig.add_trace(go.Scatter(x=df_kc.index, y=df_kc["Close"].rolling(50).mean(),
                                     line=dict(color="#ff9800", width=1, dash="dot"), name="MA50"), row=1, col=1)
        if "Volume" in df_kc.columns:
            fig.add_trace(go.Bar(x=df_kc.index, y=df_kc["Volume"],
                                 marker_color="rgba(0,170,255,0.3)", name="Volume"), row=2, col=1)
        fig.update_layout(
            paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117", font=dict(color="#c8d0e0"),
            xaxis=dict(gridcolor="#1a2332", rangeslider=dict(visible=False)),
            xaxis2=dict(gridcolor="#1a2332"),
            yaxis=dict(gridcolor="#1a2332", title="Price (¢/lb)"),
            yaxis2=dict(gridcolor="#1a2332", title="Volume"),
            height=480, margin=dict(l=10, r=10, t=20, b=10),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-label">BRL/USD OVERLAY — BRAZIL ORIGIN IMPACT</div>', unsafe_allow_html=True)
    df_brl = fetch("BRL=X", period)
    if not df_kc.empty and not df_brl.empty:
        fig2 = make_subplots(specs=[[{"secondary_y": True}]])
        fig2.add_trace(go.Scatter(x=df_kc.index, y=df_kc["Close"],
                                   line=dict(color="#00aaff", width=1.5), name="KC (¢/lb)"), secondary_y=False)
        fig2.add_trace(go.Scatter(x=df_brl.index, y=df_brl["Close"],
                                   line=dict(color="#00e676", width=1.5, dash="dash"), name="BRL/USD"), secondary_y=True)
        fig2.update_layout(
            paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117", font=dict(color="#c8d0e0"),
            xaxis=dict(gridcolor="#1a2332"),
            yaxis=dict(gridcolor="#1a2332", title="KC Price (¢/lb)"),
            yaxis2=dict(title="BRL/USD", gridcolor="#1a2332"),
            height=300, margin=dict(l=10, r=10, t=20, b=10),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig2, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: ROBUSTA DEEP DIVE
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Robusta Deep Dive":
    st.markdown('<div class="section-label">ROBUSTA (RC=F) — ICE LIFFE CONTRACT</div>', unsafe_allow_html=True)

    q = fetch_quote("RC=F")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Last Price (USD/MT)", f"{q['price']:.2f}" if q['price'] else "N/A",
                  delta=f"{q['change']:+.2f}" if q['price'] else None)
    with c2:
        st.metric("Prev Close", f"{q['prev']:.2f}" if q.get("prev") else "N/A")
    df_rc_1y = fetch("RC=F", "1y")
    with c3:
        if not df_rc_1y.empty:
            st.metric("52W High", f"{df_rc_1y['High'].max():.2f}")
    with c4:
        if not df_rc_1y.empty:
            st.metric("52W Low", f"{df_rc_1y['Low'].min():.2f}")

    st.markdown("---")
    df_rc = fetch("RC=F", period)
    if not df_rc.empty:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            row_heights=[0.75, 0.25], vertical_spacing=0.03)
        if all(c in df_rc.columns for c in ["Open","High","Low","Close"]):
            fig.add_trace(go.Candlestick(
                x=df_rc.index, open=df_rc["Open"], high=df_rc["High"],
                low=df_rc["Low"], close=df_rc["Close"],
                increasing_line_color="#00e676", decreasing_line_color="#ff5252", name="RC"),
                row=1, col=1)
        if len(df_rc) >= 20:
            fig.add_trace(go.Scatter(x=df_rc.index, y=df_rc["Close"].rolling(20).mean(),
                                     line=dict(color="#ffeb3b", width=1, dash="dot"), name="MA20"), row=1, col=1)
        if "Volume" in df_rc.columns:
            fig.add_trace(go.Bar(x=df_rc.index, y=df_rc["Volume"],
                                 marker_color="rgba(255,152,0,0.3)", name="Volume"), row=2, col=1)
        fig.update_layout(
            paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117", font=dict(color="#c8d0e0"),
            xaxis=dict(gridcolor="#1a2332", rangeslider=dict(visible=False)),
            xaxis2=dict(gridcolor="#1a2332"),
            yaxis=dict(gridcolor="#1a2332", title="Price (USD/MT)"),
            yaxis2=dict(gridcolor="#1a2332", title="Volume"),
            height=480, margin=dict(l=10, r=10, t=20, b=10),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: SPREADS & CORRELATIONS
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Spreads & Correlations":
    st.markdown('<div class="section-label">ARABICA / ROBUSTA SPREAD (ARBING THE DIFFERENTIAL)</div>', unsafe_allow_html=True)

    df_kc = fetch("KC=F", period)
    df_rc = fetch("RC=F", period)

    if not df_kc.empty and not df_rc.empty:
        merged = pd.concat([df_kc["Close"].rename("KC"), df_rc["Close"].rename("RC")], axis=1).dropna()
        if not merged.empty:
            merged["KC_usd_mt"] = merged["KC"] * KC_TO_MT
            merged["Spread_usd_mt"] = merged["KC_usd_mt"] - merged["RC"]

            col1, col2 = st.columns(2)
            spread_now = merged["Spread_usd_mt"].iloc[-1]
            spread_avg = merged["Spread_usd_mt"].mean()
            with col1:
                st.metric("Current Spread (USD/MT)", f"${spread_now:,.0f}",
                          delta=f"{spread_now - spread_avg:+.0f} vs avg")
            with col2:
                st.metric("Period Avg Spread", f"${spread_avg:,.0f}")

            fig = line_chart(merged.index, merged["Spread_usd_mt"],
                             "Arabica–Robusta Spread (USD/MT)", color="#9c27b0", height=300)
            fig.add_hline(y=spread_avg, line_dash="dot", line_color="#4a5568",
                          annotation_text="avg", annotation_font_color="#6b7fa3")
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")
            st.markdown('<div class="section-label">SIDE-BY-SIDE NORMALIZED (INDEXED TO 100)</div>', unsafe_allow_html=True)
            merged["KC_idx"] = (merged["KC"] / merged["KC"].iloc[0]) * 100
            merged["RC_idx"] = (merged["RC"] / merged["RC"].iloc[0]) * 100
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=merged.index, y=merged["KC_idx"],
                                       line=dict(color="#00aaff", width=1.5), name="Arabica (KC)"))
            fig2.add_trace(go.Scatter(x=merged.index, y=merged["RC_idx"],
                                       line=dict(color="#ff9800", width=1.5), name="Robusta (RC)"))
            fig2.add_hline(y=100, line_dash="dot", line_color="#4a5568")
            fig2.update_layout(
                paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117", font=dict(color="#c8d0e0"),
                xaxis=dict(gridcolor="#1a2332"),
                yaxis=dict(gridcolor="#1a2332", title="Indexed (base=100)"),
                height=300, margin=dict(l=10, r=10, t=20, b=10),
                legend=dict(bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")
    st.markdown('<div class="section-label">CORRELATION MATRIX</div>', unsafe_allow_html=True)
    tickers_corr = {"KC (Arabica)": "KC=F", "RC (Robusta)": "RC=F",
                    "BRL/USD": "BRL=X", "DXY": "DX-Y.NYB", "Sugar": "SB=F"}
    frames = {}
    for name, tkr in tickers_corr.items():
        df = fetch(tkr, "1y")
        if not df.empty:
            frames[name] = df["Close"]
    if len(frames) > 1:
        combined = pd.DataFrame(frames).dropna()
        corr = combined.pct_change().dropna().corr().round(2)
        fig3 = go.Figure(go.Heatmap(
            z=corr.values, x=corr.columns.tolist(), y=corr.index.tolist(),
            colorscale="RdBu", zmid=0, text=corr.values,
            texttemplate="%{text}", textfont=dict(size=12),
            colorbar=dict(tickfont=dict(color="#c8d0e0")),
        ))
        fig3.update_layout(
            paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117", font=dict(color="#c8d0e0"),
            height=350, margin=dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(fig3, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: BASIS CALCULATOR
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Basis Calculator":
    st.markdown('<div class="section-label">PHYSICAL BASIS CALCULATOR — YOUR CONTRACT VS THE SCREEN</div>', unsafe_allow_html=True)
    st.markdown("**Basis** = Physical contract price − ICE futures price")
    st.markdown("---")
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Contract Inputs**")
        contract_type  = st.selectbox("Contract Type", ["Arabica (KC) — ¢/lb", "Robusta (RC) — USD/MT"])
        physical_price = st.number_input("Your Physical Price", min_value=0.0, value=175.0)
        origin         = st.selectbox("Origin", ["Brazil","Colombia","Ethiopia","Guatemala",
                                                  "Peru","Honduras","Vietnam","Indonesia","Other"])
        grade          = st.text_input("Grade / Description", placeholder="e.g. Brazil NY2/3 Fine Cup 17/18")
        quantity_bags  = st.number_input("Quantity (bags)", min_value=0, value=250, step=50)
        quantity_mt    = quantity_bags * 0.06

    with c2:
        st.markdown("**Screen Price (auto-fetched)**")
        is_arabica   = "Arabica" in contract_type
        ticker       = "KC=F" if is_arabica else "RC=F"
        q            = fetch_quote(ticker)
        screen_price = q["price"] if q["price"] else 0.0
        st.metric("ICE Screen Price" + (" (¢/lb)" if is_arabica else " (USD/MT)"),
                  f"{screen_price:.2f}",
                  delta=f"{q['change']:+.2f} ({q['pct']:+.2f}%)" if q["price"] else None)
        screen_override = st.number_input("Override Screen Price (optional)", min_value=0.0, value=0.0)
        if screen_override > 0:
            screen_price = screen_override
        if screen_price > 0:
            basis = physical_price - screen_price
            basis_pct = (basis / screen_price) * 100
            st.metric("Basis (¢/lb)" if is_arabica else "Basis (USD/MT)",
                      f"{basis:+.2f}", delta=f"{basis_pct:+.2f}% vs screen")
            if is_arabica:
                st.metric("Basis in USD/MT", f"${basis * KC_TO_MT:+,.0f}")

    st.markdown("---")
    if screen_price > 0 and quantity_bags > 0:
        st.markdown('<div class="section-label">POSITION SUMMARY</div>', unsafe_allow_html=True)
        physical_usd_mt = physical_price * KC_TO_MT if is_arabica else physical_price
        screen_usd_mt   = screen_price   * KC_TO_MT if is_arabica else screen_price
        total_value_physical = physical_usd_mt * quantity_mt
        total_value_screen   = screen_usd_mt   * quantity_mt
        pnl_vs_screen        = total_value_physical - total_value_screen
        p1, p2, p3, p4 = st.columns(4)
        with p1: st.metric("Quantity (MT)", f"{quantity_mt:.1f}")
        with p2: st.metric("Physical Value", f"${total_value_physical:,.0f}")
        with p3: st.metric("Screen Value", f"${total_value_screen:,.0f}")
        with p4: st.metric("P&L vs Screen", f"${pnl_vs_screen:+,.0f}",
                           delta_color="normal" if pnl_vs_screen >= 0 else "inverse")

    st.markdown("---")
    st.markdown('<div class="section-label">HISTORICAL CONTEXT</div>', unsafe_allow_html=True)
    df_hist = fetch(ticker, "1y")
    if not df_hist.empty and screen_price > 0:
        percentile = (df_hist["Close"] < screen_price).mean() * 100
        fig = line_chart(df_hist.index, df_hist["Close"],
                         f"{'KC' if is_arabica else 'RC'} — 1 Year Historical", color="#00aaff", height=250)
        fig.add_hline(y=screen_price, line_color="#ff5252", line_dash="dash",
                      annotation_text=f"Current: {screen_price:.2f}", annotation_font_color="#ff5252")
        if physical_price > 0:
            fig.add_hline(y=physical_price, line_color="#00e676", line_dash="dash",
                          annotation_text=f"Your Price: {physical_price:.2f}", annotation_font_color="#00e676")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(f"Current screen price is in the **{percentile:.0f}th percentile** of the past 12 months.")

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: WEEKLY PRICE ENTRY
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Weekly Price Entry":

    # ── Expiry month definitions ──────────────────────────────────────────────
    # Arabica (KC): Mar, May, Jul, Sep, Dec
    # Robusta (RC): Jan, Mar, May, Jul, Sep, Nov
    KC_MONTHS = ["JAN","MAR","MAY","JUL","SEP","DEC"]
    RC_MONTHS = ["JAN","MAR","MAY","JUL","SEP","NOV"]

    def _next_expiries(months_list: list, n: int = 6) -> list:
        """Return next n expiry codes (e.g. JUL26) from today forward."""
        today = datetime.today()
        month_nums = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                      "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
        results = []
        year = today.year
        for _ in range(n * 3):  # scan enough calendar space
            for m in months_list:
                mn = month_nums[m]
                if (year > today.year) or (year == today.year and mn >= today.month):
                    code = f"{m}{str(year)[-2:]}"
                    if code not in results:
                        results.append(code)
                        if len(results) == n:
                            return results
            year += 1
        return results

    KC_EXPIRIES = _next_expiries(KC_MONTHS, 6)   # e.g. [JUL26, SEP26, DEC26, MAR27, MAY27, JUL27]
    RC_EXPIRIES = _next_expiries(RC_MONTHS, 6)

    # ── Page header ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">DAILY SETTLEMENT ENTRY — NY ARABICA & LONDON ROBUSTA</div>', unsafe_allow_html=True)
    st.markdown(
        "Enter settlements from your **StoneX / Sucden** daily report. "
        "Select the trade date, then fill in each expiry row. "
        "Spread (KC − RC in ¢/lb) is calculated automatically."
    )
    st.markdown("---")

    # ── Date selector ─────────────────────────────────────────────────────────
    today_date  = datetime.today().date()
    # Default to most recent weekday
    default_day = today_date
    if default_day.weekday() > 4:   # weekend → back to Friday
        default_day = default_day - timedelta(days=default_day.weekday() - 4)

    hdr1, hdr2 = st.columns([2, 6])
    with hdr1:
        trade_date = st.date_input("Trade Date", value=default_day,
                                   help="The date the settlements are for (not today's entry date).")
    trade_date_str = trade_date.strftime("%Y-%m-%d")

    # Load all saved data once
    df_all = load_settlements()
    df_day = (df_all[df_all["trade_date"].dt.strftime("%Y-%m-%d") == trade_date_str].copy()
              if not df_all.empty else pd.DataFrame())

    def _get(market, expiry, field):
        if df_day.empty:
            return 0.0
        r = df_day[(df_day["market"] == market) & (df_day["expiry_code"] == expiry)]
        if r.empty:
            return 0.0
        v = r.iloc[0].get(field, 0.0)
        return float(v) if pd.notna(v) and v != "" else 0.0

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════════════
    # NY ARABICA TABLE  (KC — ¢/lb)
    # ═════════════════════════════════════════════════════════════════════════
    st.markdown(
        '<div class="section-label">NY ARABICA — KC FUTURES &nbsp;|&nbsp; ¢/lb</div>',
        unsafe_allow_html=True,
    )

    # Column header
    kc_hdr = st.columns([1.2, 1.6, 1.6, 1.6, 1.6, 1.6, 1.8, 1.0])
    for col, lbl in zip(kc_hdr, ["EXPIRY","SETTLEMENT","CHG","HI","LO","LAST","OPEN INT",""]):
        col.markdown(
            f"<div style='font-family:Courier New;font-size:11px;color:#6b7fa3;"
            f"letter-spacing:1px;padding-bottom:4px'>{lbl}</div>",
            unsafe_allow_html=True,
        )
    st.markdown("<hr style='margin:2px 0 6px 0;border-color:#1e2d40'>", unsafe_allow_html=True)

    kc_saved_rows = {}
    for exp in KC_EXPIRIES:
        key = f"kc_{trade_date_str}_{exp}"
        cols = st.columns([1.2, 1.6, 1.6, 1.6, 1.6, 1.6, 1.8, 1.0])

        with cols[0]:
            st.markdown(
                f"<div style='padding-top:6px;font-family:Courier New;font-size:13px;"
                f"color:#00aaff;font-weight:bold'>{exp}</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            settle = st.number_input("", min_value=0.0, value=_get("KC",exp,"settlement"),
                                     step=0.05, format="%.2f",
                                     key=f"{key}_s", label_visibility="collapsed")
        with cols[2]:
            chg = st.number_input("", value=_get("KC",exp,"change"),
                                  step=0.05, format="%.2f",
                                  key=f"{key}_c", label_visibility="collapsed")
        with cols[3]:
            hi = st.number_input("", min_value=0.0, value=_get("KC",exp,"high"),
                                 step=0.05, format="%.2f",
                                 key=f"{key}_h", label_visibility="collapsed")
        with cols[4]:
            lo = st.number_input("", min_value=0.0, value=_get("KC",exp,"low"),
                                 step=0.05, format="%.2f",
                                 key=f"{key}_l", label_visibility="collapsed")
        with cols[5]:
            last = st.number_input("", min_value=0.0, value=_get("KC",exp,"last"),
                                   step=0.05, format="%.2f",
                                   key=f"{key}_la", label_visibility="collapsed")
        with cols[6]:
            oi = st.number_input("", min_value=0, value=int(_get("KC",exp,"open_interest")),
                                 step=1,
                                 key=f"{key}_oi", label_visibility="collapsed")
        with cols[7]:
            save_kc = st.button("Save", key=f"{key}_btn", use_container_width=True)

        kc_saved_rows[exp] = {
            "settle": settle, "chg": chg, "hi": hi, "lo": lo,
            "last": last, "oi": oi, "save": save_kc,
        }
        st.markdown("<hr style='margin:1px 0;border-color:#111827'>", unsafe_allow_html=True)

    st.markdown("---")

    # ═════════════════════════════════════════════════════════════════════════
    # LONDON ROBUSTA TABLE  (RC — USD/MT)
    # ═════════════════════════════════════════════════════════════════════════
    st.markdown(
        '<div class="section-label">LONDON ROBUSTA — RC FUTURES &nbsp;|&nbsp; USD/MT</div>',
        unsafe_allow_html=True,
    )

    rc_hdr = st.columns([1.2, 1.6, 1.6, 1.6, 1.6, 1.6, 1.8, 1.0])
    for col, lbl in zip(rc_hdr, ["EXPIRY","SETTLEMENT","CHG","HI","LO","LAST","OPEN INT",""]):
        col.markdown(
            f"<div style='font-family:Courier New;font-size:11px;color:#6b7fa3;"
            f"letter-spacing:1px;padding-bottom:4px'>{lbl}</div>",
            unsafe_allow_html=True,
        )
    st.markdown("<hr style='margin:2px 0 6px 0;border-color:#1e2d40'>", unsafe_allow_html=True)

    rc_saved_rows = {}
    for exp in RC_EXPIRIES:
        key = f"rc_{trade_date_str}_{exp}"
        cols = st.columns([1.2, 1.6, 1.6, 1.6, 1.6, 1.6, 1.8, 1.0])

        with cols[0]:
            st.markdown(
                f"<div style='padding-top:6px;font-family:Courier New;font-size:13px;"
                f"color:#ff9800;font-weight:bold'>{exp}</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            settle = st.number_input("", min_value=0.0, value=_get("RC",exp,"settlement"),
                                     step=1.0, format="%.2f",
                                     key=f"{key}_s", label_visibility="collapsed")
        with cols[2]:
            chg = st.number_input("", value=_get("RC",exp,"change"),
                                  step=1.0, format="%.2f",
                                  key=f"{key}_c", label_visibility="collapsed")
        with cols[3]:
            hi = st.number_input("", min_value=0.0, value=_get("RC",exp,"high"),
                                 step=1.0, format="%.2f",
                                 key=f"{key}_h", label_visibility="collapsed")
        with cols[4]:
            lo = st.number_input("", min_value=0.0, value=_get("RC",exp,"low"),
                                 step=1.0, format="%.2f",
                                 key=f"{key}_l", label_visibility="collapsed")
        with cols[5]:
            last = st.number_input("", min_value=0.0, value=_get("RC",exp,"last"),
                                   step=1.0, format="%.2f",
                                   key=f"{key}_la", label_visibility="collapsed")
        with cols[6]:
            oi = st.number_input("", min_value=0, value=int(_get("RC",exp,"open_interest")),
                                 step=1,
                                 key=f"{key}_oi", label_visibility="collapsed")
        with cols[7]:
            save_rc = st.button("Save", key=f"{key}_btn", use_container_width=True)

        rc_saved_rows[exp] = {
            "settle": settle, "chg": chg, "hi": hi, "lo": lo,
            "last": last, "oi": oi, "save": save_rc,
        }
        st.markdown("<hr style='margin:1px 0;border-color:#111827'>", unsafe_allow_html=True)

    # ── Process saves ─────────────────────────────────────────────────────────
    for exp, vals in kc_saved_rows.items():
        if vals["save"]:
            upsert_settlement({
                "trade_date": trade_date_str, "expiry_code": exp, "market": "KC",
                "settlement": vals["settle"], "change": vals["chg"],
                "high": vals["hi"], "low": vals["lo"],
                "last": vals["last"], "open_interest": vals["oi"],
                "rc_cents_lb": "", "spread_clb": "", "notes": "",
            })
            st.success(f"Saved KC {exp}")
            st.rerun()

    for exp, vals in rc_saved_rows.items():
        if vals["save"]:
            rc_clb = round(vals["settle"] / _KC_TO_MT, 4) if vals["settle"] > 0 else ""
            # Try to compute spread against KC same expiry same date
            kc_match = (_get("KC", exp, "settlement") if not df_day.empty else 0.0)
            spread   = round(kc_match - (vals["settle"] / _KC_TO_MT), 4) if (kc_match > 0 and vals["settle"] > 0) else ""
            upsert_settlement({
                "trade_date": trade_date_str, "expiry_code": exp, "market": "RC",
                "settlement": vals["settle"], "change": vals["chg"],
                "high": vals["hi"], "low": vals["lo"],
                "last": vals["last"], "open_interest": vals["oi"],
                "rc_cents_lb": rc_clb, "spread_clb": spread, "notes": "",
            })
            st.success(f"Saved RC {exp}")
            st.rerun()

    # ═════════════════════════════════════════════════════════════════════════
    # SPREAD SUMMARY TABLE — shown after both KC and RC have data
    # ═════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown('<div class="section-label">SPREAD SUMMARY — KC minus RC (¢/lb) BY EXPIRY</div>', unsafe_allow_html=True)

    df_day2 = (df_all[df_all["trade_date"].dt.strftime("%Y-%m-%d") == trade_date_str].copy()
               if not df_all.empty else pd.DataFrame())

    if not df_day2.empty:
        kc_df = df_day2[df_day2["market"] == "KC"][["expiry_code","settlement"]].rename(columns={"settlement":"kc"})
        rc_df = df_day2[df_day2["market"] == "RC"][["expiry_code","settlement","rc_cents_lb"]].rename(columns={"settlement":"rc_usd_mt"})
        spread_df = kc_df.merge(rc_df, on="expiry_code", how="inner")
        spread_df["rc_clb"]  = spread_df["rc_usd_mt"] / _KC_TO_MT
        spread_df["spread"]  = spread_df["kc"] - spread_df["rc_clb"]

        if not spread_df.empty:
            sp_cols = st.columns(min(len(spread_df), 6))
            for i, (_, row) in enumerate(spread_df.iterrows()):
                if i >= len(sp_cols):
                    break
                with sp_cols[i]:
                    color = "#00e676" if row["spread"] >= 0 else "#ff5252"
                    sign  = "+" if row["spread"] >= 0 else ""
                    st.markdown(
                        f"<div style='background:#111827;border:1px solid #1e2d40;"
                        f"border-radius:6px;padding:10px;text-align:center'>"
                        f"<div style='font-family:Courier New;font-size:11px;color:#6b7fa3'>{row['expiry_code']}</div>"
                        f"<div style='font-size:18px;font-weight:bold;color:{color}'>{sign}{row['spread']:.2f}</div>"
                        f"<div style='font-size:10px;color:#4a5568'>¢/lb</div>"
                        f"<div style='font-size:11px;color:#a0aec0;margin-top:4px'>"
                        f"KC {row['kc']:.2f} &nbsp;|&nbsp; RC {row['rc_usd_mt']:.0f}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.info("Enter both KC and RC settlements for the same expiry to see the spread.")

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: DAILY PRICE HISTORY
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Daily Price History":
    st.markdown('<div class="section-label">DAILY SETTLEMENT HISTORY — NY ARABICA vs LONDON ROBUSTA</div>', unsafe_allow_html=True)

    df_all = load_settlements()

    if df_all.empty or "settlement" not in df_all.columns:
        st.info("No data yet. Use **Daily Price Entry** to start logging settlements.")
    else:
        df_all = df_all.dropna(subset=["settlement"])
        df_all["trade_date"] = pd.to_datetime(df_all["trade_date"])

        # ── Filters bar ──────────────────────────────────────────────────────
        all_expiries = sorted(df_all["expiry_code"].dropna().unique())

        if not all_expiries:
            st.info("No settlements saved yet. Use **Weekly Price Entry** to add data.")
            st.stop()

        f1, f2, f3 = st.columns([2, 2, 2])

        with f1:
            sel_expiry = st.selectbox("Expiry", all_expiries, index=0)

        # Compute date range for the selected expiry so the slider max is meaningful
        df_sel_pre = df_all[df_all["expiry_code"] == all_expiries[0]]
        expiry_dates = sorted(df_sel_pre["trade_date"].dropna().unique())
        n_available  = max(len(expiry_dates), 1)

        with f2:
            n_days = st.slider("Days to show", min_value=1,
                               max_value=n_available,
                               value=min(30, n_available))
        with f3:
            show_ma20 = st.checkbox("MA 20", value=True)
            show_ma50 = st.checkbox("MA 50", value=True)

        # Filter to selected expiry and last n days
        df_exp = df_all[df_all["expiry_code"] == sel_expiry].copy()
        recent_dates = sorted(df_exp["trade_date"].dropna().unique())[-n_days:]
        df_exp = df_exp[df_exp["trade_date"].isin(recent_dates)].sort_values("trade_date")

        kc = df_exp[df_exp["market"] == "KC"].set_index("trade_date").sort_index()
        rc = df_exp[df_exp["market"] == "RC"].set_index("trade_date").sort_index()

        # ── KPI cards ─────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown(f'<div class="section-label">KPIs — {sel_expiry} &nbsp;|&nbsp; LAST {n_days} SESSIONS</div>', unsafe_allow_html=True)

        k1, k2, k3, k4, k5, k6 = st.columns(6)

        def _latest(s): return float(s.iloc[-1]) if len(s) else None
        def _chg(s):    return float(s.iloc[-1] - s.iloc[-2]) if len(s) >= 2 else None
        def _fmt(v, fmt): return fmt % v if v is not None else "—"

        kc_settle = kc["settlement"].dropna() if not kc.empty and "settlement" in kc.columns else pd.Series(dtype=float)
        rc_settle = rc["settlement"].dropna() if not rc.empty and "settlement" in rc.columns else pd.Series(dtype=float)
        rc_clb    = rc_settle / _KC_TO_MT

        # Align KC and RC on shared dates for spread calculation
        spread_series = pd.concat([kc_settle.rename("kc"), rc_clb.rename("rc")], axis=1).dropna()

        with k1:
            v = _latest(kc_settle)
            d = _chg(kc_settle)
            st.metric("KC Last (¢/lb)", _fmt(v, "%.2f"),
                      delta=f"{d:+.2f}" if d is not None else None)
        with k2:
            v = _latest(rc_settle)
            d = _chg(rc_settle)
            st.metric("RC Last (USD/MT)", _fmt(v, "%.0f"),
                      delta=f"{d:+.0f}" if d is not None else None)
        with k3:
            if len(spread_series) >= 1:
                sp_vals = spread_series["kc"] - spread_series["rc"]
                cur  = float(sp_vals.iloc[-1])
                prev = float(sp_vals.iloc[-2]) if len(sp_vals) >= 2 else None
                d    = round(cur - prev, 2) if prev is not None else None
                st.metric("Spread KC−RC (¢/lb)", f"{cur:+.2f}",
                          delta=f"{d:+.2f}" if d is not None else None)
            else:
                st.metric("Spread KC−RC (¢/lb)", "—")
        with k4:
            if len(kc_settle) >= 5:
                wk = float(kc_settle.iloc[-1] - kc_settle.iloc[-5])
                st.metric("KC 5-Day Chg", f"{wk:+.2f} ¢/lb")
            else:
                st.metric("KC 5-Day Chg", "—")
        with k5:
            if len(rc_settle) >= 5:
                wk_rc = float(rc_settle.iloc[-1] - rc_settle.iloc[-5])
                st.metric("RC 5-Day Chg", f"{wk_rc:+.0f} USD/MT")
            else:
                st.metric("RC 5-Day Chg", "—")
        with k6:
            if len(kc_settle) >= 2:
                hi = float(kc_settle.max())
                lo = float(kc_settle.min())
                st.metric("KC Range", f"{lo:.2f} – {hi:.2f}", delta=f"{hi-lo:.2f} spread")
            else:
                st.metric("KC Range", "—")

        st.markdown("---")

        # ── Chart 1: KC settlement with MA20/MA50 ────────────────────────────
        st.markdown('<div class="section-label">NY ARABICA KC — DAILY SETTLEMENTS (¢/lb)</div>', unsafe_allow_html=True)

        if not kc.empty and "settlement" in kc.columns:
            fig_kc = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                   row_heights=[0.72, 0.28], vertical_spacing=0.03)

            fig_kc.add_trace(go.Scatter(
                x=kc.index, y=kc["settlement"],
                mode="lines+markers", marker=dict(size=5),
                line=dict(color="#00aaff", width=2), name="KC Settlement",
            ), row=1, col=1)

            # HI/LO range band
            if "high" in kc.columns and "low" in kc.columns:
                kc_hi = kc["high"].dropna()
                kc_lo = kc["low"].dropna()
                if not kc_hi.empty:
                    fig_kc.add_trace(go.Scatter(
                        x=list(kc_hi.index) + list(kc_lo.index[::-1]),
                        y=list(kc_hi.values) + list(kc_lo.values[::-1]),
                        fill="toself", fillcolor="rgba(0,170,255,0.07)",
                        line=dict(color="rgba(0,0,0,0)"), name="Hi/Lo Range", showlegend=True,
                    ), row=1, col=1)

            if show_ma20 and len(kc_settle) >= 5:
                ma20 = kc_settle.rolling(min(20, len(kc_settle))).mean()
                fig_kc.add_trace(go.Scatter(
                    x=ma20.index, y=ma20,
                    line=dict(color="#ffeb3b", width=1.2, dash="dot"), name="MA20",
                ), row=1, col=1)

            if show_ma50 and len(kc_settle) >= 10:
                ma50 = kc_settle.rolling(min(50, len(kc_settle))).mean()
                fig_kc.add_trace(go.Scatter(
                    x=ma50.index, y=ma50,
                    line=dict(color="#ff9800", width=1.2, dash="dot"), name="MA50",
                ), row=1, col=1)

            # Daily change bars
            if "change" in kc.columns:
                kc_chg = kc["change"].dropna()
                fig_kc.add_trace(go.Bar(
                    x=kc_chg.index, y=kc_chg,
                    marker_color=["#00e676" if v >= 0 else "#ff5252" for v in kc_chg],
                    name="Daily Chg",
                ), row=2, col=1)
                fig_kc.add_hline(y=0, line_color="#1e2d40", row=2, col=1)

            fig_kc.update_layout(
                paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117", font=dict(color="#c8d0e0"),
                xaxis2=dict(gridcolor="#1a2332"),
                yaxis=dict(gridcolor="#1a2332", title="¢/lb"),
                yaxis2=dict(gridcolor="#1a2332", title="Chg"),
                height=460, margin=dict(l=10, r=10, t=20, b=10),
                legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.05),
                xaxis=dict(gridcolor="#1a2332", rangeslider=dict(visible=False)),
            )
            st.plotly_chart(fig_kc, use_container_width=True)
        else:
            st.info("No KC data for this expiry yet.")

        st.markdown("---")

        # ── Chart 2: RC settlement with MA20/MA50 ────────────────────────────
        st.markdown('<div class="section-label">LONDON ROBUSTA RC — DAILY SETTLEMENTS (USD/MT)</div>', unsafe_allow_html=True)

        if not rc.empty and "settlement" in rc.columns:
            fig_rc = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                   row_heights=[0.72, 0.28], vertical_spacing=0.03)

            fig_rc.add_trace(go.Scatter(
                x=rc.index, y=rc["settlement"],
                mode="lines+markers", marker=dict(size=5),
                line=dict(color="#ff9800", width=2), name="RC Settlement",
            ), row=1, col=1)

            if "high" in rc.columns and "low" in rc.columns:
                rc_hi = rc["high"].dropna()
                rc_lo = rc["low"].dropna()
                if not rc_hi.empty:
                    fig_rc.add_trace(go.Scatter(
                        x=list(rc_hi.index) + list(rc_lo.index[::-1]),
                        y=list(rc_hi.values) + list(rc_lo.values[::-1]),
                        fill="toself", fillcolor="rgba(255,152,0,0.07)",
                        line=dict(color="rgba(0,0,0,0)"), name="Hi/Lo Range",
                    ), row=1, col=1)

            if show_ma20 and len(rc_settle) >= 5:
                ma20_rc = rc_settle.rolling(min(20, len(rc_settle))).mean()
                fig_rc.add_trace(go.Scatter(
                    x=ma20_rc.index, y=ma20_rc,
                    line=dict(color="#ffeb3b", width=1.2, dash="dot"), name="MA20",
                ), row=1, col=1)

            if show_ma50 and len(rc_settle) >= 10:
                ma50_rc = rc_settle.rolling(min(50, len(rc_settle))).mean()
                fig_rc.add_trace(go.Scatter(
                    x=ma50_rc.index, y=ma50_rc,
                    line=dict(color="#00e676", width=1.2, dash="dot"), name="MA50",
                ), row=1, col=1)

            if "change" in rc.columns:
                rc_chg = rc["change"].dropna()
                fig_rc.add_trace(go.Bar(
                    x=rc_chg.index, y=rc_chg,
                    marker_color=["#00e676" if v >= 0 else "#ff5252" for v in rc_chg],
                    name="Daily Chg",
                ), row=2, col=1)
                fig_rc.add_hline(y=0, line_color="#1e2d40", row=2, col=1)

            fig_rc.update_layout(
                paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117", font=dict(color="#c8d0e0"),
                xaxis2=dict(gridcolor="#1a2332"),
                yaxis=dict(gridcolor="#1a2332", title="USD/MT"),
                yaxis2=dict(gridcolor="#1a2332", title="Chg"),
                height=460, margin=dict(l=10, r=10, t=20, b=10),
                legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.05),
                xaxis=dict(gridcolor="#1a2332", rangeslider=dict(visible=False)),
            )
            st.plotly_chart(fig_rc, use_container_width=True)
        else:
            st.info("No RC data for this expiry yet.")

        st.markdown("---")

        # ── Chart 3: KC vs RC normalized + spread ────────────────────────────
        st.markdown('<div class="section-label">KC vs RC — INDEXED TO 100 & SPREAD (¢/lb)</div>', unsafe_allow_html=True)

        if not kc.empty and not rc.empty:
            merged = pd.DataFrame({
                "kc": kc["settlement"],
                "rc_usd": rc["settlement"],
            }).dropna()
            merged["rc_clb"] = merged["rc_usd"] / _KC_TO_MT
            merged["spread"] = merged["kc"] - merged["rc_clb"]

            if len(merged) >= 2:
                merged["kc_idx"] = (merged["kc"] / merged["kc"].iloc[0]) * 100
                merged["rc_idx"] = (merged["rc_usd"] / merged["rc_usd"].iloc[0]) * 100

                fig_vs = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                       row_heights=[0.6, 0.4], vertical_spacing=0.04,
                                       subplot_titles=["Indexed to 100 (start of window)", "Spread KC−RC (¢/lb)"])

                fig_vs.add_trace(go.Scatter(
                    x=merged.index, y=merged["kc_idx"],
                    line=dict(color="#00aaff", width=2), name="KC (indexed)",
                ), row=1, col=1)
                fig_vs.add_trace(go.Scatter(
                    x=merged.index, y=merged["rc_idx"],
                    line=dict(color="#ff9800", width=2), name="RC (indexed)",
                ), row=1, col=1)
                fig_vs.add_hline(y=100, line_color="#1e2d40", row=1, col=1)

                spread_avg = float(merged["spread"].mean())
                spread_colors = ["#00e676" if v >= 0 else "#ff5252" for v in merged["spread"]]
                fig_vs.add_trace(go.Bar(
                    x=merged.index, y=merged["spread"],
                    marker_color=spread_colors, name="Spread (¢/lb)",
                ), row=2, col=1)
                fig_vs.add_trace(go.Scatter(
                    x=merged.index, y=merged["spread"].rolling(5).mean(),
                    line=dict(color="#9c27b0", width=1.5, dash="dot"), name="5-day MA spread",
                ), row=2, col=1)
                fig_vs.add_hline(y=spread_avg, line_color="#4a5568", line_dash="dot",
                                 annotation_text=f"avg {spread_avg:.2f}",
                                 annotation_font_color="#6b7fa3", row=2, col=1)
                fig_vs.add_hline(y=0, line_color="#1e2d40", row=2, col=1)

                fig_vs.update_layout(
                    paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117", font=dict(color="#c8d0e0"),
                    xaxis=dict(gridcolor="#1a2332", rangeslider=dict(visible=False)),
                    xaxis2=dict(gridcolor="#1a2332"),
                    yaxis=dict(gridcolor="#1a2332"),
                    yaxis2=dict(gridcolor="#1a2332", title="¢/lb"),
                    height=480, margin=dict(l=10, r=10, t=30, b=10),
                    legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.05),
                )
                st.plotly_chart(fig_vs, use_container_width=True)

        st.markdown("---")

        # ── Chart 4: Open interest ────────────────────────────────────────────
        st.markdown('<div class="section-label">OPEN INTEREST — KC & RC</div>', unsafe_allow_html=True)

        if "open_interest" in kc.columns or "open_interest" in rc.columns:
            fig_oi = go.Figure()
            if "open_interest" in kc.columns:
                kc_oi = kc["open_interest"].dropna()
                if not kc_oi.empty:
                    fig_oi.add_trace(go.Scatter(
                        x=kc_oi.index, y=kc_oi,
                        mode="lines+markers", line=dict(color="#00aaff", width=2),
                        marker=dict(size=5), name="KC OI", yaxis="y1",
                    ))
            if "open_interest" in rc.columns:
                rc_oi = rc["open_interest"].dropna()
                if not rc_oi.empty:
                    fig_oi.add_trace(go.Scatter(
                        x=rc_oi.index, y=rc_oi,
                        mode="lines+markers", line=dict(color="#ff9800", width=2),
                        marker=dict(size=5), name="RC OI", yaxis="y2",
                    ))
            fig_oi.update_layout(
                paper_bgcolor="#0a0e1a", plot_bgcolor="#0d1117", font=dict(color="#c8d0e0"),
                xaxis=dict(gridcolor="#1a2332"),
                yaxis=dict(gridcolor="#1a2332", title="KC Open Interest", side="left"),
                yaxis2=dict(gridcolor="#1a2332", title="RC Open Interest",
                            overlaying="y", side="right", showgrid=False),
                height=280, margin=dict(l=10, r=10, t=20, b=10),
                legend=dict(bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig_oi, use_container_width=True)

        st.markdown("---")

        # ── Raw data table ────────────────────────────────────────────────────
        st.markdown('<div class="section-label">RAW DATA TABLE</div>', unsafe_allow_html=True)

        disp = df_exp[["trade_date","market","expiry_code","settlement","change",
                       "high","low","last","open_interest","rc_cents_lb","spread_clb"]].copy()
        disp["trade_date"] = disp["trade_date"].dt.strftime("%Y-%m-%d")
        disp = disp.sort_values(["trade_date","market"], ascending=[False, True]).reset_index(drop=True)
        disp.columns = ["Date","Market","Expiry","Settlement","Chg","Hi","Lo","Last","OI","RC ¢/lb","Spread ¢/lb"]
        st.dataframe(disp, use_container_width=True, height=280)

        dl1, dl2 = st.columns([1, 5])
        with dl1:
            st.download_button("Download CSV",
                               data=disp.to_csv(index=False).encode(),
                               file_name=f"settlements_{sel_expiry}.csv",
                               mime="text/csv")

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: TRADINGVIEW CHARTS
# ═════════════════════════════════════════════════════════════════════════════
elif page == "TradingView Charts":
    st.markdown('<div class="section-label">TRADINGVIEW LIVE CHARTS — PROFESSIONAL CHARTING</div>', unsafe_allow_html=True)

    # ── Ticker tape ───────────────────────────────────────────────────────────
    ticker_tape_html = """
    <div class="tradingview-widget-container" style="margin-bottom:16px">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
        {
          "symbols": [
            {"proName": "ICEUS:KC1!", "title": "Arabica KC"},
            {"proName": "ICEEUR:RC1!", "title": "Robusta RC"},
            {"proName": "FX:BRLUSD",   "title": "BRL/USD"},
            {"proName": "TVC:DXY",     "title": "USD Index"},
            {"proName": "ICEUS:SB1!",  "title": "Sugar #11"},
            {"proName": "NYMEX:CL1!",  "title": "Crude Oil"}
          ],
          "showSymbolLogo": false,
          "colorTheme": "dark",
          "isTransparent": true,
          "displayMode": "adaptive",
          "locale": "en"
        }
      </script>
    </div>
    """
    st.components.v1.html(ticker_tape_html, height=60, scrolling=False)

    # ── Chart selector ────────────────────────────────────────────────────────
    tv_col1, tv_col2, tv_col3 = st.columns([2, 2, 2])
    with tv_col1:
        chart_symbol = st.selectbox(
            "Symbol",
            options=[
                ("Arabica Coffee (KC)",  "ICEUS:KC1!"),
                ("Robusta Coffee (RC)",  "ICEEUR:RC1!"),
                ("BRL/USD",              "FX:BRLUSD"),
                ("USD Index (DXY)",      "TVC:DXY"),
                ("Sugar #11 (SB)",       "ICEUS:SB1!"),
                ("Crude Oil (CL)",       "NYMEX:CL1!"),
            ],
            format_func=lambda x: x[0],
        )
    with tv_col2:
        chart_interval = st.selectbox(
            "Interval",
            options=[
                ("1 Day",   "D"),
                ("1 Week",  "W"),
                ("1 Month", "M"),
                ("4 Hour",  "240"),
                ("1 Hour",  "60"),
                ("15 Min",  "15"),
            ],
            format_func=lambda x: x[0],
        )
    with tv_col3:
        chart_style = st.selectbox(
            "Chart Style",
            options=[
                ("Candles",    "1"),
                ("Bars",       "0"),
                ("Line",       "2"),
                ("Area",       "3"),
                ("Heikin Ashi","8"),
            ],
            format_func=lambda x: x[0],
        )

    symbol_tv   = chart_symbol[1]
    interval_tv = chart_interval[1]
    style_tv    = chart_style[1]

    # ── Main advanced chart ───────────────────────────────────────────────────
    main_chart_html = f"""
    <div class="tradingview-widget-container" style="height:560px">
      <div id="tradingview_main" style="height:100%;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
        new TradingView.widget({{
          "autosize": true,
          "symbol": "{symbol_tv}",
          "interval": "{interval_tv}",
          "timezone": "America/New_York",
          "theme": "dark",
          "style": "{style_tv}",
          "locale": "en",
          "toolbar_bg": "#0d1117",
          "enable_publishing": false,
          "hide_top_toolbar": false,
          "hide_legend": false,
          "save_image": true,
          "container_id": "tradingview_main",
          "studies": [
            "MASimple@tv-basicstudies",
            "MACD@tv-basicstudies",
            "RSI@tv-basicstudies"
          ],
          "show_popup_button": true,
          "popup_width": "1000",
          "popup_height": "650"
        }});
      </script>
    </div>
    """
    st.components.v1.html(main_chart_html, height=570, scrolling=False)

    st.markdown("---")

    # ── Side-by-side KC and RC ────────────────────────────────────────────────
    st.markdown('<div class="section-label">KC vs RC — SIDE BY SIDE</div>', unsafe_allow_html=True)

    side_col1, side_col2 = st.columns(2)

    kc_chart_html = f"""
    <div class="tradingview-widget-container" style="height:380px">
      <div id="tradingview_kc" style="height:100%;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
        new TradingView.widget({{
          "autosize": true,
          "symbol": "ICEUS:KC1!",
          "interval": "{interval_tv}",
          "timezone": "America/New_York",
          "theme": "dark",
          "style": "{style_tv}",
          "locale": "en",
          "toolbar_bg": "#0d1117",
          "enable_publishing": false,
          "hide_top_toolbar": false,
          "hide_legend": false,
          "save_image": false,
          "container_id": "tradingview_kc",
          "studies": ["MASimple@tv-basicstudies", "RSI@tv-basicstudies"],
          "withdateranges": true
        }});
      </script>
    </div>
    """

    rc_chart_html = f"""
    <div class="tradingview-widget-container" style="height:380px">
      <div id="tradingview_rc" style="height:100%;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
        new TradingView.widget({{
          "autosize": true,
          "symbol": "ICEEUR:RC1!",
          "interval": "{interval_tv}",
          "timezone": "America/New_York",
          "theme": "dark",
          "style": "{style_tv}",
          "locale": "en",
          "toolbar_bg": "#0d1117",
          "enable_publishing": false,
          "hide_top_toolbar": false,
          "hide_legend": false,
          "save_image": false,
          "container_id": "tradingview_rc",
          "studies": ["MASimple@tv-basicstudies", "RSI@tv-basicstudies"],
          "withdateranges": true
        }});
      </script>
    </div>
    """

    with side_col1:
        st.markdown("<p style='color:#00aaff;font-family:Courier New;font-size:12px;margin-bottom:4px'>ARABICA (KC1!) — ICEUS</p>", unsafe_allow_html=True)
        st.components.v1.html(kc_chart_html, height=390, scrolling=False)

    with side_col2:
        st.markdown("<p style='color:#ff9800;font-family:Courier New;font-size:12px;margin-bottom:4px'>ROBUSTA (RC1!) — ICE LIFFE</p>", unsafe_allow_html=True)
        st.components.v1.html(rc_chart_html, height=390, scrolling=False)

    st.markdown("---")

    # ── BRL/USD + DXY row ─────────────────────────────────────────────────────
    st.markdown('<div class="section-label">MACRO CONTEXT — BRL/USD & USD INDEX</div>', unsafe_allow_html=True)
    macro_col1, macro_col2 = st.columns(2)

    def mini_tv_chart(container_id, symbol, color_override=""):
        return f"""
        <div class="tradingview-widget-container" style="height:280px">
          <div id="{container_id}" style="height:100%;width:100%"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
            new TradingView.widget({{
              "autosize": true,
              "symbol": "{symbol}",
              "interval": "{interval_tv}",
              "timezone": "America/New_York",
              "theme": "dark",
              "style": "2",
              "locale": "en",
              "toolbar_bg": "#0d1117",
              "enable_publishing": false,
              "hide_top_toolbar": true,
              "hide_legend": true,
              "save_image": false,
              "container_id": "{container_id}"
            }});
          </script>
        </div>
        """

    with macro_col1:
        st.markdown("<p style='color:#00e676;font-family:Courier New;font-size:12px;margin-bottom:4px'>BRL/USD</p>", unsafe_allow_html=True)
        st.components.v1.html(mini_tv_chart("tv_brl", "FX:BRLUSD"), height=290, scrolling=False)

    with macro_col2:
        st.markdown("<p style='color:#ff9800;font-family:Courier New;font-size:12px;margin-bottom:4px'>USD INDEX (DXY)</p>", unsafe_allow_html=True)
        st.components.v1.html(mini_tv_chart("tv_dxy", "TVC:DXY"), height=290, scrolling=False)
