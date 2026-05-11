"""
Real-time Price Alert Dashboard
Data source: yfinance (Yahoo Finance) — free, no API key needed
Monitors: S&P 500 stocks + major commodities
Alerts when price moves ±5% (configurable) within a time window
"""

from flask import Flask, jsonify, request, render_template_string
import threading
import time
import json
from datetime import datetime, timezone
from collections import defaultdict
import os

app = Flask(__name__)

# ─────────────────────────────────────────
# SYMBOLS
# ─────────────────────────────────────────

# Major commodities (Yahoo Finance tickers)
COMMODITIES = {
    # Energy
    "CL=F":  "Crude Oil (WTI)",
    "BZ=F":  "Brent Crude Oil",
    "NG=F":  "Natural Gas (Henry Hub)",
    "RB=F":  "RBOB Gasoline",
    "HO=F":  "Heating Oil",
    # Precious Metals
    "GC=F":  "Gold",
    "SI=F":  "Silver",
    "PL=F":  "Platinum",
    "PA=F":  "Palladium",
    # Base Metals
    "HG=F":  "Copper",
    # Grains & Oilseeds
    "ZC=F":  "Corn",
    "ZW=F":  "Wheat (Chicago SRW)",
    "KE=F":  "Wheat (Kansas HRW)",
    "ZO=F":  "Oats",
    "ZS=F":  "Soybeans",
    "ZM=F":  "Soybean Meal",
    "ZL=F":  "Soybean Oil",
    # Softs
    "CC=F":  "Cocoa",
    "KC=F":  "Coffee",
    "CT=F":  "Cotton",
    "SB=F":  "Sugar No.11",
    # Livestock
    "LE=F":  "Live Cattle",
    "GF=F":  "Feeder Cattle",
    "HE=F":  "Lean Hogs",
    # Equity Indices
    "^GSPC": "S&P 500 Index",
    "^IXIC": "NASDAQ Composite",
    "^DJI":  "Dow Jones Industrial",
    "^VIX":  "VIX Volatility Index",
    "^RUT":  "Russell 2000",
}

# Full S&P 500 list (all 500 tickers)
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
    "EVRST","ES","EXC","EXPE","EXPD","EXR","XOM","FFIV","FDS","FICO","FAST",
    "FRT","FDX","FIS","FITB","FSLR","FE","FI","FLT","FMC","F","FTNT","FTV",
    "FOXA","FOX","BEN","FCX","GRMN","IT","GE","GEHC","GEV","GEN","GNRC","GD",
    "GIS","GM","GPC","GILD","GPN","GL","GDDY","GS","HAL","HIG","HAS","HCA",
    "DOC","HSIC","HSY","HES","HPE","HLT","HOLX","HD","HON","HRL","HST","HWM",
    "HPQ","HUBB","HUM","HBAN","HII","IBM","IEX","IDXX","ITW","INCY","IR","PODD",
    "INTC","ICE","IFF","IP","IPG","INTU","ISRG","IVZ","INVH","IQV","IRM","JBHT",
    "JBL","JKHY","J","JNJ","JCI","JPM","JNPR","K","KVUE","KDP","KEY","KEYS",
    "KMB","KIM","KMI","KLAC","KHC","KR","LHX","LH","LRCX","LW","LVS","LDOS",
    "LEN","LIN","LYV","LKQ","LMT","L","LOW","LULU","LYB","MTB","MRO","MPC",
    "MKTX","MAR","MMC","MLM","MAS","MA","MTCH","MKC","MCD","MCK","MDT","MRK",
    "META","MET","MTD","MGM","MCHP","MU","MSFT","MAA","MRNA","MHK","MOH","TAP",
    "MDLZ","MPWR","MNST","MCO","MS","MOS","MSI","MSCI","NDAQ","NTAP","NFLX",
    "NEM","NWSA","NWS","NEE","NKE","NI","NDSN","NSC","NTRS","NOC","NCLH","NRG",
    "NUE","NVDA","NVR","NXPI","ORLY","OXY","ODFL","OMC","ON","OKE","ORCL","OTIS",
    "PCAR","PKG","PLTR","PH","PAYX","PAYC","PYPL","PNR","PEP","PFE","PCG","PM",
    "PSX","PNW","PXD","PNC","POOL","PPG","PPL","PFG","PG","PGR","PLD","PRU",
    "PEG","PTC","PSA","PHM","QRVO","PWR","QCOM","DGX","RL","RJF","RTX","O",
    "REG","REGN","RF","RSG","RMD","RVTY","ROK","ROL","ROP","ROST","RCL","SPGI",
    "CRM","SBAC","SLB","STX","SRE","NOW","SHW","SPG","SWKS","SJM","SW","SNA",
    "SO","LUV","SWK","SBUX","STT","STLD","STE","SYK","SMCI","SYF","SNPS","SYY",
    "TMUS","TROW","TTWO","TPR","TRGP","TGT","TEL","TDY","TFX","TER","TSLA",
    "TXN","TXT","TMO","TJX","TSCO","TT","TDG","TRV","TRMB","TFC","TYL","TSN",
    "USB","UBER","UDR","ULTA","UNP","UAL","UPS","URI","UNH","UHS","VLO","VTR",
    "VLTO","VRSN","VRSK","VZ","VRTX","VTRS","VICI","V","VST","VMC","WRB","GWW",
    "WAB","WBA","WMT","DIS","WBD","WM","WAT","WEC","WFC","WELL","WST","WDC",
    "WRK","WY","WMB","WTW","WYNN","XEL","XYL","YUM","ZBRA","ZBH","ZTS",
]

ALL_SYMBOLS = list(COMMODITIES.keys()) + SP500_TICKERS

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
config = {
    "price_change_threshold_pct": 5.0,
    "window_seconds": 300,        # 5 min window
    "poll_interval_seconds": 60,  # fetch every 60s
    "max_alerts": 200,
    "monitor_commodities": True,
    "monitor_sp500": True,
}
config_lock = threading.Lock()

state = {
    "alerts": [],
    "status": "starting",
    "symbols_tracked": 0,
    "last_checked": None,
    "uptime_start": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    "errors": [],
    "scan_count": 0,
    "yfinance_ok": False,
}
state_lock = threading.Lock()

price_history = defaultdict(list)   # { ticker: [(ts, price), ...] }
price_lock = threading.Lock()

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

def get_display_name(ticker):
    return COMMODITIES.get(ticker, ticker)

def categorize(ticker):
    if ticker in ("^GSPC","^IXIC","^DJI","^VIX","^RUT"):
        return "Index"
    if ticker in COMMODITIES:
        if ticker in ("CL=F","BZ=F","NG=F","RB=F","HO=F"):
            return "Energy"
        if ticker in ("GC=F","SI=F","PL=F","PA=F","HG=F"):
            return "Metals"
        if ticker in ("ZC=F","ZW=F","KE=F","ZO=F","ZS=F","ZM=F","ZL=F"):
            return "Grains"
        if ticker in ("CC=F","KC=F","CT=F","SB=F"):
            return "Softs"
        if ticker in ("LE=F","GF=F","HE=F"):
            return "Livestock"
        return "Commodity"
    return "Equity"

# ─────────────────────────────────────────
# FETCH PRICES via yfinance
# Batches 100 tickers at a time for efficiency
# ─────────────────────────────────────────
def fetch_prices_batch(tickers):
    """Returns {ticker: price} dict."""
    import yfinance as yf
    results = {}
    # yfinance download accepts space-separated tickers
    chunk_size = 100
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
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
            # Get latest Close price for each ticker
            close = data["Close"]
            if len(chunk) == 1:
                # Single ticker returns a Series
                price = float(close.dropna().iloc[-1])
                results[chunk[0]] = price
            else:
                for ticker in chunk:
                    try:
                        col = close[ticker].dropna()
                        if not col.empty:
                            results[ticker] = float(col.iloc[-1])
                    except Exception:
                        pass
        except Exception as e:
            log_error(f"yfinance batch {i//chunk_size}: {e}")
    return results

# ─────────────────────────────────────────
# SCAN
# ─────────────────────────────────────────
def scan():
    with config_lock:
        window_s      = config["window_seconds"]
        threshold_pct = config["price_change_threshold_pct"]
        do_commodities= config["monitor_commodities"]
        do_sp500      = config["monitor_sp500"]

    tickers = []
    if do_commodities:
        tickers += list(COMMODITIES.keys())
    if do_sp500:
        tickers += SP500_TICKERS

    if not tickers:
        return

    print(f"[{ts_now()}] Fetching {len(tickers)} symbols...", flush=True)
    prices = fetch_prices_batch(tickers)
    print(f"[{ts_now()}] Got prices for {len(prices)} symbols.", flush=True)

    if prices:
        with state_lock:
            state["yfinance_ok"] = True

    now = time.time()
    alerts_added = 0

    for ticker, price in prices.items():
        if price is None or price <= 0:
            continue

        with price_lock:
            price_history[ticker].append((now, price))
            price_history[ticker] = [
                (t, p) for t, p in price_history[ticker] if now - t <= window_s
            ]
            history = price_history[ticker]

        if len(history) < 2:
            continue

        oldest_ts, oldest_price = history[0]
        if oldest_price <= 0:
            continue

        pct_change = ((price - oldest_price) / oldest_price) * 100

        if abs(pct_change) >= threshold_pct:
            name      = get_display_name(ticker)
            category  = categorize(ticker)
            direction = "UP" if pct_change > 0 else "DOWN"
            alert = {
                "time":           ts_now(),
                "ticker":         ticker,
                "name":           name,
                "category":       category,
                "old_price":      round(oldest_price, 4),
                "new_price":      round(price, 4),
                "pct_change":     round(pct_change, 2),
                "direction":      direction,
                "window_minutes": round((now - oldest_ts) / 60, 1),
            }
            print(f"[ALERT] {ticker} ({name}): {pct_change:+.2f}%  ${oldest_price:.4f} → ${price:.4f}", flush=True)
            with state_lock:
                state["alerts"].insert(0, alert)
                if len(state["alerts"]) > config["max_alerts"]:
                    state["alerts"] = state["alerts"][:config["max_alerts"]]
            with price_lock:
                price_history[ticker] = [(now, price)]
            alerts_added += 1

    with state_lock:
        state["symbols_tracked"] = len(prices)
        state["last_checked"]    = ts_now()
        state["scan_count"]     += 1

    print(f"[{ts_now()}] Scan complete. {alerts_added} new alerts.", flush=True)

# ─────────────────────────────────────────
# MONITOR LOOP
# ─────────────────────────────────────────
def monitor_loop():
    # Install yfinance if not present
    try:
        import yfinance
        print(f"[{ts_now()}] yfinance ready.", flush=True)
    except ImportError:
        import subprocess, sys
        print(f"[{ts_now()}] Installing yfinance...", flush=True)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "-q"])
        print(f"[{ts_now()}] yfinance installed.", flush=True)

    with state_lock:
        state["status"] = "running"

    print(f"[{ts_now()}] Monitor started. Tracking {len(ALL_SYMBOLS)} symbols.", flush=True)

    while True:
        try:
            scan()
        except Exception as e:
            log_error(f"Scan error: {e}")

        with config_lock:
            sleep_time = config["poll_interval_seconds"]

        print(f"[{ts_now()}] Sleeping {sleep_time}s.", flush=True)
        time.sleep(sleep_time)

# Start at import time so gunicorn picks it up
_thread = threading.Thread(target=monitor_loop, daemon=True)
_thread.start()

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────
@app.route("/")
def index():
    with open("templates/index.html") as f:
        return render_template_string(f.read())

@app.route("/api/alerts")
def api_alerts():
    with state_lock:
        alerts   = list(state["alerts"])
        s        = {k: v for k, v in state.items() if k != "alerts"}
    with config_lock:
        c = dict(config)
    return jsonify({**s, "alerts": alerts, "config": c})

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
    print(f"[{ts_now()}] Config updated: {config}", flush=True)
    return jsonify({"ok": True, "config": config})

@app.route("/api/clear", methods=["POST"])
def clear_alerts():
    with state_lock:
        state["alerts"] = []
    return jsonify({"ok": True})

@app.route("/api/debug")
def debug():
    samples = []
    with price_lock:
        for ticker, hist in list(price_history.items())[:10]:
            if hist:
                samples.append({
                    "ticker":       ticker,
                    "name":         get_display_name(ticker),
                    "latest_price": round(hist[-1][1], 4),
                    "data_points":  len(hist),
                })
    with state_lock:
        errs = list(state["errors"])
        sc   = state["scan_count"]
        sym  = state["symbols_tracked"]
        ok   = state["yfinance_ok"]
    return jsonify({
        "yfinance_ok":     ok,
        "scan_count":      sc,
        "symbols_tracked": sym,
        "price_samples":   samples,
        "recent_errors":   errs,
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
