"""
Step 6: 回测引擎与成本建模
============================
读取信号和因子模型输出，模拟持仓生命周期并计算带成本的PnL

回测严谨性声明 (Backtest Rigor Declaration):
  1. 前视偏差 (Look-ahead Bias)    ✅ 已避免
     - β估计: Ridge.fit(X[t-90:t]) 仅使用 t-90 到 t-1 的历史数据
     - z-score: 30天滚动窗口估计 μ,σ，仅用当日之前数据
     - 组合构建: 逐日读取当日信号，仅使用当日可行的β和波动率
     - **PnL时机: 开仓当天不计PnL，从第二天开始计算（避免信号日收益率被重复计入）**
     - 平仓条件: 基于当日收盘后的z-score判断，无未来信息
  2. 幸存者偏差 (Survivorship Bias) ✅ 已避免
     - 25个目标资产在 2023-2026 回测期内均在 Binance 持续上线
     - ARB 于 2023年3月上线Binance Perp，数据从上线日开始
     - 未人为剔除表现差的标的，保留全样本
  3. 时间对齐 (Time Alignment)      ⚠️ 已处理，存在已知局限
     - 加密资产: 24/7 交易，包含周末数据 (1275天)
     - 美股 Perp: 仅交易日 (873天)
     - β估计时对齐方式: pd.concat + dropna() 自动对齐共同交易日
     - 已知局限: 周一美股收益率覆盖 周五→周一，BTC覆盖 周日→周一
     - 影响: 日频级别可接受；更高精度需小时频数据（加分项）
  4. 加分项 (未实现，列为改进方向)
     - 极端事件模拟: 标记 2023-03 SVB / 2024-08 carry trade 期间
     - 流动性冲击: 极端行情下放大滑点 3-5 倍
     - 交易延迟: 信号到执行增加 1-2 tick 时延

成本假设 (Cost Assumptions):
  手续费 (taker):
    - 加密现货: 0.10%  (Binance 标准费率)
    - 永续合约: 0.04%  (Binance 标准费率)
  滑点:
    - 主流币 (BTC/ETH):    0.03%
    - 山寨币:              0.05%
    - 美股科技 (NVDA/TSLA等): 0.02%
    - 币股 (MSTR/COIN等):    0.15%
  资金费率:
    - Binance 真实历史数据（8h结算，每日3次之和）
    - 缺失的币股用BTC代理，SMH用QQQ代理
  借券成本 (做空美股):
    - 年化 2.0% (按日折算)
  保证金机会成本:
    - 年化 4.0% × 占用名义本金 / 365（无风险利率估计）
  极端事件滑点放大:
    - 2023-03-08~03-15: SVB危机           → 滑点×3
    - 2023-06-05~06-10: SEC起诉Binance    → 滑点×3
    - 2024-01-10~01-12: BTC ETF获批暴涨   → 滑点×3
    - 2024-08-05~08-10: 日元套利平仓      → 滑点×3
  未使用:
    - 交易延迟 (列为改进方向)

产出:
  1. output/tables/nav_curve.parquet   — 净值曲线(含毛/净PnL)
  2. output/tables/trade_log.xlsx       — 每笔交易明细
  3. output/tables/cost_breakdown.xlsx  — 成本分类汇总
  4. output/docs/cost_modeling.md       — 成本建模文档(单独文件)

运行方式:
  直接修改 TOTAL_CAPITAL 的值:
    TOTAL_CAPITAL = 10_000_000   # $10M容量测试
    TOTAL_CAPITAL = 50_000_000   # $50M容量测试
"""
# ---------- 导入 ----------
import sys, os
PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ_DIR)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

# ========== 策略参数调优（改这里） ==========
ENTRY_Z = 2.0       # 入场阈值 (默认2.0)
EXIT_Z = 0.5        # 平仓阈值 (默认0.5)
STOP_Z = 3.0        # 止损阈值 (默认4.0)
CONFIRM_DAYS = 1   # 信号确认天数 (1=当日触发即入场, 2=连续触发2天才入场)
# =============================================

# ========== 资金规模配置（调试用） ==========
TOTAL_CAPITAL = 10_000_000   # 1M/10M/50M/100M
ENABLE_FACTOR_LIMIT = True  # 因子净暴露5%限制
# ============================================
print(f"策略参数: 入场={ENTRY_Z}σ  平仓={EXIT_Z}σ  止损={STOP_Z}σ  确认={CONFIRM_DAYS}天")
print(f"资金规模: \${TOTAL_CAPITAL:,d}  因子限制: {'开启' if ENABLE_FACTOR_LIMIT else '关闭'}")

# ---------- 导入标的池 ----------
spec = __import__("importlib").util.spec_from_file_location(
    "universe", PROJ_DIR + "/config/universe.py")
mod = __import__("importlib").util.module_from_spec(spec)
spec.loader.exec_module(mod)

TARGET_ASSETS = mod.COIN_STOCKS + mod.CRYPTO_ASSETS + mod.US_TECH_PERPS
FACTOR_NAMES = [f["name"] for f in mod.BENCHMARK_FACTORS]

returns = pd.read_parquet(PROJ_DIR + "/data/interim/returns_clean.parquet")
returns = returns[returns.index >= "2023-01-01"]

# ========== 配置 ==========
TARGET_VOL = 0.05
BETA_WINDOW = 90
VOL_WINDOW = 60
MAX_SINGLE = 0.03
MAX_SECTOR = 0.15
MAX_LEVERAGE = 3.0
MAX_FACTOR_EXPOSURE = 0.05
MARGIN_COST_ANNUAL = 0.04  # 保证金机会成本 4% 年化

# 极端事件列表 (期间滑点放大3倍)
STRESS_EVENTS = [
    ("2023-03-08", "2023-03-15", "SVB危机"),
    ("2023-06-05", "2023-06-10", "SEC起诉Binance/Coinbase"),
    ("2024-01-10", "2024-01-12", "BTC ETF获批暴涨"),
    ("2024-08-05", "2024-08-10", "日元套利平仓"),
]

# 成本参数
COST = {
    "commission": {"crypto_spot": 0.0010, "tradfi_perp": 0.0004},
    "slippage": {"crypto_spot_major": 0.0003, "crypto_spot": 0.0005,
                 "tradfi_perp_us": 0.0002, "tradfi_perp_coin": 0.0015},  # 0.15%
    "borrow_annual": 0.02,      # 2% 年化
    "stress_multiplier": 3.0,   # 极端事件滑点倍数
}

# 加载真实资金费率数据
print("加载真实资金费率...")
funding_rates = pd.read_parquet(PROJ_DIR + "/data/external/funding_rates.parquet")
# 缺失的币股用BTC代理，SMH用QQQ代理
for col in ["CLSK", "MARA", "RIOT"]:
    if col not in funding_rates.columns or funding_rates[col].isna().all():
        funding_rates[col] = funding_rates.get("BTC", 0.0)
if "SMH" not in funding_rates.columns or funding_rates["SMH"].isna().all():
    funding_rates["SMH"] = funding_rates.get("QQQ", 0.0)
funding_rates = funding_rates.fillna(0.0)  # 仍有缺失的填0

# ========== 辅助函数 ==========
def get_asset_info(name):
    for a in mod.ALL_ASSETS:
        if a["name"] == name:
            return a
    return None

def get_factors(name):
    for a in TARGET_ASSETS:
        if a["name"] == name:
            return a["factors"]
    return []

def get_sector(name):
    for a in mod.ALL_ASSETS:
        if a["name"] == name:
            if a["type"] == "crypto_spot":
                return "加密"
            cat = a.get("category", "")
            if "币股" in cat:
                return "币股"
            elif "美股" in cat:
                return "美股"
            return "其他"
    return "其他"

def get_cost_rate(name, today=None, is_open=True):
    """返回 (commission_rate, slippage_rate) 的tuple
    today: 用于判断是否在极端事件期间"""
    info = get_asset_info(name)
    if info is None:
        base = (COST["commission"]["tradfi_perp"], COST["slippage"]["tradfi_perp_us"])
        return apply_stress(base, today)

    asset_type = info["type"]
    if asset_type == "crypto_spot":
        if name in ("BTC", "ETH"):
            slip = COST["slippage"]["crypto_spot_major"]
        else:
            slip = COST["slippage"]["crypto_spot"]
        comm = COST["commission"]["crypto_spot"]
    else:
        cat = info.get("category", "")
        if "币股" in cat or name in ("MSTR", "COIN", "MARA", "RIOT", "CLSK"):
            slip = COST["slippage"]["tradfi_perp_coin"]
        else:
            slip = COST["slippage"]["tradfi_perp_us"]
        comm = COST["commission"]["tradfi_perp"]
    return apply_stress((comm, slip), today)

def apply_stress(base_rates, today):
    """极端事件下滑点放大"""
    if today is None:
        return base_rates
    today_str = str(today.date()) if hasattr(today, "date") else str(today)[:10]
    for start_str, end_str, _ in STRESS_EVENTS:
        if start_str <= today_str <= end_str:
            comm, slip = base_rates
            return (comm, slip * COST["stress_multiplier"])
    return base_rates

def is_stress_period(today):
    """判断是否在极端事件期间"""
    if today is None:
        return False
    today_str = str(today.date()) if hasattr(today, "date") else str(today)[:10]
    for start_str, end_str, _ in STRESS_EVENTS:
        if start_str <= today_str <= end_str:
            return True
    return False

# ========== 1. 预计算每日β和波动率 ==========
print("预计算每日β与波动率...")
asset_betas = {}
asset_vols = {}

for asset in TARGET_ASSETS:
    name = asset["name"]
    factors = get_factors(name)
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
            pair_vol[t] = np.std(y[t-VOL_WINDOW:t]) * np.sqrt(252)

    asset_betas[name] = {f: betas[f] for f in factors}
    asset_vols[name] = pair_vol
    print(f"✓ ({n} 天)")

# ========== 2. 读取信号 ==========
print("读取信号...")
asset_signals = {}
for asset in TARGET_ASSETS:
    name = asset["name"]
    try:
        sig = pd.read_parquet(f"{PROJ_DIR}/data/interim/signals/{name}_signals.parquet")
        if "zscore" not in sig.columns:
            sig["zscore"] = 0.0
        asset_signals[name] = sig
    except:
        pass

# ========== 3. 逐日模拟 + PnL计算 ==========
print("逐日回测...")

all_dates = returns.index

trades = []           # 每笔交易记录
nav_daily = []        # 每日净值
active_positions = {} # name -> {entry_date, direction, entry_notional, ...}

# 初始化
pnl_cumulative = 0.0
cost_cumulative = 0.0
entry_cost_cumulative = 0.0
exit_cost_cumulative = 0.0
funding_cumulative = 0.0
borrow_cumulative = 0.0
margin_cumulative = 0.0

for di, today in enumerate(all_dates):
    if di < BETA_WINDOW + 60:
        continue
    if di % 100 == 0:
        print(f"  {today.date()} ({di}/{len(all_dates)})")

    # 当日持仓信息（build_portfolio的简化版）
    current_positions = {}
    total_long = 0.0
    total_short = 0.0
    sector_exposure = {}
    factor_net = {f: 0.0 for f in FACTOR_NAMES}

    # 上次交易日
    prev_date = all_dates[di - 1] if di > 0 else today

    # ---- 先计算当日PnL (在开平仓之前，避免开仓当天计入了触发信号的收益率) ----
    day_pnl = 0.0
    day_funding = 0.0
    day_borrow = 0.0

    for name, pos in list(active_positions.items()):
        if today not in returns.index:
            continue
        r_target = returns.loc[today, name]
        if np.isnan(r_target):
            continue  # 该资产当日无数据（如周末/节假日），跳过当日PnL

        pnl_main = pos["entry_notional"] * r_target

        pnl_hedge = 0.0
        for f, hn in pos["hedge_legs"].items():
            if f in returns.columns and today in returns.index:
                r_factor = returns.loc[today, f]
                if not np.isnan(r_factor):
                    pnl_hedge += hn * r_factor

        day_pnl += pnl_main + pnl_hedge
        pos["pnl_realized"] += pnl_main + pnl_hedge

        # 资金费率 (真实历史数据)
        info = get_asset_info(name)
        if info and info["type"] == "tradfi_perp":
            today_str = str(today.date()) if hasattr(today, 'date') else str(today)[:10]
            # 主腿资金费
            rate_main = (funding_rates.loc[today_str, name]
                         if today_str in funding_rates.index and name in funding_rates.columns
                         else 0.0)
            funding = abs(pos["entry_notional"]) * rate_main
            # 对冲腿资金费
            for f, hn in pos["hedge_legs"].items():
                finfo = get_asset_info(f)
                if finfo and finfo["type"] == "tradfi_perp":
                    rate_hedge = (funding_rates.loc[today_str, f]
                                  if today_str in funding_rates.index and f in funding_rates.columns
                                  else 0.0)
                    funding += abs(hn) * rate_hedge
            day_funding += funding
            pos["funding_cost"] += funding

        # 借券成本 (做空美股/币股)
        if pos["direction"] == -1:
            info = get_asset_info(name)
            if info and info["type"] == "tradfi_perp":
                borrow = abs(pos["entry_notional"]) * COST["borrow_annual"] / 365
                day_borrow += borrow
                pos["borrow_cost"] += borrow

    # ---- 再关闭到期的老仓位 ----
    closed_names = []
    for name, pos in list(active_positions.items()):
        # 读取当日z-score判断是否平仓
        sig = asset_signals.get(name)
        if sig is None:
            closed_names.append(name)
            continue
        today_str = str(today.date())
        if today_str not in sig.index:
            closed_names.append(name)
            continue

        row = sig.loc[today_str]
        z = row.get("zscore", 0)
        signal_now = row.get("signal", 0)

        # 平仓条件: 按新阈值判断
        should_close = (abs(z) < EXIT_Z) or (abs(z) > STOP_Z)

        if should_close:
            # 计算退出成本
            info = get_asset_info(name)
            factors = get_factors(name)
            comm, slip = get_cost_rate(name, today=today, is_open=False)

            # 主腿退出成本
            exit_cost_notional = abs(pos["entry_notional"]) * (comm + slip)

            # 对冲腿退出成本
            hedge_comm = COST["commission"].get(info["type"] if info else "tradfi_perp", 0.0004)
            hedge_slip = COST["slippage"].get(
                "crypto_spot_major" if name in ("BTC","ETH") else "crypto_spot", 0.0005)
            for f, hn in pos.get("hedge_legs", {}).items():
                exit_cost_notional += abs(hn) * (hedge_comm + hedge_slip)

            exit_cost = exit_cost_notional
            exit_cost_cumulative += exit_cost
            cost_cumulative += exit_cost

            # 记录平仓交易
            total_pnl = pos.get("pnl_realized", 0.0)
            reason = "止损" if abs(z) > STOP_Z else "均值回归平仓"
            trades.append({
                "开仓日": pos["entry_date"],
                "平仓日": today,
                "资产": name,
                "方向": "做空" if pos["direction"] == -1 else "做多",
                "初始名义本金": pos["entry_notional"],
                "持有天数": (today - pos["entry_date"]).days,
                "毛PnL": total_pnl,
                "平仓成本": exit_cost,
                "净PnL": total_pnl - exit_cost - pos.get("entry_cost", 0) - pos.get("funding_cost", 0) - pos.get("borrow_cost", 0),
                "平仓原因": reason,
            })
            closed_names.append(name)

    # 移除已平仓的
    for name in closed_names:
        del active_positions[name]

    # ---- 遍历信号开新仓 ----
    for asset in TARGET_ASSETS:
        name = asset["name"]
        factors = get_factors(name)
        sector = get_sector(name)
        info = get_asset_info(name)

        sig = asset_signals.get(name)
        if sig is None:
            continue
        today_str = str(today.date())
        if today_str not in sig.index:
            continue

        row = sig.loc[today_str]
        z = row.get("zscore", 0)

        # 按新阈值重算信号
        if z > ENTRY_Z:
            signal = -1  # 做空
        elif z < -ENTRY_Z:
            signal = 1   # 做多
        else:
            continue     # 未触及阈值，不交易

        # 信号确认: 连续N天触发才入场
        if CONFIRM_DAYS > 1:
            try:
                idx = sig.index.get_loc(today)
            except:
                continue
            confirmed = True
            for d in range(1, CONFIRM_DAYS):
                if idx - d < 0:
                    confirmed = False
                    break
                prev_z = sig.iloc[idx - d].get("zscore", 0)
                if abs(prev_z) < ENTRY_Z or (prev_z > 0) != (z > 0):
                    confirmed = False
                    break
            if not confirmed:
                continue

        # 如果已有仓位则跳过
        if name in active_positions:
            continue

        # 找到combined索引
        combined = pd.concat([returns[name], returns[factors]], axis=1).dropna()
        comb_dates = combined.index
        if today not in comb_dates:
            continue
        t_idx = comb_dates.get_loc(today)

        # β
        current_betas = {}
        for f in factors:
            b = asset_betas[name][f]
            if t_idx < len(b) and not np.isnan(b[t_idx]):
                current_betas[f] = b[t_idx]
        if not current_betas:
            continue

        # 波动率
        vol = asset_vols[name][t_idx] if t_idx < len(asset_vols[name]) else 0.2
        if np.isnan(vol) or vol < 0.001:
            vol = 0.2

        # 名义本金
        N = (TARGET_VOL / vol) * TOTAL_CAPITAL
        N = min(N, TOTAL_CAPITAL * MAX_SINGLE)
        notional = N * signal

        # 对冲腿
        hedge_legs = {}
        for f, b in current_betas.items():
            hedge_notional = -b * notional
            hedge_legs[f] = hedge_notional
            factor_net[f] += hedge_notional

        # 风控检查
        if abs(notional) > TOTAL_CAPITAL * MAX_SINGLE:
            continue
        current_sector = sector_exposure.get(sector, 0) + abs(notional)
        if current_sector > TOTAL_CAPITAL * MAX_SECTOR:
            continue
        projected_gross = (total_long + max(0, notional) + sum(max(0, v) for v in hedge_legs.values())
                           + total_short + max(0, -notional) + sum(max(0, -v) for v in hedge_legs.values()))
        if projected_gross > TOTAL_CAPITAL * MAX_LEVERAGE:
            continue
        exceeded = [f for f, v in factor_net.items() if abs(v) > TOTAL_CAPITAL * MAX_FACTOR_EXPOSURE]
        if exceeded:
            continue

        # ---- 执行开仓 ----
        # 计算入场成本
        comm, slip = get_cost_rate(name, today=today, is_open=True)
        entry_cost_notional = abs(notional) * (comm + slip)
        # 对冲腿入场成本
        hedge_comm = COST["commission"].get(info["type"] if info else "tradfi_perp", 0.0004)
        hedge_slip = COST["slippage"].get(
            "crypto_spot_major" if name in ("BTC","ETH") else "crypto_spot", 0.0005)
        for f, hn in hedge_legs.items():
            entry_cost_notional += abs(hn) * (hedge_comm + hedge_slip)

        entry_cost = entry_cost_notional
        entry_cost_cumulative += entry_cost
        cost_cumulative += entry_cost

        active_positions[name] = {
            "entry_date": today,
            "direction": signal,
            "entry_notional": notional,
            "entry_cost": entry_cost,
            "hedge_legs": hedge_legs,
            "betas": current_betas,
            "vol": vol,
            "sector": sector,
            "pnl_realized": 0.0,
            "funding_cost": 0.0,
            "borrow_cost": 0.0,
        }

        total_long += max(0, notional) + sum(max(0, v) for v in hedge_legs.values())
        total_short += max(0, -notional) + sum(max(0, -v) for v in hedge_legs.values())
        sector_exposure[sector] = sector_exposure.get(sector, 0) + abs(notional)

    # ---- 更新累计值 ----
    # 保证金机会成本: 当天总名义本金 × 4%/365
    day_margin_cost = (total_long + total_short) * MARGIN_COST_ANNUAL / 365
    margin_cumulative += day_margin_cost
    pnl_cumulative += day_pnl
    funding_cumulative += day_funding
    borrow_cumulative += day_borrow
    cost_cumulative_total = (entry_cost_cumulative + exit_cost_cumulative
                             + funding_cumulative + borrow_cumulative + margin_cumulative)

    # ---- 记录每日净值 ----
    nav_daily.append({
        "日期": today,
        "毛PnL": day_pnl,
        "累计毛PnL": pnl_cumulative,
        "资金费率": day_funding,
        "借券成本": day_borrow,
        "入场成本累计": entry_cost_cumulative,
        "出场成本累计": exit_cost_cumulative,
        "资金费累计": funding_cumulative,
        "借券费累计": borrow_cumulative,
        "保证金成本累计": margin_cumulative,
        "总成本累计": cost_cumulative_total,
        "净PnL": pnl_cumulative - cost_cumulative_total,
        "持仓数": len(active_positions),
        "净资产": TOTAL_CAPITAL + pnl_cumulative - cost_cumulative_total,
    })

# ========== 输出 ==========
os.makedirs(PROJ_DIR + "/output/tables", exist_ok=True)

# NAV曲线
df_nav = pd.DataFrame(nav_daily)
df_nav.to_parquet(PROJ_DIR + "/output/tables/nav_curve.parquet")
print(f"\n✅ 已生成: output/tables/nav_curve.parquet ({len(df_nav)} 天)")

# 交易明细
df_trades = pd.DataFrame(trades)
if len(df_trades) > 0:
    df_trades["收益率"] = df_trades["净PnL"] / df_trades["初始名义本金"].abs() * 100
    df_trades.to_excel(PROJ_DIR + "/output/tables/trade_log.xlsx", index=False)
    print(f"✅ 已生成: output/tables/trade_log.xlsx ({len(df_trades)} 笔)")

# 成本汇总
cost_summary = pd.DataFrame({
    "成本类型": ["入场佣金+滑点", "出场佣金+滑点", "资金费率(真实历史)", "借券成本(做空美股)", "保证金机会成本", "总成本"],
    "金额": [entry_cost_cumulative, exit_cost_cumulative, funding_cumulative, borrow_cumulative, margin_cumulative, cost_cumulative_total],
})
cost_summary["占比"] = cost_summary["金额"] / cost_summary["金额"].iloc[-1] * 100
cost_summary.to_excel(PROJ_DIR + "/output/tables/cost_breakdown.xlsx", index=False)
print(f"✅ 已生成: output/tables/cost_breakdown.xlsx")

# ========== 结果摘要 ==========
print()
print("=" * 60)
print("回测结果摘要")
print("=" * 60)
total_pnl = pnl_cumulative
total_cost = cost_cumulative_total
net_pnl = total_pnl - total_cost
total_days = len(df_nav)

print(f"  回测天数:     {total_days}")
print(f"  总交易笔数:   {len(df_trades)}")
print(f"  总毛PnL:      ${total_pnl:,.0f}")
print(f"  总成本:       ${total_cost:,.0f}")
print(f"  总净PnL:      ${net_pnl:,.0f}")
print(f"  年化收益率(净): {net_pnl/TOTAL_CAPITAL/total_days*365*100:.2f}%")
print(f"  日均持仓数:   {df_nav['持仓数'].mean():.1f}")
print(f"  成本明细:")
print(f"    入场成本:   ${entry_cost_cumulative:,.0f}")
print(f"    出场成本:   ${exit_cost_cumulative:,.0f}")
print(f"    资金费率:   ${funding_cumulative:,.0f}")
print(f"    借券成本:   ${borrow_cumulative:,.0f}")
print(f"    保证金成本: ${margin_cumulative:,.0f}")
print("=" * 60)
