# 跨市场特质均值回归统计套利策略

Idiosyncratic Mean-Reversion Statistical Arbitrage Strategy on Binance

## 项目说明

在 Binance 平台上设计并回测跨市场特质均值回归统计套利策略，利用加密资产（24/7）与传统金融资产（6.5h/日）之间的跨市场定价偏差，通过 Ridge 因子模型剥离系统性风险，捕捉特质残差的均值回归收益。

本项目完整包含方法论框架、回测引擎、成本建模与策略分析报告。

## 策略核心逻辑

```
r_target = α + β₁·r_factor₁ + β₂·r_factor₂ + ε
                                              ↑
                                        特质残差(ε)
                                    z > 2.0 → 做空/做多
                                    z < 0.5 → 平仓
```

## 文件结构

```
├── config/
│   └── universe.py             标的池配置（5基准因子 + 25目标资产）
├── scripts/
│   ├── download_data.py         Step 1: 原始行情下载
│   ├── preprocess_data.py       Step 2: 数据清洗与对齐
│   ├── factor_model.py          Step 3: Ridge滚动回归 + 质量检验
│   ├── generate_signals.py      Step 4: z-score信号生成
│   ├── build_portfolio.py       Step 5: 组合构建与风控
│   ├── backtest.py              Step 6: 回测引擎 + 成本建模
│   ├── risk_dashboard.py        Step 7: 风控可视化
│   ├── visualize_samples.py     Step 8: 样本交易可视化
│   └── generate_docx_report.py  Step 9: 生成Word报告
├── output/
│   ├── figures/                 可视化图表
│   ├── tables/                  回测数据（净值、交易记录、成本分解等）
│   ├── reports/
│   │   └── strategy_report.docx 最终策略分析报告
│   └── docs/
│       └── cost_modeling.md     成本建模说明
├── data/
│   ├── external/                外部数据（资金费率）
│   └── interim/                 中间数据（收益率矩阵、信号等）
├── requirements.txt             Python依赖
├── README.md                    本文件
└── .gitignore
```

## 运行顺序

**必须按以下顺序执行：**

```bash
pip install -r requirements.txt

# 一键运行全部步骤
python run_all.py

# 或按顺序手动执行
python scripts/download_data.py          # 下载原始数据
python scripts/preprocess_data.py        # 清洗对齐
python scripts/factor_model.py           # 因子模型
python scripts/generate_signals.py       # 信号生成
python scripts/build_portfolio.py        # 组合构建
python scripts/backtest.py               # 回测
python scripts/risk_dashboard.py         # 风控图表
python scripts/generate_docx_report.py   # 生成报告
```

## run_all.py 参数

| 参数 | 说明 |
|------|------|
| `--skip-download` | 跳过数据下载（已有数据时使用） |
| `--force-report` | 强制重新生成报告（默认报告存在时跳过） |

## 最终报告

`output/reports/strategy_report.docx`

在 Word 中打开后可调整格式，另存为 PDF 即可。

## 环境要求

- Python >= 3.9
- 依赖详见 `requirements.txt`

## 参数说明

`backtest.py` 顶部可修改三个核心参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| ENTRY_Z | 2.0 | z-score入场阈值 |
| EXIT_Z | 0.5 | z-score平仓阈值 |
| STOP_Z | 3.0 | z-score止损阈值 |

## 回测结果摘要

| 指标 | 数值 |
|------|------|
| 回测期间 | 2023-06 ~ 2026-06（3年, 1125天） |
| 初始资金 | $10,000,000 |
| 标的池 | 5基准因子 + 25目标资产 |
| 因子模型 | Ridge回归(α=0.01), 90天滚动 |
| 入场/平仓/止损 | ±2σ / ±0.5σ / ±3σ |
| 年化收益 | -6.91% |
| 夏普比率 | -2.51 |
| 最大回撤 | -21.44% |
| 总成本 | 约年化4.3% |

> 策略日频级别不赚钱是预期内的——残差半衰期分析(0.1-0.4天)表明均值回归发生在日内(4-8小时)，日频数据无法捕捉。更深层原因是25个配对中仅2个(UNI、AMZN)通过累积残差ADF协整检验，多数配对不存在长期均衡关系。核心价值在于方法论框架与诚实分析，改进方向为协整前置筛选+4小时级别数据。

## 使用的AI工具

本项目的部分代码生成和文档撰写使用了 AI 辅助工具 (WorkBuddy/Claude)，所有关键逻辑（因子模型、信号规则、回测引擎）均经过独立验证与确认。

## 联系方式

- 作者：赵文旭
- 邮箱：zhaowenxu6@gmail.com
