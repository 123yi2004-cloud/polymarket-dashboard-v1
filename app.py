"""
Polymarket Large Bet Alert Dashboard
后端：Flask + 后台监控线程
"""

from flask import Flask, jsonify, render_template_string
import threading
import requests
import time
from datetime import datetime, timezone
from collections import defaultdict
import json

app = Flask(__name__)

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
CONFIG = {
    "alert_threshold_usdc": 5_000,
    "cumulative_threshold_usdc": 20_000,
    "cumulative_window_seconds": 120,
    "poll_interval_seconds": 15,
    "max_alerts": 100,       # 最多保留多少条告警
    "max_markets": 200,
    "keywords": [
        "s&p", "sp500", "nasdaq", "dow jones", "nikkei", "hang seng",
        "ftse", "dax", "stoxx", "russell", "vix",
        "gold", "silver", "oil", "crude", "brent", "wti",
        "natural gas", "copper", "wheat", "corn", "soybean",
        "cotton", "sugar", "coffee", "cocoa",
        "fed rate", "interest rate", "inflation", "cpi", "recession",
        "treasury", "yield curve",
        "bitcoin", "btc", "ethereum", "eth",
    ],
}

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = "https://clob.polymarket.com"

# 全局状态
state = {
    "alerts": [],          # 告警列表
    "status": "starting",  # 监控状态
    "markets_count": 0,
    "last_checked": None,
    "total_checked": 0,
}
state_lock = threading.Lock()

# ─────────────────────────────────────────
# 监控逻辑
# ─────────────────────────────────────────
def ts_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def matches_keywords(title):
    t = title.lower()
    return any(kw in t for kw in CONFIG["keywords"])

def fetch_relevant_markets():
    markets = []
    offset, limit = 0, 100
    seen = set()
    while len(markets) < CONFIG["max_markets"]:
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
                    })
        offset += limit
        if len(data) < limit:
            break
    return markets

def fetch_trades(token_id):
    try:
        r = requests.get(f"{CLOB_API}/trades",
                         params={"token_id": token_id, "limit": 10},
                         timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("data", data) if isinstance(data, dict) else data
    except Exception:
        return []

def add_alert(alert_type, title, outcome, side, usdc, price, size, token_id, extra=""):
    alert = {
        "type": alert_type,          # "LARGE_BET" or "SURGE"
        "time": ts_now(),
        "title": title,
        "outcome": outcome,
        "side": side,
        "usdc": round(usdc, 2),
        "price": round(price, 4),
        "size": round(size, 2),
        "token_id": token_id[:20] + "...",
        "extra": extra,
    }
    with state_lock:
        state["alerts"].insert(0, alert)
        if len(state["alerts"]) > CONFIG["max_alerts"]:
            state["alerts"] = state["alerts"][:CONFIG["max_alerts"]]

def monitor_loop():
    seen_trade_ids = set()
    cumulative = defaultdict(list)
    last_market_refresh = 0
    token_index = {}

    with state_lock:
        state["status"] = "running"

    while True:
        now = time.time()

        # 每小时刷新市场
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
                        }
            last_market_refresh = now
            with state_lock:
                state["markets_count"] = len(markets)

        all_tokens = list(token_index.keys())

        for token_id in all_tokens:
            trades = fetch_trades(token_id)
            for trade in trades:
                tid = (trade.get("id") or trade.get("tradeId") or
                       trade.get("transaction_hash", "") + str(trade.get("size", "")))
                if tid in seen_trade_ids:
                    continue
                seen_trade_ids.add(tid)

                try:
                    size  = float(trade.get("size", 0) or 0)
                    price = float(trade.get("price", 0) or 0)
                    usdc  = size * price
                except Exception:
                    continue

                if usdc <= 0:
                    continue

                info    = token_index.get(token_id, {})
                title   = info.get("title", "Unknown")
                outcome = info.get("outcome", "")
                side    = trade.get("side", trade.get("makerSide", "?")).upper()

                # 单笔大额
                if usdc >= CONFIG["alert_threshold_usdc"]:
                    add_alert("LARGE_BET", title, outcome, side,
                              usdc, price, size, token_id)

                # 累计突发
                window = CONFIG["cumulative_window_seconds"]
                cumulative[token_id].append((now, usdc))
                cumulative[token_id] = [
                    (t, u) for t, u in cumulative[token_id] if now - t <= window
                ]
                total = sum(u for _, u in cumulative[token_id])
                if (total >= CONFIG["cumulative_threshold_usdc"]
                        and usdc < CONFIG["alert_threshold_usdc"]):
                    add_alert("SURGE", title, outcome, side,
                              usdc, price, size, token_id,
                              extra=f"累计 ${total:,.0f} / {window}s")
                    cumulative[token_id] = []

        # 控制 seen 大小
        if len(seen_trade_ids) > 50_000:
            seen_trade_ids = set(list(seen_trade_ids)[-10_000:])

        with state_lock:
            state["last_checked"] = ts_now()
            state["total_checked"] += len(all_tokens)

        time.sleep(CONFIG["poll_interval_seconds"])

# ─────────────────────────────────────────
# Flask 路由
# ─────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(open("templates/index.html").read())

@app.route("/api/alerts")
def api_alerts():
    with state_lock:
        return jsonify({
            "alerts": state["alerts"],
            "status": state["status"],
            "markets_count": state["markets_count"],
            "last_checked": state["last_checked"],
            "total_checked": state["total_checked"],
            "thresholds": {
                "single": CONFIG["alert_threshold_usdc"],
                "cumulative": CONFIG["cumulative_threshold_usdc"],
            }
        })

@app.route("/api/config")
def api_config():
    return jsonify(CONFIG)

# ─────────────────────────────────────────
# 启动
# ─────────────────────────────────────────
if __name__ == "__main__":
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=10000, debug=False)
