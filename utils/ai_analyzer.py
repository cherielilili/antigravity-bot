#!/usr/bin/env python3
"""
AI Analyzer - 支持多个大模型提供商
优先使用智谱 GLM，备选 Gemini

支持的提供商:
- 智谱 AI (GLM-4-Flash) - 推荐，便宜且稳定
- Google Gemini (备选)
"""

import os
import time
import logging
from datetime import datetime, timedelta
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)

# ============== API 配置 ==============
# 智谱 AI
ZHIPU_API_KEY = os.getenv('ZHIPU_API_KEY')
# Gemini (备选)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 默认提供商优先级
DEFAULT_PROVIDER = os.getenv('AI_PROVIDER', 'zhipu')  # zhipu 或 gemini

# ============== 限流配置 ==============
RATE_LIMIT = {
    "zhipu": {
        "requests_per_minute": 30,
        "cooldown_seconds": 2,
    },
    "gemini": {
        "requests_per_minute": 10,
        "cooldown_seconds": 6,
    }
}

# 请求计数器
request_counter = {
    "zhipu": {"count": 0, "last_reset": datetime.now(), "last_request": None},
    "gemini": {"count": 0, "last_reset": datetime.now(), "last_request": None}
}


class RateLimitExceeded(Exception):
    """速率限制异常"""
    pass


def check_rate_limit_sync(provider: str):
    """同步检查限流"""
    config = RATE_LIMIT.get(provider, RATE_LIMIT["zhipu"])
    counter = request_counter.get(provider, request_counter["zhipu"])

    # 重置每分钟计数
    if datetime.now() - counter["last_reset"] > timedelta(minutes=1):
        counter["count"] = 0
        counter["last_reset"] = datetime.now()

    # 检查每分钟限制
    if counter["count"] >= config["requests_per_minute"]:
        raise RateLimitExceeded(f"{provider} 每分钟请求限制已达到")

    # 检查冷却时间
    if counter["last_request"]:
        elapsed = (datetime.now() - counter["last_request"]).total_seconds()
        if elapsed < config["cooldown_seconds"]:
            wait_time = config["cooldown_seconds"] - elapsed
            logger.debug(f"等待冷却: {wait_time:.1f}秒")
            time.sleep(wait_time)

    # 更新计数器
    counter["count"] += 1
    counter["last_request"] = datetime.now()


# ============== 智谱 AI (GLM) ==============

zhipu_client = None


def init_zhipu():
    """初始化智谱 AI"""
    global zhipu_client

    if not ZHIPU_API_KEY:
        logger.warning("未配置 ZHIPU_API_KEY")
        return False

    try:
        from zhipuai import ZhipuAI
        zhipu_client = ZhipuAI(api_key=ZHIPU_API_KEY)
        logger.info("智谱 AI 初始化成功")
        return True
    except ImportError:
        logger.error("请安装 zhipuai: pip install zhipuai")
        return False
    except Exception as e:
        logger.error(f"智谱 AI 初始化失败: {e}")
        return False


def analyze_with_zhipu(prompt: str, max_retries: int = 3) -> str:
    """
    使用智谱 GLM 分析

    Args:
        prompt: 分析提示词
        max_retries: 最大重试次数

    Returns:
        str: 分析结果，失败返回 None
    """
    global zhipu_client

    if not zhipu_client:
        if not init_zhipu():
            return None

    for attempt in range(max_retries):
        try:
            check_rate_limit_sync("zhipu")

            response = zhipu_client.chat.completions.create(
                model="glm-4-flash",  # 便宜快速的模型
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1024,
            )

            result = response.choices[0].message.content
            logger.info(f"智谱分析成功 (尝试 {attempt + 1})")
            return result

        except RateLimitExceeded as e:
            logger.warning(f"智谱速率限制: {e}")
            return None

        except Exception as e:
            error_msg = str(e).lower()

            # 速率限制错误
            if "rate" in error_msg or "quota" in error_msg or "429" in str(e):
                wait_time = 10 * (attempt + 1)
                logger.warning(f"智谱 API 限制，等待 {wait_time} 秒")
                time.sleep(wait_time)
                continue

            # 其他错误
            logger.error(f"智谱调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return None

            time.sleep(3)

    return None


# ============== Gemini API (备选) ==============

gemini_model = None


def init_gemini():
    """初始化 Gemini"""
    global gemini_model

    if not GEMINI_API_KEY:
        logger.warning("未配置 GEMINI_API_KEY")
        return False

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel('gemini-2.0-flash')
        logger.info("Gemini 初始化成功")
        return True
    except Exception as e:
        logger.error(f"Gemini 初始化失败: {e}")
        return False


def analyze_with_gemini(prompt: str, max_retries: int = 2) -> str:
    """
    使用 Gemini 分析 (备选)

    Returns:
        str: 分析结果，失败返回 None
    """
    global gemini_model

    if not gemini_model:
        if not init_gemini():
            return None

    for attempt in range(max_retries):
        try:
            check_rate_limit_sync("gemini")
            response = gemini_model.generate_content(prompt)
            return response.text

        except RateLimitExceeded:
            return None

        except Exception as e:
            error_msg = str(e).lower()

            if "rate" in error_msg or "quota" in error_msg or "429" in error_msg:
                logger.warning(f"Gemini API 限制")
                return None

            logger.error(f"Gemini 调用失败: {e}")
            if attempt == max_retries - 1:
                return None

            time.sleep(5)

    return None


# ============== 统一分析入口 ==============

def analyze(prompt: str, prefer: str = None) -> str:
    """
    统一 AI 分析入口，自动选择可用的提供商

    优先级:
    1. 智谱 GLM (如果配置了 ZHIPU_API_KEY)
    2. Gemini (如果配置了 GEMINI_API_KEY)
    3. 返回 None (让调用方使用规则分析)

    Args:
        prompt: 分析提示词
        prefer: 优先使用的提供商 (可选)

    Returns:
        str: 分析结果，如果所有提供商都失败则返回 None
    """
    provider = prefer or DEFAULT_PROVIDER

    # 尝试主要提供商
    if provider == "zhipu" and ZHIPU_API_KEY:
        result = analyze_with_zhipu(prompt)
        if result:
            return result
        logger.info("智谱分析失败，尝试备选...")

    elif provider == "gemini" and GEMINI_API_KEY:
        result = analyze_with_gemini(prompt)
        if result:
            return result
        logger.info("Gemini 分析失败，尝试备选...")

    # 尝试备选提供商
    if provider != "zhipu" and ZHIPU_API_KEY:
        result = analyze_with_zhipu(prompt)
        if result:
            return result

    if provider != "gemini" and GEMINI_API_KEY:
        result = analyze_with_gemini(prompt)
        if result:
            return result

    # 所有提供商都失败
    logger.warning("所有 AI 提供商都不可用，将使用规则分析")
    return None


# ============== 专用分析函数 ==============

def analyze_market_breadth(data: dict) -> str:
    """
    分析市场宽度数据
    """
    if not data or not data.get("latest"):
        return "无数据可分析"

    latest = data["latest"]

    # 安全获取数值
    def safe_num(val, default=0, is_float=False):
        if val in [None, 'N/A', '', 'null']:
            return default
        try:
            return float(val) if is_float else int(val)
        except (ValueError, TypeError):
            return default

    up_4pct = safe_num(latest.get('up_4pct'), 0)
    down_4pct = safe_num(latest.get('down_4pct'), 0)
    ratio_5d = safe_num(latest.get('ratio_5d'), 1.0, is_float=True)
    ratio_10d = safe_num(latest.get('ratio_10d'), 1.0, is_float=True)
    up_25pct_qtr = safe_num(latest.get('up_25pct_qtr'), 0)
    down_25pct_qtr = safe_num(latest.get('down_25pct_qtr'), 0)

    prompt = f"""分析美股市场宽度数据，直接输出结论，不要开场白：

【短期指标】日涨4%+: {up_4pct} | 日跌4%+: {down_4pct} | 5日比: {ratio_5d} | 10日比: {ratio_10d}
【中期指标】季涨25%+: {up_25pct_qtr} | 季跌25%+: {down_25pct_qtr}

输出格式（严格遵守，每行末尾不要句号）：
1. 短期：[偏强/偏弱/震荡] - [简洁原因，用"个股"而非"股票"]
2. 中期：[偏强/偏弱] - [基于季度数据的简洁判断]
3. 信号：[无极端信号 或 具体信号]
4. 建议：[观望/积极/减仓] - [简洁建议，15字以内]

极端信号规则：
- 季涨25%+<350：底部区域
- 日涨4%+>1000且5日比>2：过热

示例输出：
1. 短期：偏弱 - 跌4%+个股数量明显多于涨4%+，5日比小于1，短期市场承压
2. 中期：偏强 - 季度上涨个股数量超过下跌个股数量
3. 信号：无极端信号
4. 建议：观望 - 短期市场偏弱，不建议追高，等待企稳信号，控制仓位"""

    # 尝试 AI 分析
    ai_result = analyze(prompt)

    if ai_result:
        return ai_result

    # AI 失败，使用规则分析
    return rule_based_market_analysis(up_4pct, down_4pct, ratio_5d, ratio_10d, up_25pct_qtr, down_25pct_qtr)


def rule_based_market_analysis(up_4pct, down_4pct, ratio_5d, ratio_10d, up_25pct_qtr, down_25pct_qtr) -> str:
    """规则分析 Market Monitor"""
    parts = []

    # 1. 短期判断
    if up_4pct > down_4pct * 1.5:
        parts.append(f"1. 短期：偏强 - 涨4%+({up_4pct})明显多于跌4%+({down_4pct})")
    elif down_4pct > up_4pct * 1.5:
        parts.append(f"1. 短期：偏弱 - 跌4%+({down_4pct})明显多于涨4%+({up_4pct})，5日比{ratio_5d}小于1")
    else:
        parts.append(f"1. 短期：震荡 - 涨跌接近（涨{up_4pct}/跌{down_4pct}）")

    # 2. 中期判断
    if up_25pct_qtr > down_25pct_qtr:
        parts.append(f"2. 中期：偏强 - 季度上涨个股({up_25pct_qtr})多于下跌({down_25pct_qtr})")
    else:
        parts.append(f"2. 中期：偏弱 - 季度下跌个股({down_25pct_qtr})多于上涨({up_25pct_qtr})")

    # 3. 极端信号
    if up_25pct_qtr < 350 and up_25pct_qtr > 0:
        parts.append(f"3. 信号：底部信号 - 季度涨25%+仅{up_25pct_qtr}只(<350)")
    elif up_4pct > 1000 and ratio_5d > 2:
        parts.append(f"3. 信号：过热警告 - 日涨4%+达{up_4pct}且5日比{ratio_5d}>2")
    else:
        parts.append("3. 信号：无极端信号")

    # 4. 建议
    if ratio_5d < 1 and down_4pct > up_4pct:
        parts.append("4. 建议：观望 - 短期市场偏弱，不建议追高，等待企稳信号，控制仓位")
    elif ratio_5d > 1.2:
        parts.append("4. 建议：积极 - 可适度加仓强势股，但控制单笔风险")
    else:
        parts.append("4. 建议：谨慎 - 保持观察，关注风险回报比")

    return "\n".join(parts)


def analyze_momentum_stocks(data: dict, include_descriptions: bool = True) -> str:
    """
    分析 Momentum 50 数据
    """
    if not data:
        return "无数据可分析"

    tickers = data.get("tickers", [])[:20]
    new_entries = data.get("new_entries", [])
    dropped = data.get("dropped", [])

    ticker_list = ", ".join(tickers)
    new_list = ", ".join(new_entries[:10]) if new_entries else "无"
    dropped_list = ", ".join(dropped[:10]) if dropped else "无"

    prompt = f"""你是专业的美股动量交易分析师。分析以下 Momentum 50 榜单：

日期: {data.get('latest_date', 'N/A')}
榜单前20: {ticker_list}
今日新进入: {new_list}
今日掉出: {dropped_list}

请提供简洁分析（适合手机阅读）：
1. 行业分布：哪些板块占主导（1-2句）
2. 新进标的点评：每个新进标的一句话（公司简介+关注点）
   格式: TICKER：[公司简介10字]。关注点：[看点]

要求：
- 如果不了解某只股票，写"未知"即可，不要编造
- 直接输出，不要开场白"""

    # 尝试 AI 分析
    ai_result = analyze(prompt)

    if ai_result:
        return ai_result

    # AI 失败，使用规则分析
    return rule_based_momentum_analysis(data)


def rule_based_momentum_analysis(data: dict) -> str:
    """规则分析 Momentum 50"""
    parts = []

    tickers = data.get("tickers", [])
    new_entries = data.get("new_entries", [])
    dropped = data.get("dropped", [])

    # 换手率
    if tickers:
        turnover = len(new_entries) / len(tickers) * 100
        if turnover > 20:
            parts.append(f"1. 行业分布：换手率较高({turnover:.0f}%)，市场热点可能在切换")
        else:
            parts.append(f"1. 行业分布：换手率{turnover:.0f}%，热点相对稳定")

    # 新进标的
    parts.append("\n2. 新进标的点评：")
    if new_entries:
        for ticker in new_entries[:10]:
            parts.append(f"{ticker}：需要进一步研究。关注点：新进榜单，关注突破形态")
    else:
        parts.append("今日无新进入标的")

    # 建议
    parts.append("\n3. 建议：")
    if len(new_entries) > 10:
        parts.append("- 新进标的较多，关注新热点但注意追高风险")
    else:
        parts.append("- 关注持续在榜的领涨股")
    parts.append("- 结合量价分析，设置止损控制风险")

    return "\n".join(parts)


def get_ticker_descriptions(tickers: list) -> dict:
    """
    批量获取股票简介
    """
    if not tickers:
        return {}

    ticker_list = ", ".join(tickers[:15])

    prompt = f"""请为以下美股标的提供简短介绍（每个10-15字，只写主营业务）：

{ticker_list}

格式（严格遵守）：
TICKER: 简介

示例：
AAPL: iPhone及消费电子巨头
NVDA: AI芯片龙头，GPU领导者

如果不了解某只股票，写 "TICKER: 未知" 即可。
只输出格式化结果，不要其他内容。"""

    result = analyze(prompt)

    descriptions = {}
    if result:
        for line in result.strip().split('\n'):
            if ':' in line:
                parts = line.split(':', 1)
                ticker = parts[0].strip().upper()
                desc = parts[1].strip() if len(parts) > 1 else "未知"
                if ticker in [t.upper() for t in tickers]:
                    descriptions[ticker] = desc

    # 填充未获取到的
    for ticker in tickers:
        if ticker.upper() not in descriptions:
            descriptions[ticker.upper()] = "未知"

    return descriptions


# ============== 测试 ==============

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 50)
    print("AI Analyzer 测试")
    print("=" * 50)

    # 检查配置
    print(f"\n配置状态:")
    print(f"  - 智谱 API Key: {'已配置' if ZHIPU_API_KEY else '未配置'}")
    print(f"  - Gemini API Key: {'已配置' if GEMINI_API_KEY else '未配置'}")
    print(f"  - 默认提供商: {DEFAULT_PROVIDER}")

    # 测试分析
    if ZHIPU_API_KEY or GEMINI_API_KEY:
        print("\n测试 AI 分析...")
        result = analyze("用一句话解释什么是市场宽度指标")
        if result:
            print(f"结果: {result[:200]}...")
        else:
            print("AI 分析失败，将使用规则分析")
    else:
        print("\n未配置任何 API Key，将使用规则分析")
