#!/usr/bin/env python3
"""
Momentum 50 Scraper
从 Google Sheets 抓取 Stockbee Momentum 50 数据
"""

import requests
import csv
from io import StringIO
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Google Sheet 配置
SHEET_ID = "1xjbe9SF0HsxwY_Uy3NC2tT92BqK0nhArUaYU16Q0p9M"
GID = "1499398020"  # 2026 tab

# CSV 导出 URL
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"


def fetch_momentum50() -> dict:
    """
    抓取 Momentum 50 数据

    Returns:
        dict: {
            "date": "2026-02-03",
            "tickers": ["ANL", "GITS", "AZN", ...],  # 最新的50个
            "history": {
                "02/03/2026": ["ANL", "GITS", ...],
                "02/02/2026": ["TCGL", "ANL", ...],
                ...
            },
            "new_entries": ["ANL", "AZN"],  # 今天新进入榜单的
            "dropped": ["XYZ", "ABC"],  # 今天掉出榜单的
        }
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

        response = requests.get(CSV_URL, headers=headers, timeout=30)
        response.raise_for_status()

        # 解析 CSV
        reader = csv.reader(StringIO(response.text))
        rows = list(reader)

        if len(rows) < 2:
            logger.warning("Momentum 50 数据为空")
            return None

        # 第一行是日期
        dates = rows[0]

        # 构建历史数据
        history = {}
        for col_idx, date in enumerate(dates):
            if not date or date.strip() == "":
                continue

            tickers = []
            for row in rows[1:51]:  # 获取前50行
                if col_idx < len(row) and row[col_idx]:
                    ticker = row[col_idx].strip().upper()
                    if ticker and ticker != "":
                        tickers.append(ticker)

            if tickers:
                history[date] = tickers

        # 获取最新日期的数据
        latest_date = dates[0] if dates else None
        latest_tickers = history.get(latest_date, [])

        # 计算新进入和掉出的标的
        new_entries = []
        dropped = []

        if len(dates) >= 2 and dates[1] in history:
            prev_tickers = set(history[dates[1]])
            curr_tickers = set(latest_tickers)

            new_entries = list(curr_tickers - prev_tickers)
            dropped = list(prev_tickers - curr_tickers)

        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "latest_date": latest_date,
            "tickers": latest_tickers,
            "history": history,
            "new_entries": new_entries,
            "dropped": dropped,
            "source": "google_sheets"
        }

    except Exception as e:
        logger.error(f"抓取 Momentum 50 失败: {e}")
        return None


def get_tradingview_watchlist(tickers: list) -> str:
    """
    生成 TradingView watchlist 格式的字符串
    可以直接复制粘贴到 TradingView

    Args:
        tickers: 股票代码列表

    Returns:
        str: TradingView 格式的 watchlist
    """
    # TradingView 格式：每行一个代码，或者逗号分隔
    # 添加 NASDAQ/NYSE 前缀
    formatted = []
    for ticker in tickers:
        # 默认使用 NASDAQ，大部分 momentum 股票在 NASDAQ
        formatted.append(f"NASDAQ:{ticker}")

    return ",".join(formatted)


def get_ticker_info_prompt(tickers: list) -> str:
    """
    生成用于 AI 获取股票简介的 prompt

    Args:
        tickers: 股票代码列表

    Returns:
        str: AI prompt
    """
    ticker_list = ", ".join(tickers[:20])  # 只取前20个避免太长

    return f"""请为以下美股标的提供简短介绍（每个不超过15字）：

{ticker_list}

格式：
TICKER: 一句话描述公司主营业务

示例：
AAPL: 全球最大消费电子公司，iPhone制造商
NVDA: AI芯片龙头，GPU市场领导者

请直接按格式输出，不要其他解释。"""


def analyze_momentum_changes(data: dict) -> dict:
    """
    分析 Momentum 50 变化情况

    Args:
        data: fetch_momentum50 返回的数据

    Returns:
        dict: 分析结果
    """
    if not data:
        return {"error": "无数据"}

    analysis = {
        "date": data.get("latest_date"),
        "total_count": len(data.get("tickers", [])),
        "new_count": len(data.get("new_entries", [])),
        "dropped_count": len(data.get("dropped", [])),
        "turnover_rate": 0,
        "signals": [],
    }

    # 计算换手率
    if analysis["total_count"] > 0:
        analysis["turnover_rate"] = round(
            analysis["new_count"] / analysis["total_count"] * 100, 1
        )

    # 生成信号
    if analysis["turnover_rate"] > 20:
        analysis["signals"].append({
            "type": "high_turnover",
            "message": f"换手率较高 ({analysis['turnover_rate']}%)，市场热点可能在切换"
        })

    if analysis["new_count"] > 10:
        analysis["signals"].append({
            "type": "many_new_entries",
            "message": f"今日新进入 {analysis['new_count']} 只股票，关注新热点"
        })

    # 检查历史连续性
    if data.get("history"):
        dates = sorted(data["history"].keys(), reverse=True)
        if len(dates) >= 3:
            # 检查最近3天都在榜单的股票（持续强势）
            persistent = set(data["history"][dates[0]])
            for date in dates[1:3]:
                persistent &= set(data["history"][date])

            analysis["persistent_leaders"] = list(persistent)[:10]

    return analysis


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)

    result = fetch_momentum50()
    if result:
        print(f"日期: {result.get('latest_date')}")
        print(f"获取到 {len(result.get('tickers', []))} 个标的")
        print(f"前10个: {result.get('tickers', [])[:10]}")
        print(f"新进入: {result.get('new_entries', [])}")
        print(f"掉出: {result.get('dropped', [])}")

        # TradingView watchlist
        tv_list = get_tradingview_watchlist(result.get('tickers', []))
        print(f"\nTradingView Watchlist (前5个):")
        print(",".join(tv_list.split(",")[:5]))

        # 分析
        analysis = analyze_momentum_changes(result)
        print(f"\n分析结果: {analysis}")
    else:
        print("获取数据失败")
