"""
可视化：样本交易开平仓点位 + 权益曲线
用真实收盘价日线绘制开平仓信号
"""
import sys, os
PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ_DIR)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

os.makedirs(PROJ_DIR + "/output/figures", exist_ok=True)

returns = pd.read_parquet(PROJ_DIR + "/data/interim/returns_clean.parquet")
returns = returns[returns.index >= "2023-01-01"]
nav = pd.read_parquet(PROJ_DIR + "/output/tables/nav_curve.parquet")
trades = pd.read_excel(PROJ_DIR + "/output/tables/trade_log.xlsx")

# ============ 图1: 权益曲线 ============
print("绘制: 权益曲线...")
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [3, 1]})

dates_nav = nav["日期"].values
nav_m = nav["净资产"] / 1e6
ax1.plot(dates_nav, nav_m, color="#2196F3", lw=1.2)
ax1.axhline(1.0, color="gray", ls="--", lw=0.5, alpha=0.4)
ax1.fill_between(dates_nav, 0, nav_m, alpha=0.08, color="#2196F3")
ax1.set_ylabel("净资产 ($M)", fontsize=11, color="#2196F3")
ax1.tick_params(axis="y", labelcolor="#2196F3")
ax1.set_ylim(max(0.5, nav_m.min()*0.95), max(1.3, nav_m.max()*1.05))

final_val = nav["净资产"].iloc[-1]
ax1.annotate(f"初始 $1M", xy=(dates_nav[0], 1.0),
             fontsize=9, color="gray",
             arrowprops=dict(arrowstyle="->", color="gray", lw=0.8))
ax1.annotate(f"最终 ${final_val/1e6:.2f}M",
             xy=(dates_nav[-1], final_val/1e6),
             fontsize=9, color="red" if final_val < 1e6 else "green", ha="right")

ax2.bar(dates_nav, nav["持仓数"].values, width=1.0, color="#4CAF50", alpha=0.5)
ax2.set_ylabel("持仓数", fontsize=11)
ax2.set_xlabel("日期", fontsize=11)
ax2.set_ylim(0, nav["持仓数"].max() + 2)

for ax in [ax1, ax2]:
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)

ax1.set_title("策略权益曲线 (NAV)", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(PROJ_DIR + "/output/figures/equity_curve.png", dpi=150, bbox_inches="tight")
plt.close()
print("  ✅ equity_curve.png")

# ============ 图2-4: 样本交易 ============
SAMPLES = {"ARB": "最赚钱 (+$7,505)", "MSTR": "币股代表 (+$190)", "OP": "亏钱代表 (-$37K)"}

def load_close_price(name):
    """加载真实的收盘价数据"""
    for base_dir in ["crypto_spot", "tradfi_perp"]:
        path = f"{PROJ_DIR}/data/raw/{base_dir}/1d/{name}.parquet"
        if os.path.exists(path):
            p = pd.read_parquet(path)
            p["timestamp"] = pd.to_datetime(p["timestamp"])
            p = p.set_index("timestamp")
            # 统一日期（去掉时间部分）
            p.index = p.index.normalize()
            return p["close"]
    return None

for name, subtitle in SAMPLES.items():
    print(f"绘制: {name} ({subtitle})...")

    close_prices = load_close_price(name)
    if close_prices is None:
        print(f"  ⚠️ 无价格数据，跳过")
        continue

    sig = pd.read_parquet(f"{PROJ_DIR}/data/interim/signals/{name}_signals.parquet")
    trades_asset = trades[trades["资产"] == name].sort_values("开仓日")

    if len(trades_asset) < 5:
        sample_trades = trades_asset
    else:
        sample_trades = trades_asset.head(6)

    start_date = sample_trades["开仓日"].min() - pd.Timedelta(days=5)
    end_date = sample_trades["平仓日"].max() + pd.Timedelta(days=5)

    # 对齐三个数据源
    all_dates = sig.index.intersection(close_prices.index).intersection(returns.index)
    all_dates = all_dates[(all_dates >= start_date) & (all_dates <= end_date)]

    if len(all_dates) == 0:
        print(f"  ⚠️ 无对齐日期，跳过")
        continue

    plot_sig = sig.loc[all_dates]
    plot_price = close_prices.loc[all_dates]
    plot_ret = returns.loc[all_dates, name]

    # 过滤样本交易到可视范围内
    sample_trades = sample_trades[
        (sample_trades["开仓日"].isin(all_dates)) | (sample_trades["平仓日"].isin(all_dates))
    ]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7), sharex=True,
                                     gridspec_kw={"height_ratios": [2, 1]})

    # === 上图：收盘价日线 + 开平仓标记 ===
    ax1.plot(all_dates, plot_price.values, color="#333333", lw=1.0, label="收盘价")

    # 标记每笔交易
    for _, t in sample_trades.iterrows():
        entry = t["开仓日"]
        exit_d = t["平仓日"]
        direction = t["方向"]
        pnl = t["毛PnL"]

        color = "#F44336" if direction == "做空" else "#4CAF50"
        marker = "v" if direction == "做空" else "^"
        label = "做空" if direction == "做空" else "做多"

        # 开仓标记
        if entry in all_dates:
            price_at_entry = plot_price.loc[entry]
            ax1.scatter(entry, price_at_entry, color=color, marker=marker,
                       s=120, zorder=6, edgecolors="black", linewidths=0.8)
            ax1.annotate(f"开{label}", xy=(entry, price_at_entry),
                        xytext=(0, 18 if direction=="做空" else -18),
                        textcoords="offset points", fontsize=8,
                        ha="center", color=color, fontweight="bold",
                        arrowprops=dict(arrowstyle="->", color=color, lw=0.8))

        # 平仓标记
        if exit_d in all_dates:
            price_at_exit = plot_price.loc[exit_d]
            ax1.scatter(exit_d, price_at_exit, color=color, marker="o",
                       s=100, zorder=6, edgecolors="black", linewidths=0.8,
                       facecolors="white")
            pnl_label = f"+${pnl:.0f}" if pnl > 0 else f"-${abs(pnl):.0f}"
            ax1.annotate(pnl_label, xy=(exit_d, price_at_exit),
                        xytext=(8, 12 if pnl > 0 else -12),
                        textcoords="offset points", fontsize=8,
                        color="#4CAF50" if pnl > 0 else "#F44336",
                        fontweight="bold")

    # 画连接线连接开仓到平仓
    for _, t in sample_trades.iterrows():
        entry, exit_d = t["开仓日"], t["平仓日"]
        if entry in all_dates and exit_d in all_dates:
            color = "#F44336" if t["方向"] == "做空" else "#4CAF50"
            ax1.axvspan(entry, exit_d, alpha=0.06, color=color)

    ax1.set_ylabel("收盘价", fontsize=11)
    ax1.set_title(f"{name} — {subtitle} (▼=做空, ▲=做多, ○=平仓)", fontsize=13, fontweight="bold")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.3)

    # 格式化y轴价格
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:.2f}" if x < 100 else f"${x:.0f}"))

    # === 下图：z-score ===
    ax2.plot(all_dates, plot_sig["zscore"].values, color="#FF9800", lw=0.8, label="z-score")
    ax2.axhline(2.0, color="red", ls="--", lw=0.8, alpha=0.4, label="+2σ (做空)")
    ax2.axhline(-2.0, color="green", ls="--", lw=0.8, alpha=0.4, label="-2σ (做多)")
    ax2.axhline(0.5, color="orange", ls=":", lw=0.6, alpha=0.3)
    ax2.axhline(-0.5, color="orange", ls=":", lw=0.6, alpha=0.3)
    ax2.axhline(0, color="gray", ls="-", lw=0.5, alpha=0.3)
    ax2.fill_between(all_dates, 2, plot_sig["zscore"].clip(upper=10),
                      color="red", alpha=0.06)
    ax2.fill_between(all_dates, -2, plot_sig["zscore"].clip(lower=-10),
                      color="green", alpha=0.06)

    # z-score上也标记开平仓
    for _, t in sample_trades.iterrows():
        entry, exit_d = t["开仓日"], t["平仓日"]
        direction = t["方向"]
        color = "#F44336" if direction == "做空" else "#4CAF50"

        if entry in all_dates:
            ax2.scatter(entry, plot_sig.loc[entry, "zscore"],
                       color=color, marker="v" if direction=="做空" else "^",
                       s=60, zorder=5, edgecolors="black", linewidths=0.5)
        if exit_d in all_dates and exit_d in plot_sig.index:
            ax2.scatter(exit_d, plot_sig.loc[exit_d, "zscore"],
                       color=color, marker="o", s=50, zorder=5,
                       edgecolors="black", linewidths=0.5, facecolors="white")

    ax2.set_ylabel("z-score", fontsize=11)
    ax2.set_xlabel("日期", fontsize=11)
    ax2.set_ylim(-4, 4.5)
    ax2.legend(loc="upper left", ncol=5, fontsize=7)
    ax2.grid(alpha=0.3)

    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=8)

    plt.tight_layout()
    plt.savefig(f"{PROJ_DIR}/output/figures/sample_{name}.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✅ sample_{name}.png")

# ============ 统计汇总图 ============
print("绘制: 交易统计汇总...")
fig, axes = plt.subplots(2, 2, figsize=(12, 8))

asset_pnl = trades.groupby("资产")["净PnL"].sum().sort_values()
colors = ["#4CAF50" if v > 0 else "#F44336" for v in asset_pnl.values]
asset_pnl.plot(kind="barh", ax=axes[0,0], color=colors, width=0.7)
axes[0,0].axvline(0, color="gray", lw=0.5)
axes[0,0].set_title("各资产净PnL", fontsize=11)
axes[0,0].set_xlabel("净PnL ($)")

held = trades["持有天数"].clip(0, 15).value_counts().sort_index()
held.plot(kind="bar", ax=axes[0,1], color="#2196F3", width=0.6)
axes[0,1].set_title("持有天数分布", fontsize=11)
axes[0,1].set_xlabel("天数")
axes[0,1].set_ylabel("笔数")

nav["月"] = pd.to_datetime(nav["日期"]).dt.to_period("M")
monthly = nav.groupby("月")["毛PnL"].sum()
mcolors = ["#4CAF50" if v > 0 else "#F44336" for v in monthly.values]
monthly.plot(kind="bar", ax=axes[1,0], color=mcolors, width=0.7)
axes[1,0].set_title("月度毛PnL", fontsize=11)
axes[1,0].set_ylabel("$")
axes[1,0].tick_params(axis="x", rotation=45, labelsize=6)

win = trades.groupby("持有天数").agg(胜率=("毛PnL", lambda x: (x>0).sum()/len(x))).loc[:10]
win.plot(kind="line", marker="o", ax=axes[1,1], color="#FF5722", lw=1.5)
axes[1,1].axhline(0.5, color="gray", ls="--", lw=0.5)
axes[1,1].set_title("胜率 vs 持有天数", fontsize=11)
axes[1,1].set_xlabel("天数")
axes[1,1].set_ylabel("胜率")
axes[1,1].set_ylim(0, 1)
axes[1,1].grid(alpha=0.3)

plt.tight_layout()
plt.savefig(PROJ_DIR + "/output/figures/trade_statistics.png", dpi=150, bbox_inches="tight")
plt.close()
print("  ✅ trade_statistics.png")

print("\n" + "=" * 60)
print("可视化完成")
print("=" * 60)
print("  equity_curve.png     — 权益曲线")
print("  sample_ARB.png       — ARB收盘价+开平仓")
print("  sample_MSTR.png      — MSTR收盘价+开平仓")
print("  sample_OP.png        — OP收盘价+开平仓")
print("  trade_statistics.png — 交易统计")
print("=" * 60)
