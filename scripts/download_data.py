"""
数据下载器 
- 加密资产: Binance 现货 API（urllib，零外部依赖） ✅
- 美股/ETF: Yahoo Finance 原始 API（JSON 直取，无限速） ✅
- 保存为 Parquet（依赖 pandas + pyarrow）
- 支持断点续传（已有文件自动跳过）

用法：
  python scripts/download_data.py        # 自动用代理 127.0.0.1:7897
  NO_PROXY=1 python scripts/download_data.py   # 不用代理（国内直连 Binance）

花的时间比较长（yfinance 限速每个 ticker 等 3 秒），耐心等待。
"""
import os, sys, time, json, urllib.request, datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ========== 代理 ==========
USE_PROXY = os.environ.get("NO_PROXY", "0") != "1"
if USE_PROXY:
    proxy = urllib.request.ProxyHandler({"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"})
    urllib.request.install_opener(urllib.request.build_opener(proxy))

# ========== 配置 ==========
DATA_DIR = PROJ_DIR + "/data"           # 数据根目录
SPOT_URL = "https://api.binance.com/api/v3/klines"  # Binance 现货 K 线 API
START = "2023-01-01"                      # 起始日期
END = "2026-06-30"                        # 截止日期

# 美股 ticker 映射（用于 Yahoo Finance 原始 API）
YF_MAP = {
    "MSTR": "MSTR", "COIN": "COIN",
    "MARA": "MARA", "RIOT": "RIOT", "CLSK": "CLSK",
    "NVDA": "NVDA", "TSLA": "TSLA", "AAPL": "AAPL",
    "MSFT": "MSFT", "META": "META", "AMD": "AMD",
    "AMZN": "AMZN", "GOOGL": "GOOGL",
    "SPY": "SPY", "QQQ": "QQQ", "SMH": "SMH",
}


def log(msg):
    t = dt.datetime.now().strftime("%H:%M:%S")
    print("[%s] %s" % (t, msg), flush=True)


def api_get(url, params, retries=3):
    """调 Binance API，自动重试。永不抛出异常"""
    qs = "&".join("%s=%s" % (k, v) for k, v in params.items())
    full = "%s?%s" % (url, qs)
    for i in range(retries):
        try:
            req = urllib.request.Request(full)
            req.add_header("User-Agent", "Mozilla/5.0")
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            log("  重试 %d/%d: %s" % (i + 1, retries, str(e)[:60]))
            time.sleep(2)
    log("  [SKIP] %s 重试 %d 次都失败，跳过" % (params.get("symbol", ""), retries))
    return None


def download_binance(name, symbol, interval, out):
    """从 Binance 分批下载，保存为 parquet"""
    if os.path.exists(out):
        log("  %s [%s] 已存在，跳过" % (name, interval))
        return True

    start_ms = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    end_ms   = int(dt.datetime(2026, 6, 30, 23, 59, 59, tzinfo=dt.timezone.utc).timestamp() * 1000)

    rows = []
    cur = start_ms
    sys.stdout.write("  %s [%s] ... " % (name, interval))
    sys.stdout.flush()
    while cur < end_ms:
        data = api_get(SPOT_URL, {"symbol": symbol, "interval": interval, "startTime": cur, "limit": 1000})
        if data is None:
            break
        if isinstance(data, dict) and "code" in data:
            log("API错误: %s" % data.get("msg", ""))
            break
        rows.extend(data)
        cur = data[-1][0] + 1
        if len(data) < 1000:
            break

    if not rows:
        log("无数据")
        return False

    # 转 DataFrame
    import pandas as pd
    cols = ["timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]

    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_parquet(out, index=False)
    log("完成（%d 根）" % len(df))
    return True


def download_us_stock(name, yahoo_ticker, out):
    """用 Yahoo Finance 原始 API 下载美股日线（JSON，无需库）"""
    if os.path.exists(out):
        log("  %s [1d] 已存在，跳过" % name)
        return True

    import pandas as pd
    YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=5y&interval=1d"

    sys.stdout.write("  %s [1d] ..." % name)
    sys.stdout.flush()
    try:
        url = YAHOO_URL % yahoo_ticker
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        result = data.get("chart", {}).get("result", [None])[0]
        if not result:
            log(" 无数据")
            return False

        timestamps = result.get("timestamp", [])
        quotes = result.get("indicators", {}).get("quote", [{}])[0]
        opens = quotes.get("open", [])
        highs = quotes.get("high", [])
        lows = quotes.get("low", [])
        closes = quotes.get("close", [])
        volumes = quotes.get("volume", [])

        if not closes or all(c is None for c in closes):
            log(" 无有效数据")
            return False

        rows = []
        for i in range(len(timestamps)):
            if closes[i] is not None:
                rows.append([
                    pd.Timestamp(timestamps[i], unit="s"),
                    opens[i] or 0.0, highs[i] or 0.0, lows[i] or 0.0,
                    closes[i] or 0.0, volumes[i] or 0
                ])

        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        df.to_parquet(out, index=False)
        log(" 完成（%d 根）" % len(df))
        return True
    except Exception as e:
        log(" FAIL: %s" % str(e)[:60])
        return False


def main():
    log("=" * 50)
    log("数据下载器 v3")
    log("时间: %s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log("代理: %s" % ("启用" if USE_PROXY else "禁用"))
    log("=" * 50)

    # 导入标的池
    import importlib.util
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location("universe", PROJ_DIR + "/config/universe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    ok_c, ok_s = 0, 0
    for a in mod.ALL_ASSETS:
        if a["type"] == "crypto_spot":
            for iv in ["1h", "4h", "1d"]:
                out = os.path.join(DATA_DIR, "raw", "crypto_spot", iv, "%s.parquet" % a["name"])
                if download_binance(a["name"], a["symbol"], iv, out):
                    ok_c += 1
        elif a["type"] == "tradfi_perp":
            yahoo_ticker = YF_MAP.get(a["name"])
            if not yahoo_ticker:
                log("[WARN] %s 无 Yahoo ticker，跳过" % a["name"])
                continue
            out = os.path.join(DATA_DIR, "raw", "tradfi_perp", "1d", "%s.parquet" % a["name"])
            if download_us_stock(a["name"], yahoo_ticker, out):
                ok_s += 1

    log("")
    log("=" * 50)
    log("下载完成！加密=%d  美股=%d" % (ok_c, ok_s))
    log("数据: %s/raw/" % DATA_DIR)
    log("=" * 50)


if __name__ == "__main__":
    main()
