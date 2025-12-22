"""
System-wide configuration for BlockchainMAS v0

This file contains all magic numbers, thresholds, and environment-based settings.
For v0, config is static (requires restart to change). For v1+, consider adding
runtime-modifiable ConfigState in GraphState.
"""

import os
from typing import Literal

from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


# ==================== Agent Loop Limits ====================

# Trace workflow
TRACE_MAX_ITERATIONS = 10      # Orchestrator 最大迭代次数
TRACE_MAX_DEPTH = 5            # 跨链溯源最大跳数（CrossChainLink 数量上限）
TRACE_MAX_ERRORS = 100         # Error 列表软上限（超过后考虑终止）
TRACE_ERRORS_WARNING = 50      # Error 警告阈值（触发策略评估）

# Fallback workflow
FALLBACK_MAX_ITERATIONS = 8    # Fallback Orchestrator 最大迭代次数
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

# Exponential decay parameters (for time/value features)
CCLINK_TAU_TIME_BRIDGE = 30 * 60      # 桥的时间衰减常数 (30分钟)
CCLINK_TAU_TIME_EXCHANGE = 12 * 3600  # 交易所的时间衰减常数 (12小时)
CCLINK_TAU_VALUE = 0.05               # 价值衰减常数 (5%)


# ==================== Fetcher Config ====================

FETCHER_DEFAULT_TOP_K = 5      # 默认返回 top-k 结果（避免返回过多数据）


# ==================== API Keys (from environment variables) ====================

# BTC/DOGE APIs
BLOCKCYPHER_TOKEN = os.getenv("BLOCKCYPHER_TOKEN", "")
BLOCKCHAIR_API_KEY = os.getenv("BLOCKCHAIR_API_KEY", "")
BITQUERY_API_KEY = os.getenv("BITQUERY_API_KEY", "")

# ETH APIs
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY", "")
INFURA_PROJECT_ID = os.getenv("INFURA_PROJECT_ID", "")

# Price/Exchange rate APIs (for cross-chain value matching)
# Binance: 无需 API key，完全免费
CRYPTOCOMPARE_API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY", "")  # Optional, 备用方案


# ==================== LLM Config ====================

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_TEMPERATURE = 0.1  # 低温度，减少随机性，提高确定性
LLM_MAX_TOKENS = 4096  # 最大输出 token 数


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

def validate_chain(chain: str) -> bool:
    """验证 chain 标识符是否有效"""
    return chain in SUPPORTED_CHAINS


# ==================== Logging Config ====================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


# ==================== Development/Debug Config ====================

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
VERBOSE_ERRORS = DEBUG_MODE  # 是否在 error 中包含完整 traceback


# ==================== v1+ Preview (not used in v0) ====================

# 以下配置在 v1 中才会使用，v0 中暂时忽略

# Memory config
MEMORY_ENABLED = False  # v1+ feature
MEMORY_MAX_ENTRIES = 100
MEMORY_EMBEDDING_MODEL = "text-embedding-ada-002"

# Storage config
STORAGE_ENABLED = False  # v1+ feature
STORAGE_BACKEND: Literal["sqlite", "postgres", "mongodb"] = "sqlite"
STORAGE_PATH = "./data/blockchain_mas.db"

# Advanced error handling
ERR_SUMMARY_NODE_ENABLED = False  # v1+ feature: LLM-based error compression
ERR_SUMMARY_KEEP_RECENT = 20      # 压缩时保留最近的 N 条 error
