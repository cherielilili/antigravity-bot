#!/usr/bin/env python3
"""
Antigravity Telegram Bot v2.0
云端运行的投研助手 - 集成 AI 分析 + 定时推送
"""

import os
import sys
import logging
from datetime import datetime, time
import asyncio

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue,
)
import google.generativeai as genai

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 从环境变量获取配置
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
TIMEZONE = os.getenv('TIMEZONE', 'Asia/Shanghai')  # 中国时间

# 推送时间配置（中国时间）
PUSH_SCHEDULE = {
    "market_monitor": {"hour": 10, "minute": 0},  # 上午10:00
    "momentum50": {"hour": 10, "minute": 5},       # 上午10:05
}

# 配置 Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.0-flash')
    logger.info("✅ Gemini AI 已配置")
else:
    gemini_model = None
    logger.warning("⚠️ 未配置 GEMINI_API_KEY，AI 功能不可用")

# AI 系统提示词
SYSTEM_PROMPT = """你是 Antigravity 投研助手，一个专业的美股投资分析 AI。

你的特点：
1. 专注于美股市场，尤其是科技股和成长股
2. 分析风格：数据驱动、逻辑清晰、观点明确
3. 回答简洁有力，避免废话
4. 会主动指出风险和不确定性
5. 使用 emoji 让回复更易读

当用户问到具体标的时：
- 分析核心业务和竞争优势
- 指出关键的多空论点
- 给出需要关注的验证点

当用户分享文章或观点时：
- 提取核心论点
- 指出可能的盲点
- 关联到具体投资机会

请用中文回复，保持专业但友好的语气。回复控制在 300 字以内，除非用户要求详细分析。
"""


# ============== AI 功能 ==============

async def ask_ai(prompt: str, context: str = "") -> str:
    """调用 Gemini AI（带限流）"""
    if not gemini_model:
        return "❌ AI 功能未配置，请添加 GEMINI_API_KEY"

    try:
        full_prompt = f"{SYSTEM_PROMPT}\n\n"
        if context:
            full_prompt += f"上下文：{context}\n\n"
        full_prompt += f"用户消息：{prompt}"

        # 简单限流：每次调用等待
        await asyncio.sleep(1)

        response = gemini_model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        error_msg = str(e).lower()
        if "rate" in error_msg or "quota" in error_msg:
            logger.warning(f"Gemini 速率限制: {e}")
            return "⏳ AI 服务繁忙，请稍后再试"
        logger.error(f"AI 调用失败: {e}")
        return f"❌ AI 调用出错: {str(e)}"


# ============== 定时任务 ==============

async def scheduled_market_monitor(context: ContextTypes.DEFAULT_TYPE):
    """定时推送 Market Monitor"""
    logger.info("执行定时任务: Market Monitor")

    try:
        from utils.daily_push import push_market_monitor
        await push_market_monitor()
    except Exception as e:
        logger.error(f"Market Monitor 推送失败: {e}")
        if CHAT_ID:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=f"❌ Market Monitor 推送失败: {str(e)}"
            )


async def scheduled_momentum50(context: ContextTypes.DEFAULT_TYPE):
    """定时推送 Momentum 50"""
    logger.info("执行定时任务: Momentum 50")

    try:
        from utils.daily_push import push_momentum50
        await push_momentum50()
    except Exception as e:
        logger.error(f"Momentum 50 推送失败: {e}")
        if CHAT_ID:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=f"❌ Momentum 50 推送失败: {str(e)}"
            )


def setup_scheduled_jobs(application: Application):
    """设置定时任务"""
    job_queue = application.job_queue

    if not job_queue:
        logger.warning("JobQueue 未启用")
        return

    try:
        from datetime import timezone
        import pytz

        tz = pytz.timezone(TIMEZONE)

        # Market Monitor - 每天上午10点（中国时间）
        mm_time = time(
            hour=PUSH_SCHEDULE["market_monitor"]["hour"],
            minute=PUSH_SCHEDULE["market_monitor"]["minute"],
            tzinfo=tz
        )
        job_queue.run_daily(
            scheduled_market_monitor,
            time=mm_time,
            days=(0, 1, 2, 3, 4),  # 周一到周五
            name="market_monitor_daily"
        )
        logger.info(f"✅ Market Monitor 定时任务已设置: {mm_time}")

        # Momentum 50 - 每天上午10点（中国时间）
        m50_time = time(
            hour=PUSH_SCHEDULE["momentum50"]["hour"],
            minute=PUSH_SCHEDULE["momentum50"]["minute"],
            tzinfo=tz
        )
        job_queue.run_daily(
            scheduled_momentum50,
            time=m50_time,
            days=(0, 1, 2, 3, 4),  # 周一到周五
            name="momentum50_daily"
        )
        logger.info(f"✅ Momentum 50 定时任务已设置: {m50_time}")

    except Exception as e:
        logger.error(f"设置定时任务失败: {e}")


# ============== 命令处理 ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    ai_status = "✅ 已启用" if gemini_model else "❌ 未配置"

    await update.message.reply_text(
        f"🚀 *Antigravity Assistant v2.0 已启动*\n\n"
        f"AI 分析: {ai_status}\n\n"
        f"*每日推送 (中国时间):*\n"
        f"📊 Market Monitor - 10:00 AM\n"
        f"🚀 Momentum 50 - 10:05 AM\n\n"
        f"*命令:*\n"
        f"/mm - 立即获取 Market Monitor\n"
        f"/m50 - 立即获取 Momentum 50\n"
        f"/status TICKER - 查看标的状态\n"
        f"/ask 问题 - 问 AI 任何问题\n"
        f"/help - 显示帮助\n\n"
        f"💡 你也可以直接发消息，我会用 AI 回复你！",
        parse_mode='Markdown'
    )
    logger.info(f"用户 Chat ID: {update.effective_chat.id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /help 命令"""
    help_text = """
📋 *命令列表*

*每日推送:*
/mm - 立即获取 Market Monitor
/m50 - 立即获取 Momentum 50
/push - 手动触发所有推送

*AI 功能:*
/ask 问题 - 问 AI 任何投资问题
/analyze TICKER - AI 深度分析标的
直接发消息 - AI 自动回复

*查询类:*
/status TICKER - 查看标的状态
/week - 本周关注

*系统:*
/ping - 测试连接
/jobs - 查看定时任务状态

💡 *定时推送时间 (中国时间):*
• Market Monitor: 10:00 AM
• Momentum 50: 10:05 AM
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """测试连接"""
    ai_status = "✅" if gemini_model else "❌"
    await update.message.reply_text(
        f"🏓 Pong!\n"
        f"Bot 运行正常\n"
        f"AI 状态: {ai_status}\n"
        f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


async def jobs_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看定时任务状态"""
    jobs = context.application.job_queue.jobs()

    if not jobs:
        await update.message.reply_text("📋 当前没有定时任务")
        return

    job_info = []
    for job in jobs:
        next_run = job.next_t.strftime("%Y-%m-%d %H:%M:%S") if job.next_t else "N/A"
        job_info.append(f"• {job.name}: 下次运行 {next_run}")

    await update.message.reply_text(
        f"📋 *定时任务状态*\n\n" + "\n".join(job_info),
        parse_mode='Markdown'
    )


async def manual_market_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """手动触发 Market Monitor"""
    await update.message.reply_text("📊 正在获取 Market Monitor...")

    try:
        from utils.daily_push import push_market_monitor
        await push_market_monitor()
    except Exception as e:
        await update.message.reply_text(f"❌ 获取失败: {str(e)}")


async def manual_momentum50(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """手动触发 Momentum 50"""
    await update.message.reply_text("🚀 正在获取 Momentum 50...")

    try:
        from utils.daily_push import push_momentum50
        await push_momentum50()
    except Exception as e:
        await update.message.reply_text(f"❌ 获取失败: {str(e)}")


async def manual_push_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """手动触发所有推送"""
    await update.message.reply_text("📋 开始所有推送...")

    try:
        from utils.daily_push import daily_push_all
        results = await daily_push_all()
        success = sum(results.values())
        total = len(results)
        await update.message.reply_text(f"✅ 推送完成: {success}/{total} 成功")
    except Exception as e:
        await update.message.reply_text(f"❌ 推送失败: {str(e)}")


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /ask 命令 - 直接问 AI"""
    if not context.args:
        await update.message.reply_text("请输入问题，例如: /ask SHOP 的核心竞争力是什么")
        return

    question = ' '.join(context.args)
    thinking_msg = await update.message.reply_text("🤔 正在分析...")

    response = await ask_ai(question)
    await thinking_msg.edit_text(response)


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /analyze 命令 - AI 深度分析标的"""
    if not context.args:
        await update.message.reply_text("请指定标的，例如: /analyze SHOP")
        return

    ticker = context.args[0].upper()
    thinking_msg = await update.message.reply_text(f"🔍 正在深度分析 {ticker}...")

    prompt = f"""请对 {ticker} 进行深度分析，包括：

1. 📊 公司概况（一句话描述）
2. 💪 核心竞争优势（2-3点）
3. 📈 多头论点（看涨理由）
4. 📉 空头论点（风险因素）
5. 🎯 关键验证点（需要关注什么来验证投资逻辑）
6. 💡 当前观点（简短总结）

请基于公开信息分析，保持客观。"""

    response = await ask_ai(prompt)
    await thinking_msg.edit_text(f"📊 *{ticker} AI 分析*\n\n{response}", parse_mode='Markdown')


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /status 命令"""
    if not context.args:
        await update.message.reply_text("请指定标的，例如: /status SHOP")
        return

    ticker = context.args[0].upper()
    thinking_msg = await update.message.reply_text(f"📊 查询 {ticker}...")

    prompt = f"简要介绍一下 {ticker} 这只股票，包括当前市场关注的焦点（不超过100字）"
    response = await ask_ai(prompt)

    await thinking_msg.edit_text(
        f"📊 *{ticker}*\n\n"
        f"{response}\n\n"
        f"_实时价格功能开发中..._",
        parse_mode='Markdown'
    )


async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /week 命令"""
    thinking_msg = await update.message.reply_text("📅 生成本周关注...")

    prompt = """请告诉我本周美股市场需要关注的重点：
1. 重要财报（如果有）
2. 宏观数据发布
3. 市场主题/热点
保持简洁，用 bullet points。"""

    response = await ask_ai(prompt)
    await thinking_msg.edit_text(f"📅 *本周关注*\n\n{response}", parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理普通消息 - 用 AI 回复"""
    text = update.message.text

    if not gemini_model:
        await update.message.reply_text(
            "🤔 AI 功能未启用\n"
            "请使用 /help 查看可用命令"
        )
        return

    thinking_msg = await update.message.reply_text("🤔 思考中...")
    response = await ask_ai(text)
    await thinking_msg.edit_text(response)


# ============== 启动 Bot ==============

def main():
    """启动 Bot"""
    if not TELEGRAM_TOKEN:
        logger.error("未设置 TELEGRAM_TOKEN 环境变量")
        return

    # 创建 Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # 注册命令处理器
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("jobs", jobs_status))
    application.add_handler(CommandHandler("mm", manual_market_monitor))
    application.add_handler(CommandHandler("m50", manual_momentum50))
    application.add_handler(CommandHandler("push", manual_push_all))
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("analyze", analyze))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("week", week))

    # 注册消息处理器（处理非命令消息 - AI 回复）
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 设置定时任务
    setup_scheduled_jobs(application)

    # 启动 Bot
    logger.info("🚀 Antigravity Bot v2.0 启动中...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
