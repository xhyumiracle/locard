"""
System-wide configuration for BlockchainMAS v0

This file contains all magic numbers, thresholds, and environment-based settings.
For v0, config is static (requires restart to change). For v1+, consider adding
runtime-modifiable ConfigState in GraphState.
"""

import os
from typing import Literal

from dotenv import load_dotenv

from src.utils.time import ensure_ts_seconds

# Load environment variables from .env
load_dotenv()


# ==================== Agent Loop Limits ====================

# Trace workflow - dynamic planning with iteration limit
TRACE_MAX_ITERATIONS = 25      # 最大迭代次数（orchestrator → fetcher 循环）
TRACE_MAX_DEPTH = 5            # 跨链溯源最大跳数（CrossChainLink 数量上限）
TRACE_MAX_ERRORS = 100         # Error 列表软上限（超过后考虑终止）
TRACE_ERRORS_WARNING = 50      # Error 警告阈值（触发策略评估）

# Fallback workflow
FALLBACK_MAX_ITERATIONS = 15   # 最大迭代次数
FALLBACK_MAX_ERRORS = 50       # Fallback workflow error 上限


# ==================== Tool Retry Config ====================

TOOL_MAX_RETRIES = 3           # API 调用最大重试次数（不包括首次尝试）
TOOL_RETRY_BACKOFF_BASE = 2    # 指数退避基数（秒），第 n 次重试等待 base^n 秒
TOOL_TIMEOUT = 30              # 单次 API 调用超时时间（秒）


# ==================== Cache Config ====================

CACHE_ENABLED = True           # 是否启用工具调用缓存
CACHE_SERIALIZATION: Literal["json", "pickle"] = "json"  # 缓存序列化方式

# Cache key generation
def make_cache_key(tool_name: str, args: dict) -> str:
    """
    生成缓存 key。

    v0 简化版：直接使用 JSON 序列化后的字符串作为 key。
    优点：简单高效，只要 args 不是超长就没问题。
    """
    import json
    normalized_args = json.dumps(args, sort_keys=True)
    return f"{tool_name}:{normalized_args}"


# ==================== Cross-chain Link Config ====================

# Time windows for candidate generation (seconds)
CCLINK_TIME_WINDOW_BRIDGE = 120 * 60      # 桥: 2小时
CCLINK_TIME_WINDOW_EXCHANGE = 48 * 3600   # 交易所: 48小时
CCLINK_TIME_WINDOW_DEFAULT = 6 * 3600     # 默认: 6小时

# Value matching tolerance
CCLINK_VALUE_TOLERANCE_REL = 0.05         # 金额相对容差 5%
CCLINK_VALUE_TOLERANCE_ABS = 10.0         # 金额绝对容差 $10 (USD)

# Feature weights (from link_confidence.md v0 minimal)
# v0 只使用 4 个核心特征
CCLINK_WEIGHT_META = 4.0       # 跨链元数据证据（事件日志、nonce 等）
CCLINK_WEIGHT_VALUE = 2.0      # 价值一致性
CCLINK_WEIGHT_TIME = 1.5       # 时间接近度
CCLINK_WEIGHT_UNIQUE = 2.0     # 唯一性（歧义惩罚）

# Optional features (v1+)
CCLINK_WEIGHT_TAG = 1.0        # 端点标签命中（桥/交易所地址）
CCLINK_WEIGHT_FEE = 1.0        # 费用/滑点合理性
CCLINK_WEIGHT_ROUNDING = 0.5   # 数值人类痕迹
CCLINK_WEIGHT_FLOW = 0.5       # 链路上下文一致性

# Confidence thresholds
CCLINK_CONFIDENCE_LOW = 0.35   # 低于此不连边（认为是噪声）
CCLINK_CONFIDENCE_HIGH = 0.75  # 高于此自动选为主链路（高置信度）
CCLINK_TOP_K_CANDIDATES = 5    # 保留候选数（每个 src_op 最多保留多少候选）

# Exponential decay parameters (for time/amount features)
CCLINK_TAU_TIME_BRIDGE = 30 * 60      # 桥的时间衰减常数 (30分钟)
CCLINK_TAU_TIME_EXCHANGE = 12 * 3600  # 交易所的时间衰减常数 (12小时)
CCLINK_TAU_VALUE = 0.05               # 价值衰减常数 (5%)

# Price buffer percentages for scoring (applied to raw price range from Binance)
# These expand the price range to account for market realities:
# - PRICE_MAX_FEE_RATE: max acceptable fee rate, expands lower bound (min_price * (1 - rate))
#   This creates room for swap fees, bridge fees, slippage, etc.
# - PRICE_MAX_DEVIATION_RATE: max price deviation across platforms, expands upper bound (max_price * (1 + rate))
#   This accounts for price differences between Binance and actual swap platform
PRICE_MAX_FEE_RATE = 0.10             # 10% - max acceptable fee rate (lower buffer)
PRICE_MAX_DEVIATION_RATE = 0.01       # 1% - max price deviation across platforms (upper buffer)

# Scoring feature weights and decay constants
SCORING_TAU_TIME = 1800               # Time decay constant (30 minutes)
SCORING_W_TIME = 2.0                  # Weight for time feature (f_time)
SCORING_W_VALUE = 8.0                 # Weight for amount feature (f_amount, based on fee rate range)


# ==================== Fetcher Config ====================

FETCHER_DEFAULT_TOP_K = 5      # 默认返回 top-k 结果（避免返回过多数据）


# ==================== TraceTx State Initialization Config ====================

# Default parameters for initializing TraceTxState
TRACETX_SEARCH_TIME_SPAN = 1800    # 搜索时间窗口（秒） (-span, +0)
TRACETX_SEARCH_PRICE_BUFFER = 0.05  # 价格搜索缓冲区（5%）
TRACETX_CHECK_TIME_SPAN = 300      # 价格检查时间窗口（秒）(-span, +span)

def get_tracetx_search_time_window(anchor_time: int, time_span: int) -> tuple[int, int]:
    return ensure_ts_seconds(anchor_time) - time_span, ensure_ts_seconds(anchor_time) + 0
def get_tracetx_check_time_window(anchor_time: int, time_span: int) -> tuple[int, int]:
    return ensure_ts_seconds(anchor_time) - time_span, ensure_ts_seconds(anchor_time) + time_span

# ==================== API Keys (from environment variables) ====================

# BTC/DOGE APIs
BLOCKCYPHER_TOKEN = os.getenv("BLOCKCYPHER_TOKEN", "")
BLOCKCHAIR_API_KEY = os.getenv("BLOCKCHAIR_API_KEY", "")
BITQUERY_API_KEY = os.getenv("BITQUERY_API_KEY", "")

# ETH APIs
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY", "")
INFURA_PROJECT_ID = os.getenv("INFURA_PROJECT_ID", "")

# Price/Exchange rate APIs (for cross-chain amount matching)
# Binance: 无需 API key，完全免费
CRYPTOCOMPARE_API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY", "")  # Optional, 备用方案


# ==================== LLM Config ====================

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_MODEL_LITE = os.getenv("LLM_MODEL_LITE", "gpt-4o-mini")  # 用于简单任务，成本更低
LLM_TEMPERATURE = 0.1  # 低温度，减少随机性，提高确定性
LLM_MAX_TOKENS = 8192  # 最大输出 token 数

# Per-agent model configuration
# Each agent can have its own model override. If None or empty, uses default.
AGENT_MODELS = {
    "trace_orchestrator": os.getenv("AGENT_MODEL_ORCHESTRATOR") or None,
    "trace_fetcher": os.getenv("AGENT_MODEL_FETCHER") or None,
    "router": os.getenv("AGENT_MODEL_ROUTER") or LLM_MODEL_LITE,  # Default to lite
    "report": os.getenv("AGENT_MODEL_REPORT") or LLM_MODEL_LITE,  # Default to lite
}

def get_agent_model(agent_name: str) -> str:
    """Get the model for a specific agent.

    Args:
        agent_name: Name of the agent (e.g., "trace_orchestrator", "trace_fetcher")

    Returns:
        Model name to use for this agent
    """
    return AGENT_MODELS.get(agent_name) or LLM_MODEL

# LLM Retry Config (for rate limit handling)
LLM_MAX_RETRIES = 5  # 最大重试次数
LLM_TIMEOUT = 120  # 单次请求超时（秒）
LLM_RETRY_MIN_WAIT = 2  # 最小等待时间（秒）
LLM_RETRY_MAX_WAIT = 60  # 最大等待时间（秒）
LLM_RETRY_MULTIPLIER = 2  # 指数退避乘数


# ==================== Supported Chains ====================

# v0 支持的链（使用简化标识符）
# 格式：<CHAIN> 或 <CHAIN>-<network>
# 使用大写字母缩写，统一用 - 连接

SUPPORTED_CHAINS = [
    # Bitcoin 系列
    "BTC",           # Bitcoin 主网
    "BTC-test",      # Bitcoin 测试网
    "DOGE",          # Dogecoin
    "LTC",           # Litecoin
    "BCH",           # Bitcoin Cash

    # Ethereum 系列
    "ETH",           # Ethereum 主网
    "ETH-sepolia",   # Ethereum Sepolia 测试网
    "ETH-goerli",    # Ethereum Goerli 测试网

    # Layer 2 (v1+ 扩展)
    "ARB",           # Arbitrum
    "OP",            # Optimism
    "MATIC",         # Polygon
    "BASE",          # Base
]

# Chain type classification
UTXO_CHAINS = ["BTC", "DOGE", "LTC", "BCH"]  # UTXO-based chains
ACCOUNT_CHAINS = ["ETH", "ARB", "OP", "MATIC", "BASE"]  # Account-based chains

# Asset decimals (token precision)
# Format: "CHAIN.ASSET" -> decimals
# Used for converting between raw units (satoshi/wei) and human-readable units
ASSET_DECIMALS = {
    # Bitcoin-like native tokens (8 decimals)
    "BTC.BTC": 8,
    "DOGE.DOGE": 8,
    "LTC.LTC": 8,
    "BCH.BCH": 8,
    # Ethereum-like native tokens (18 decimals)
    "ETH.ETH": 18,
    "ARB.ETH": 18,
    "OP.ETH": 18,
    "MATIC.MATIC": 18,
    "BASE.ETH": 18,
    # Common stablecoins (6 decimals)
    "ETH.USDT": 6,
    "ETH.USDC": 6,
    # Wrapped tokens
    "ETH.WETH": 18,
    "ETH.WBTC": 8,
}

def get_asset_decimals(chain: str, asset: str = None) -> int:
    """获取资产的 decimals，用于 raw/human 单位转换

    Args:
        chain: 链标识符 (e.g., "BTC", "ETH")
        asset: 资产标识符，默认为链的原生代币

    Returns:
        decimals 值
    """
    base_chain = chain.upper().split("-")[0]
    if asset is None:
        asset = base_chain  # 默认原生代币
    key = f"{base_chain}.{asset.upper()}"
    return ASSET_DECIMALS.get(key, 8)  # 默认 8

def get_asset_unit(chain: str, asset: str = None) -> float:
    """获取资产的单位转换因子 (10^decimals)"""
    return 10 ** get_asset_decimals(chain, asset)

def validate_chain(chain: str) -> bool:
    """验证 chain 标识符是否有效"""
    return chain in SUPPORTED_CHAINS

def is_utxo_chain(chain: str) -> bool:
    """判断是否是 UTXO 链"""
    return chain.upper().split("-")[0] in UTXO_CHAINS

def is_account_chain(chain: str) -> bool:
    """判断是否是账户模型链"""
    return chain.upper().split("-")[0] in ACCOUNT_CHAINS


# ==================== Logging Config ====================

import logging as _logging

# Unified verbosity configuration
# Controls both logging level and debug output detail
VERBOSE_LEVEL = int(os.getenv("VERBOSE_LEVEL", "0"))

def get_log_level() -> int:
    """
    Convert VERBOSE_LEVEL to Python logging level for root logger.

    Levels:
      0 -> WARNING (default, only show warnings and errors)
      1 -> INFO (basic workflow information)
      2 -> INFO (business code will be promoted to DEBUG separately)
      3+ -> DEBUG (everything including third-party libraries)
    """
    if VERBOSE_LEVEL == 0:
        return _logging.WARNING
    elif VERBOSE_LEVEL == 1:
        return _logging.INFO
    elif VERBOSE_LEVEL == 2:
        return _logging.INFO  # Root stays at INFO to suppress third-party DEBUG
    else:  # >= 3
        return _logging.DEBUG

def setup_logging():
    """
    Configure logging based on VERBOSE_LEVEL using namespace isolation.

    This is the recommended way to set up logging for the entire application.
    Call this once at application startup (in main.py or benchmark/__main__.py).

    Logging levels:
      0: WARNING  - Only warnings and errors (all loggers)
      1: INFO     - Basic workflow information (all loggers)
      2: DEBUG    - Business code (src.*, benchmark.*) + INFO for third-party
      3: DEBUG    - Everything including third-party libraries

    Implementation:
      - Uses logger namespace hierarchy (src.*, benchmark.*)
      - No need to maintain third-party library lists
      - New business modules automatically inherit DEBUG at level 2
      - New third-party libraries automatically stay at INFO at level 2
    """
    root_logger = _logging.getLogger()
    root_level = get_log_level()
    root_logger.setLevel(root_level)

    if VERBOSE_LEVEL == 2:
        # Level 2: Promote business code to DEBUG, keep third-party at INFO
        # Only set our business namespaces to DEBUG
        _logging.getLogger('src').setLevel(_logging.DEBUG)
        _logging.getLogger('benchmark').setLevel(_logging.DEBUG)
        # Root logger stays at INFO (affects all third-party loggers)

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"  # Only show time (HH:MM:SS), no date or milliseconds


# ==================== Development/Debug Config ====================

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
VERBOSE_ERRORS = DEBUG_MODE  # 是否在 error 中包含完整 traceback
