"""
Real-time Price Dashboard + Alert System
- Shows live prices for all symbols
- Groups big movers (>5%) by sector
"""

from flask import Flask, jsonify, request, render_template_string
import threading
import time
from datetime import datetime, timezone
from collections import defaultdict
import os

app = Flask(__name__)

# ─────────────────────────────────────────
# SYMBOLS
# ─────────────────────────────────────────
COMMODITIES = {
    # Energy
    "CL=F":  ("Crude Oil (WTI)",        "Energy"),
    "BZ=F":  ("Brent Crude Oil",         "Energy"),
    "NG=F":  ("Natural Gas",             "Energy"),
    "RB=F":  ("RBOB Gasoline",           "Energy"),
    "HO=F":  ("Heating Oil",             "Energy"),
    # Precious Metals
    "GC=F":  ("Gold",                    "Metals"),
    "SI=F":  ("Silver",                  "Metals"),
    "PL=F":  ("Platinum",                "Metals"),
    "PA=F":  ("Palladium",               "Metals"),
    "HG=F":  ("Copper",                  "Metals"),
    # Grains & Oilseeds
    "ZC=F":  ("Corn",                    "Grains"),
    "ZW=F":  ("Wheat (Chicago SRW)",     "Grains"),
    "KE=F":  ("Wheat (Kansas HRW)",      "Grains"),
    "ZO=F":  ("Oats",                    "Grains"),
    "ZS=F":  ("Soybeans",                "Grains"),
    "ZM=F":  ("Soybean Meal",            "Grains"),
    "ZL=F":  ("Soybean Oil",             "Grains"),
    # Softs
    "CC=F":  ("Cocoa",                   "Softs"),
    "KC=F":  ("Coffee",                  "Softs"),
    "CT=F":  ("Cotton",                  "Softs"),
    "SB=F":  ("Sugar No.11",             "Softs"),
    # Livestock
    "LE=F":  ("Live Cattle",             "Livestock"),
    "GF=F":  ("Feeder Cattle",           "Livestock"),
    "HE=F":  ("Lean Hogs",               "Livestock"),
    # Indices
    "^GSPC": ("S&P 500",                 "Indices"),
    "^IXIC": ("NASDAQ",                  "Indices"),
    "^DJI":  ("Dow Jones",               "Indices"),
    "^VIX":  ("VIX",                     "Indices"),
    "^RUT":  ("Russell 2000",            "Indices"),
}

SP500_TICKERS = [
    "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD","ABNB",
    "AKAM","ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG","MO","AMZN",
    "AMCR","AEE","AAL","AEP","AXP","AIG","AMT","AWK","AMP","AME","AMGN","APH",
    "ADI","ANSS","AON","APA","AAPL","AMAT","APTV","ACGL","ADM","ANET","AJG",
    "AIZ","T","ATO","ADSK","ADP","AZO","AVB","AVY","AXON","BKR","BALL","BAC",
    "BK","BBWI","BAX","BDX","BRK-B","BBY","TECH","BIO","BIIB","BLK","BX","BA",
    "BCR","BMY","AVGO","BR","BRO","BF-B","BLDR","BG","CDNS","CZR","CPT","CPB",
    "COF","CAH","KMX","CCL","CARR","CTLT","CAT","CBOE","CBRE","CDW","CE","COR",
    "CNC","CNP","CF","CHRW","CRL","SCHW","CHTR","CVX","CMG","CB","CHD","CI",
    "CINF","CTAS","CSCO","C","CFG","CLX","CME","CMS","KO","CTSH","CL","CMCSA",
    "CMA","CAG","COP","ED","STZ","CEG","COO","CPRT","GLW","CTVA","CSGP","COST",
    "CTRA","CCI","CSX","CMI","CVS","DHR","DRI","DVA","DAY","DECK","DE","DAL",
    "DVN","DXCM","FANG","DLR","DFS","DG","DLTR","D","DPZ","DOV","DOW","DHI",
    "DTE","DUK","DD","EMN","ETN","EBAY","ECL","EIX","EW","EA","ELV","LLY","EMR",
    "ENPH","ETR","EOG","EPAM","EQT","EFX","EQIX","EQR","ESS","EL","ETSY","EG",
    "ES","EXC","EXPE","EXPD","EXR","XOM","FFIV","FDS","FICO","FAST","FRT","FDX",
    "FIS","FITB","FSLR","FE","FI","FLT","FMC","F","FTNT","FTV","FOXA","FOX",
    "BEN","FCX","GRMN","IT","GE","GEHC","GEV","GEN","GNRC","GD","GIS","GM",
    "GPC","GILD","GPN","GL","GDDY","GS","HAL","HIG","HAS","HCA","DOC","HSIC",
    "HSY","HES","HPE","HLT","HOLX","HD","HON","HRL","HST","HWM","HPQ","HUBB",
    "HUM","HBAN","HII","IBM","IEX","IDXX","ITW","INCY","IR","PODD","INTC","ICE",
    "IFF","IP","IPG","INTU","ISRG","IVZ","INVH","IQV","IRM","JBHT","JBL","JKHY",
    "J","JNJ","JCI","JPM","JNPR","K","KVUE","KDP","KEY","KEYS","KMB","KIM","KMI",
    "KLAC","KHC","KR","LHX","LH","LRCX","LW","LVS","LDOS","LEN","LIN","LYV",
    "LKQ","LMT","L","LOW","LULU","LYB","MTB","MRO","MPC","MKTX","MAR","MMC",
    "MLM","MAS","MA","MTCH","MKC","MCD","MCK","MDT","MRK","META","MET","MTD",
    "MGM","MCHP","MU","MSFT","MAA","MRNA","MHK","MOH","TAP","MDLZ","MPWR",
    "MNST","MCO","MS","MOS","MSI","MSCI","NDAQ","NTAP","NFLX","NEM","NWSA",
    "NWS","NEE","NKE","NI","NDSN","NSC","NTRS","NOC","NCLH","NRG","NUE","NVDA",
    "NVR","NXPI","ORLY","OXY","ODFL","OMC","ON","OKE","ORCL","OTIS","PCAR",
    "PKG","PLTR","PH","PAYX","PAYC","PYPL","PNR","PEP","PFE","PCG","PM","PSX",
    "PNW","PNC","POOL","PPG","PPL","PFG","PG","PGR","PLD","PRU","PEG","PTC",
    "PSA","PHM","PWR","QCOM","DGX","RL","RJF","RTX","O","REG","REGN","RF","RSG",
    "RMD","RVTY","ROK","ROL","ROP","ROST","RCL","SPGI","CRM","SBAC","SLB","STX",
    "SRE","NOW","SHW","SPG","SWKS","SJM","SW","SNA","SO","LUV","SWK","SBUX",
    "STT","STLD","STE","SYK","SMCI","SYF","SNPS","SYY","TMUS","TROW","TTWO",
    "TPR","TRGP","TGT","TEL","TDY","TFX","TER","TSLA","TXN","TXT","TMO","TJX",
    "TSCO","TT","TDG","TRV","TRMB","TFC","TYL","TSN","USB","UBER","UDR","ULTA",
    "UNP","UAL","UPS","URI","UNH","UHS","VLO","VTR","VLTO","VRSN","VRSK","VZ",
    "VRTX","VTRS","VICI","V","VST","VMC","WRB","GWW","WAB","WBA","WMT","DIS",
    "WBD","WM","WAT","WEC","WFC","WELL","WST","WDC","WY","WMB","WTW","WYNN",
    "XEL","XYL","YUM","ZBRA","ZBH","ZTS",
]

def get_name(ticker):
    if ticker in COMMODITIES:
        return COMMODITIES[ticker][0]
    return ticker

def get_category(ticker):
    if ticker in COMMODITIES:
        return COMMODITIES[ticker][1]
    return "Equity"

ALL_SYMBOLS = list(COMMODITIES.keys()) + SP500_TICKERS

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
config = {
    "price_change_threshold_pct": 5.0,
    "window_seconds": 300,
    "poll_interval_seconds": 60,
    "monitor_commodities": True,
    "monitor_sp500": True,
}
config_lock = threading.Lock()

# ─────────────────────────────────────────
# STATE
# ─────────────────────────────────────────
state = {
    "status": "starting",
    "scan_count": 0,
    "last_checked": None,
    "yfinance_ok": False,
    "errors": [],
    "uptime_start": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
}
state_lock = threading.Lock()

# Current prices: { ticker: {price, pct_change, category, name, updated} }
current_prices = {}
prices_lock = threading.Lock()

# Price history for change detection: { ticker: [(ts, price), ...] }
price_history = defaultdict(list)
history_lock = threading.Lock()

# Active alerts: { ticker: alert_dict }  — deduped by ticker
active_alerts = {}
alerts_lock = threading.Lock()

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def ts_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def log_error(msg):
    with state_lock:
        state["errors"].insert(0, f"[{ts_now()}] {msg}")
        state["errors"] = state["errors"][:20]
    print(f"ERROR: {msg}", flush=True)

# ─────────────────────────────────────────
# FETCH
# ─────────────────────────────────────────
def fetch_prices_batch(tickers):
    import yfinance as yf
    results = {}
    chunk_size = 100
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        try:
            data = yf.download(
                " ".join(chunk),
                period="1d",
                interval="1m",
                progress=False,
                auto_adjust=True,
                threads=True,
            )
            if data.empty:
                continue
            close = data["Close"]
            if len(chunk) == 1:
                col = close.dropna()
                if not col.empty:
                    results[chunk[0]] = float(col.iloc[-1])
            else:
                for ticker in chunk:
                    try:
                        col = close[ticker].dropna()
                        if not col.empty:
                            results[ticker] = float(col.iloc[-1])
                    except Exception:
                        pass
        except Exception as e:
            log_error(f"yfinance chunk {i//chunk_size}: {e}")
    return results

# ─────────────────────────────────────────
# SCAN
# ─────────────────────────────────────────
def scan():
    with config_lock:
        window_s      = config["window_seconds"]
        threshold_pct = config["price_change_threshold_pct"]
        do_comm       = config["monitor_commodities"]
        do_sp500      = config["monitor_sp500"]

    tickers = []
    if do_comm:
        tickers += list(COMMODITIES.keys())
    if do_sp500:
        tickers += SP500_TICKERS

    if not tickers:
        return

    print(f"[{ts_now()}] Fetching {len(tickers)} symbols...", flush=True)
    prices = fetch_prices_batch(tickers)
    print(f"[{ts_now()}] Got {len(prices)} prices.", flush=True)

    if not prices:
        return

    with state_lock:
        state["yfinance_ok"] = True

    now = time.time()

    for ticker, price in prices.items():
        if price is None or price <= 0:
            continue

        name     = get_name(ticker)
        category = get_category(ticker)

        # Update price history
        with history_lock:
            price_history[ticker].append((now, price))
            price_history[ticker] = [
                (t, p) for t, p in price_history[ticker] if now - t <= window_s
            ]
            history = price_history[ticker]

        # Calc % change vs oldest price in window
        pct_change = 0.0
        if len(history) >= 2:
            oldest_price = history[0][1]
            if oldest_price > 0:
                pct_change = ((price - oldest_price) / oldest_price) * 100

        # Update current_prices (shown in main table)
        with prices_lock:
            current_prices[ticker] = {
                "ticker":     ticker,
                "name":       name,
                "category":   category,
                "price":      round(price, 4),
                "pct_change": round(pct_change, 2),
                "direction":  "up" if pct_change >= 0 else "down",
                "updated":    ts_now(),
            }

        # Update active_alerts if threshold crossed
        with alerts_lock:
            if abs(pct_change) >= threshold_pct:
                active_alerts[ticker] = {
                    "ticker":     ticker,
                    "name":       name,
                    "category":   category,
                    "price":      round(price, 4),
                    "pct_change": round(pct_change, 2),
                    "direction":  "up" if pct_change > 0 else "down",
                    "alerted_at": ts_now(),
                }
                print(f"[ALERT] {ticker} {name}: {pct_change:+.2f}%", flush=True)
            else:
                # Clear alert once price settles back
                active_alerts.pop(ticker, None)

    with state_lock:
        state["last_checked"] = ts_now()
        state["scan_count"]  += 1

    print(f"[{ts_now()}] Scan #{state['scan_count']} done. {len(active_alerts)} active alerts.", flush=True)

# ─────────────────────────────────────────
# MONITOR LOOP
# ─────────────────────────────────────────
def monitor_loop():
    try:
        import yfinance
        print(f"[{ts_now()}] yfinance ready.", flush=True)
    except ImportError:
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "-q"])

    with state_lock:
        state["status"] = "running"

    print(f"[{ts_now()}] Monitor started. {len(ALL_SYMBOLS)} symbols.", flush=True)

    while True:
        try:
            scan()
        except Exception as e:
            log_error(f"Scan error: {e}")

        with config_lock:
            sleep_time = config["poll_interval_seconds"]
        time.sleep(sleep_time)

_thread = threading.Thread(target=monitor_loop, daemon=True)
_thread.start()

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────
@app.route("/")
def index():
    with open("templates/index.html") as f:
        return render_template_string(f.read())

@app.route("/api/prices")
def api_prices():
    """All current prices for the main table."""
    with prices_lock:
        data = list(current_prices.values())
    with state_lock:
        s = dict(state)
    with config_lock:
        c = dict(config)
    return jsonify({
        "prices": data,
        "status": s,
        "config": c,
    })

@app.route("/api/alerts")
def api_alerts():
    """Active alerts grouped by sector."""
    with alerts_lock:
        alerts = list(active_alerts.values())
    # Group by category
    sectors = defaultdict(list)
    for a in alerts:
        sectors[a["category"]].append(a)
    return jsonify({
        "alerts":      alerts,
        "by_sector":   dict(sectors),
        "total":       len(alerts),
    })

@app.route("/api/config", methods=["POST"])
def update_config():
    data = request.get_json(silent=True) or {}
    with config_lock:
        if "price_change_threshold_pct" in data:
            config["price_change_threshold_pct"] = float(data["price_change_threshold_pct"])
        if "window_seconds" in data:
            config["window_seconds"] = int(data["window_seconds"])
        if "poll_interval_seconds" in data:
            config["poll_interval_seconds"] = max(30, int(data["poll_interval_seconds"]))
        if "monitor_commodities" in data:
            config["monitor_commodities"] = bool(data["monitor_commodities"])
        if "monitor_sp500" in data:
            config["monitor_sp500"] = bool(data["monitor_sp500"])
    print(f"[{ts_now()}] Config updated.", flush=True)
    return jsonify({"ok": True, "config": config})

@app.route("/api/debug")
def debug():
    with prices_lock:
        sample = list(current_prices.values())[:5]
    with alerts_lock:
        nalerts = len(active_alerts)
    with state_lock:
        s = dict(state)
    return jsonify({"sample_prices": sample, "active_alerts": nalerts, "state": s})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
