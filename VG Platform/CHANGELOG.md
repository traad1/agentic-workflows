# Vidya Global Coffee Terminal — Changelog

All notable changes to this project are documented here.
Format: `[version] — date — summary`

---

## [1.3.0] — 2026-05-15 — Daily Price History page

### Changed
- Replaced "Weekly Price History" with **Daily Price History**
- Fully rebuilt from the new settlements schema (trade_date × expiry × market)

### Daily Price History — what's in it
- **Expiry selector** — pick any contract month (JUL26, SEP26, etc.)
- **Days slider** — show last 5 to all available sessions
- **MA20 / MA50 toggles** — add/remove moving averages on both charts
- **6 KPI cards**: KC last + daily Δ, RC last + daily Δ, spread KC−RC ¢/lb, 5-day move KC, 5-day move RC, KC hi/lo range
- **KC chart**: settlement line + hi/lo band + MA20/MA50 + daily change bars below
- **RC chart**: same layout in USD/MT
- **Indexed comparison**: both contracts indexed to 100 at window start + spread bar chart below with 5-day MA and period average line
- **Open interest**: dual-axis KC and RC OI over time
- **Raw data table** with CSV download per expiry

---

## [1.0.0] — 2026-05-14 — Initial Release

### Platform
- Streamlit-based web terminal with dark Bloomberg-style theme
- Sidebar navigation, timeframe selector, live refresh button
- Deployed on Streamlit Community Cloud

### Pages

**Market Overview**
- Live quote cards: Arabica (KC), Robusta (RC), BRL/USD, USD Index, Sugar #11, Crude Oil
- Candlestick charts for KC and RC with selected timeframe
- BRL/USD and DXY line charts

**Arabica Deep Dive**
- Full OHLC candlestick with MA20 / MA50 overlays and volume panel
- 52-week high / low metrics
- Dual-axis BRL/USD overlay chart

**Robusta Deep Dive**
- Full OHLC candlestick with MA20 overlay and volume panel
- 52-week high / low metrics

**Spreads & Correlations**
- Arabica–Robusta spread in USD/MT (KC converted at 22.0462)
- Normalized index chart (both contracts indexed to 100)
- 1-year correlation heatmap: KC, RC, BRL/USD, DXY, Sugar

**Basis Calculator**
- Physical contract price input vs live ICE screen price
- Basis shown in ¢/lb and USD/MT
- Full position P&L vs screen (bags → MT conversion)
- 1-year historical percentile chart with price overlays

**Weekly Price Entry**
- Manual entry grid: Monday Open + Mon–Fri Settlements
- Arabica input: ¢/lb | Robusta input: USD/MT
- Auto-calculates RC in ¢/lb and spread (KC − RC) in ¢/lb per session
- Per-row Save buttons; pre-fills from saved data on revisit
- Weekly summary metrics: KC/RC week change, spread change
- Data persisted to `dashboard/data/weekly_prices.xlsx`

**Weekly Price History**
- Line charts: KC & RC settlements over time (both in ¢/lb)
- Bar chart: Arabica–Robusta spread (¢/lb) with average line
- Robusta USD/MT chart (as entered)
- Weekly range bars: Monday Open → Friday Settlement delta
- Sliding week-count filter (last N weeks)
- Raw data table with CSV download

**TradingView Charts**
- Live ticker tape: KC, RC, BRL/USD, DXY, Sugar, Crude
- Full advanced chart: symbol selector, interval, chart style (candles/bars/line/area/Heikin Ashi)
- Default studies: MA, MACD, RSI
- Side-by-side KC vs RC continuous front-month charts
- BRL/USD and DXY mini charts (macro context row)

### Data sources
- Live market data: yfinance (15-min delayed on some exchanges)
- Professional charts: TradingView free embed widget (real-time)
- Manual data: local Excel file (`weekly_prices.xlsx`)

### Tech stack
- Python 3.9+
- Streamlit 1.35+
- yfinance, pandas, plotly, numpy, openpyxl
- TradingView widget (free public embed)

---

## Roadmap / Ideas for Future Versions

- [ ] Open positions tracker (enter all active contracts, see aggregate long/short exposure)
- [ ] Coffee news feed (scrape ICO, Reuters commodity RSS)
- [ ] Price alerts (notify when KC or RC breaks a level)
- [ ] Multi-origin basis table (Brazil, Colombia, Ethiopia differentials)
- [ ] Contract calendar (first notice days, expiry dates for KC/RC)
- [ ] Export weekly report to PDF
