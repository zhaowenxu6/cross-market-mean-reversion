"""
信号生成 (Step 4)
基于因子模型残差，生成多空交易信号

产出:
  1. data/interim/signals/  — 每个资产的信号 parquet
  2. output/tables/signal_statistics.xlsx — 信号统计报告
  3. output/figures/signal_*.png — 3个典型配对的信号图
"""
import sys, os, importlib.util
PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ_DIR)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False
from sklearn.linear_model import RidgeCV

# ---------- 导入 ----------
spec = importlib.util.spec_from_file_location("universe", PROJ_DIR + "/config/universe.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TARGET_ASSETS = mod.COIN_STOCKS + mod.CRYPTO_ASSETS + mod.US_TECH_PERPS
returns = pd.read_parquet(PROJ_DIR + "/data/interim/returns_clean.parquet")
returns = returns[returns.index >= "2023-01-01"]

# ---------- 配置 ----------
BETA_WINDOW = 90     # 估计β用的窗口（交易日）
Z_WINDOW = 60        # z-score均值和标准差用的窗口
ENTRY_Z = 2.0        # 入场阈值
EXIT_Z = 0.5         # 平仓阈值
STOP_Z = 4.0         # 止损阈值

os.makedirs(PROJ_DIR + "/data/interim/signals", exist_ok=True)
os.makedirs(PROJ_DIR + "/output/tables", exist_ok=True)
os.makedirs(PROJ_DIR + "/output/figures", exist_ok=True)

# ---------- 主循环 ----------
all_stats = []

for idx, asset in enumerate(TARGET_ASSETS, 1):
    name = asset["name"]
    factors = asset["factors"]
    print(f"[{idx}/{len(TARGET_ASSETS)}] {name} ← {factors} ...", end=" ", flush=True)

    asset_ret = returns[name]
    factor_rets = returns[factors]
    combined = pd.concat([asset_ret, factor_rets], axis=1).dropna()
    y = combined[name].values
    X = combined[factors].values
    dates = combined.index.values

    n = len(y)
    if n < BETA_WINDOW + Z_WINDOW:
        print(f"数据不足")
        continue

    # 逐日滚动回归
    residuals = np.full(n, np.nan)
    betas_history = []

    for t in range(BETA_WINDOW, n):
        y_win = y[t - BETA_WINDOW:t]
        X_win = X[t - BETA_WINDOW:t]

        try:
            model = RidgeCV(alphas=[0.001, 0.005, 0.01, 0.05, 0.1], fit_intercept=True, cv=3)
            model.fit(X_win, y_win)
            # 用今天的因子收益率预测
            y_pred = model.intercept_ + np.dot(model.coef_, X[t])
            residuals[t] = y[t] - y_pred
            betas_history.append(model.coef_)
        except:
            continue

    if np.sum(~np.isnan(residuals)) < Z_WINDOW:
        print("残差不足")
        continue

    # z-score（滚动60天）
    z_scores = np.full(n, np.nan)
    for t in range(BETA_WINDOW + Z_WINDOW, n):
        res_window = residuals[t - Z_WINDOW + 1:t + 1]
        mu = np.nanmean(res_window)
        sigma = np.nanstd(res_window)
        if sigma > 1e-10:
            z_scores[t] = (residuals[t] - mu) / sigma

    # 生成信号 + 交易记录
    # 0=无持仓, 1=做多, -1=做空
    signals = np.zeros(n)
    position = 0
    current_trade = None  # 跟踪当前未平仓的交易
    trades = []           # 已完成的交易列表

    for t in range(BETA_WINDOW + Z_WINDOW + 1, n):
        z = z_scores[t]
        if np.isnan(z):
            continue

        # 止损
        if position != 0 and abs(z) > STOP_Z:
            if current_trade:
                current_trade["exit_date"] = dates[t]
                current_trade["exit_z"] = z
                current_trade["reason"] = "止损"
                trades.append(current_trade)
                current_trade = None
            signals[t] = 0
            position = 0
            continue

        # 平仓
        if position != 0 and abs(z) < EXIT_Z:
            if current_trade:
                current_trade["exit_date"] = dates[t]
                current_trade["exit_z"] = z
                current_trade["reason"] = "平仓"
                trades.append(current_trade)
                current_trade = None
            signals[t] = 0
            position = 0
            continue

        # 开仓
        if position == 0:
            if z < -ENTRY_Z:
                position = 1
                signals[t] = 1
                current_trade = {
                    "name": name,
                    "direction": "做多",
                    "entry_date": dates[t],
                    "entry_z": z,
                    "exit_date": None,
                    "exit_z": None,
                    "reason": None,
                }
            elif z > ENTRY_Z:
                position = -1
                signals[t] = -1
                current_trade = {
                    "name": name,
                    "direction": "做空",
                    "entry_date": dates[t],
                    "entry_z": z,
                    "exit_date": None,
                    "exit_z": None,
                    "reason": None,
                }
        else:
            signals[t] = position

    # 保存信号
    # 保存信号
    sig_df = pd.DataFrame({
        "timestamp": dates,
        "residual": residuals,
        "zscore": z_scores,
        "signal": signals,
    }, index=dates)
    sig_df.to_parquet(f"{PROJ_DIR}/data/interim/signals/{name}_signals.parquet")

    # 保存交易记录
    trades_df = pd.DataFrame(trades)
    if len(trades_df) > 0:
        trades_df["entry_date"] = pd.to_datetime(trades_df["entry_date"])
        trades_df["exit_date"] = pd.to_datetime(trades_df["exit_date"])
        trades_df.to_parquet(f"{PROJ_DIR}/data/interim/signals/{name}_trades.parquet")

    # 统计
    n_trades = len(trades)
    if n_trades == 0:
        print(f"无交易")
        all_stats.append({"代码": name, "因子": "+".join(factors), "总交易数": 0})
        continue

    long_trades = [t for t in trades if t["direction"] == "做多"]
    short_trades = [t for t in trades if t["direction"] == "做空"]
    stop_trades = [t for t in trades if t["reason"] == "止损"]

    # 平均持仓周期
    hold_days = []
    for t in trades:
        if t["exit_date"] is not None and t["entry_date"] is not None:
            hold = (pd.Timestamp(t["exit_date"]) - pd.Timestamp(t["entry_date"])).days
            hold_days.append(hold)

    avg_hold = np.mean(hold_days) if hold_days else 0

    stop_ratio = len(stop_trades) / max(n_trades, 1)

    print(f"交易={n_trades}  做多={len(long_trades)}  做空={len(short_trades)}  "
          f"止损={len(stop_trades)}  持仓={avg_hold:.1f}天")

    all_stats.append({
        "代码": name,
        "因子": "+".join(factors),
        "R²均值": 0,
        "总交易数": n_trades,
        "做多": len(long_trades),
        "做空": len(short_trades),
        "止损": len(stop_trades),
        "止损率": round(stop_ratio, 3),
        "平均持仓天数": round(avg_hold, 1),
    })

# ===== 信号统计报告 =====
df_stats = pd.DataFrame(all_stats)
df_stats = df_stats.sort_values("总交易数", ascending=False)

# 补R²
try:
    qdf = pd.read_excel(PROJ_DIR + "/output/tables/factor_model_quality.xlsx")
    r2_map = dict(zip(qdf["代码"], qdf["R²均值"]))
    df_stats["R²均值"] = df_stats["代码"].map(r2_map)
except:
    pass

excel_path = PROJ_DIR + "/output/tables/signal_statistics.xlsx"
with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
    df_stats.to_excel(writer, index=False, sheet_name="信号统计")
    ws = writer.sheets["信号统计"]
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 30)

# ===== 汇总统计（匹配面试题格式） =====
total_trades_from_sig = df_stats["总交易数"].sum()
total_days = len(returns)

# 从交易记录算胜率
import os
trades_dir = PROJ_DIR + "/data/interim/signals/"
total_trades = 0
total_wins = 0
total_losses = 0
all_hold_days = []

for f in os.listdir(trades_dir):
    if not f.endswith("_trades.parquet"):
        continue
    tdf = pd.read_parquet(trades_dir + f)
    if len(tdf) == 0:
        continue
    completed = tdf[tdf["reason"].notna()]
    total_trades += len(completed)
    total_wins += len(completed[completed["reason"] == "平仓"])
    total_losses += len(completed[completed["reason"] == "止损"])
    for _, r in completed.iterrows():
        if r["exit_date"] is not None:
            h = (pd.Timestamp(r["exit_date"]) - pd.Timestamp(r["entry_date"])).days
            all_hold_days.append(h)

avg_daily = total_trades / total_days
avg_hold = sum(all_hold_days) / len(all_hold_days) if all_hold_days else 0
sorted_hold = sorted(all_hold_days)
med_hold = sorted_hold[len(sorted_hold)//2] if sorted_hold else 0
max_h = max(all_hold_days) if all_hold_days else 0
win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0

print()
print("=" * 60)
print("信号统计报告")
print("=" * 60)
print(f"  {'指标':16} {'数值'}")
print(f"  {'-'*16} {'-'*10}")
print(f"  {'每日平均新信号数':16} {avg_daily:.1f}")
print(f"  {'平均信号持续时间':16} {avg_hold:.1f} 天")
print(f"  {'信号胜率':16} {win_rate:.1f}%")
print(f"  {'半衰期中位数':16} {med_hold:.1f} 天")
print(f"  {'最长持有时间':16} {max_h:.1f} 天")
print(f"  {'总交易数':16} {total_trades}")
print(f"  {'平仓(胜)':16} {total_wins}")
print(f"  {'止损(败)':16} {total_losses}")

# ===== 输出汇总表 Excel =====
summary_rows = [
    {"指标": "每日平均新信号数", "数值": f"{avg_daily:.1f}"},
    {"指标": "平均信号持续时间", "数值": f"{avg_hold:.1f} 天"},
    {"指标": "信号胜率", "数值": f"{win_rate:.1f}%"},
    {"指标": "半衰期中位数", "数值": f"{med_hold:.1f} 天"},
    {"指标": "最长持有时间", "数值": f"{max_h:.1f} 天"},
]
summary_df = pd.DataFrame(summary_rows)
summary_path = PROJ_DIR + "/output/tables/signal_summary.xlsx"
os.makedirs(PROJ_DIR + "/output/tables", exist_ok=True)
summary_df.to_excel(summary_path, index=False, sheet_name="信号统计汇总")
print(f"\n✅ 已生成: {summary_path}")

# ===== 可视化（3个典型配对） =====
demo_assets = [
    {"name": "MSTR", "title": "MSTR — 币股典型 (BTC+QQQ)"},
    {"name": "ARB", "title": "ARB — L2代币典型 (ETH+BTC)"},
    {"name": "NVDA", "title": "NVDA — 美股科技典型 (QQQ+SMH)"},
]

for demo in demo_assets:
    name = demo["name"]
    try:
        sig = pd.read_parquet(f"{PROJ_DIR}/data/interim/signals/{name}_signals.parquet")
    except:
        continue

    # 取最近400天
    sig = sig.tail(400).copy()
    sig = sig.reset_index()

    # 获取价格（用于子图）
    asset_info = [a for a in TARGET_ASSETS if a["name"] == name]
    if not asset_info:
        continue
    atype = asset_info[0]["type"]
    if atype == "crypto_spot":
        price_path = f"{PROJ_DIR}/data/raw/crypto_spot/1d/{name}.parquet"
    else:
        price_path = f"{PROJ_DIR}/data/raw/tradfi_perp/1d/{name}.parquet"
    price_df = pd.read_parquet(price_path)
    price_df["date"] = pd.to_datetime(price_df["timestamp"].dt.date)
    price_df = price_df.set_index("date")

    # 合并
    sig["date"] = pd.to_datetime(sig["index"])
    sig = sig.set_index("date")
    merged = price_df[["close"]].join(sig[["residual", "zscore", "signal"]], how="inner").dropna()
    merged = merged.tail(400)

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)

    # 子图1: 价格
    ax = axes[0]
    ax.plot(merged.index, merged["close"], color="#333333", linewidth=1)
    ax.set_title(f"{demo['title']} — 价格与信号", fontsize=12)
    ax.set_ylabel("价格")
    ax.grid(True, alpha=0.3)

    # 子图2: z-score
    ax = axes[1]
    ax.plot(merged.index, merged["zscore"], color="#2962FF", linewidth=1, alpha=0.8)
    ax.axhline(y=ENTRY_Z, color="red", linestyle="--", alpha=0.5, label=f"做空线 z={ENTRY_Z}")
    ax.axhline(y=-ENTRY_Z, color="green", linestyle="--", alpha=0.5, label=f"做多线 z={-ENTRY_Z}")
    ax.axhline(y=EXIT_Z, color="gray", linestyle=":", alpha=0.4)
    ax.axhline(y=-EXIT_Z, color="gray", linestyle=":", alpha=0.4)
    ax.axhline(y=0, color="black", linestyle="-", alpha=0.2)
    # 加载交易记录（只标记开仓日，不标记持续持仓）
    try:
        tdf = pd.read_parquet(f"{PROJ_DIR}/data/interim/signals/{name}_trades.parquet")
        tdf["entry_date"] = pd.to_datetime(tdf["entry_date"])
        tdf = tdf.set_index("entry_date")
        # 只取在画图范围内的交易
        tdf = tdf[tdf.index >= merged.index[0]]
        tdf = tdf[tdf.index <= merged.index[-1]]
        long_entries = tdf[tdf["direction"] == "做多"]
        short_entries = tdf[tdf["direction"] == "做空"]
    except:
        long_entries = pd.DataFrame()
        short_entries = pd.DataFrame()

    # 标记信号点（只标开仓日）
    ax = axes[1]
    if len(long_entries) > 0:
        ax.scatter(long_entries.index,
                   [merged.loc[d, "zscore"] if d in merged.index else 0 for d in long_entries.index],
                   color="green", s=40, marker="^", label="做多", zorder=5)
    if len(short_entries) > 0:
        ax.scatter(short_entries.index,
                   [merged.loc[d, "zscore"] if d in merged.index else 0 for d in short_entries.index],
                   color="red", s=40, marker="v", label="做空", zorder=5)
    ax.set_ylabel("z-score")
    ax.legend(fontsize=8, ncol=3)
    ax.grid(True, alpha=0.3)

    # 子图3: 仓位
    ax = axes[2]
    ax.fill_between(merged.index, 0, merged["signal"],
                     where=merged["signal"] > 0, color="green", alpha=0.3, label="做多")
    ax.fill_between(merged.index, 0, merged["signal"],
                     where=merged["signal"] < 0, color="red", alpha=0.3, label="做空")
    ax.set_ylabel("仓位方向")
    ax.set_xlabel("日期")
    ax.set_ylim(-1.5, 1.5)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = f"{PROJ_DIR}/output/figures/signal_{name}.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✅ signal_{name}.png")

print(f"\n✅ 信号统计: {excel_path}")
print(f"✅ 信号图: output/figures/signal_*.png")
