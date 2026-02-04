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
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }

    try:
        response = requests.get(MM_URL, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # 查找嵌入的 Google Sheet iframe
        iframes = soup.find_all('iframe')
        sheet_url = None

        for iframe in iframes:
            src = iframe.get('src', '')
            if 'docs.google.com/spreadsheets' in src:
                sheet_url = src
                break

        if sheet_url:
            # 从 Google Sheets 获取数据
            return fetch_from_google_sheets(sheet_url)

        # 如果没有找到 iframe，尝试直接解析页面上的表格
        tables = soup.find_all('table')

        for table in tables:
            data = parse_mm_table(table)
            if data:
                return {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "data": data,
                    "latest": data[0] if data else None,
                    "source": "direct_scrape"
                }

        logger.warning("未找到 Market Monitor 表格")
        return None

    except Exception as e:
        logger.error(f"抓取 Market Monitor 失败: {e}")
        return None


def fetch_from_google_sheets(iframe_url: str) -> dict:
    """
    从 Google Sheets iframe URL 提取数据
    """
    # 从 iframe URL 提取 spreadsheet ID
    # 格式: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/...
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', iframe_url)
    if not match:
        logger.warning(f"无法从 URL 提取 Sheet ID: {iframe_url}")
        return None

    sheet_id = match.group(1)

    # 尝试获取 gid
    gid_match = re.search(r'gid=(\d+)', iframe_url)
    gid = gid_match.group(1) if gid_match else "0"

    # 构建 CSV 导出 URL
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

    try:
        response = requests.get(csv_url, timeout=30)
        response.raise_for_status()

        # 解析 CSV
        lines = response.text.strip().split('\n')
        data = parse_csv_data(lines)

        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "data": data,
            "latest": data[0] if data else None,
            "source": "google_sheets",
            "sheet_id": sheet_id
        }

    except Exception as e:
        logger.error(f"从 Google Sheets 获取数据失败: {e}")
        return None


def parse_mm_table(table) -> list:
    """
    解析 Market Monitor HTML 表格
    """
    rows = table.find_all('tr')
    data = []

    # 跳过表头行
    for row in rows[2:]:  # 假设前两行是表头
        cells = row.find_all(['td', 'th'])
        if len(cells) < 8:
            continue

        try:
            # 提取数据和颜色
            row_data = {
                "date": cells[0].get_text(strip=True),
                "up_4pct": parse_int(cells[1].get_text(strip=True)),
                "down_4pct": parse_int(cells[2].get_text(strip=True)),
                "ratio_5d": parse_float(cells[3].get_text(strip=True)),
                "ratio_10d": parse_float(cells[4].get_text(strip=True)),
                "up_25pct_qtr": parse_int(cells[5].get_text(strip=True)),
                "down_25pct_qtr": parse_int(cells[6].get_text(strip=True)),
            }

            # 如果有更多列
            if len(cells) >= 12:
                row_data.update({
                    "up_25pct_month": parse_int(cells[7].get_text(strip=True)),
                    "down_25pct_month": parse_int(cells[8].get_text(strip=True)),
                    "up_50pct_month": parse_int(cells[9].get_text(strip=True)),
                    "down_50pct_month": parse_int(cells[10].get_text(strip=True)),
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
