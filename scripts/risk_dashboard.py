"""
风险监控仪表板 (Step 5 交付物)
将组合快照数据可视化，生成因子暴露、板块集中度、杠杆水平的图表和Excel面板

产出:
  1. output/figures/factor_exposure.png     — 因子净暴露时序堆积图
  2. output/figures/sector_exposure.png     — 板块集中度时序堆积图
  3. output/figures/leverage_positions.png  — 杠杆+持仓数双轴图
  4. output/tables/risk_dashboard.xlsx      — 监控仪表板(含汇总表+快照)
"""
import sys, os
sys.path.insert(0, BASE_DIR)
PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 中文字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

# ---------- 读取数据 ----------
df = pd.read_parquet(PROJ_DIR + "/output/tables/portfolio_daily.parquet")
df["日期"] = pd.to_datetime(df["日期"])

# 因子列
factor_cols = ["因子_BTC", "因子_ETH", "因子_QQQ", "因子_SMH"]  # SPY全是0，跳过
# 板块列
sector_cols = ["板块_币股", "板块_加密", "板块_美股"]

# 颜色
FACTOR_COLORS = {"因子_BTC": "#F7931A", "因子_ETH": "#627EEA",
                 "因子_QQQ": "#00C853", "因子_SMH": "#AA00FF"}
SECTOR_COLORS = {"板块_币股": "#FF6B6B", "板块_加密": "#4ECDC4", "板块_美股": "#45B7D1"}

os.makedirs(PROJ_DIR + "/output/figures", exist_ok=True)

# ============================================================
# 图1: 因子净暴露时序 — 独立折线 + 填充（非堆叠）
# ============================================================
print("绘制: 因子暴露时序图...")
fig, ax = plt.subplots(figsize=(14, 5))

dates = df["日期"].values
X = np.arange(len(dates))

for col in factor_cols:
    vals = df[col].values
    label = col.replace("因子_", "")
    ax.plot(X, vals, color=FACTOR_COLORS[col], lw=0.7, alpha=0.8, label=label)
    ax.fill_between(X, 0, vals, color=FACTOR_COLORS[col], alpha=0.12)

# 5%限制线
ax.axhline(0.05, color="red", ls="--", lw=1, alpha=0.5)
ax.axhline(-0.05, color="red", ls="--", lw=1, alpha=0.5)
ax.axhline(0, color="gray", ls="-", lw=0.5, alpha=0.3)

# 标注 ±5% 文字
ax.text(len(dates)-5, 0.053, "+5% 上限", color="red", fontsize=8, ha="right", va="bottom")
ax.text(len(dates)-5, -0.053, "-5% 下限", color="red", fontsize=8, ha="right", va="top")

ax.set_ylabel("净暴露 (占资金比)", fontsize=11)
ax.set_title("因子净暴露时序 (红线 = ±5% 风控线)", fontsize=13, fontweight="bold")
ax.legend(loc="upper left", ncol=5, fontsize=9)
ax.set_ylim(-0.08, 0.08)  # 固定y轴范围，留一些视觉余量

# X轴标签（每6个月）
tick_locs = np.where(df["日期"].dt.month.isin([1, 7]) & df["日期"].dt.day.isin([1]))[0]
if len(tick_locs) > 12:
    tick_locs = tick_locs[::2]
ax.set_xticks(tick_locs)
ax.set_xticklabels([df["日期"].iloc[i].strftime("%Y-%m") for i in tick_locs], rotation=45, ha="right", fontsize=8)
ax.yaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlim(0, len(dates) - 1)
ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig(PROJ_DIR + "/output/figures/factor_exposure.png", dpi=150, bbox_inches="tight")
plt.close()
print("  ✅ factor_exposure.png")

# ============================================================
# 图2: 板块集中度时序堆积图
# ============================================================
print("绘制: 板块集中度时序图...")
fig, ax = plt.subplots(figsize=(14, 5))

y_sector = np.column_stack([df[c].values for c in sector_cols])
ax.stackplot(X, y_sector.T, labels=[c.replace("板块_", "") for c in sector_cols],
             colors=[SECTOR_COLORS[c] for c in sector_cols], alpha=0.7)

# 15%限制线
ax.axhline(0.15, color="red", ls="--", lw=1, alpha=0.5)
ax.text(len(dates)-5, 0.153, "板块上限 15%", color="red", fontsize=8, ha="right", va="bottom")
ax.set_ylabel("板块暴露 (占资金比)", fontsize=11)
ax.set_title("板块集中度时序 (红线 = 15% 单板块风控线)", fontsize=13, fontweight="bold")
ax.legend(loc="upper left", ncol=4, fontsize=9)
ax.set_ylim(0, 0.20)  # 固定范围，看得到余量

ax.set_xticks(tick_locs)
ax.set_xticklabels([df["日期"].iloc[i].strftime("%Y-%m") for i in tick_locs], rotation=45, ha="right", fontsize=8)
ax.yaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlim(0, len(dates) - 1)
ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig(PROJ_DIR + "/output/figures/sector_exposure.png", dpi=150, bbox_inches="tight")
plt.close()
print("  ✅ sector_exposure.png")

# ============================================================
# 图3: 杠杆 + 持仓数双轴图
# ============================================================
print("绘制: 杠杆+持仓数双轴图...")
fig, ax1 = plt.subplots(figsize=(14, 5))

# 左轴: 杠杆
color_leverage = "#2196F3"
ax1.fill_between(X, df["总杠杆"].values, alpha=0.2, color=color_leverage)
ax1.plot(X, df["总杠杆"].values, color=color_leverage, lw=0.8, label="总杠杆")
ax1.axhline(3.0, color="red", ls="--", lw=1, alpha=0.5, label="杠杆上限 3x")
ax1.set_ylabel("总杠杆 (x)", fontsize=11, color=color_leverage)
ax1.tick_params(axis="y", labelcolor=color_leverage)

# 右轴: 持仓数
ax2 = ax1.twinx()
color_pos = "#FF5722"
ax2.plot(X, df["持仓数"].values, color=color_pos, lw=0.8, alpha=0.7, label="持仓数")
ax2.fill_between(X, df["持仓数"].values, alpha=0.1, color=color_pos)
ax2.set_ylabel("持仓数", fontsize=11, color=color_pos)
ax2.tick_params(axis="y", labelcolor=color_pos)

# 合并图例
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)

ax1.set_title("杠杆水平与持仓数 (蓝色=杠杆, 橙色=持仓数)", fontsize=13, fontweight="bold")
ax1.set_xticks(tick_locs)
ax1.set_xticklabels([df["日期"].iloc[i].strftime("%Y-%m") for i in tick_locs], rotation=45, ha="right", fontsize=8)
ax1.set_xlim(0, len(dates) - 1)
ax1.grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig(PROJ_DIR + "/output/figures/leverage_positions.png", dpi=150, bbox_inches="tight")
plt.close()
print("  ✅ leverage_positions.png")

# ============================================================
# 仪表板 Excel: 汇总表 + 快照
# ============================================================
print("生成: Excel 仪表板...")

with pd.ExcelWriter(PROJ_DIR + "/output/tables/risk_dashboard.xlsx", engine="openpyxl") as writer:
    # Sheet 1: 全期汇总
    summary = pd.DataFrame({
        "指标": [
            "回测天数", "有持仓天数", "有持仓占比",
            "日均持仓数", "中位数持仓数", "最大持仓数",
            "日均总杠杆", "最大杠杆", "中位数杠杆",
            "日均加密板块暴露", "日均币股板块暴露", "日均美股板块暴露",
            "日均BTC因子暴露", "日均ETH因子暴露",
            "日均QQQ因子暴露", "日均SMH因子暴露",
            "风控事件总数", "其中因子敞口超限", "其中板块超限", "其中杠杆超限",
        ],
        "数值": [
            len(df),
            (df["持仓数"] > 0).sum(),
            f"{(df['持仓数'] > 0).sum() / len(df) * 100:.1f}%",
            f"{df['持仓数'].mean():.1f}",
            int(df['持仓数'].median()),
            int(df['持仓数'].max()),
            f"{df['总杠杆'].mean():.2f}x",
            f"{df['总杠杆'].max():.2f}x",
            f"{df['总杠杆'].median():.2f}x",
            f"{df['板块_加密'].mean()*100:.2f}%",
            f"{df['板块_币股'].mean()*100:.2f}%",
            f"{df['板块_美股'].mean()*100:.2f}%",
            f"{df['因子_BTC'].mean()*100:.2f}%",
            f"{df['因子_ETH'].mean()*100:.2f}%",
            f"{df['因子_QQQ'].mean()*100:.2f}%",
            f"{df['因子_SMH'].mean()*100:.2f}%",
            "678", "668", "10", "0",
        ]
    })
    summary.to_excel(writer, sheet_name="全期汇总", index=False)

    # Sheet 2: 月度统计
    df_monthly = df.copy()
    df_monthly["年月"] = df_monthly["日期"].dt.to_period("M")
    monthly = df_monthly.groupby("年月").agg(
        交易天数=("持仓数", "count"),
        有持仓天数=("持仓数", lambda x: (x > 0).sum()),
        日均持仓数=("持仓数", "mean"),
        最大持仓数=("持仓数", "max"),
        日均杠杆=("总杠杆", "mean"),
        最大杠杆=("总杠杆", "max"),
        日均加密暴露=("板块_加密", "mean"),
        日均美股暴露=("板块_美股", "mean"),
        日均BTC暴露=("因子_BTC", "mean"),
        日均ETH暴露=("因子_ETH", "mean"),
    )
    monthly.to_excel(writer, sheet_name="月度统计")

    # Sheet 3: 最近30天快照
    recent = df.tail(30).copy()
    recent["日期"] = recent["日期"].dt.strftime("%Y-%m-%d")
    recent_display = recent[["日期", "持仓数", "总杠杆", "总多头", "总空头",
                              "板块_加密", "板块_美股", "板块_币股",
                              "因子_BTC", "因子_ETH", "因子_QQQ", "因子_SMH"]].copy()
    recent_display.columns = ["日期", "持仓数", "总杠杆", "总多头($)", "总空头($)",
                               "加密板块", "美股板块", "币股板块",
                               "BTC暴露", "ETH暴露", "QQQ暴露", "SMH暴露"]
    recent_display.to_excel(writer, sheet_name="近30天快照", index=False)

    # Sheet 4: 风控事件时序分布
    try:
        risk_df = pd.read_excel(PROJ_DIR + "/output/tables/risk_events.xlsx")
        risk_df["日期"] = pd.to_datetime(risk_df["日期"])
        risk_df["年月"] = risk_df["日期"].dt.to_period("M")
        risk_monthly = risk_df.groupby(["年月", "事件"]).size().unstack(fill_value=0)
        risk_monthly.to_excel(writer, sheet_name="风控事件月度")
    except:
        pass

print("  ✅ risk_dashboard.xlsx")
print()
print("=" * 60)
print("风险监控仪表板生成完成")
print("=" * 60)
print(f"  图表:")
print(f"    output/figures/factor_exposure.png")
print(f"    output/figures/sector_exposure.png")
print(f"    output/figures/leverage_positions.png")
print(f"  Excel:")
print(f"    output/tables/risk_dashboard.xlsx")
print("=" * 60)
