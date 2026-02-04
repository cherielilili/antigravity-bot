#!/usr/bin/env python3
"""
Market Monitor Scraper
从 Google Sheets 直接获取 CSV 数据
简单可靠的方案
"""

import csv
import io
import re
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# Google Sheets 直接导出 URL
SHEET_ID = "1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE"
SHEET_GID = "1082103394"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

# 指标说明
INDICATOR_MEANINGS = {
    "up_4pct": "当日涨幅超过4%的股票数量，高值=市场强势",
    "down_4pct": "当日跌幅超过4%的股票数量，高值=市场弱势",
    "ratio_5d": "5日涨跌比，>1=bullish, <1=bearish",
    "ratio_10d": "10日涨跌比，>1=bullish, <1=bearish",
}

# 极值阈值
EXTREME_THRESHOLDS = {
    "up_4pct": {"extreme_high": 500, "high": 300, "low": 100},
    "down_4pct": {"extreme_high": 500, "high": 300, "low": 100},
    "ratio_5d": {"extreme_high": 2.0, "high": 1.5, "low": 0.5, "extreme_low": 0.3},
    "ratio_10d": {"extreme_high": 1.5, "high": 1.2, "low": 0.8, "extreme_low": 0.6},
}


def parse_int(s: str) -> int:
    """解析整数，处理逗号分隔符"""
    try:
        return int(str(s).replace(',', '').strip())
    except:
        return 0


def parse_float(s: str) -> float:
    """解析浮点数"""
    try:
        return float(str(s).replace(',', '').strip())
    except:
        return 0.0


def fetch_csv_data() -> Optional[List[List[str]]]:
    """直接从 Google Sheets 获取 CSV 数据"""
    logger.info(f"正在从 Google Sheets 获取数据...")

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(CSV_URL, headers=headers, timeout=30)
        response.raise_for_status()

        # 解析 CSV
        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)

        logger.info(f"获取到 {len(rows)} 行数据")
        return rows

    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {e}")
        return None
    except Exception as e:
        logger.error(f"解析失败: {e}")
        return None


def parse_table_data(rows: List[List[str]]) -> List[Dict]:
    """解析表格数据"""
    data = []

    for row in rows:
        if len(row) < 7:
            continue

        first_cell = row[0].strip()
        # 检查是否是日期格式 (如 "2/3/2026")
        if not re.match(r'\d{1,2}/\d{1,2}/\d{4}', first_cell):
            continue

        try:
            row_data = {
                "date": first_cell,
                "up_4pct": parse_int(row[1]) if len(row) > 1 else 0,
                "down_4pct": parse_int(row[2]) if len(row) > 2 else 0,
                "ratio_5d": parse_float(row[3]) if len(row) > 3 else 0,
                "ratio_10d": parse_float(row[4]) if len(row) > 4 else 0,
                "up_25pct_qtr": parse_int(row[5]) if len(row) > 5 else 0,
                "down_25pct_qtr": parse_int(row[6]) if len(row) > 6 else 0,
            }

            # 额外指标
            if len(row) >= 11:
                row_data.update({
                    "up_25pct_month": parse_int(row[7]),
                    "down_25pct_month": parse_int(row[8]),
                    "up_50pct_month": parse_int(row[9]),
                    "down_50pct_month": parse_int(row[10]),
                })

            data.append(row_data)
        except Exception as e:
            logger.debug(f"解析行失败: {e}")
            continue

    return data


def fetch_market_monitor() -> Optional[Dict]:
    """抓取 Market Monitor 数据 - 主入口函数"""
    rows = fetch_csv_data()

    if not rows:
        logger.error("无法获取 CSV 数据")
        return None

    data = parse_table_data(rows)

    if not data:
        logger.error("无法解析表格数据")
        return None

    logger.info(f"成功获取 {len(data)} 条数据")

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "data": data,
        "latest": data[0] if data else None,
        "source": "google_sheets_csv"
    }


def analyze_trend(data: list, days: int = 5) -> dict:
    """分析趋势变化"""
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
            })
        elif "extreme_low" in thresholds and value <= thresholds["extreme_low"]:
            analysis["extremes"].append({
                "indicator": key,
                "value": value,
                "level": "extreme_low",
            })

    # 趋势变化
    if len(recent) >= 2:
        prev = recent[1]
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

    # 市场状态
    if latest.get("ratio_5d"):
        if latest["ratio_5d"] > 1.2:
            analysis["summary"].append("市场短期强势")
        elif latest["ratio_5d"] < 0.8:
            analysis["summary"].append("市场短期弱势")

    return analysis


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = fetch_market_monitor()
    if result:
        print(f"获取到 {len(result.get('data', []))} 天的数据")
        print(f"最新数据: {result.get('latest')}")
    else:
        print("获取数据失败")
