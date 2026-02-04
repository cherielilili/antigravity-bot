#!/usr/bin/env python3
"""
Market Monitor Scraper
从 Stockbee 抓取市场宽度数据
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import logging

logger = logging.getLogger(__name__)

# Market Monitor 页面 URL
MM_URL = "https://stockbee.blogspot.com/p/mm.html"

# 直接使用已知的 Google Sheets URL（公开分享的表格）
# 这个 Sheet 是 Stockbee 嵌入在页面中的，可以通过 pubhtml 访问
KNOWN_SHEET_URLS = [
    # Stockbee Market Monitor - 尝试多种格式
    "https://docs.google.com/spreadsheet/pub?key=0Am_cU8NLIU20dEhiQnVHN3Nnc3B1S3J6eGhKZFo0N3c&output=csv",
]
# 指标说明（用于分析）
INDICATOR_MEANINGS = {
    "up_4pct": "当日涨幅超过4%的股票数量，高值=市场强势",
    "down_4pct": "当日跌幅超过4%的股票数量，高值=市场弱势",
    "ratio_5d": "5日涨跌比，>1=bullish, <1=bearish",
    "ratio_10d": "10日涨跌比，>1=bullish, <1=bearish",
    "up_25pct_qtr": "季度涨幅超25%的股票数，高值=市场有动量",
    "down_25pct_qtr": "季度跌幅超25%的股票数，高值=市场承压",
    "up_25pct_month": "月涨幅超25%的股票数",
    "down_25pct_month": "月跌幅超25%的股票数",
    "up_50pct_month": "月涨幅超50%的股票数，高值=极端乐观",
    "down_50pct_month": "月跌幅超50%的股票数，高值=极端悲观",
}

# 极值阈值（用于判断极端情况）
EXTREME_THRESHOLDS = {
    "up_4pct": {"extreme_high": 500, "high": 300, "low": 100},
    "down_4pct": {"extreme_high": 500, "high": 300, "low": 100},
    "ratio_5d": {"extreme_high": 2.0, "high": 1.5, "low": 0.5, "extreme_low": 0.3},
    "ratio_10d": {"extreme_high": 1.5, "high": 1.2, "low": 0.8, "extreme_low": 0.6},
}


def fetch_market_monitor() -> dict:
    """
    抓取 Market Monitor 数据

    Returns:
        dict: {
            "date": "2026-02-03",
            "data": [
                {"date": "2/3/2026", "up_4pct": 321, "down_4pct": 531, ...},
                ...
            ],
            "latest": {...},  # 最新一天的数据
            "raw_html": "..."  # 原始 HTML（用于调试）
        }
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    # 方法1: 先尝试从 Stockbee 页面获取 iframe URL
    try:
        logger.info("尝试从 Stockbee 页面获取数据...")
        response = requests.get(MM_URL, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # 查找嵌入的 Google Sheet iframe
        iframes = soup.find_all('iframe')

        for iframe in iframes:
            src = iframe.get('src', '')
            logger.info(f"找到 iframe: {src[:100]}...")

            if 'docs.google.com/spreadsheets' in src:
                # 尝试从 iframe 获取数据
                result = fetch_from_google_sheets(src)
                if result and result.get('data'):
                    logger.info(f"从 Google Sheets iframe 获取到 {len(result['data'])} 条数据")
                    return result

    except Exception as e:
        logger.warning(f"从 Stockbee 页面获取失败: {e}")

    # 方法2: 尝试直接从已知的 Google Sheets 公开链接获取
    for known_url in KNOWN_SHEET_URLS:
        try:
            logger.info(f"尝试已知的 Sheet URL: {known_url[:50]}...")
            result = fetch_from_pubhtml(known_url)
            if result and result.get('data'):
                logger.info(f"从已知 URL 获取到 {len(result['data'])} 条数据")
                return result
        except Exception as e:
            logger.warning(f"从已知 URL 获取失败: {e}")
            continue

    logger.error("所有数据获取方法都失败了")
    return None


def fetch_from_pubhtml(pubhtml_url: str) -> dict:
    """
    从 Google Sheets 的 pubhtml 格式获取数据
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }

    try:
        response = requests.get(pubhtml_url, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # 查找所有表格
        tables = soup.find_all('table')

        for table in tables:
            data = parse_mm_table(table)
            if data and len(data) > 5:  # 确保有足够的数据
                return {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "data": data,
                    "latest": data[0] if data else None,
                    "source": "pubhtml"
                }

        return None

    except Exception as e:
        logger.error(f"从 pubhtml 获取数据失败: {e}")
        return None


def fetch_from_google_sheets(iframe_url: str) -> dict:
    """
    从 Google Sheets iframe URL 提取数据
    尝试多种方法: CSV导出, pubhtml, 直接HTML解析
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }

    # 从 iframe URL 提取 spreadsheet ID
    # 格式: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/...
    # 或者: https://docs.google.com/spreadsheets/d/e/PUBLISHED_ID/...
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', iframe_url)
    if not match:
        # 尝试 /d/e/ 格式
        match = re.search(r'/d/e/([a-zA-Z0-9_-]+)', iframe_url)

    if not match:
        logger.warning(f"无法从 URL 提取 Sheet ID: {iframe_url}")
        # 尝试直接获取 iframe 内容
        return fetch_from_pubhtml(iframe_url)

    sheet_id = match.group(1)

    # 尝试获取 gid
    gid_match = re.search(r'gid=(\d+)', iframe_url)
    gid = gid_match.group(1) if gid_match else "0"

    # 方法1: 尝试 CSV 导出
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    try:
        logger.info(f"尝试 CSV 导出: {csv_url[:60]}...")
        response = requests.get(csv_url, headers=headers, timeout=30)
        if response.status_code == 200 and 'text/csv' in response.headers.get('content-type', ''):
            lines = response.text.strip().split('\n')
            data = parse_csv_data(lines)
            if data and len(data) > 3:
                return {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "data": data,
                    "latest": data[0] if data else None,
                    "source": "google_sheets_csv",
                    "sheet_id": sheet_id
                }
    except Exception as e:
        logger.warning(f"CSV 导出失败: {e}")

    # 方法2: 尝试 pubhtml 格式
    pubhtml_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/pubhtml?gid={gid}"
    try:
        logger.info(f"尝试 pubhtml: {pubhtml_url[:60]}...")
        response = requests.get(pubhtml_url, headers=headers, timeout=30)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            tables = soup.find_all('table')
            for table in tables:
                data = parse_mm_table(table)
                if data and len(data) > 3:
                    return {
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "data": data,
                        "latest": data[0] if data else None,
                        "source": "google_sheets_pubhtml",
                        "sheet_id": sheet_id
                    }
    except Exception as e:
        logger.warning(f"pubhtml 获取失败: {e}")

    # 方法3: 直接获取原始 iframe URL
    try:
        logger.info(f"尝试直接获取 iframe: {iframe_url[:60]}...")
        response = requests.get(iframe_url, headers=headers, timeout=30)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            tables = soup.find_all('table')
            for table in tables:
                data = parse_mm_table(table)
                if data and len(data) > 3:
                    return {
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "data": data,
                        "latest": data[0] if data else None,
                        "source": "google_sheets_iframe",
                        "sheet_id": sheet_id
                    }
    except Exception as e:
        logger.warning(f"iframe 直接获取失败: {e}")

    logger.error(f"所有 Google Sheets 获取方法都失败了")
    return None


def parse_mm_table(table) -> list:
    """
    解析 Market Monitor HTML 表格
    支持多种表格格式
    """
    rows = table.find_all('tr')
    data = []

    # 找到数据行的起始位置（跳过表头）
    start_row = 0
    for i, row in enumerate(rows):
        cells = row.find_all(['td', 'th'])
        if cells:
            first_cell = cells[0].get_text(strip=True)
            # 检查是否是日期格式 (如 "2/3/2026" 或 "1/30/2026")
            if re.match(r'\d{1,2}/\d{1,2}/\d{4}', first_cell):
                start_row = i
                break

    # 解析数据行
    for row in rows[start_row:]:
        cells = row.find_all(['td', 'th'])
        if len(cells) < 7:
            continue

        try:
            first_cell = cells[0].get_text(strip=True)

            # 验证是日期格式
            if not re.match(r'\d{1,2}/\d{1,2}/\d{4}', first_cell):
                continue

            # 提取数据和颜色
            row_data = {
                "date": first_cell,
                "up_4pct": parse_int(cells[1].get_text(strip=True)),
                "down_4pct": parse_int(cells[2].get_text(strip=True)),
                "ratio_5d": parse_float(cells[3].get_text(strip=True)),
                "ratio_10d": parse_float(cells[4].get_text(strip=True)),
                "up_25pct_qtr": parse_int(cells[5].get_text(strip=True)),
                "down_25pct_qtr": parse_int(cells[6].get_text(strip=True)),
            }

            # 如果有更多列 (Secondary Breadth Indicators)
            if len(cells) >= 11:
                row_data.update({
                    "up_25pct_month": parse_int(cells[7].get_text(strip=True)),
                    "down_25pct_month": parse_int(cells[8].get_text(strip=True)),
                    "up_50pct_month": parse_int(cells[9].get_text(strip=True)),
                    "down_50pct_month": parse_int(cells[10].get_text(strip=True)),
                })

            # 额外列: 13% in 34 days 和 Worden
            if len(cells) >= 14:
                row_data.update({
                    "up_13pct_34d": parse_int(cells[11].get_text(strip=True)),
                    "down_13pct_34d": parse_int(cells[12].get_text(strip=True)),
                    "worden_universe": parse_int(cells[13].get_text(strip=True)),
                })

            # 提取颜色信息
            row_data["colors"] = extract_colors(cells)

            data.append(row_data)

        except Exception as e:
            logger.debug(f"解析行失败: {e}")
            continue

    return data


def parse_csv_data(lines: list) -> list:
    """
    解析 CSV 格式的 Market Monitor 数据
    """
    import csv
    from io import StringIO

    csv_content = '\n'.join(lines)
    reader = csv.reader(StringIO(csv_content))
    rows = list(reader)

    if len(rows) < 3:
        return []

    data = []
    # 跳过表头行（通常前2行）
    for row in rows[2:]:
        if len(row) < 8 or not row[0]:
            continue

        try:
            row_data = {
                "date": row[0],
                "up_4pct": parse_int(row[1]) if len(row) > 1 else 0,
                "down_4pct": parse_int(row[2]) if len(row) > 2 else 0,
                "ratio_5d": parse_float(row[3]) if len(row) > 3 else 0,
                "ratio_10d": parse_float(row[4]) if len(row) > 4 else 0,
                "up_25pct_qtr": parse_int(row[5]) if len(row) > 5 else 0,
                "down_25pct_qtr": parse_int(row[6]) if len(row) > 6 else 0,
            }

            if len(row) >= 12:
                row_data.update({
                    "up_25pct_month": parse_int(row[7]),
                    "down_25pct_month": parse_int(row[8]),
                    "up_50pct_month": parse_int(row[9]),
                    "down_50pct_month": parse_int(row[10]),
                })

            data.append(row_data)

        except Exception as e:
            logger.debug(f"解析CSV行失败: {e}")
            continue

    return data


def extract_colors(cells) -> dict:
    """
    从表格单元格提取背景颜色信息
    """
    colors = {}
    color_map = {
        'green': 'bullish',
        'lime': 'bullish',
        '#00ff00': 'bullish',
        '#90ee90': 'bullish',
        'red': 'bearish',
        '#ff0000': 'bearish',
        '#ff6666': 'bearish',
        'yellow': 'warning',
        '#ffff00': 'warning',
        '#ffff99': 'warning',
        'cyan': 'neutral',
    }

    for i, cell in enumerate(cells):
        style = cell.get('style', '')
        bgcolor = cell.get('bgcolor', '')

        color = None
        if bgcolor:
            color = bgcolor.lower()
        elif 'background' in style.lower():
            # 从 style 提取颜色
            match = re.search(r'background[^:]*:\s*([^;]+)', style, re.I)
            if match:
                color = match.group(1).strip().lower()

        if color:
            for color_key, sentiment in color_map.items():
                if color_key in color:
                    colors[f"cell_{i}"] = sentiment
                    break

    return colors


def analyze_trend(data: list, days: int = 5) -> dict:
    """
    分析趋势变化

    Args:
        data: Market Monitor 数据列表（按日期降序）
        days: 分析的天数

    Returns:
        dict: 趋势分析结果
    """
    if not data or len(data) < 2:
        return {"trend": "insufficient_data"}

    recent = data[:days]
    latest = recent[0]

    analysis = {
        "date": latest.get("date"),
        "summary": [],
        "signals": [],
        "extremes": [],
    }

    # 检查极值
    for key, thresholds in EXTREME_THRESHOLDS.items():
        value = latest.get(key)
        if value is None:
            continue

        if "extreme_high" in thresholds and value >= thresholds["extreme_high"]:
            analysis["extremes"].append({
                "indicator": key,
                "value": value,
                "level": "extreme_high",
                "meaning": INDICATOR_MEANINGS.get(key, "")
            })
        elif "extreme_low" in thresholds and value <= thresholds["extreme_low"]:
            analysis["extremes"].append({
                "indicator": key,
                "value": value,
                "level": "extreme_low",
                "meaning": INDICATOR_MEANINGS.get(key, "")
            })

    # 计算变化趋势
    if len(recent) >= 2:
        prev = recent[1]

        # 涨跌比变化
        if latest.get("ratio_5d") and prev.get("ratio_5d"):
            change = latest["ratio_5d"] - prev["ratio_5d"]
            if abs(change) > 0.1:
                direction = "improving" if change > 0 else "deteriorating"
                analysis["signals"].append({
                    "type": "ratio_change",
                    "indicator": "5日涨跌比",
                    "change": round(change, 2),
                    "direction": direction
                })

        # 大涨股票数量变化
        if latest.get("up_4pct") and prev.get("up_4pct"):
            change = latest["up_4pct"] - prev["up_4pct"]
            if abs(change) > 100:
                direction = "增加" if change > 0 else "减少"
                analysis["signals"].append({
                    "type": "breadth_change",
                    "indicator": "4%+涨幅股票数",
                    "change": change,
                    "direction": direction
                })

    # 生成总结
    if latest.get("ratio_5d"):
        if latest["ratio_5d"] > 1.2:
            analysis["summary"].append("市场短期强势，涨跌比健康")
        elif latest["ratio_5d"] < 0.8:
            analysis["summary"].append("市场短期弱势，需要谨慎")

    if analysis["extremes"]:
        analysis["summary"].append(f"检测到 {len(analysis['extremes'])} 个极值信号")

    return analysis


def parse_int(s: str) -> int:
    """安全解析整数"""
    try:
        return int(s.replace(',', '').strip())
    except:
        return 0


def parse_float(s: str) -> float:
    """安全解析浮点数"""
    try:
        return float(s.replace(',', '').strip())
    except:
        return 0.0


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)

    result = fetch_market_monitor()
    if result:
        print(f"获取到 {len(result.get('data', []))} 天的数据")
        print(f"最新数据: {result.get('latest')}")

        if result.get('data'):
            trend = analyze_trend(result['data'])
            print(f"趋势分析: {trend}")
    else:
        print("获取数据失败")
