#!/usr/bin/env python3
"""
Daily Push Module
生成 MD 文档并推送到 Telegram 和 GitHub
"""

import os
import logging
from datetime import datetime
from pathlib import Path
import asyncio
import base64
import requests

# Telegram
from telegram import Bot
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# GitHub 配置
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPO', 'cherieli/antigravity-bot')
GITHUB_BRANCH = os.getenv('GITHUB_BRANCH', 'main')

# 配置
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Obsidian 配置
# 注意：这是 iCloud 路径，云端无法直接访问
# 需要通过其他方式同步（如 GitHub、Dropbox API 等）
OBSIDIAN_VAULT_PATH = os.getenv(
    'OBSIDIAN_VAULT_PATH',
    '/Users/cherieli/Library/Mobile Documents/iCloud~md~obsidian/Documents/Antigravity'
)

# 文件存储路径（云端临时存储）
CLOUD_STORAGE_PATH = os.getenv('CLOUD_STORAGE_PATH', './data')


def ensure_dirs():
    """确保必要的目录存在"""
    dirs = [
        f"{CLOUD_STORAGE_PATH}/MarketMonitor",
        f"{CLOUD_STORAGE_PATH}/Momentum50",
        f"{CLOUD_STORAGE_PATH}/Archives",
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


# ============== MD 生成 ==============

def generate_market_monitor_md(data: dict, analysis: str) -> str:
    """
    生成 Market Monitor Markdown 文档

    Args:
        data: Market Monitor 数据
        analysis: AI 分析结果

    Returns:
        str: Markdown 内容
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    latest = data.get("latest", {}) if data else {}

    # 构建表格数据
    table_rows = []
    if data and data.get("data"):
        for row in data["data"][:10]:  # 最近10天
            table_rows.append(
                f"| {row.get('date', '')} | {row.get('up_4pct', '')} | "
                f"{row.get('down_4pct', '')} | {row.get('ratio_5d', '')} | "
                f"{row.get('ratio_10d', '')} |"
            )

    table_content = "\n".join(table_rows) if table_rows else "| 暂无数据 |"

    md_content = f"""---
title: Market Monitor {date_str}
date: {date_str}
time: {time_str}
type: daily-push
source: stockbee
tags:
  - market-breadth
  - daily-monitor
---

# Market Monitor {date_str}

> 更新时间: {time_str}
> 来源: [Stockbee Market Monitor](https://stockbee.blogspot.com/p/mm.html)

## 今日数据

| 日期 | 涨4%+ | 跌4%+ | 5日比 | 10日比 |
|------|-------|-------|-------|--------|
{table_content}

## AI 分析

{analysis}

## 关键指标说明

- **涨/跌4%+**: 当日涨跌幅超过4%的股票数量
- **5日/10日比**: 涨跌比，>1 表示多头主导，<1 表示空头主导
- **极值信号**: 当涨4%+>500 或 <50 时，通常预示反转

## 快速链接

- [Market Monitor](https://stockbee.blogspot.com/p/mm.html)
- [指标说明](https://stockbee.blogspot.com/2022/12/market-monitor-scans.html)

---
*自动生成于 {now.strftime("%Y-%m-%d %H:%M:%S")}*
"""

    return md_content


def generate_momentum50_md(data: dict, analysis: str, descriptions: dict = None) -> str:
    """
    生成 Momentum 50 Markdown 文档

    Args:
        data: Momentum 50 数据
        analysis: AI 分析结果
        descriptions: 股票简介字典

    Returns:
        str: Markdown 内容
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    tickers = data.get("tickers", []) if data else []
    new_entries = data.get("new_entries", []) if data else []
    dropped = data.get("dropped", []) if data else []
    descriptions = descriptions or {}

    # 构建榜单表格
    ticker_rows = []
    for i, ticker in enumerate(tickers[:50], 1):
        desc = descriptions.get(ticker, "-")
        is_new = "🆕" if ticker in new_entries else ""
        ticker_rows.append(f"| {i} | {ticker} {is_new} | {desc} |")

    ticker_table = "\n".join(ticker_rows) if ticker_rows else "| 暂无数据 |"

    # TradingView watchlist
    tv_list = ",".join([f"NASDAQ:{t}" for t in tickers[:50]])

    # 新进入标的
    new_entries_section = ""
    if new_entries:
        new_items = []
        for ticker in new_entries[:10]:
            desc = descriptions.get(ticker, "")
            new_items.append(f"- **{ticker}**: {desc}")
        new_entries_section = "\n".join(new_items)
    else:
        new_entries_section = "今日无新进入标的"

    # 掉出标的
    dropped_section = ", ".join(dropped[:10]) if dropped else "无"

    md_content = f"""---
title: Momentum 50 {date_str}
date: {date_str}
time: {time_str}
type: daily-push
source: stockbee
tags:
  - momentum
  - watchlist
  - daily-monitor
---

# Momentum 50 {date_str}

> 更新时间: {time_str}
> 来源: [Stockbee Momentum 50](https://docs.google.com/spreadsheets/d/1xjbe9SF0HsxwY_Uy3NC2tT92BqK0nhArUaYU16Q0p9M)

## AI 分析

{analysis}

## 新进入榜单 🆕

{new_entries_section}

## 掉出榜单

{dropped_section}

## 完整榜单

| # | Ticker | 简介 |
|---|--------|------|
{ticker_table}

## TradingView Watchlist

<details>
<summary>点击复制到 TradingView</summary>

```
{tv_list}
```

</details>

## 使用方法

1. 复制上方代码
2. 打开 TradingView → Watchlist → 导入
3. 粘贴即可批量添加

---
*自动生成于 {now.strftime("%Y-%m-%d %H:%M:%S")}*
"""

    return md_content


def save_md_file(content: str, category: str, filename: str = None) -> str:
    """
    保存 MD 文件

    Args:
        content: MD 内容
        category: 类别 (MarketMonitor/Momentum50)
        filename: 文件名（可选）

    Returns:
        str: 保存的文件路径
    """
    ensure_dirs()

    if not filename:
        filename = f"{datetime.now().strftime('%Y-%m-%d')}.md"

    filepath = Path(CLOUD_STORAGE_PATH) / category / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    logger.info(f"MD 文件已保存: {filepath}")
    return str(filepath)


# ============== GitHub 推送 ==============

def push_to_github(content: str, category: str, filename: str = None) -> bool:
    """
    推送 MD 文件到 GitHub obsidian-content 目录

    Args:
        content: MD 内容
        category: 类别 (MarketMonitor/Momentum50)
        filename: 文件名（可选）

    Returns:
        bool: 是否成功
    """
    if not GITHUB_TOKEN:
        logger.warning("GitHub Token 未配置，跳过 GitHub 同步")
        return False

    if not filename:
        filename = f"{datetime.now().strftime('%Y-%m-%d')}.md"

    # GitHub API 路径
    file_path = f"obsidian-content/{category}/{filename}"
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Base64 编码内容
    content_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')

    try:
        # 检查文件是否存在（获取 SHA）
        existing = requests.get(api_url, headers=headers)
        sha = None
        if existing.status_code == 200:
            sha = existing.json().get('sha')

        # 准备请求数据
        data = {
            "message": f"Update {category}/{filename}",
            "content": content_b64,
            "branch": GITHUB_BRANCH
        }
        if sha:
            data["sha"] = sha

        # 创建或更新文件
        response = requests.put(api_url, headers=headers, json=data)

        if response.status_code in [200, 201]:
            logger.info(f"GitHub 同步成功: {file_path}")
            return True
        else:
            logger.error(f"GitHub 同步失败: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"GitHub 同步异常: {e}")
        return False


# ============== Telegram 推送 ==============

async def send_telegram_message(
    text: str,
    parse_mode: str = ParseMode.MARKDOWN,
    disable_preview: bool = True
) -> bool:
    """
    发送 Telegram 消息

    Args:
        text: 消息内容
        parse_mode: 解析模式
        disable_preview: 是否禁用链接预览

    Returns:
        bool: 是否成功
    """
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("Telegram 配置不完整")
        return False

    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(
            chat_id=CHAT_ID,
            text=text,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_preview
        )
        logger.info("Telegram 消息发送成功")
        return True
    except Exception as e:
        logger.error(f"Telegram 发送失败: {e}")
        return False


def format_market_monitor_telegram(data: dict, analysis: str, ob_link: str = None) -> str:
    """
    格式化 Market Monitor Telegram 消息

    Args:
        data: Market Monitor 数据
        analysis: AI 分析
        ob_link: Obsidian 链接

    Returns:
        str: 格式化的消息
    """
    latest = data.get("latest", {}) if data else {}
    date_str = datetime.now().strftime("%Y-%m-%d")

    # 提取关键数据
    up_4pct = latest.get("up_4pct", "N/A")
    down_4pct = latest.get("down_4pct", "N/A")
    ratio_5d = latest.get("ratio_5d", "N/A")
    ratio_10d = latest.get("ratio_10d", "N/A")

    # 判断市场情绪
    emoji = "📊"
    if isinstance(ratio_5d, (int, float)):
        if ratio_5d > 1.2:
            emoji = "🟢"
        elif ratio_5d < 0.8:
            emoji = "🔴"
        else:
            emoji = "🟡"

    message = f"""{emoji} *Market Monitor {date_str}*

📈 涨4%+: `{up_4pct}` | 📉 跌4%+: `{down_4pct}`
📊 5日比: `{ratio_5d}` | 10日比: `{ratio_10d}`

*分析:*
{analysis[:500]}

🔗 [详细数据](https://stockbee.blogspot.com/p/mm.html)"""

    if ob_link:
        message += f"\n📝 [Obsidian]({ob_link})"

    return message


def format_momentum50_telegram(data: dict, analysis: str, ob_link: str = None) -> str:
    """
    格式化 Momentum 50 Telegram 消息

    Args:
        data: Momentum 50 数据
        analysis: AI 分析
        ob_link: Obsidian 链接

    Returns:
        str: 格式化的消息
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    tickers = data.get("tickers", [])[:10] if data else []
    new_entries = data.get("new_entries", []) if data else []

    ticker_preview = " ".join([f"`{t}`" for t in tickers])

    new_section = ""
    if new_entries:
        new_tickers = " ".join([f"`{t}`" for t in new_entries[:5]])
        new_section = f"\n🆕 *新进入:* {new_tickers}"

    message = f"""🚀 *Momentum 50 {date_str}*

*Top 10:*
{ticker_preview}
{new_section}

*分析:*
{analysis[:400]}

🔗 [完整榜单](https://docs.google.com/spreadsheets/d/1xjbe9SF0HsxwY_Uy3NC2tT92BqK0nhArUaYU16Q0p9M)"""

    if ob_link:
        message += f"\n📝 [Obsidian]({ob_link})"

    return message


# ============== 完整流程 ==============

async def push_market_monitor():
    """
    Market Monitor 完整推送流程
    """
    from scrapers.market_monitor import fetch_market_monitor, analyze_trend
    from utils.ai_analyzer import analyze_market_breadth

    logger.info("开始 Market Monitor 推送...")

    # 1. 抓取数据
    data = fetch_market_monitor()
    if not data:
        await send_telegram_message("❌ Market Monitor 数据获取失败")
        return False

    # 2. AI 分析
    analysis = analyze_market_breadth(data)

    # 3. 生成 MD
    md_content = generate_market_monitor_md(data, analysis)
    md_path = save_md_file(md_content, "MarketMonitor")

    # 4. 推送到 GitHub
    push_to_github(md_content, "MarketMonitor")

    # 5. 发送 Telegram
    # 注意：ob_link 需要配合 Obsidian URI scheme 使用
    # 格式: obsidian://open?vault=Antigravity&file=10_DailyPush/MarketMonitor/2026-02-04
    date_str = datetime.now().strftime("%Y-%m-%d")
    ob_link = f"obsidian://open?vault=Antigravity&file=10_DailyPush/MarketMonitor/{date_str}"

    message = format_market_monitor_telegram(data, analysis, ob_link)
    await send_telegram_message(message)

    logger.info("Market Monitor 推送完成")
    return True


async def push_momentum50():
    """
    Momentum 50 完整推送流程
    """
    from scrapers.momentum50 import fetch_momentum50
    from utils.ai_analyzer import analyze_momentum_stocks, get_ticker_descriptions

    logger.info("开始 Momentum 50 推送...")

    # 1. 抓取数据
    data = fetch_momentum50()
    if not data:
        await send_telegram_message("❌ Momentum 50 数据获取失败")
        return False

    # 2. 获取股票简介（可选，消耗 API）
    descriptions = {}
    if data.get("new_entries"):
        descriptions = get_ticker_descriptions(data["new_entries"][:10])

    # 3. AI 分析
    analysis = analyze_momentum_stocks(data)

    # 4. 生成 MD
    md_content = generate_momentum50_md(data, analysis, descriptions)
    md_path = save_md_file(md_content, "Momentum50")

    # 5. 推送到 GitHub
    push_to_github(md_content, "Momentum50")

    # 6. 发送 Telegram
    date_str = datetime.now().strftime("%Y-%m-%d")
    ob_link = f"obsidian://open?vault=Antigravity&file=10_DailyPush/Momentum50/{date_str}"

    message = format_momentum50_telegram(data, analysis, ob_link)
    await send_telegram_message(message)

    logger.info("Momentum 50 推送完成")
    return True


async def daily_push_all():
    """
    执行所有每日推送
    """
    logger.info("=" * 50)
    logger.info("开始每日推送")
    logger.info("=" * 50)

    results = {
        "market_monitor": await push_market_monitor(),
        "momentum50": await push_momentum50(),
    }

    success_count = sum(results.values())
    total_count = len(results)

    summary = f"📋 每日推送完成: {success_count}/{total_count} 成功"
    await send_telegram_message(summary)

    return results


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)

    # 测试生成 MD
    test_data = {
        "latest": {
            "date": "2/3/2026",
            "up_4pct": 321,
            "down_4pct": 531,
            "ratio_5d": 0.59,
            "ratio_10d": 0.96,
        },
        "data": [
            {"date": "2/3/2026", "up_4pct": 321, "down_4pct": 531, "ratio_5d": 0.59, "ratio_10d": 0.96},
            {"date": "2/2/2026", "up_4pct": 274, "down_4pct": 200, "ratio_5d": 0.69, "ratio_10d": 0.96},
        ]
    }

    md = generate_market_monitor_md(test_data, "测试分析内容")
    print(md[:500])

    # 测试 Telegram 格式
    tg_msg = format_market_monitor_telegram(test_data, "市场短期偏弱，需要关注反弹信号")
    print("\n" + tg_msg)
