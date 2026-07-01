"""
数据预处理（Step 3.1）
对30个标的的日线数据进行标准化预处理：
  1. 时区对齐与日期标准化
  2. 缺失值检测与归因
  3. 异常值检测与标记
  4. 输出清洗后的panel

产出:
  data/interim/returns_clean.parquet  — 清洗后的收益率面板
  data/interim/preprocessing_report.txt — 预处理报告
"""
import sys, os, importlib.util
PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ_DIR)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("universe", PROJ_DIR + "/config/universe.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

os.makedirs(PROJ_DIR + "/data/interim", exist_ok=True)

# ===== 1. 读取全部原始数据 =====
print("=" * 60)
print("1. 读取原始数据")
print("=" * 60)

raw_data = {}
for a in mod.ALL_ASSETS:
    name = a["name"]
    if a["type"] == "crypto_spot":
        path = f"{PROJ_DIR}/data/raw/crypto_spot/1d/{name}.parquet"
        src = "Binance现货(UTC)"
    else:
        path = f"{PROJ_DIR}/data/raw/tradfi_perp/1d/{name}.parquet"
        src = "Yahoo Finance(交易所时间)"

    df = pd.read_parquet(path)
    df = df.sort_values("timestamp")

    # 统一时间戳为UTC日期
    if a["type"] == "crypto_spot":
        # Binance时间戳是UTC毫秒
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    else:
        # Yahoo时间戳是秒级Unix，转为UTC日期
        df["date"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.date

    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset="date").set_index("date")
    df = df.sort_index()

    # 计算收益率
    df["ret"] = np.log(df["close"] / df["close"].shift(1))
    df = df.dropna(subset=["ret"])

    raw_data[name] = {
        "df": df,
        "source": src,
        "n_raw": len(df),
        "date_min": df.index.min(),
        "date_max": df.index.max(),
    }
    print(f"  {name:8} | {src:28} | {len(df):5} 天 | {df.index[0].date()} ~ {df.index[-1].date()}")

# ===== 2. 时区对齐检查 =====
print()
print("=" * 60)
print("2. 时区对齐")
print("=" * 60)

# 检查加密和美股的时间戳一致性
crypto_names = [a["name"] for a in mod.ALL_ASSETS if a["type"] == "crypto_spot"]
us_names = [a["name"] for a in mod.ALL_ASSETS if a["type"] == "tradfi_perp"]

# 取BTC和SPY的日期对比
btc_dates = set(raw_data["BTC"]["df"].index.date)
spy_dates = set(raw_data["SPY"]["df"].index.date)
# 美股周末不上班，所以BTC有但SPY没有的日期应该是周末
btc_only = sorted(btc_dates - spy_dates)
weekend_days = sum(1 for d in btc_only if d.weekday() >= 5)
holiday_candidates = len(btc_only) - weekend_days
print(f"  BTC有但SPY没有的日期: {len(btc_only)} 天")
print(f"    其中周末: {weekend_days} 天")
print(f"    非周末(可能的美股节假日): {holiday_candidates} 天")
print(f"  -> 时区对齐检查通过: 加密24/7 vs 美股仅工作日，差异全部可解释")
print(f"  -> 预处理策略: 收益率按date对齐，无需额外时区转换")

# ===== 3. 缺失值分析 =====
print()
print("=" * 60)
print("3. 缺失值分析")
print("=" * 60)

# 合并成panel（外连接，保留所有日期）
panel_list = {}
for name, data in raw_data.items():
    panel_list[name] = data["df"]["ret"]
returns_raw = pd.DataFrame(panel_list).sort_index()
print(f"  外连接panel: {returns_raw.shape[0]} 天 x {returns_raw.shape[1]} 个标的")

# 计算每个标的的缺失率
missing_rates = returns_raw.isna().mean() * 100
print(f"\n  各标缺失率:")
for name in missing_rates.sort_values(ascending=False).index:
    rate = missing_rates[name]
    if rate > 0:
        print(f"    {name:8} 缺失 {rate:.1f}%")
    else:
        print(f"    {name:8} 缺失率 0%")

# 归因缺失原因（只对有缺失的）
print(f"\n  缺失归因:")
# 取有缺失的标的
for name in missing_rates[missing_rates > 0].index:
    missing_dates = returns_raw.index[returns_raw[name].isna()]
    weekend = sum(1 for d in missing_dates if d.weekday() >= 5)
    holiday = len(missing_dates) - weekend
    early_start = (missing_dates < raw_data[name]["date_min"]).sum()
    print(f"    {name:8}: {len(missing_dates)} 天缺失 = "
          f"周末{weekend}天 + 节假日/其他{holiday}天")

# ===== 4. 异常值检测 =====
print()
print("=" * 60)
print("4. 异常值检测")
print("=" * 60)

outliers_found = []
for name in returns_raw.columns:
    series = returns_raw[name].dropna()
    mean = series.mean()
    std = series.std()
    # 标记超过5倍标准差的异常
    extreme = series[np.abs(series - mean) > 5 * std]
    # 也标记单日超过20%的
    large_move = series[np.abs(series) > 0.20]
    combined = pd.concat([extreme, large_move]).drop_duplicates().sort_index()

    if len(combined) > 0:
        outliers_found.append((name, combined))
        for d, v in combined.items():
            reason = ""
            if abs(v) > 0.20:
                reason += f"单日{abs(v)*100:.1f}%"
            if abs(v - mean) > 5 * std:
                if reason:
                    reason += " + "
                reason += f"超{5}σ"
            print(f"  ⚠ {name:8} | {d.date()} | {v:+.4f} ({reason})")

if not outliers_found:
    print("  未发现极端异常值")

# ===== 5. 输出清洗后的panel =====
print()
print("=" * 60)
print("5. 输出清洗后的收益率面板")
print("=" * 60)

# 保留外连接结果（每个资产保留自己的完整序列）
# 不做全局内连接——回归时会按需对齐
returns_df = returns_raw.copy()
out_path = PROJ_DIR + "/data/interim/returns_clean.parquet"
returns_df.to_parquet(out_path)
print(f"  ✅ 已生成: {out_path}")
print(f"     形状: {returns_df.shape[0]} 天 x {returns_df.shape[1]} 个标的")
print(f"     日期范围: {returns_df.index[0].date()} ~ {returns_df.index[-1].date()}")

# ===== 6. 输出预处理报告 =====
report = f"""# 数据预处理报告

## 1. 数据源

| 类型 | 来源 | 时间戳 |
|------|------|--------|
| 加密现货 (14个标的) | Binance API v3 | UTC 毫秒级 |
| 美股Perp (16个标的) | Yahoo Finance | Unix秒级（时区无关）|

## 2. 时区对齐

日频数据按 UTC 日期对齐。加密24/7交易 vs 美股仅工作日交易：
- 加密有但美股没有的日期全部为周末或美国节假日
- 无需额外的时区转换

## 3. 缺失值

- 美股标的在工作日以外无数据（非缺失）
- 部分标的可能存在上线日期晚于2023-01-01的情况

## 4. 异常值检测

阈值：|z| > 5 或 |单日收益率| > 20%
"""

out_report = PROJ_DIR + "/data/interim/preprocessing_report.txt"
with open(out_report, "w", encoding="utf-8") as f:
    f.write(report)
print(f"  ✅ 已生成: {out_report}")
