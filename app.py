"""
Polymarket Price Movement Alert Dashboard - Fixed Version
- Monitor thread starts correctly with gunicorn
- Uses Gamma API lastTradePrice (no auth needed)
- Settings don't auto-reset
"""

from flask import Flask, jsonify, request, render_template_string
import threading
import requests
import time
from datetime import datetime, timezone
from collections import defaultdict
import os

app = Flask(__name__)

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
config = {
    "price_change_threshold_pct": 5.0,
    "window_seconds": 300,
    "poll_interval_seconds": 30,
    "max_alerts": 100,
    "max_markets": 200,
    "keywords": [
        "s&p", "sp500", "nasdaq", "dow jones", "nikkei", "hang seng",
        "ftse", "dax", "stoxx", "russell", "vix", "stock market",
        "bull", "bear", "recession", "crash", "rally",
        "gold", "silver", "oil", "crude", "brent", "wti",
        "natural gas", "copper", "wheat", "corn", "soybean",
        "cotton", "sugar", "coffee", "cocoa", "platinum", "palladium",
        "fed rate", "interest rate", "inflation", "cpi", "pce",
        "treasury", "yield", "gdp",
        "bitcoin", "btc", "ethereum", "eth",
    ],
}
config_lock = threading.Lock()

state = {
    "alerts": [],
    "status": "starting",
    "markets_count": 0,
    "tokens_count": 0,
    "last_checked": None,
    "uptime_start": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    "errors": [],
    "prices_fetched": 0,
}
state_lock = threading.Lock()

price_history = defaultdict(list)
price_lock = threading.Lock()

GAMMA_API = "https://gamma-api.polymarket.com"

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
# FETCH MARKETS + PRICES from Gamma API
# Gamma API returns lastTradePrice — no auth needed
# ─────────────────────────────────────────
def fetch_markets_with_prices():
    """Returns list of {token_id, title, outcome, category, price}"""
    results = []
    offset, limit = 0, 100
    seen = set()
    with config_lock:
        max_m = config["max_markets"]

    print(f"[{ts_now()}] Fetching markets...", flush=True)

    while len(results) < max_m:
        try:
            r = requests.get(
                f"{GAMMA_API}/markets",
                params={"active": "true", "closed": "false",
                        "limit": limit, "offset": offset},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log_error(f"Gamma API failed: {e}")
            break

        if not data:
            break

        for m in data:
            title = m.get("question") or m.get("title") or ""
            if not matches_keywords(title):
                continue

            cid = m.get("conditionId") or m.get("condition_id")
            if not cid or cid in seen:
                continue
            seen.add(cid)

            category = categorize(title)
            tokens = m.get("tokens", [])

            for tok in tokens:
                tid = tok.get("token_id") or tok.get("tokenId")
                if not tid:
                    continue

                # Gamma API provides lastTradePrice directly — no auth needed
                price = None
                for field in ["lastTradePrice", "price", "midpoint"]:
                    raw = tok.get(field) or m.get(field)
                    if raw is not None:
                        try:
                            price = float(raw)
                            break
                        except (ValueError, TypeError):
                            pass

                results.append({
                    "token_id": tid,
                    "title":    title,
                    "outcome":  tok.get("outcome", ""),
                    "category": category,
                    "price":    price,
                })

        offset += limit
        if len(data) < limit:
            break

    valid = [r for r in results if r["price"] is not None and 0 < r["price"] < 1]
    print(f"[{ts_now()}] Found {len(results)} tokens, {len(valid)} with valid prices", flush=True)
    return results

# ─────────────────────────────────────────
# ALERT
# ─────────────────────────────────────────
def add_alert(title, outcome, category, old_price, new_price, pct_change, token_id, window_s):
    direction = "UP" if pct_change > 0 else "DOWN"
    alert = {
        "time":           ts_now(),
        "title":          title,
        "outcome":        outcome,
        "category":       category,
        "old_price":      round(old_price, 4),
        "new_price":      round(new_price, 4),
        "pct_change":     round(pct_change, 2),
        "direction":      direction,
        "window_minutes": round(window_s / 60, 1),
        "token_id":       token_id[:20] + "...",
    }
    print(f"[ALERT] {title} | {pct_change:+.2f}% | {old_price:.4f} -> {new_price:.4f}", flush=True)
    with state_lock:
        state["alerts"].insert(0, alert)
        if len(state["alerts"]) > config["max_alerts"]:
            state["alerts"] = state["alerts"][:config["max_alerts"]]

# ─────────────────────────────────────────
# MONITOR LOOP
# ─────────────────────────────────────────
def monitor_loop():
    print(f"[{ts_now()}] Monitor thread started", flush=True)
    with state_lock:
        state["status"] = "running"

    while True:
        try:
            now = time.time()
            with config_lock:
                poll_interval = config["poll_interval_seconds"]
                window_s      = config["window_seconds"]
                threshold_pct = config["price_change_threshold_pct"]

            # Fetch all markets + their current prices
            tokens = fetch_markets_with_prices()

            with state_lock:
                state["markets_count"] = len(set(t["title"] for t in tokens))
                state["tokens_count"]  = len(tokens)

            fetched = 0
            for tok in tokens:
                token_id = tok["token_id"]
                price    = tok["price"]
                if price is None:
                    continue

                fetched += 1
                now2 = time.time()

                with price_lock:
                    price_history[token_id].append((now2, price))
                    price_history[token_id] = [
                        (t, p) for t, p in price_history[token_id]
                        if now2 - t <= window_s
                    ]
                    history = price_history[token_id]

                if len(history) < 2:
                    continue

                oldest_ts, oldest_price = history[0]
                if oldest_price <= 0:
                    continue

                pct_change = ((price - oldest_price) / oldest_price) * 100

                if abs(pct_change) >= threshold_pct:
                    add_alert(
                        title=tok["title"],
                        outcome=tok["outcome"],
                        category=tok["category"],
                        old_price=oldest_price,
                        new_price=price,
                        pct_change=pct_change,
                        token_id=token_id,
                        window_s=now2 - oldest_ts,
                    )
                    with price_lock:
                        price_history[token_id] = [(now2, price)]

            with state_lock:
                state["last_checked"]   = ts_now()
                state["prices_fetched"] += fetched

            print(f"[{ts_now()}] Scanned {fetched} tokens with prices. Sleeping {poll_interval}s.", flush=True)

        except Exception as e:
            log_error(f"Monitor loop error: {e}")

        time.sleep(poll_interval)

# ─────────────────────────────────────────
# START THREAD — runs at import time so
# gunicorn picks it up correctly
# ─────────────────────────────────────────
_monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
_monitor_thread.start()

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
        s = {k: v for k, v in state.items() if k != "alerts"}
        alerts = list(state["alerts"])
    with config_lock:
        c = dict(config)
    return jsonify({
        "alerts":         alerts,
        "status":         s["status"],
        "markets_count":  s["markets_count"],
        "tokens_count":   s["tokens_count"],
        "last_checked":   s["last_checked"],
        "uptime_start":   s["uptime_start"],
        "prices_fetched": s["prices_fetched"],
        "errors":         s["errors"][:5],
        "config":         c,
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
            config["poll_interval_seconds"] = max(10, int(data["poll_interval_seconds"]))
    print(f"[{ts_now()}] Config updated: {config['price_change_threshold_pct']}% / {config['window_seconds']}s", flush=True)
    return jsonify({"ok": True, "config": config})

@app.route("/api/clear", methods=["POST"])
def clear_alerts():
    with state_lock:
        state["alerts"] = []
    return jsonify({"ok": True})

@app.route("/api/debug")
def debug():
    sample = {}
    with price_lock:
        for tid, hist in list(price_history.items())[:5]:
            if hist:
                sample[tid[:20]+"..."] = {
                    "latest_price": hist[-1][1],
                    "data_points":  len(hist),
                }
    with state_lock:
        errs = list(state["errors"])
    return jsonify({"price_samples": sample, "recent_errors": errs})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
