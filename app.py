"""
Polymarket Price Movement Alert Dashboard
Monitors sudden price changes in commodity & equity markets on Polymarket.
"""

from flask import Flask, jsonify, render_template_string
import threading
import requests
import time
from datetime import datetime, timezone
from collections import defaultdict
import os

app = Flask(__name__)

# ─────────────────────────────────────────
# DEFAULT CONFIG (can be updated via API)
# ─────────────────────────────────────────
config = {
    "price_change_threshold_pct": 10.0,   # % change to trigger alert
    "window_seconds": 300,                 # time window to measure change (5 min)
    "poll_interval_seconds": 20,
    "max_alerts": 100,
    "max_markets": 300,
    "keywords": [
        # US Equity
        "s&p", "sp500", "nasdaq", "dow jones", "nikkei", "hang seng",
        "ftse", "dax", "stoxx", "russell", "vix", "stock market",
        "bull", "bear", "recession", "crash", "rally",
        # Commodities
        "gold", "silver", "oil", "crude", "brent", "wti",
        "natural gas", "copper", "wheat", "corn", "soybean",
        "cotton", "sugar", "coffee", "cocoa", "platinum", "palladium",
        # Macro / rates
        "fed rate", "interest rate", "inflation", "cpi", "pce",
        "treasury", "yield", "gdp",
        # Crypto (correlated)
        "bitcoin", "btc", "ethereum", "eth",
    ],
}
config_lock = threading.Lock()

# ─────────────────────────────────────────
# STATE
# ─────────────────────────────────────────
state = {
    "alerts": [],
    "status": "starting",
    "markets_count": 0,
    "tokens_count": 0,
    "last_checked": None,
    "uptime_start": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
}
state_lock = threading.Lock()

# price history: { token_id: [(timestamp, price), ...] }
price_history = defaultdict(list)
price_lock = threading.Lock()

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = "https://clob.polymarket.com"

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def ts_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def matches_keywords(title):
    t = title.lower()
    with config_lock:
        kws = config["keywords"]
    return any(kw in t for kw in kws)

def categorize(title):
    t = title.lower()
    if any(k in t for k in ["gold","silver","oil","crude","brent","wti","natural gas",
                              "copper","wheat","corn","soybean","cotton","sugar","coffee",
                              "cocoa","platinum","palladium"]):
        return "Commodity"
    if any(k in t for k in ["s&p","sp500","nasdaq","dow","nikkei","hang seng","ftse",
                              "dax","stoxx","russell","vix","stock"]):
        return "Equity"
    if any(k in t for k in ["bitcoin","btc","ethereum","eth"]):
        return "Crypto"
    if any(k in t for k in ["fed rate","interest rate","inflation","cpi","treasury","yield","gdp"]):
        return "Macro"
    return "Other"

# ─────────────────────────────────────────
# MARKET FETCHING
# ─────────────────────────────────────────
def fetch_relevant_markets():
    markets = []
    offset, limit = 0, 100
    seen = set()
    with config_lock:
        max_m = config["max_markets"]

    while len(markets) < max_m:
        try:
            r = requests.get(f"{GAMMA_API}/markets",
                             params={"active": "true", "closed": "false",
                                     "limit": limit, "offset": offset},
                             timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception:
            break
        if not data:
            break
        for m in data:
            title = m.get("question") or m.get("title") or ""
            if matches_keywords(title):
                cid = m.get("conditionId") or m.get("condition_id")
                if cid and cid not in seen:
                    seen.add(cid)
                    markets.append({
                        "title": title,
                        "condition_id": cid,
                        "tokens": m.get("tokens", []),
                        "category": categorize(title),
                    })
        offset += limit
        if len(data) < limit:
            break
    return markets

# ─────────────────────────────────────────
# PRICE FETCHING
# ─────────────────────────────────────────
def fetch_orderbook_midpoint(token_id):
    """Get current mid price from orderbook."""
    try:
        r = requests.get(f"{CLOB_API}/book",
                         params={"token_id": token_id},
                         timeout=10)
        r.raise_for_status()
        book = r.json()
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        if bids and asks:
            best_bid = float(bids[0]["price"])
            best_ask = float(asks[0]["price"])
            return (best_bid + best_ask) / 2
        elif bids:
            return float(bids[0]["price"])
        elif asks:
            return float(asks[0]["price"])
    except Exception:
        pass
    return None

# ─────────────────────────────────────────
# ALERT
# ─────────────────────────────────────────
def add_alert(title, outcome, category, old_price, new_price, pct_change, token_id, window_s):
    direction = "▲ UP" if pct_change > 0 else "▼ DOWN"
    alert = {
        "time": ts_now(),
        "title": title,
        "outcome": outcome,
        "category": category,
        "old_price": round(old_price, 4),
        "new_price": round(new_price, 4),
        "pct_change": round(pct_change, 2),
        "direction": direction,
        "window_minutes": round(window_s / 60, 1),
        "token_id": token_id[:20] + "...",
    }
    with state_lock:
        state["alerts"].insert(0, alert)
        if len(state["alerts"]) > config["max_alerts"]:
            state["alerts"] = state["alerts"][:config["max_alerts"]]

# ─────────────────────────────────────────
# MONITOR LOOP
# ─────────────────────────────────────────
def monitor_loop():
    token_index = {}
    last_market_refresh = 0

    with state_lock:
        state["status"] = "running"

    while True:
        now = time.time()
        with config_lock:
            poll_interval = config["poll_interval_seconds"]
            window_s = config["window_seconds"]
            threshold_pct = config["price_change_threshold_pct"]

        # Refresh markets every hour
        if now - last_market_refresh > 3600:
            markets = fetch_relevant_markets()
            token_index = {}
            for m in markets:
                for tok in m.get("tokens", []):
                    tid = tok.get("token_id") or tok.get("tokenId")
                    if tid:
                        token_index[tid] = {
                            "title": m["title"],
                            "outcome": tok.get("outcome", ""),
                            "category": m["category"],
                        }
            last_market_refresh = now
            with state_lock:
                state["markets_count"] = len(markets)
                state["tokens_count"] = len(token_index)

        all_tokens = list(token_index.keys())

        for token_id in all_tokens:
            price = fetch_orderbook_midpoint(token_id)
            if price is None:
                continue

            with price_lock:
                history = price_history[token_id]
                history.append((now, price))
                # Keep only prices within window
                price_history[token_id] = [(t, p) for t, p in history if now - t <= window_s]
                history = price_history[token_id]

            if len(history) < 2:
                continue

            oldest_price = history[0][1]
            if oldest_price <= 0:
                continue

            pct_change = ((price - oldest_price) / oldest_price) * 100

            if abs(pct_change) >= threshold_pct:
                info = token_index.get(token_id, {})
                add_alert(
                    title=info.get("title", "Unknown"),
                    outcome=info.get("outcome", ""),
                    category=info.get("category", "Other"),
                    old_price=oldest_price,
                    new_price=price,
                    pct_change=pct_change,
                    token_id=token_id,
                    window_s=now - history[0][0],
                )
                # Reset history to avoid repeated alerts
                with price_lock:
                    price_history[token_id] = [(now, price)]

        with state_lock:
            state["last_checked"] = ts_now()

        time.sleep(poll_interval)

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
        s = dict(state)
    with config_lock:
        c = dict(config)
    return jsonify({"alerts": s["alerts"], "status": s["status"],
                    "markets_count": s["markets_count"],
                    "tokens_count": s["tokens_count"],
                    "last_checked": s["last_checked"],
                    "uptime_start": s["uptime_start"],
                    "config": c})

@app.route("/api/config", methods=["POST"])
def update_config():
    from flask import request
    data = request.get_json(silent=True) or {}
    with config_lock:
        if "price_change_threshold_pct" in data:
            config["price_change_threshold_pct"] = float(data["price_change_threshold_pct"])
        if "window_seconds" in data:
            config["window_seconds"] = int(data["window_seconds"])
        if "poll_interval_seconds" in data:
            config["poll_interval_seconds"] = max(10, int(data["poll_interval_seconds"]))
    return jsonify({"ok": True, "config": config})

@app.route("/api/clear", methods=["POST"])
def clear_alerts():
    with state_lock:
        state["alerts"] = []
    return jsonify({"ok": True})

# ─────────────────────────────────────────
# START
# ─────────────────────────────────────────
if __name__ == "__main__":
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
