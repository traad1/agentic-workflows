"""
THEME — Bloomberg-Style Dark Blue (original v1.0)
Backup of the original theme before the cointop redesign.
To restore, copy THEME_CSS back into app.py replacing the cointop block.
"""

THEME_CSS = """
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
"""
