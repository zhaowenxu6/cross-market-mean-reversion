"""
标的池配置 (Universe Configuration)
定义基准因子 + 目标资产 + 配对逻辑

设计原则：
  1. 基准因子 4-5 个（解释变量，用于回归）
  2. 目标资产 25-30 个（被解释变量，产生残差）
  3. 每个目标资产指定 1-3 个因子
  4. 因子归属必须有经济学逻辑，不能纯靠统计相关性
"""

from typing import List, Dict

# ========== 基准因子 (Benchmark Factors) ==========
# 这些是做回归时的解释变量，即 X
# 设计原则：4-5 个
BENCHMARK_FACTORS: List[Dict] = [
    {
        "name": "BTC",
        "symbol": "BTCUSDT",
        "type": "crypto_spot",
        "category": "factor-L1",
        "note": "加密市场整体β，绝大多数加密资产的系统性因子",
    },
    {
        "name": "ETH",
        "symbol": "ETHUSDT",
        "type": "crypto_spot",
        "category": "factor-L1",
        "note": "以太坊生态β，ETH生态代币的系统性因子",
    },
    {
        "name": "SPY",
        "symbol": "SPYUSDT",
        "type": "tradfi_perp",
        "category": "factor-us-market",
        "note": "美股大盘β，标普500代理",
    },
    {
        "name": "QQQ",
        "symbol": "QQQUSDT",
        "type": "tradfi_perp",
        "category": "factor-tech",
        "note": "科技股β，纳斯达克100代理",
    },
    {
        "name": "SMH",
        "symbol": "SMHUSDT",
        "type": "tradfi_perp",
        "category": "factor-semiconductor",
        "note": "半导体板块β，矿企成本端+芯片股暴露",
    },
]


# ========== A 类：币股 (Coin Stocks) ==========
# 业务和加密强相关的美股，在 Binance 有 Perp
# 每个标的必须明确指定 factors（1-3 个）
COIN_STOCKS: List[Dict] = [
    {
        "name": "MSTR",
        "symbol": "MSTRUSDT",
        "type": "tradfi_perp",
        "category": "币股-持币机构",
        "factors": ["BTC", "QQQ"],
        "note": "MicroStrategy，持有约25万枚BTC，BTC代理股+科技股属性",
    },
    {
        "name": "COIN",
        "symbol": "COINUSDT",
        "type": "tradfi_perp",
        "category": "币股-交易所",
        "factors": ["BTC", "ETH", "QQQ"],
        "note": "美国最大加密交易所，收入挂钩BTC/ETH交易量，估值受美股科技股影响",
    },
    {
        "name": "MARA",
        "symbol": "MARAUSDT",
        "type": "tradfi_perp",
        "category": "币股-矿企",
        "factors": ["BTC", "SMH"],
        "note": "美国最大比特币矿企之一，收入靠BTC，成本靠半导体矿机",
    },
    {
        "name": "RIOT",
        "symbol": "RIOTUSDT",
        "type": "tradfi_perp",
        "category": "币股-矿企",
        "factors": ["BTC", "SMH"],
        "note": "另一大矿企，和MARA高度相关，收入靠BTC，成本靠半导体矿机",
    },
    {
        "name": "CLSK",
        "symbol": "CLSKUSDT",
        "type": "tradfi_perp",
        "category": "币股-矿企",
        "factors": ["BTC", "SMH"],
        "note": "矿企，和MARA/RIOT同类，收入靠BTC，成本靠半导体矿机",
    },
]


# ========== B 类：加密资产 (Crypto Assets) ==========
# 主流币、L2、DeFi、平台币、Meme
# 每个标的必须明确指定 factors（1-3 个）
CRYPTO_ASSETS: List[Dict] = [
    {
        "name": "SOL",
        "symbol": "SOLUSDT",
        "type": "crypto_spot",
        "category": "L1",
        "factors": ["BTC", "ETH"],
        "note": "高性能L1公链，系统性风险由BTC代理，ETH走势影响整个L1赛道估值重定价",
    },
    {
        "name": "BNB",
        "symbol": "BNBUSDT",
        "type": "crypto_spot",
        "category": "平台币",
        "factors": ["BTC", "ETH"],
        "note": "币安平台币，系统性因子BTC+ETH（币安交易生态），特质来自BSC/Launchpad",
    },
    {
        "name": "XRP",
        "symbol": "XRPUSDT",
        "type": "crypto_spot",
        "category": "L1",
        "factors": ["BTC", "ETH"],
        "note": "跨境支付币，整体加密流动性受ETH+BTC双重影响，特质来自SEC监管和银行采用",
    },
    {
        "name": "ADA",
        "symbol": "ADAUSDT",
        "type": "crypto_spot",
        "category": "L1",
        "factors": ["BTC", "ETH"],
        "note": "学术派L1公链，整体L1赛道系统性风险由BTC+ETH代理，特质来自生态发展缓慢的补涨特征",
    },
    {
        "name": "AVAX",
        "symbol": "AVAXUSDT",
        "type": "crypto_spot",
        "category": "L1",
        "factors": ["BTC", "ETH"],
        "note": "EVM兼容L1，双因子BTC+ETH，特质来自子网技术和企业合作",
    },
    {
        "name": "ARB",
        "symbol": "ARBUSDT",
        "type": "crypto_spot",
        "category": "Layer2",
        "factors": ["ETH", "BTC"],
        "note": "Arbitrum，最大ETH L2，系统性因子ETH+BTC，特质来自L2赛道竞争",
    },
    {
        "name": "OP",
        "symbol": "OPUSDT",
        "type": "crypto_spot",
        "category": "Layer2",
        "factors": ["ETH", "BTC"],
        "note": "Optimism，第二大ETH L2，系统性因子ETH+BTC，特质来自Superchain竞争",
    },
    {
        "name": "UNI",
        "symbol": "UNIUSDT",
        "type": "crypto_spot",
        "category": "DeFi",
        "factors": ["ETH", "BTC"],
        "note": "Uniswap，最大DEX，系统性因子ETH+BTC，特质来自V4升级和费用开关",
    },
    {
        "name": "AAVE",
        "symbol": "AAVEUSDT",
        "type": "crypto_spot",
        "category": "DeFi",
        "factors": ["ETH", "BTC"],
        "note": "去中心化借贷，系统性因子ETH+BTC，特质来自GHO稳定币和多链扩展",
    },
    {
        "name": "LDO",
        "symbol": "LDOUSDT",
        "type": "crypto_spot",
        "category": "DeFi",
        "factors": ["ETH", "BTC"],
        "note": "Lido ETH质押协议，系统性因子ETH+BTC，特质来自再质押(EigenLayer)",
    },
    {
        "name": "DOGE",
        "symbol": "DOGEUSDT",
        "type": "crypto_spot",
        "category": "Meme",
        "factors": ["BTC"],
        "note": "Meme币，散户情绪温度计，单因子BTC足够，特质来自马斯克效应和社交媒体热度",
    },
    {
        "name": "LINK",
        "symbol": "LINKUSDT",
        "type": "crypto_spot",
        "category": "基础设施",
        "factors": ["ETH", "BTC"],
        "note": "Chainlink预言机，ETH生态基础设施，系统性因子ETH+BTC，特质来自CCIP跨链协议",
    },
]


# ========== C 类：美股科技 (US Tech Perps) ==========
# Binance TradFi Perp，必须实际确认已上线
US_TECH_PERPS: List[Dict] = [
    {
        "name": "NVDA",
        "symbol": "NVDAUSDT",
        "type": "tradfi_perp",
        "category": "美股-科技",
        "factors": ["QQQ", "SMH"],
        "note": "英伟达，AI芯片龙头，双因子QQQ+SMH，特质来自AI算力需求",
    },
    {
        "name": "AMD",
        "symbol": "AMDUSDT",
        "type": "tradfi_perp",
        "category": "美股-科技",
        "factors": ["QQQ", "SMH"],
        "note": "AMD，NVDA竞争对手，双因子QQQ+SMH，特质来自CPU/GPU市场份额",
    },
    {
        "name": "TSLA",
        "symbol": "TSLAUSDT",
        "type": "tradfi_perp",
        "category": "美股-科技",
        "factors": ["QQQ", "SMH"],
        "note": "特斯拉，电动车芯片需求+AI Dojo算力依赖半导体，特质来自马斯克效应和电动车周期",
    },
    {
        "name": "AAPL",
        "symbol": "AAPLUSDT",
        "type": "tradfi_perp",
        "category": "美股-科技",
        "factors": ["QQQ", "SMH"],
        "note": "苹果，A/M系列芯片自研，半导体供应链敏感，特质来自iPhone周期和服务收入转型",
    },
    {
        "name": "MSFT",
        "symbol": "MSFTUSDT",
        "type": "tradfi_perp",
        "category": "美股-科技",
        "factors": ["QQQ", "SMH"],
        "note": "微软，Azure AI基础设施（GPU/TPU依赖半导体），特质来自AI Copilot商业化和Azure增长",
    },
    {
        "name": "META",
        "symbol": "METAUSDT",
        "type": "tradfi_perp",
        "category": "美股-科技",
        "factors": ["QQQ", "SMH"],
        "note": "Meta，AI算力投资+VR/AR硬件都是芯片密集型，特质来自广告周期和元宇宙投资冲突",
    },
    {
        "name": "AMZN",
        "symbol": "AMZNUSDT",
        "type": "tradfi_perp",
        "category": "美股-科技",
        "factors": ["QQQ", "SMH"],
        "note": "亚马逊，AWS自研芯片Graviton/Trainium依赖半导体供应链，特质来自电商利润率vs AWS增长",
    },
    {
        "name": "GOOGL",
        "symbol": "GOOGLUSDT",
        "type": "tradfi_perp",
        "category": "美股-科技",
        "factors": ["QQQ", "SMH"],
        "note": "谷歌，TPU芯片自研+AI数据中心依赖半导体，特质来自AI搜索威胁和Gemini防御",
    },
]


# ========== 汇总 ==========
ALL_ASSETS: List[Dict] = []
ALL_ASSETS.extend(BENCHMARK_FACTORS)
ALL_ASSETS.extend(COIN_STOCKS)
ALL_ASSETS.extend(CRYPTO_ASSETS)
ALL_ASSETS.extend(US_TECH_PERPS)


# ========== 统计 ==========
if __name__ == "__main__":
    print(f"基准因子: {len(BENCHMARK_FACTORS)} 个")
    print(f"币股: {len(COIN_STOCKS)} 个")
    print(f"加密资产: {len(CRYPTO_ASSETS)} 个")
    print(f"美股科技Perp: {len(US_TECH_PERPS)} 个")
    print(f"总计: {len(ALL_ASSETS)} 个")
    print()
    print("=" * 80)
    print("完整标的池清单")
    print("=" * 80)
    for i, a in enumerate(ALL_ASSETS, 1):
        factors_str = ", ".join(a.get("factors", []))
        print(f"{i:2}. {a['name']:8} | {a['symbol']:15} | {a['type']:15} | 因子: {factors_str}")
    print("=" * 80)
