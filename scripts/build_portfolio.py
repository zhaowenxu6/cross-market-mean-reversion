"""
组合构建与风险管理 (Step 5)
将信号转为多腿对冲组合 + 实时风控

产出:
  1. output/tables/portfolio_daily.parquet — 每日持仓与风控快照
  2. output/tables/risk_events.xlsx — 风控事件日志
"""
import sys, os, importlib.util
sys.path.insert(0, BASE_DIR)
PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------- 导入 ----------
spec = importlib.util.spec_from_file_location("universe", PROJ_DIR + "/config/universe.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TARGET_ASSETS = mod.COIN_STOCKS + mod.CRYPTO_ASSETS + mod.US_TECH_PERPS
FACTOR_NAMES = [f["name"] for f in mod.BENCHMARK_FACTORS]

returns = pd.read_parquet(PROJ_DIR + "/data/interim/returns_clean.parquet")
returns = returns[returns.index >= "2023-01-01"]
dates_all = returns.index

# ---------- 配置 ----------
TOTAL_CAPITAL = 1_000_000      # 总资金 $1M
TARGET_VOL = 0.05              # 单配对目标波动率 5%
BETA_WINDOW = 90               # β滚动窗口
VOL_WINDOW = 60                # 波动率窗口
ENTRY_Z = 2.0
EXIT_Z = 0.5

# 风控约束
MAX_SINGLE = 0.03              # 单资产 ≤ 3%
MAX_SECTOR = 0.15              # 同板块 ≤ 15%
MAX_LEVERAGE = 3.0             # 杠杆 ≤ 3x
MAX_FACTOR_EXPOSURE = 0.05     # 单因子净敞口 ≤ 5%

# ---------- 辅助函数 ----------
def get_sector(asset_name):
    """获取资产所属板块"""
    for a in mod.ALL_ASSETS:
        if a["name"] == asset_name:
            if a["type"] == "crypto_spot":
                return "加密"
            cat = a.get("category", "")
            if "币股" in cat:
                return "币股"
            elif "美股" in cat:
                return "美股"
            return "其他"
    return "其他"

def get_factors(asset_name):
    for a in TARGET_ASSETS:
        if a["name"] == asset_name:
            return a["factors"]
    return []

# ---------- 预计算所有资产的每日β和波动率 ----------
print("预计算每日β与波动率（使用Ridge alpha=0.01，快速模式）...")
asset_betas = {}
asset_vols = {}

for asset in TARGET_ASSETS:
    name = asset["name"]
    factors = asset["factors"]
    print(f"  {name} ...", end=" ", flush=True)
    combined = pd.concat([returns[name], returns[factors]], axis=1).dropna()
    y = combined[name].values
    X = combined[factors].values
    n = len(y)

    betas = {f: np.full(n, np.nan) for f in factors}
    pair_vol = np.full(n, np.nan)

    model = Ridge(alpha=0.01, fit_intercept=True)
    for t in range(BETA_WINDOW, n):
        try:
            model.fit(X[t-BETA_WINDOW:t], y[t-BETA_WINDOW:t])
            for j, f in enumerate(factors):
                betas[f][t] = model.coef_[j]
        except:
            pass

        if t >= VOL_WINDOW:
            pair_vol[t] = np.std(y[t-VOL_WINDOW:t]) * np.sqrt(252)  # 年化波动率

    asset_betas[name] = {f: betas[f] for f in factors}
    asset_vols[name] = pair_vol
    print(f"✓ ({n} 天)")

# ---------- 读取信号 ----------
print("读取信号...")
asset_signals = {}
for asset in TARGET_ASSETS:
    name = asset["name"]
    try:
        sig = pd.read_parquet(f"{PROJ_DIR}/data/interim/signals/{name}_signals.parquet")
        asset_signals[name] = sig
    except:
        pass

# ---------- 逐日模拟持仓 ----------
print("逐日模拟持仓...")

# 对齐所有资产到同一日期网格
all_dates = returns.index
date_idx = {d: i for i, d in enumerate(all_dates)}

risk_events = []
daily_snapshots = []

for di, today in enumerate(all_dates):
    if di < BETA_WINDOW + 60:
        continue
    if di % 100 == 0:
        print(f"  {today.date()} ({di}/{len(all_dates)})")

    positions = {}       # name -> {"direction": 1/-1, "notional": $, "hedge_legs": {factor: $}}
    total_long = 0.0
    total_short = 0.0
    sector_exposure = {}
    factor_net = {f: 0.0 for f in FACTOR_NAMES}

    # 遍历所有资产，检查是否有信号
    for asset in TARGET_ASSETS:
        name = asset["name"]
        factors = get_factors(name)
        sector = get_sector(name)

        # 获取当日信号
        sig = asset_signals.get(name)
        if sig is None:
            continue
        today_str = str(today.date())
        if today_str not in sig.index:
            continue

        row = sig.loc[today_str]
        signal = row["signal"]
        if signal == 0:
            continue

        # 找到该资产在returns中的索引
        combined = pd.concat([returns[name], returns[factors]], axis=1).dropna()
        combined_dates = combined.index
        if today not in combined_dates:
            continue
        t_idx = combined_dates.get_loc(today)
        if isinstance(t_idx, slice):
            continue

        # β
        current_betas = {}
        for f in factors:
            b = asset_betas[name][f]
            if t_idx < len(b) and not np.isnan(b[t_idx]):
                current_betas[f] = b[t_idx]
        if not current_betas:
            continue

        # 波动率（年化）
        vol = asset_vols[name][t_idx] if t_idx < len(asset_vols[name]) else 0.2
        if np.isnan(vol) or vol < 0.001:
            vol = 0.2

        # 头寸规模: N = (σ_target / σ_pair) × TOTAL_CAPITAL
        # σ_target=1%(年化), σ_pair=年化波动率(如MSTR≈60%)
        # MSTR例: N = 1%/60% × $1M = $16,667
        N = (TARGET_VOL / vol) * TOTAL_CAPITAL
        N = min(N, TOTAL_CAPITAL * MAX_SINGLE)  # 上限3%=$30K
        N = min(N, TOTAL_CAPITAL * MAX_SINGLE)

        # 主腿方向
        notional = N * signal  # 做多=+N, 做空=-N

        # 对冲腿: 抵消主腿的因子暴露
        # 主腿对因子f的暴露 = b × notional
        # 对冲腿 = -b × notional
        hedge_legs = {}
        for f, b in current_betas.items():
            hedge_notional = -b * notional
            hedge_legs[f] = hedge_notional
            factor_net[f] += hedge_notional

        # ===== 风控检查 =====
        # 1. 单资产限额
        if abs(notional) > TOTAL_CAPITAL * MAX_SINGLE:
            continue

        # 2. 板块集中度
        current_sector = sector_exposure.get(sector, 0) + abs(notional)
        if current_sector > TOTAL_CAPITAL * MAX_SECTOR:
            risk_events.append({
                "日期": today, "资产": name, "事件": "板块超限",
                "板块": sector, "超限因子": "",
                "当前暴露": current_sector,
                "限制": f"板块 ≤ ${TOTAL_CAPITAL*MAX_SECTOR:,.0f} ({MAX_SECTOR:.0%})"
            })
            continue

        # 3. 杠杆检查
        projected_long = total_long + max(0, notional) + sum(max(0, v) for v in hedge_legs.values())
        projected_short = total_short + max(0, -notional) + sum(max(0, -v) for v in hedge_legs.values())
        projected_gross = projected_long + projected_short
        if projected_gross > TOTAL_CAPITAL * MAX_LEVERAGE:
            risk_events.append({
                "日期": today, "资产": name, "事件": "杠杆超限",
                "板块": sector, "超限因子": "",
                "当前暴露": f"{projected_gross/TOTAL_CAPITAL:.1f}x",
                "限制": f"≤ {MAX_LEVERAGE}x"
            })
            continue

        # 4. 因子暴露
        exceeded_factors = [f for f, v in factor_net.items() if abs(v) > TOTAL_CAPITAL * MAX_FACTOR_EXPOSURE]
        if exceeded_factors:
            # 记录超限因子详情及当前暴露
            exceeded_detail = "; ".join(
                f"{f}={factor_net[f]:,.0f} ({factor_net[f]/TOTAL_CAPITAL:.1%})"
                for f in exceeded_factors
            )
            max_exposure = max(abs(factor_net[f]) for f in exceeded_factors)
            risk_events.append({
                "日期": today, "资产": name, "事件": "因子敞口超限",
                "板块": sector, "超限因子": exceeded_detail,
                "当前暴露": round(max_exposure),
                "限制": f"单因子 ≤ ${TOTAL_CAPITAL*MAX_FACTOR_EXPOSURE:,.0f} ({MAX_FACTOR_EXPOSURE:.0%})"
            })
            continue

        # ===== 执行开仓 =====
        positions[name] = {
            "方向": signal,
            "名义本金": notional,
            "对冲腿": hedge_legs,
            "β值": current_betas,
            "波动率": vol,
            "板块": sector,
        }

        total_long += max(0, notional) + sum(max(0, v) for v in hedge_legs.values())
        total_short += max(0, -notional) + sum(max(0, -v) for v in hedge_legs.values())
        sector_exposure[sector] = sector_exposure.get(sector, 0) + abs(notional)

    # ===== 每日快照 =====
    total_gross = total_long + total_short
    snapshot = {
        "日期": today,
        "持仓数": len(positions),
        "总多头": round(total_long),
        "总空头": round(total_short),
        "总杠杆": round(total_gross / TOTAL_CAPITAL, 2),
    }
    # 板块暴露
    for s in ["币股", "加密", "美股", "其他"]:
        snapshot[f"板块_{s}"] = round(sector_exposure.get(s, 0) / TOTAL_CAPITAL, 4)
    # 因子暴露
    for f in FACTOR_NAMES:
        snapshot[f"因子_{f}"] = round(factor_net.get(f, 0) / TOTAL_CAPITAL, 4)
    daily_snapshots.append(snapshot)

# ===== 输出 =====
os.makedirs(PROJ_DIR + "/output/tables", exist_ok=True)

# 每日快照
df_snap = pd.DataFrame(daily_snapshots)
df_snap.to_parquet(PROJ_DIR + "/output/tables/portfolio_daily.parquet")
print(f"\n✅ 已生成: output/tables/portfolio_daily.parquet ({len(df_snap)} 天)")

# 风控事件
df_risk = pd.DataFrame(risk_events)
if len(df_risk) > 0:
    df_risk.to_excel(PROJ_DIR + "/output/tables/risk_events.xlsx", index=False)
    print(f"✅ 已生成: output/tables/risk_events.xlsx ({len(df_risk)} 条事件)")

# ===== 汇总统计 =====
print()
print("=" * 60)
print("组合构建统计")
print("=" * 60)
print(f"  日均持仓数: {df_snap['持仓数'].mean():.1f}")
print(f"  日均总杠杆: {df_snap['总杠杆'].mean():.2f}x")
print(f"  最大杠杆:   {df_snap['总杠杆'].max():.2f}x")
print(f"  风控事件:   {len(df_risk)} 条")
print(f"  回测天数:   {len(df_snap)} 天")
