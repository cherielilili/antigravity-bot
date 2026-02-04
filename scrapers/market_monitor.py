#!/usr/bin/env python3
"""
Market Monitor Scraper
从 Stockbee 抓取市场宽度数据
使用 Playwright 渲染页面获取 iframe 内的数据
"""

import asyncio
import re
import logging
from datetime import datetime
from typing import Optional, Dict, List

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
}

# 极值阈值
EXTREME_THRESHOLDS = {
    "up_4pct": {"extreme_high": 500, "high": 300, "low": 100},
    "down_4pct": {"extreme_high": 500, "high": 300, "low": 100},
    "ratio_5d": {"extreme_high": 2.0, "high": 1.5, "low": 0.5, "extreme_low": 0.3},
    "ratio_10d": {"extreme_high": 1.5, "high": 1.2, "low": 0.8, "extreme_low": 0.6},
}


def parse_int(s: str) -> int:
    try:
        return int(s.replace(',', '').strip())
    except:
        return 0


def parse_float(s: str) -> float:
    try:
        return float(s.replace(',', '').strip())
    except:
        return 0.0


async def fetch_with_playwright() -> Optional[Dict]:
    """使用 Playwright 渲染页面并提取数据"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright 未安装")
        return None

    logger.info("使用 Playwright 获取 Market Monitor 数据...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto(MM_URL, wait_until='networkidle', timeout=60000)
            logger.info("页面加载完成，等待 iframe...")

            await page.wait_for_selector('iframe[src*="docs.google.com"]', timeout=30000)

            frames = page.frames
            google_frame = None
            for frame in frames:
                if 'docs.google.com' in frame.url:
                    google_frame = frame
                    break

            if not google_frame:
                logger.error("未找到 Google Sheets iframe")
                await browser.close()
                return None

            logger.info(f"找到 iframe: {google_frame.url[:60]}...")

            await google_frame.wait_for_selector('table', timeout=30000)

            rows_data = await google_frame.evaluate('''() => {
                const tables = document.querySelectorAll('table');
                for (const table of tables) {
                    const rows = table.querySelectorAll('tr');
                    if (rows.length < 5) continue;
                    const data = [];
                    for (const row of rows) {
                        const cells = row.querySelectorAll('td, th');
                        const rowData = [];
                        for (const cell of cells) {
                            rowData.push(cell.textContent.trim());
                        }
                        if (rowData.length > 0) {
                            data.push(rowData);
                        }
                    }
                    if (data.length > 5) return data;
                }
                return [];
            }''')

            await browser.close()

            if not rows_data or len(rows_data) < 3:
                logger.error("未能提取表格数据")
                return None

            logger.info(f"提取到 {len(rows_data)} 行原始数据")

            data = parse_table_data(rows_data)
            if data:
                return {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "data": data,
                    "latest": data[0] if data else None,
                    "source": "playwright"
                }

            return None

        except Exception as e:
            logger.error(f"Playwright 获取失败: {e}")
            await browser.close()
            return None


def parse_table_data(rows: List[List[str]]) -> List[Dict]:
    """解析表格数据"""
    data = []

    for row in rows:
        if len(row) < 7:
            continue

        first_cell = row[0]
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
    """抓取 Market Monitor 数据"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    result = loop.run_until_complete(fetch_with_playwright())

    if result:
        logger.info(f"成功获取 {len(result.get('data', []))} 条数据")
    else:
        logger.error("Market Monitor 数据获取失败")

    return result


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
