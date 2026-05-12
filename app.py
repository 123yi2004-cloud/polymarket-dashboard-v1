"""
Real-time Price Dashboard
- Today's open vs latest price for pct_change (works from scan #1)
- Uses yf.Ticker per symbol for maximum reliability
- Covers: Commodities + S&P 500 + NASDAQ 100
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
    "CL=F":  ("Crude Oil (WTI)",      "Energy"),
    "BZ=F":  ("Brent Crude Oil",       "Energy"),
    "NG=F":  ("Natural Gas",           "Energy"),
    "RB=F":  ("RBOB Gasoline",         "Energy"),
    "HO=F":  ("Heating Oil",           "Energy"),
    "GC=F":  ("Gold",                  "Metals"),
    "SI=F":  ("Silver",                "Metals"),
    "PL=F":  ("Platinum",              "Metals"),
    "PA=F":  ("Palladium",             "Metals"),
    "HG=F":  ("Copper",                "Metals"),
    "ZC=F":  ("Corn",                  "Grains"),
    "ZW=F":  ("Wheat (Chicago SRW)",   "Grains"),
    "KE=F":  ("Wheat (Kansas HRW)",    "Grains"),
    "ZO=F":  ("Oats",                  "Grains"),
    "ZS=F":  ("Soybeans",              "Grains"),
    "ZM=F":  ("Soybean Meal",          "Grains"),
    "ZL=F":  ("Soybean Oil",           "Grains"),
    "CC=F":  ("Cocoa",                 "Softs"),
    "KC=F":  ("Coffee",                "Softs"),
    "CT=F":  ("Cotton",                "Softs"),
    "SB=F":  ("Sugar No.11",           "Softs"),
    "LE=F":  ("Live Cattle",           "Livestock"),
    "GF=F":  ("Feeder Cattle",         "Livestock"),
    "HE=F":  ("Lean Hogs",             "Livestock"),
    "^GSPC": ("S&P 500",               "Indices"),
    "^IXIC": ("NASDAQ Composite",      "Indices"),
    "^DJI":  ("Dow Jones",             "Indices"),
    "^VIX":  ("VIX",                   "Indices"),
    "^RUT":  ("Russell 2000",          "Indices"),
    "^NDX":  ("NASDAQ 100",            "Indices"),
}

# S&P 500
SP500 = [
    "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD","ABNB",
    "AKAM","ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG","MO","AMZN",
    "AMCR","AEE","AAL","AEP","AXP","AIG","AMT","AWK","AMP","AME","AMGN","APH",
    "ADI","ANSS","AON","APA","AAPL","AMAT","APTV","ACGL","ADM","ANET","AJG",
    "AIZ","T","ATO","ADSK","ADP","AZO","AVB","AVY","AXON","BKR","BALL","BAC",
    "BK","BBWI","BAX","BDX","BRK-B","BBY","TECH","BIO","BIIB","BLK","BX","BA",
    "BMY","AVGO","BR","BRO","BF-B","BLDR","BG","CDNS","CZR","CPT","CPB","COF",
    "CAH","KMX","CCL","CARR","CAT","CBOE","CBRE","CDW","CE","COR","CNC","CNP",
    "CF","CHRW","CRL","SCHW","CHTR","CVX","CMG","CB","CHD","CI","CINF","CTAS",
    "CSCO","C","CFG","CLX","CME","CMS","KO","CTSH","CL","CMCSA","CAG","COP",
    "ED","STZ","CEG","COO","CPRT","GLW","CTVA","CSGP","COST","CTRA","CCI","CSX",
    "CMI","CVS","DHR","DRI","DVA","DECK","DE","DAL","DVN","DXCM","FANG","DLR",
    "DFS","DG","DLTR","D","DPZ","DOV","DOW","DHI","DTE","DUK","DD","EMN","ETN",
    "EBAY","ECL","EIX","EW","EA","ELV","LLY","EMR","ENPH","ETR","EOG","EPAM",
    "EQT","EFX","EQIX","EQR","ESS","EL","ETSY","EG","ES","EXC","EXPE","EXPD",
    "EXR","XOM","FFIV","FDS","FICO","FAST","FRT","FDX","FIS","FITB","FSLR","FE",
    "FI","FLT","FMC","F","FTNT","FTV","FOXA","FOX","BEN","FCX","GRMN","IT","GE",
    "GEHC","GEV","GEN","GNRC","GD","GIS","GM","GPC","GILD","GPN","GL","GDDY",
    "GS","HAL","HIG","HAS","HCA","DOC","HSIC","HSY","HES","HPE","HLT","HOLX",
    "HD","HON","HRL","HST","HWM","HPQ","HUBB","HUM","HBAN","HII","IBM","IEX",
    "IDXX","ITW","INCY","IR","PODD","INTC","ICE","IFF","IP","IPG","INTU","ISRG",
    "IVZ","INVH","IQV","IRM","JBHT","JBL","JKHY","J","JNJ","JCI","JPM","JNPR",
    "K","KVUE","KDP","KEY","KEYS","KMB","KIM","KMI","KLAC","KHC","KR","LHX",
    "LH","LRCX","LW","LVS","LDOS","LEN","LIN","LYV","LKQ","LMT","L","LOW",
    "LULU","LYB","MTB","MRO","MPC","MKTX","MAR","MMC","MLM","MAS","MA","MTCH",
    "MKC","MCD","MCK","MDT","MRK","META","MET","MTD","MGM","MCHP","MU","MSFT",
    "MAA","MRNA","MHK","MOH","TAP","MDLZ","MPWR","MNST","MCO","MS","MOS","MSI",
    "MSCI","NDAQ","NTAP","NFLX","NEM","NWSA","NWS","NEE","NKE","NI","NDSN",
    "NSC","NTRS","NOC","NCLH","NRG","NUE","NVDA","NVR","NXPI","ORLY","OXY",
    "ODFL","OMC","ON","OKE","ORCL","OTIS","PCAR","PKG","PLTR","PH","PAYX",
    "PAYC","PYPL","PNR","PEP","PFE","PCG","PM","PSX","PNW","PNC","POOL","PPG",
    "PPL","PFG","PG","PGR","PLD","PRU","PEG","PTC","PSA","PHM","PWR","QCOM",
    "DGX","RL","RJF","RTX","O","REG","REGN","RF","RSG","RMD","RVTY","ROK","ROL",
    "ROP","ROST","RCL","SPGI","CRM","SBAC","SLB","STX","SRE","NOW","SHW","SPG",
    "SWKS","SJM","SW","SNA","SO","LUV","SWK","SBUX","STT","STLD","STE","SYK",
    "SMCI","SYF","SNPS","SYY","TMUS","TROW","TTWO","TPR","TRGP","TGT","TEL",
    "TDY","TFX","TER","TSLA","TXN","TXT","TMO","TJX","TSCO","TT","TDG","TRV",
    "TRMB","TFC","TYL","TSN","USB","UBER","UDR","ULTA","UNP","UAL","UPS","URI",
    "UNH","UHS","VLO","VTR","VLTO","VRSN","VRSK","VZ","VRTX","VTRS","VICI","V",
    "VST","VMC","WRB","GWW","WAB","WBA","WMT","DIS","WBD","WM","WAT","WEC",
    "WFC","WELL","WST","WDC","WY","WMB","WTW","WYNN","XEL","XYL","YUM","ZBRA",
    "ZBH","ZTS",
]

# NASDAQ 100 (non-overlapping with S&P 500 above)
NDX100 = [
    "ADSK","AEP","ALGN","AMAT","AMD","AMGN","AMZN","ANSS","ASML","AVGO",
    "AXON","BIIB","BKNG","CDNS","CDW","CEG","CHTR","CMCSA","COST","CPRT",
    "CRWD","CSCO","CSX","CTAS","CTSH","DDOG","DLTR","DXCM","EA","EXC","FANG",
    "FAST","FTNT","GEHC","GILD","GOOG","GOOGL","HON","IDXX","ILMN","INTC",
    "INTU","ISRG","KDP","KHC","KLAC","LRCX","LULU","MAR","MCHP","MDLZ","META",
    "MNST","MRNA","MSFT","MU","NFLX","NXPI","ODFL","ON","ORLY","PANW","PAYX",
    "PCAR","PDD","PEP","PYPL","QCOM","REGN","ROST","SBUX","SNPS","TEAM","TMUS",
    "TSLA","TTD","TTWO","TXN","VRSK","VRTX","WBD","WBA","WDAY","XEL","ZS","ZM",
]

def get_name(ticker):
    if ticker in COMMODITIES:
        return COMMODITIES[ticker][0]
    return ticker

def get_category(ticker):
    if ticker in COMMODITIES:
        return COMMODITIES[ticker][1]
    # Determine if NDX-only or S&P
    sp500_set = set(SP500)
    ndx_set   = set(NDX100)
    if ticker in ndx_set and ticker not in sp500_set:
        return "NASDAQ 100"
    return "S&P 500"

# Build full symbol list (deduplicated)
_all = list(COMMODITIES.keys())
_seen = set(_all)
for t in SP500 + NDX100:
    if t not in _seen:
        _all.append(t)
        _seen.add(t)
ALL_SYMBOLS = _all

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
config = {
    "price_change_threshold_pct": 5.0,
    "poll_interval_seconds": 120,
    "monitor_commodities": True,
    "monitor_sp500":       True,
    "monitor_ndx100":      True,
}
config_lock = threading.Lock()

# ─────────────────────────────────────────
# STATE
# ─────────────────────────────────────────
state = {
    "status":      "starting",
    "scan_count":  0,
    "last_checked": None,
    "yfinance_ok": False,
    "errors":      [],
    "uptime_start": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    "fetched_count": 0,
}
state_lock = threading.Lock()

current_prices = {}   # ticker -> price dict
prices_lock    = threading.Lock()

active_alerts  = {}   # ticker -> alert dict
alerts_lock    = threading.Lock()

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
# FETCH — batch download with open+close
# ─────────────────────────────────────────
def fetch_all_prices(tickers):
    """
    Batch download 1d / 5m bars for all tickers.
    Returns {ticker: {"price": float, "open": float}}.
    Uses group_by='ticker' so multi-ticker DataFrames are easy to slice.
    Falls back to individual Ticker.history() for any failures.
    """
    import yfinance as yf
    results = {}
    chunk_size = 50

    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        try:
            raw = yf.download(
                tickers=" ".join(chunk),
                period="1d",
                interval="5m",
                progress=False,
                auto_adjust=True,
                threads=True,
                group_by="ticker",
            )
            if raw.empty:
                log_error(f"Chunk {i//chunk_size} empty")
                continue

            for ticker in chunk:
                try:
                    # Single ticker: raw IS the df; multi: raw[ticker]
                    df = raw if len(chunk) == 1 else raw.get(ticker, None)
                    if df is None or df.empty:
                        continue
                    df = df.dropna(how="all")
                    closes = df["Close"].dropna()
                    opens  = df["Open"].dropna()
                    if closes.empty:
                        continue
                    price = float(closes.iloc[-1])
                    open_ = float(opens.iloc[0]) if not opens.empty else price
                    if price > 0:
                        results[ticker] = {"price": price, "open": open_}
                except Exception:
                    pass
        except Exception as e:
            log_error(f"Batch chunk {i//chunk_size}: {e}")

    # Fallback: individually fetch anything still missing
    missing = [t for t in tickers if t not in results]
    if missing:
        print(f"[{ts_now()}] Fallback for {len(missing)} tickers...", flush=True)
        for ticker in missing:
            try:
                hist = yf.Ticker(ticker).history(period="1d", interval="5m")
                if hist.empty:
                    continue
                closes = hist["Close"].dropna()
                opens  = hist["Open"].dropna()
                if closes.empty:
                    continue
                price = float(closes.iloc[-1])
                open_ = float(opens.iloc[0]) if not opens.empty else price
                if price > 0:
                    results[ticker] = {"price": price, "open": open_}
            except Exception:
                pass

    return results

# ─────────────────────────────────────────
# SCAN
# ─────────────────────────────────────────
def scan():
    with config_lock:
        threshold_pct = config["price_change_threshold_pct"]
        do_comm  = config["monitor_commodities"]
        do_sp500 = config["monitor_sp500"]
        do_ndx   = config["monitor_ndx100"]

    tickers = []
    sp500_set = set(SP500)
    ndx_set   = set(NDX100)

    if do_comm:
        tickers += list(COMMODITIES.keys())
    if do_sp500:
        tickers += [t for t in SP500 if t not in set(tickers)]
    if do_ndx:
        tickers += [t for t in NDX100 if t not in set(tickers)]

    if not tickers:
        return

    print(f"[{ts_now()}] Scanning {len(tickers)} symbols...", flush=True)
    prices = fetch_all_prices(tickers)
    print(f"[{ts_now()}] Got {len(prices)}/{len(tickers)} prices.", flush=True)

    if not prices:
        return

    with state_lock:
        state["yfinance_ok"]  = True
        state["fetched_count"] = len(prices)

    now = time.time()

    for ticker, data in prices.items():
        price = data["price"]
        open_ = data["open"]

        if price <= 0:
            continue

        name     = get_name(ticker)
        category = get_category(ticker)

        # pct_change = today open vs now (available from scan #1)
        pct_change = 0.0
        if open_ and open_ > 0:
            pct_change = ((price - open_) / open_) * 100

        row = {
            "ticker":     ticker,
            "name":       name,
            "category":   category,
            "price":      round(price, 4),
            "open":       round(open_, 4),
            "pct_change": round(pct_change, 3),
            "direction":  "up" if pct_change >= 0 else "down",
            "updated":    ts_now(),
        }

        with prices_lock:
            current_prices[ticker] = row

        with alerts_lock:
            if abs(pct_change) >= threshold_pct:
                active_alerts[ticker] = {**row, "alerted_at": ts_now()}
                print(f"[ALERT] {ticker} {name}: {pct_change:+.2f}%", flush=True)
            else:
                active_alerts.pop(ticker, None)

    with state_lock:
        state["last_checked"] = ts_now()
        state["scan_count"]  += 1

    print(f"[{ts_now()}] Done. {len(active_alerts)} active alerts.", flush=True)

# ─────────────────────────────────────────
# MONITOR LOOP
# ─────────────────────────────────────────
def monitor_loop():
    try:
        import yfinance
        print(f"[{ts_now()}] yfinance ready.", flush=True)
    except ImportError:
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "pandas", "-q"])

    with state_lock:
        state["status"] = "running"

    while True:
        try:
            scan()
        except Exception as e:
            log_error(f"Scan error: {e}")

        with config_lock:
            sleep_time = config["poll_interval_seconds"]
        print(f"[{ts_now()}] Sleeping {sleep_time}s.", flush=True)
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
    with prices_lock:
        data = list(current_prices.values())
    with state_lock:
        s = dict(state)
    with config_lock:
        c = dict(config)
    return jsonify({"prices": data, "status": s, "config": c})

@app.route("/api/alerts")
def api_alerts_route():
    from collections import defaultdict
    with alerts_lock:
        alerts = list(active_alerts.values())
    sectors = defaultdict(list)
    for a in alerts:
        sectors[a["category"]].append(a)
    return jsonify({"alerts": alerts, "by_sector": dict(sectors), "total": len(alerts)})

@app.route("/api/config", methods=["POST"])
def update_config():
    data = request.get_json(silent=True) or {}
    with config_lock:
        if "price_change_threshold_pct" in data:
            config["price_change_threshold_pct"] = float(data["price_change_threshold_pct"])
        if "poll_interval_seconds" in data:
            config["poll_interval_seconds"] = max(60, int(data["poll_interval_seconds"]))
        if "monitor_commodities" in data:
            config["monitor_commodities"] = bool(data["monitor_commodities"])
        if "monitor_sp500" in data:
            config["monitor_sp500"] = bool(data["monitor_sp500"])
        if "monitor_ndx100" in data:
            config["monitor_ndx100"] = bool(data["monitor_ndx100"])
    print(f"[{ts_now()}] Config updated.", flush=True)
    return jsonify({"ok": True, "config": config})

@app.route("/api/clear", methods=["POST"])
def clear_alerts():
    with alerts_lock:
        active_alerts.clear()
    return jsonify({"ok": True})

@app.route("/api/debug")
def debug():
    with prices_lock:
        sample = list(current_prices.values())[:8]
        total  = len(current_prices)
    with alerts_lock:
        na = len(active_alerts)
    with state_lock:
        s = dict(state)
    return jsonify({"total_prices": total, "active_alerts": na, "sample": sample, "state": s})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
