#!/usr/bin/env python3
"""
AI Analyzer with Rate Limiting
使用 Gemini/Claude 进行分析，带限流功能
"""

import os
import time
import logging
from datetime import datetime, timedelta
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)

# API 配置
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# 限流配置
RATE_LIMIT = {
    "gemini": {
        "requests_per_minute": 10,  # 保守设置
        "requests_per_day": 1000,
        "cooldown_seconds": 6,  # 每次请求间隔
    },
    "claude": {
        "requests_per_minute": 20,
        "requests_per_day": 5000,
        "cooldown_seconds": 3,
    }
}

# 请求计数器
request_counter = {
    "gemini": {"count": 0, "last_reset": datetime.now(), "last_request": None},
    "claude": {"count": 0, "last_reset": datetime.now(), "last_request": None}
}


class RateLimitExceeded(Exception):
    """速率限制异常"""
    pass


def rate_limit(provider: str):
    """
    限流装饰器

    Args:
        provider: "gemini" 或 "claude"
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            await check_rate_limit(provider)
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            check_rate_limit_sync(provider)
            return func(*args, **kwargs)

        # 根据函数类型返回对应的 wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


async def check_rate_limit(provider: str):
    """异步检查限流"""
    config = RATE_LIMIT.get(provider, RATE_LIMIT["gemini"])
    counter = request_counter.get(provider, request_counter["gemini"])

    # 重置每日计数
    if datetime.now() - counter["last_reset"] > timedelta(days=1):
        counter["count"] = 0
        counter["last_reset"] = datetime.now()

    # 检查每日限制
    if counter["count"] >= config["requests_per_day"]:
        raise RateLimitExceeded(f"{provider} 每日请求限制已达到")

    # 检查冷却时间
    if counter["last_request"]:
        elapsed = (datetime.now() - counter["last_request"]).total_seconds()
        if elapsed < config["cooldown_seconds"]:
            wait_time = config["cooldown_seconds"] - elapsed
            logger.debug(f"等待冷却: {wait_time:.1f}秒")
            await asyncio.sleep(wait_time)

    # 更新计数器
    counter["count"] += 1
    counter["last_request"] = datetime.now()


def check_rate_limit_sync(provider: str):
    """同步检查限流"""
    config = RATE_LIMIT.get(provider, RATE_LIMIT["gemini"])
    counter = request_counter.get(provider, request_counter["gemini"])

    # 重置每日计数
    if datetime.now() - counter["last_reset"] > timedelta(days=1):
        counter["count"] = 0
        counter["last_reset"] = datetime.now()

    # 检查每日限制
    if counter["count"] >= config["requests_per_day"]:
        raise RateLimitExceeded(f"{provider} 每日请求限制已达到")

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


# ============== Gemini API ==============

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


@rate_limit("gemini")
def analyze_with_gemini(prompt: str, max_retries: int = 3) -> str:
    """
    使用 Gemini 分析

    Args:
        prompt: 分析提示词
        max_retries: 最大重试次数

    Returns:
        str: 分析结果
    """
    global gemini_model

    if not gemini_model:
        if not init_gemini():
            return "Gemini API 未配置"

    for attempt in range(max_retries):
        try:
            response = gemini_model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_msg = str(e).lower()

            # 检查是否是速率限制错误
            if "rate" in error_msg or "quota" in error_msg or "429" in error_msg:
                wait_time = 30 * (attempt + 1)  # 递增等待时间
                logger.warning(f"Gemini 速率限制，等待 {wait_time} 秒后重试")
                time.sleep(wait_time)
                continue

            # 其他错误
            logger.error(f"Gemini 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return f"分析失败: {str(e)}"

            time.sleep(5)

    return "分析失败: 超过最大重试次数"


# ============== Claude API ==============

anthropic_client = None


def init_claude():
    """初始化 Claude"""
    global anthropic_client

    if not ANTHROPIC_API_KEY:
        logger.warning("未配置 ANTHROPIC_API_KEY")
        return False

    try:
        import anthropic
        anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        logger.info("Claude 初始化成功")
        return True
    except Exception as e:
        logger.error(f"Claude 初始化失败: {e}")
        return False


@rate_limit("claude")
def analyze_with_claude(prompt: str, max_retries: int = 3) -> str:
    """
    使用 Claude 分析

    Args:
        prompt: 分析提示词
        max_retries: 最大重试次数

    Returns:
        str: 分析结果
    """
    global anthropic_client

    if not anthropic_client:
        if not init_claude():
            return "Claude API 未配置"

    for attempt in range(max_retries):
        try:
            message = anthropic_client.messages.create(
                model="claude-3-5-haiku-20241022",  # 使用较便宜的模型
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except Exception as e:
            error_msg = str(e).lower()

            if "rate" in error_msg or "429" in error_msg:
                wait_time = 30 * (attempt + 1)
                logger.warning(f"Claude 速率限制，等待 {wait_time} 秒后重试")
                time.sleep(wait_time)
                continue

            logger.error(f"Claude 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return f"分析失败: {str(e)}"

            time.sleep(5)

    return "分析失败: 超过最大重试次数"


# ============== 智能路由 ==============

def analyze(prompt: str, prefer: str = "gemini") -> str:
    """
    使用 Gemini 分析（不再回退到 Claude）

    Args:
        prompt: 分析提示词
        prefer: 保留参数，但只使用 Gemini

    Returns:
        str: 分析结果
    """
    # 只使用 Gemini
    try:
        result = analyze_with_gemini(prompt)
        if not result.startswith("分析失败") and "未配置" not in result:
            return result
        logger.warning(f"Gemini 分析失败: {result}")
        return None  # 返回 None 让调用方使用规则分析
    except RateLimitExceeded as e:
        logger.warning(f"Gemini 速率限制: {e}")
        return None
    except Exception as e:
        logger.warning(f"Gemini 异常: {e}")
        return None


# ============== 专用分析函数 ==============

def analyze_market_breadth(data: dict) -> str:
    """
    分析市场宽度数据

    Args:
        data: Market Monitor 数据

    Returns:
        str: 分析结果
    """
    if not data or not data.get("latest"):
        return "无数据可分析"

    latest = data["latest"]

    # 获取数值（用于规则分析）
    up_4pct = latest.get('up_4pct', 0)
    down_4pct = latest.get('down_4pct', 0)
    ratio_5d = latest.get('ratio_5d', 1.0)
    ratio_10d = latest.get('ratio_10d', 1.0)

    # 尝试转换为数字
    try:
        up_4pct = int(up_4pct) if up_4pct != 'N/A' else 0
        down_4pct = int(down_4pct) if down_4pct != 'N/A' else 0
        ratio_5d = float(ratio_5d) if ratio_5d != 'N/A' else 1.0
        ratio_10d = float(ratio_10d) if ratio_10d != 'N/A' else 1.0
    except (ValueError, TypeError):
        pass

    prompt = f"""分析美股市场宽度数据，直接输出结论，不要开场白：

数据：涨4%+: {up_4pct}只 | 跌4%+: {down_4pct}只 | 5日比: {ratio_5d} | 10日比: {ratio_10d}

输出格式（严格遵守，每行一句话）：
1. 强弱：[偏强/偏弱/震荡] - [原因]
2. 信号：[关键观察]
3. 建议：[积极/观望/减仓] - [理由]

规则：涨跌比>1多头占优，<1空头占优；大涨或大跌>400是极端信号"""

    # 尝试 AI 分析
    ai_result = analyze(prompt, prefer="gemini")

    # 如果 AI 成功，返回结果
    if ai_result:
        return ai_result

    # AI 失败，使用简单规则分析
    logger.info("AI 不可用，使用规则分析")

    # 规则分析
    analysis_parts = []

    # 1. 今日强弱判断
    if up_4pct > down_4pct * 1.5:
        analysis_parts.append(f"📈 今天市场偏强，大涨股({up_4pct}只)明显多于大跌股({down_4pct}只)")
    elif down_4pct > up_4pct * 1.5:
        analysis_parts.append(f"📉 今天市场偏弱，大跌股({down_4pct}只)明显多于大涨股({up_4pct}只)")
    else:
        analysis_parts.append(f"⚖️ 今天市场震荡，涨跌股票数量接近（涨{up_4pct}/跌{down_4pct}）")

    # 2. 趋势判断
    if ratio_5d > 1.2 and ratio_10d > 1.2:
        analysis_parts.append("短期和中期趋势都向上，市场较健康")
    elif ratio_5d < 0.8 and ratio_10d < 0.8:
        analysis_parts.append("短期和中期都在走弱，需要谨慎")
    elif ratio_5d > 1 and ratio_10d < 1:
        analysis_parts.append("短期有反弹迹象，但中期仍偏弱")
    elif ratio_5d < 1 and ratio_10d > 1:
        analysis_parts.append("短期有回调，但中期趋势仍在")

    # 3. 极端信号
    if up_4pct > 400:
        analysis_parts.append(f"⚠️ 大涨股超400只({up_4pct})，可能是短期过热信号")
    if down_4pct > 400:
        analysis_parts.append(f"⚠️ 大跌股超400只({down_4pct})，可能接近恐慌底部")

    # 4. 操作建议
    if ratio_5d > 1.2 and up_4pct > down_4pct:
        analysis_parts.append("💡 建议：趋势向上，可以积极一些")
    elif ratio_5d < 0.8 and down_4pct > up_4pct:
        analysis_parts.append("💡 建议：趋势向下，观望或减仓")
    else:
        analysis_parts.append("💡 建议：震荡市，轻仓观望")

    return "\n".join(analysis_parts)


def analyze_momentum_stocks(data: dict, include_descriptions: bool = True) -> str:
    """
    分析 Momentum 50 数据

    Args:
        data: Momentum 50 数据
        include_descriptions: 是否包含股票简介

    Returns:
        str: 分析结果
    """
    if not data:
        return "无数据可分析"

    tickers = data.get("tickers", [])[:20]  # 前20个
    new_entries = data.get("new_entries", [])
    dropped = data.get("dropped", [])

    ticker_list = ", ".join(tickers)
    new_list = ", ".join(new_entries[:10]) if new_entries else "无"
    dropped_list = ", ".join(dropped[:10]) if dropped else "无"

    prompt = f"""你是专业的美股动量交易分析师。请分析以下 Momentum 50 榜单：

日期: {data.get('latest_date', 'N/A')}
榜单前20: {ticker_list}
今日新进入: {new_list}
今日掉出: {dropped_list}

请提供：
1. 榜单特征（哪些板块/主题占主导，1-2句话）
2. 新进入标的点评（如有，每个标的一句话简介+看点）
3. 热点趋势判断
4. 注意事项

要求：
- 对每个新进入的标的，提供一句话公司简介（10-15字）
- 重点关注是否有板块轮动迹象
- 回答简洁，适合手机阅读

直接输出分析，不要加开场白。"""

    return analyze(prompt, prefer="gemini")


def get_ticker_descriptions(tickers: list) -> dict:
    """
    批量获取股票简介

    Args:
        tickers: 股票代码列表

    Returns:
        dict: {ticker: description}
    """
    if not tickers:
        return {}

    # 分批处理，每批10个
    batch_size = 10
    all_descriptions = {}

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        ticker_list = ", ".join(batch)

        prompt = f"""请为以下美股标的提供简短介绍（每个10-15字，只写主营业务）：

{ticker_list}

格式（严格遵守）：
TICKER: 简介

示例：
AAPL: iPhone及消费电子巨头
NVDA: AI芯片龙头，GPU领导者

只输出格式化结果，不要其他内容。"""

        result = analyze(prompt, prefer="gemini")

        # 解析结果
        for line in result.strip().split('\n'):
            if ':' in line:
                parts = line.split(':', 1)
                ticker = parts[0].strip().upper()
                desc = parts[1].strip() if len(parts) > 1 else ""
                if ticker in batch:
                    all_descriptions[ticker] = desc

        # 批次间等待
        if i + batch_size < len(tickers):
            time.sleep(2)

    return all_descriptions


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)

    # 测试 Gemini
    print("测试 Gemini...")
    result = analyze("用一句话解释什么是市场宽度指标", prefer="gemini")
    print(f"结果: {result[:200]}...")

    # 测试限流
    print("\n测试限流...")
    for i in range(3):
        start = time.time()
        result = analyze("测试", prefer="gemini")
        elapsed = time.time() - start
        print(f"请求 {i + 1}: {elapsed:.1f}秒")
