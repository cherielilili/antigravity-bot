#!/usr/bin/env python3
"""
Antigravity Telegram Bot
云端运行的投研助手 - 集成 AI 分析
"""

import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

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
    """调用 Gemini AI"""
    if not gemini_model:
        return "❌ AI 功能未配置，请添加 GEMINI_API_KEY"

    try:
        full_prompt = f"{SYSTEM_PROMPT}\n\n"
        if context:
            full_prompt += f"上下文：{context}\n\n"
        full_prompt += f"用户消息：{prompt}"

        response = gemini_model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        logger.error(f"AI 调用失败: {e}")
        return f"❌ AI 调用出错: {str(e)}"


# ============== 命令处理 ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    ai_status = "✅ 已启用" if gemini_model else "❌ 未配置"

    await update.message.reply_text(
        f"🚀 *Antigravity Assistant 已启动*\n\n"
        f"AI 分析: {ai_status}\n\n"
        f"*命令:*\n"
        f"/status TICKER - 查看标的状态\n"
        f"/ask 问题 - 问 AI 任何问题\n"
        f"/analyze TICKER - AI 分析标的\n"
        f"/help - 显示帮助\n\n"
        f"💡 你也可以直接发消息，我会用 AI 回复你！",
        parse_mode='Markdown'
    )
    logger.info(f"用户 Chat ID: {update.effective_chat.id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /help 命令"""
    help_text = """
📋 *命令列表*

*AI 功能:*
/ask 问题 - 问 AI 任何投资问题
/analyze TICKER - AI 深度分析标的
直接发消息 - AI 自动回复

*查询类:*
/status TICKER - 查看标的状态
/brief - 今日简报
/week - 本周关注
/position - 当前持仓

*记录类:*
/idea TICKER 内容 - 快速记录想法

*系统:*
/ping - 测试连接

💡 *示例:*
• "SHOP 最近怎么样"
• "分析一下 META 的 AI 战略"
• "这周财报有什么要注意的"
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


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /ask 命令 - 直接问 AI"""
    if not context.args:
        await update.message.reply_text("请输入问题，例如: /ask SHOP 的核心竞争力是什么")
        return

    question = ' '.join(context.args)

    # 发送"正在思考"提示
    thinking_msg = await update.message.reply_text("🤔 正在分析...")

    # 调用 AI
    response = await ask_ai(question)

    # 更新回复
    await thinking_msg.edit_text(response)


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /analyze 命令 - AI 深度分析标的"""
    if not context.args:
        await update.message.reply_text("请指定标的，例如: /analyze SHOP")
        return

    ticker = context.args[0].upper()

    # 发送"正在分析"提示
    thinking_msg = await update.message.reply_text(f"🔍 正在深度分析 {ticker}...")

    # 构建分析提示
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

    # TODO: 接入 Finnhub 获取实时数据
    # 目前用 AI 生成一个基本回复

    thinking_msg = await update.message.reply_text(f"📊 查询 {ticker}...")

    prompt = f"简要介绍一下 {ticker} 这只股票，包括当前市场关注的焦点（不超过100字）"
    response = await ask_ai(prompt)

    await thinking_msg.edit_text(
        f"📊 *{ticker}*\n\n"
        f"{response}\n\n"
        f"_实时价格功能开发中..._",
        parse_mode='Markdown'
    )


async def brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /brief 命令"""
    await update.message.reply_text(
        "📧 *今日简报*\n\n"
        "_定时推送功能开发中_\n\n"
        "💡 你可以直接问我任何投资问题！",
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


async def position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /position 命令"""
    await update.message.reply_text(
        "💼 *当前持仓*\n\n"
        "_持仓同步功能开发中..._",
        parse_mode='Markdown'
    )


async def idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /idea 命令 - 快速记录"""
    if len(context.args) < 2:
        await update.message.reply_text("格式: /idea TICKER 你的想法内容")
        return

    ticker = context.args[0].upper()
    content = ' '.join(context.args[1:])
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

    # TODO: 写入到 Obsidian Hub 文件

    await update.message.reply_text(
        f"✅ 已记录到 {ticker}\n"
        f"📝 {content}\n"
        f"⏰ {timestamp}",
        parse_mode='Markdown'
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理普通消息 - 用 AI 回复"""
    text = update.message.text

    if not gemini_model:
        await update.message.reply_text(
            "🤔 AI 功能未启用\n"
            "请使用 /help 查看可用命令"
        )
        return

    # 发送"正在思考"提示
    thinking_msg = await update.message.reply_text("🤔 思考中...")

    # 调用 AI
    response = await ask_ai(text)

    # 更新回复
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
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("analyze", analyze))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("brief", brief))
    application.add_handler(CommandHandler("week", week))
    application.add_handler(CommandHandler("position", position))
    application.add_handler(CommandHandler("idea", idea))

    # 注册消息处理器（处理非命令消息 - AI 回复）
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 启动 Bot
    logger.info("🚀 Antigravity Bot 启动中...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
