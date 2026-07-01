"""
因子模型构建与验证 (Step 3)
对25个目标资产跑滚动OLS回归，提取残差并验证模型质量

产出:
  1. output/tables/factor_model_quality.xlsx — 模型质量汇总表
  2. output/figures/beta_*.png — 每个配对的β时序图
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
# 中文字体配置
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False
from scipy import stats
from sklearn.linear_model import RidgeCV

# 导入标的池
spec = importlib.util.spec_from_file_location("universe", PROJ_DIR + "/config/universe.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TARGET_ASSETS = mod.COIN_STOCKS + mod.CRYPTO_ASSETS + mod.US_TECH_PERPS
FACTOR_NAMES = [f["name"] for f in mod.BENCHMARK_FACTORS]

# ---------- 配置 ----------
WINDOW = 90        # 滚动窗口（交易日）
STEP = 22          # 步长（约每月一次）
MIN_OBS = 60       # 最少有效观测数

# ---------- 加载收益率 panel ----------
returns = pd.read_parquet(PROJ_DIR + "/data/interim/returns_clean.parquet")
returns = returns.sort_index()
# 裁剪到面试要求的时间范围 2023-01-01 起
returns = returns[returns.index >= "2023-01-01"]
print(f"收益率面板: {returns.shape[0]} 天 x {returns.shape[1]} 个标的")
print(f"日期范围: {returns.index[0].date()} ~ {returns.index[-1].date()}")
print()

# ---------- 工具函数 ----------
def ridge_regression(y, X):
    """Ridge回归（岭回归），用交叉验证自动选最优alpha
    解决因子间共线性问题，比OLS的β估计更稳定
    """
    n = len(y)
    try:
        # 自动从[0.001, 0.01, 0.1, 1.0, 10.0]中选最佳alpha
        model = RidgeCV(alphas=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
                        fit_intercept=True, cv=5)
        model.fit(X, y)
        alpha_hat = model.intercept_
        beta = model.coef_
        predicted = model.predict(X)
        residuals = y - predicted

        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        p = X.shape[1]
        adj_r2 = 1 - (1 - r2) * (n - 1) / (n - p - 1)

        return {
            "alpha": alpha_hat, "beta": beta,
            "r2": r2, "adj_r2": adj_r2,
            "residuals": residuals,
            "n_obs": n,
            "ridge_alpha": model.alpha_,
        }
    except:
        return None

def adf_test(series):
    """ADF检验，返回p值"""
    from statsmodels.tsa.stattools import adfuller
    try:
        result = adfuller(series, maxlag=10, autolag="AIC")
        return result[1]
    except:
        return 1.0

# ---------- 主循环 ----------
os.makedirs(PROJ_DIR + "/output/figures", exist_ok=True)
os.makedirs(PROJ_DIR + "/output/tables", exist_ok=True)

results = []
FACTOR_COLORS = {"BTC": "#F7931A", "ETH": "#8B8CF7", "SPY": "#1B9D76",
                 "QQQ": "#2962FF", "SMH": "#E91E63"}

total = len(TARGET_ASSETS)
for idx, asset in enumerate(TARGET_ASSETS, 1):
    name = asset["name"]
    factors = asset["factors"]
    print(f"[{idx}/{total}] {name} ← {factors} ...", end=" ", flush=True)

    # 提取收益率
    asset_ret = returns[name]
    factor_rets = returns[factors]

    # 对齐（只取都有数据的日期）
    combined = pd.concat([asset_ret, factor_rets], axis=1).dropna()
    y = combined[name].values
    X = combined[factors].values

    if len(y) < MIN_OBS:
        print(f"数据不足 ({len(y)} < {MIN_OBS})，跳过")
        continue

    # ===== 滚动回归 =====
    n = len(y)
    rolling_betas = [[] for _ in factors]
    rolling_alphas = []
    rolling_r2 = []
    rolling_dates = []
    all_residuals = []

    for i in range(0, n - WINDOW + 1, STEP):
        end = i + WINDOW
        y_win = y[i:end]
        X_win = X[i:end]

        result = ridge_regression(y_win, X_win)
        if result is None or result["r2"] < 0.01:
            continue

        rolling_dates.append(combined.index[end - 1])
        rolling_alphas.append(result["alpha"])
        for j, b in enumerate(result["beta"]):
            rolling_betas[j].append(b)
        rolling_r2.append(result["r2"])
        # 用窗口内最后一笔的残差做全样本残差
        in_sample_resid = y_win - np.column_stack([np.ones(WINDOW), X_win]) @ np.append(result["alpha"], result["beta"])
        all_residuals.extend(in_sample_resid)

    if len(rolling_dates) < 3:
        print(f"滚动回归结果不足，跳过")
        continue

    # ===== 全样本残差（用于ADF+Ljung-Box检验） =====
    # 预测收益率 = α + β₁·r₁ + β₂·r₂
    # 特质残差 ε = 实际收益率 - 预测收益率
    # ADF检验对象：累积残差（cumulative residual）
    #   - 日频残差天然均值回归（围绕0波动），ADF必然通过，无区分力
    #   - 累积残差检验的是"价差是否均值回归"，即协整关系是否存在
    #   - 这是统计套利中ADF检验的正确用法
    # Ljung-Box检验对象：日频残差自相关
    full_result = ridge_regression(y, X)
    if full_result is None:
        print("全样本回归失败，跳过")
        continue

    residuals = full_result["residuals"]
    cum_residuals = np.cumsum(residuals)
    adf_p_daily = adf_test(residuals)       # 日频残差ADF
    adf_p_cum = adf_test(cum_residuals)     # 累积残差ADF（协整检验）
    adf_p = adf_p_cum  # 主判定用累积残差

    # Ljung-Box检验（日频残差自相关，滞后10期）
    from statsmodels.stats.diagnostic import acorr_ljungbox
    try:
        lb_result = acorr_ljungbox(residuals, lags=[10], return_df=True)
        lb_p = lb_result["lb_pvalue"].iloc[0]
    except:
        lb_p = 1.0

    # 均值β和β范围
    beta_mean = [np.mean(b) for b in rolling_betas]
    beta_min = [np.min(b) for b in rolling_betas]
    beta_max = [np.max(b) for b in rolling_betas]

    # 截距项
    alpha_mean = np.mean(rolling_alphas)
    alpha_tstat = alpha_mean / (np.std(rolling_alphas) / np.sqrt(len(rolling_alphas))) if len(rolling_alphas) > 2 else 0

    r2_mean = np.mean(rolling_r2)
    r2_std = np.std(rolling_r2)

    # β时变性（变异系数）
    beta_cv = [np.std(b) / max(abs(np.mean(b)), 0.01) for b in rolling_betas]

    # 通过标准：R²>=0.5 且 累积残差ADF<0.05 且 日频残差白噪声(LB>0.05)
    # 注意：ADF检验对象为累积残差（协整检验），非日频残差
    passed = (r2_mean >= 0.5) and (adf_p_cum < 0.05) and (lb_p > 0.05)
    adf_display = f"日频={adf_p_daily:.2e}  累积={adf_p_cum:.4f}"

    rid_alpha = full_result.get("ridge_alpha", 0)
    lb_display = f"{lb_p:.2e}" if lb_p < 0.0001 else f"{lb_p:.4f}"
    print(f"R²={r2_mean:.3f}  ADF={adf_display}  LB={lb_display}  {'通过' if passed else '未通过'}  滚动窗口={len(rolling_dates)}")

    results.append({
        "代码": name,
        "类别": asset.get("category", ""),
        "因子组合": "+".join(factors),
        "观测数": len(y),
        "有效滚动窗口": len(rolling_dates),
        "R²均值": round(r2_mean, 4),
        "R²标准差": round(r2_std, 4),
        "α均值": round(alpha_mean, 6),
        "ADF(日频残差)P值": round(adf_p_daily, 4) if adf_p_daily >= 0.0001 else adf_p_daily,
        "ADF(累积残差)P值": round(adf_p_cum, 4) if adf_p_cum >= 0.0001 else adf_p_cum,
        "累积残差平稳": "是" if adf_p_cum < 0.05 else "否",
        "Ljung-Box P值": round(lb_p, 4) if lb_p >= 0.0001 else lb_p,
        "残差白噪声": "是" if lb_p > 0.05 else "否",
        "是否通过": "✅" if passed else "❌",
    })

    # 逐因子记录
    for j, f in enumerate(factors):
        results[-1][f"β_{f}均值"] = round(beta_mean[j], 4)
        results[-1][f"β_{f}范围"] = f"[{beta_min[j]:.3f}, {beta_max[j]:.3f}]"
        results[-1][f"β_{f}变异系数"] = round(beta_cv[j], 3)

    # ===== 画β时序图 =====
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={"height_ratios": [2, 1]})

    # 上：β时序
    ax = axes[0]
    x_dates = rolling_dates
    for j, f in enumerate(factors):
        ax.plot(x_dates, rolling_betas[j], label=f"β_{f}",
                color=FACTOR_COLORS.get(f, f"C{j}"), linewidth=1.5)
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    ax.set_title(f"{name} 滚动β时序 (窗口{WINDOW}d, 步长{STEP}d)", fontsize=11)
    ax.set_ylabel("因子载荷 β")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # 下：滚动R²
    ax = axes[1]
    ax.plot(x_dates, rolling_r2, color="#2962FF", linewidth=1.5)
    ax.axhline(y=0.5, color="red", linestyle="--", alpha=0.5, label="R²=0.5")
    ax.set_ylabel("R²")
    ax.set_xlabel("日期")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    # 文件名去掉特殊字符
    safe_name = name.replace("/", "_").replace(".", "_")
    fig_path = f"{PROJ_DIR}/output/figures/beta_{safe_name}.png"
    plt.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

# ===== 输出质量表 =====
df_results = pd.DataFrame(results)
df_results = df_results.sort_values("R²均值", ascending=False)

excel_path = PROJ_DIR + "/output/tables/factor_model_quality.xlsx"
with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
    df_results.to_excel(writer, index=False, sheet_name="模型质量")
    ws = writer.sheets["模型质量"]
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

# ===== 汇总统计 =====
print()
print("=" * 60)
print("模型质量汇总")
print("=" * 60)
passed_count = len(df_results[df_results["是否通过"] == "✅"])
failed_count = len(df_results[df_results["是否通过"] == "❌"])
print(f"  通过验证(R²>=0.5 + ADF<0.05 + LB>0.05): {passed_count} / {len(TARGET_ASSETS)}")
print(f"  未通过: {failed_count} / {len(TARGET_ASSETS)}")
print(f"  R²中位数: {df_results['R²均值'].median():.4f}")
passed_r2 = df_results[df_results["R²均值"] >= 0.5]
print(f"  R²>=0.5: {len(passed_r2)} / {len(df_results)} ({len(passed_r2)/len(df_results)*100:.0f}%)")
failed_r2 = df_results[df_results["R²均值"] < 0.5]
print(f"  R²<0.5: {len(failed_r2)} / {len(df_results)}")
if len(failed_r2) > 0:
    print(f"    低R²资产: {', '.join(failed_r2['代码'].tolist())}")
stable = df_results[df_results["累积残差平稳"] == "是"]
print(f"  累积残差平稳(ADF<0.05): {len(stable)} / {len(df_results)}")

print()
print(f"✅ 已生成: {excel_path}")
print(f"✅ 已生成: output/figures/beta_*.png ({len(results)} 张)")
