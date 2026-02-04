#!/usr/bin/env python3
"""
Momentum 50 Scraper
从 Stockbee / Google Sheets 抓取 Momentum 50 数据

数据源：
1. Stockbee 页面嵌入的 Google Sheets
2. 直接访问已知的 Google Sheets URL
"""

import requests
import csv
import re
from io import StringIO
from datetime import datetime
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

# Stockbee Momentum 50 页面 URL
STOCKBEE_M50_URL = "https://stockbee.blogspot.com/p/momentum-50.html"

# Google Sheet 配置
SHEET_ID = "1xjbe9SF0HsxwY_Uy3NC2tT92BqK0nhArUaYU16Q0p9M"

# 年份对应的 GID（每年可能需要更新）
YEAR_GIDS = {
    "2026": "1499398020",
    "2025": "0",  # 默认 sheet
    "2024": "1234567890",  # 示例，需要确认
}

# 默认 Headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def fetch_momentum50() -> dict:
    """
    抓取 Momentum 50 数据

    尝试多种方法获取数据:
    1. 从 Stockbee 页面获取 iframe 中的 Google Sheets URL
    2. 直接访问已知的 Google Sheets CSV 导出 URL
    3. 尝试 pubhtml 格式

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
    # 方法1: 从 Stockbee 页面获取 iframe URL
    try:
        logger.info("方法1: 尝试从 Stockbee 页面获取数据...")
        result = fetch_from_stockbee_page()
        if result and result.get('tickers'):
            logger.info(f"从 Stockbee 页面获取成功: {len(result['tickers'])} 个标的")
            return result
    except Exception as e:
        logger.warning(f"从 Stockbee 页面获取失败: {e}")

    # 方法2: 直接尝试 CSV 导出（当前年份）
    current_year = str(datetime.now().year)
    gid = YEAR_GIDS.get(current_year, YEAR_GIDS.get("2026", "0"))

    try:
        logger.info(f"方法2: 尝试直接 CSV 导出 (年份={current_year}, GID={gid})...")
        csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
        result = fetch_from_csv_url(csv_url)
        if result and result.get('tickers'):
            logger.info(f"从 CSV 导出获取成功: {len(result['tickers'])} 个标的")
            return result
    except Exception as e:
        logger.warning(f"CSV 导出失败: {e}")

    # 方法3: 尝试 pubhtml 格式
    try:
        logger.info("方法3: 尝试 pubhtml 格式...")
        pubhtml_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/pubhtml?gid={gid}"
        result = fetch_from_pubhtml(pubhtml_url)
        if result and result.get('tickers'):
            logger.info(f"从 pubhtml 获取成功: {len(result['tickers'])} 个标的")
            return result
    except Exception as e:
        logger.warning(f"pubhtml 格式失败: {e}")

    # 方法4: 尝试其他年份的 GID
    for year, alt_gid in YEAR_GIDS.items():
        if alt_gid == gid:
            continue
        try:
            logger.info(f"方法4: 尝试备用 GID (年份={year}, GID={alt_gid})...")
            csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={alt_gid}"
            result = fetch_from_csv_url(csv_url)
            if result and result.get('tickers'):
                logger.info(f"从备用 GID 获取成功: {len(result['tickers'])} 个标的")
                return result
        except Exception as e:
            logger.warning(f"备用 GID {alt_gid} 失败: {e}")

    logger.error("所有 Momentum 50 数据获取方法都失败了")
    return None


def fetch_from_stockbee_page() -> dict:
    """
    从 Stockbee 页面获取嵌入的 Google Sheets URL
    """
    response = requests.get(STOCKBEE_M50_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')

    # 查找 iframe
    iframes = soup.find_all('iframe')
    for iframe in iframes:
        src = iframe.get('src', '')
        if 'docs.google.com/spreadsheets' in src:
            logger.info(f"找到 Google Sheets iframe: {src[:80]}...")

            # 提取 sheet ID 和 gid
            sheet_id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', src)
            if not sheet_id_match:
                sheet_id_match = re.search(r'/d/e/([a-zA-Z0-9_-]+)', src)

            if sheet_id_match:
                sheet_id = sheet_id_match.group(1)
                gid_match = re.search(r'gid=(\d+)', src)
                gid = gid_match.group(1) if gid_match else "0"

                # 尝试 CSV 导出
                csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
                result = fetch_from_csv_url(csv_url)
                if result:
                    result['source'] = 'stockbee_page'
                    return result

    return None


def fetch_from_csv_url(csv_url: str) -> dict:
    """
    从 Google Sheets CSV 导出 URL 获取数据
    """
    response = requests.get(csv_url, headers=HEADERS, timeout=30)

    # 检查是否是 CSV 内容
    content_type = response.headers.get('content-type', '')
    if response.status_code != 200:
        logger.warning(f"CSV 请求失败: {response.status_code}")
        return None

    if 'text/csv' not in content_type and 'text/plain' not in content_type:
        # 可能是 HTML 错误页面
        if 'html' in content_type.lower():
            logger.warning("收到 HTML 而非 CSV，可能需要公开分享")
            return None

    return parse_csv_content(response.text)


def fetch_from_pubhtml(pubhtml_url: str) -> dict:
    """
    从 Google Sheets pubhtml 格式获取数据
    """
    response = requests.get(pubhtml_url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    tables = soup.find_all('table')

    for table in tables:
        result = parse_html_table(table)
        if result and result.get('tickers') and len(result['tickers']) >= 10:
            result['source'] = 'pubhtml'
            return result

    return None


def parse_csv_content(csv_text: str) -> dict:
    """
    解析 CSV 内容

    预期格式:
    - 第一行是日期（列标题）
    - 后续行是各列对应的股票代码
    """
    reader = csv.reader(StringIO(csv_text))
    rows = list(reader)

    if len(rows) < 2:
        logger.warning("CSV 数据行数不足")
        return None

    # 第一行是日期
    dates = [d.strip() for d in rows[0] if d.strip()]

    if not dates:
        logger.warning("无法解析日期行")
        return None

    # 构建历史数据
    history = {}
    for col_idx, date in enumerate(rows[0]):
        if not date or date.strip() == "":
            continue

        date = date.strip()
        tickers = []
        for row in rows[1:51]:  # 获取前50行数据
            if col_idx < len(row) and row[col_idx]:
                ticker = row[col_idx].strip().upper()
                # 过滤无效的 ticker
                if ticker and ticker != "" and is_valid_ticker(ticker):
                    tickers.append(ticker)

        if tickers:
            history[date] = tickers

    if not history:
        logger.warning("未解析到有效数据")
        return None

    # 获取最新日期的数据（第一列）
    first_valid_date = None
    for date in rows[0]:
        date = date.strip() if date else ""
        if date and date in history:
            first_valid_date = date
            break

    latest_date = first_valid_date
    latest_tickers = history.get(latest_date, [])

    # 计算新进入和掉出
    new_entries = []
    dropped = []

    sorted_dates = [d.strip() for d in rows[0] if d.strip() and d.strip() in history]
    if len(sorted_dates) >= 2:
        prev_date = sorted_dates[1]
        prev_tickers = set(history.get(prev_date, []))
        curr_tickers = set(latest_tickers)

        new_entries = sorted(list(curr_tickers - prev_tickers))
        dropped = sorted(list(prev_tickers - curr_tickers))

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "latest_date": latest_date,
        "tickers": latest_tickers,
        "history": history,
        "new_entries": new_entries,
        "dropped": dropped,
        "source": "google_sheets_csv"
    }


def parse_html_table(table) -> dict:
    """
    解析 HTML 表格（pubhtml 格式）
    """
    rows = table.find_all('tr')
    if len(rows) < 2:
        return None

    # 提取表头（日期）
    header_row = rows[0]
    dates = []
    for cell in header_row.find_all(['td', 'th']):
        text = cell.get_text(strip=True)
        if text and re.match(r'\d{1,2}/\d{1,2}/\d{4}', text):
            dates.append(text)

    if not dates:
        return None

    # 构建历史数据
    history = {date: [] for date in dates}

    for row in rows[1:51]:  # 前50行数据
        cells = row.find_all(['td', 'th'])
        for col_idx, cell in enumerate(cells):
            if col_idx < len(dates):
                text = cell.get_text(strip=True).upper()
                if text and is_valid_ticker(text):
                    history[dates[col_idx]].append(text)

    # 过滤空列表
    history = {k: v for k, v in history.items() if v}

    if not history:
        return None

    latest_date = dates[0] if dates[0] in history else None
    latest_tickers = history.get(latest_date, [])

    # 计算新进入和掉出
    new_entries = []
    dropped = []

    if len(dates) >= 2 and dates[1] in history:
        prev_tickers = set(history[dates[1]])
        curr_tickers = set(latest_tickers)
        new_entries = sorted(list(curr_tickers - prev_tickers))
        dropped = sorted(list(prev_tickers - curr_tickers))

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "latest_date": latest_date,
        "tickers": latest_tickers,
        "history": history,
        "new_entries": new_entries,
        "dropped": dropped,
    }


def is_valid_ticker(ticker: str) -> bool:
    """
    验证是否是有效的股票代码
    """
    if not ticker or len(ticker) > 6:
        return False
    # 股票代码通常是1-5个大写字母，可能带数字
    if not re.match(r'^[A-Z]{1,5}[A-Z0-9]*$', ticker):
        return False
    # 排除常见的非股票代码
    invalid_patterns = ['DATE', 'TICKER', 'STOCK', 'NAME', 'N/A', 'NA', 'NULL']
    if ticker in invalid_patterns:
        return False
    return True


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
