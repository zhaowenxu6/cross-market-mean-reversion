# 策略报告制作指南

## 报告结构（建议8章，14-18页）

---

### 封面（1页）
标题：跨市场特质均值回归策略分析报告
副标题：Idiosyncratic Mean-Reversion Statistical Arbitrage on Binance
信息：候选人/投递岗位/回测期/资金规模/生成日期

---

### 第一章：标的池筛选与配对逻辑（2页）

**1.1 标的池清单（放表格）**
| 来源 | 文件 |
|:-----|:-----|
| 25个目标资产+5因子 | `config/universe.py` |

**1.2 配对经济学逻辑（放表格）**
| 配对类型 | 示例 | 经济学逻辑 |
| 币股←BTC+QQQ | MSTR | MSTR持25万BTC；估值=BTC价值+软件业务 |
| 币股←BTC+SMH | MARA | 矿企收入挂钩BTC，成本受半导体影响 |
| L2←ETH+BTC | ARB | Arbitrum以太坊L2，受ETH生态驱动 |
| L1←BTC+ETH | SOL | SON第2大L1，ETH影响赛道估值 |
| 美股Perp←QQQ+SMH | NVDA | 受科技股+半导体双重驱动 |
| 平台币←BTC+ETH | BNB | 币安收入挂钩BTC/ETH交易量 |

---

### 第二章：因子模型构建与验证（2页）

**2.1 模型质量表**
| 来源 | 文件 |
|:-----|:-----|
| R²/β/ADF/Ljung-Box | `output/tables/factor_model_quality.xlsx` |
| 关键数据：R²中位数0.535, 15/25通过, ADF全部<0.05 |

**2.2 β时序图（放图片）**
- 从 `output/figures/` 选2-3个关键资产的β图（如果有）
- 说明：Ridge回归相比OLS更平稳

---

### 第三章：信号生成与质量评估（2页）

**3.1 信号规则**
- 入场：|z|>2.0 | 平仓：|z|<0.5 | 止损：|z|>3.0
- z-score 30天滚动窗口

**3.2 信号统计表**
| 来源 | 文件 |
|:-----|:-----|
| 日均信号/持有期/胜率 | `output/tables/signal_summary.xlsx` |

**3.3 样本交易图（放3张）**
- `output/figures/sample_ARB.png` — 最赚钱标的
- `output/figures/sample_MSTR.png` — 币股代表
- `output/figures/sample_OP.png` — 亏钱代表

**3.4 关键分析点（必写）**
> 96.4%的胜率（按z回归±0.5定义）≠ PnL为正。
> 做空时每日PnL = -N×ε，只要ε>0就在亏损。
> z从+2.0回归到+0.3算"胜"但仍在亏。
> 真正盈利需要残差穿越零轴——这在日频下不够频繁。

---

### 第四章：组合构建与风险管理（2页）

**4.1 风控约束表**
| 来源 |
|:-----|
| 单资产≤3%/板块≤15%/杠杆≤3x/因子≤5% |

**4.2 风控事件**
| 来源 | 文件 |
|:-----|:-----|
| 678条事件, 98%因子超限 | `output/tables/risk_events.xlsx` |

**4.3 风险监控图（放3张）**
- `output/figures/factor_exposure.png`
- `output/figures/sector_exposure.png`
- `output/figures/leverage_positions.png`

---

### 第五章：回测引擎与成本建模（3页）

**5.1 核心业绩表（最重要的表格）**
| 来源 | 文件 |
|:-----|:-----|
| 年化收益/波动/夏普/卡玛/最大回撤/胜率 | `output/tables/nav_curve.parquet` |
| 交易笔数/毛PnL/成本 | `output/tables/trade_log.xlsx` |
| 关键公式：年化=-6.91%, 夏普=-2.51, 最大回撤=-9.41% |

**5.2 权益曲线图**
- `output/figures/equity_curve.png`

**5.3 年度表现表**
| 年份 | 2023 | 2024 | 2025 | 2026 |
| 毛PnL | -$284K | -$546K | +$36K | -$5K |

**5.4 成本分解表**
| 来源 | 文件 |
|:-----|:-----|
| 入场/出场/资金费/借券/保证金 | `output/tables/cost_breakdown.xlsx` |
| 重点：入场+出场=94%成本 |

**5.5 容量分析表**
| 规模 | $1M | $10M | $50M | $500M |
| 结论 | ✅ | ✅ | ⚠️ | ❌ |

---

### 第六章：策略分析与评估（3页）

**6.1 损益归因表**
| 来源 | 文件 |
|:-----|:-----|
| 按类别(加密/美股/币股) | `output/tables/trade_log.xlsx` |
| 按资产前5名 | trade_log分组统计 |

**6.2 因子暴露归因表**
| 来源 | 文件 |
|:-----|:-----|
| BTC/ETH/QQQ/SMH/SPY | `output/tables/portfolio_daily.parquet` |
| 注意：BTC最大22%超限 |

**6.3 极端事件表**
| 来源 |
|:-----|
| 最差5天：2025-05-10 / 2024-04-13 / 2024-11-10 / 2024-07-16 / 2023-12-22 |
| 共同特征：加密做空被逼仓 |

**6.4 策略局限（必写）**
1. Alpha不足以覆盖成本——毛PnL本身为负
2. 残差半衰期<0.5天——日频无法捕捉日内回归
3. 日均仅0.8个新信号——分散化不足
4. 改进方向：4小时K线/精选标的/LASSO降费

---

### 附录A：回测严谨性声明（1页）

**表：5项红线标准**
| 标准 | 实现方式 |
|:-----|:---------|
| 前视偏差 | β[t]←X[t-90:t)仅历史数据；开仓当天不计PnL |
| 幸存者偏差 | 25个标的持续上线Binance |
| 时间对齐 | 日频加密24/7 vs美股6.5h可接受 |
| 交易成本 | 手续费+滑点+真实资金费率+借券+保证金 |
| 极端事件 | SVB/SEC/ETF/日元套利期间滑点×3 |

---

### 附录B：文件清单（1页）

| 脚本 | 用途 |
|:-----|:------|
| download_data.py | 数据下载 |
| preprocess_data.py | 预处理 |
| factor_model.py | 因子模型 |
| generate_signals.py | 信号生成 |
| build_portfolio.py | 组合构建 |
| backtest.py | 回测引擎 |
| generate_pdf_report.py | 报告生成 |

---

## 所有图表来源汇总

| 图表 | 路径 |
|:-----|:------|
| 权益曲线 | `output/figures/equity_curve.png` |
| 因子暴露 | `output/figures/factor_exposure.png` |
| 板块集中度 | `output/figures/sector_exposure.png` |
| 杠杆+持仓 | `output/figures/leverage_positions.png` |
| ARB样本 | `output/figures/sample_ARB.png` |
| MSTR样本 | `output/figures/sample_MSTR.png` |
| OP样本 | `output/figures/sample_OP.png` |
| 交易统计 | `output/figures/trade_statistics.png` |

## 所有数据来源汇总

| 数据 | 路径 |
|:-----|:------|
| 因子模型质量 | `output/tables/factor_model_quality.xlsx` |
| 信号统计 | `output/tables/signal_summary.xlsx` |
| 组合快照 | `output/tables/portfolio_daily.parquet` |
| 风险事件 | `output/tables/risk_events.xlsx` |
| NAV曲线 | `output/tables/nav_curve.parquet` |
| 交易日志 | `output/tables/trade_log.xlsx` |
| 成本分解 | `output/tables/cost_breakdown.xlsx` |
| 风控仪表板 | `output/tables/risk_dashboard.xlsx` |
