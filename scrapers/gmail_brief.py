#!/usr/bin/env python3
"""
Gmail Brief - 云端版本
读取 Gmail 邮件，生成 AI 摘要，推送到 Telegram
"""

import os
import json
import base64
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# 配置
GMAIL_LABEL = os.getenv('GMAIL_LABEL', 'Newsletter')
HOURS_TO_LOOK_BACK = int(os.getenv('GMAIL_HOURS_BACK', '24'))
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def get_gmail_credentials():
    """
    从环境变量获取 Gmail 凭据

    环境变量 GMAIL_TOKEN_JSON 应该包含 token.json 的完整内容
    """
    token_json = os.getenv('GMAIL_TOKEN_JSON')

    if not token_json:
        logger.error("未配置 GMAIL_TOKEN_JSON 环境变量")
        return None

    try:
        token_data = json.loads(token_json)
        creds = Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes', GMAIL_SCOPES)
        )

        # 检查是否需要刷新
        if creds.expired and creds.refresh_token:
            logger.info("Token 已过期，正在刷新...")
            creds.refresh(Request())
            logger.info("Token 刷新成功")

        return creds
    except Exception as e:
        logger.error(f"解析 Gmail 凭据失败: {e}")
        return None


def get_gmail_service():
    """获取 Gmail API 服务实例"""
    creds = get_gmail_credentials()
    if not creds:
        return None

    try:
        return build('gmail', 'v1', credentials=creds)
    except Exception as e:
        logger.error(f"创建 Gmail 服务失败: {e}")
        return None


def get_label_id(service, label_name):
    """根据标签名称获取标签 ID"""
    try:
        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])

        for label in labels:
            if label['name'].lower() == label_name.lower():
                return label['id']

        logger.warning(f"找不到标签: {label_name}")
        return None
    except Exception as e:
        logger.error(f"获取标签失败: {e}")
        return None


def decode_email_body(payload):
    """解码邮件正文"""
    body = ""

    if 'body' in payload and payload['body'].get('data'):
        body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    elif 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            if mime_type == 'text/plain':
                if 'data' in part.get('body', {}):
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                    break
            elif mime_type == 'text/html' and not body:
                if 'data' in part.get('body', {}):
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
            elif 'parts' in part:
                body = decode_email_body(part)
                if body:
                    break

    return body


def fetch_gmail_emails(label_name=None, hours_back=None):
    """
    获取指定标签的邮件

    Args:
        label_name: 邮件标签名称
        hours_back: 查看多少小时内的邮件

    Returns:
        邮件列表，每封邮件包含 subject, sender, date, body, snippet, gmail_link
    """
    label_name = label_name or GMAIL_LABEL
    hours_back = hours_back or HOURS_TO_LOOK_BACK

    service = get_gmail_service()
    if not service:
        logger.error("无法连接 Gmail 服务")
        return []

    # 获取标签 ID
    label_id = get_label_id(service, label_name)
    if not label_id:
        return []

    # 计算时间过滤
    after_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    query = f"after:{after_time.strftime('%Y/%m/%d')}"

    try:
        # 获取邮件列表
        results = service.users().messages().list(
            userId='me',
            labelIds=[label_id],
            q=query,
            maxResults=50
        ).execute()

        messages = results.get('messages', [])

        if not messages:
            logger.info(f"最近 {hours_back} 小时内没有标签为 [{label_name}] 的新邮件")
            return []

        logger.info(f"找到 {len(messages)} 封邮件")

        emails = []
        for msg in messages:
            # 获取邮件详情
            message = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='full'
            ).execute()

            headers = message.get('payload', {}).get('headers', [])

            # 提取邮件信息
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(无主题)')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), '(未知发件人)')
            date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')

            # 解析日期
            try:
                date = parsedate_to_datetime(date_str)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
            except:
                date = datetime.now(timezone.utc)

            # 检查是否在时间范围内
            if date < after_time:
                continue

            # 获取邮件正文
            body = decode_email_body(message.get('payload', {}))
            snippet = message.get('snippet', '')

            # 生成 Gmail 邮件链接
            msg_id = msg['id']
            gmail_link = f"https://mail.google.com/mail/u/0/#inbox/{msg_id}"

            emails.append({
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body[:10000] if body else snippet,
                'snippet': snippet,
                'gmail_link': gmail_link
            })

        # 按时间排序，最新的在前
        emails.sort(key=lambda x: x['date'], reverse=True)

        return emails

    except Exception as e:
        logger.error(f"获取邮件失败: {e}")
        return []


def summarize_email_with_ai(email: dict) -> str:
    """使用 AI 对单封邮件进行摘要"""
    from utils.ai_analyzer import analyze

    prompt = f"""请对以下邮件内容进行简洁的中文摘要（2-3句话），提取关键信息：

邮件主题: {email['subject']}
发件人: {email['sender']}
内容摘要:
{email['body'][:3000]}

输出格式：直接输出摘要，不要任何前缀。重点突出主要信息和关键数据。"""

    result = analyze(prompt, prefer="gemini")
    if result:
        return result
    return email.get('snippet', '(无法生成摘要)')[:200]


def generate_gmail_brief(emails: list) -> dict:
    """
    生成 Gmail 简报

    Returns:
        dict: {
            'emails': 带摘要的邮件列表,
            'overall_summary': 整体摘要,
            'telegram_message': Telegram 消息格式
        }
    """
    if not emails:
        return {
            'emails': [],
            'overall_summary': '今日没有新邮件',
            'telegram_message': '📭 *Gmail 简报*\n\n今日没有新邮件'
        }

    # 对每封邮件生成摘要
    logger.info(f"正在生成 {len(emails)} 封邮件的摘要...")
    for i, email in enumerate(emails):
        logger.info(f"处理 ({i+1}/{len(emails)}): {email['subject'][:30]}...")
        email['summary'] = summarize_email_with_ai(email)

    # 生成整体摘要
    from utils.ai_analyzer import analyze

    summaries_text = "\n".join([
        f"- 【{e['subject'][:50]}】{e['summary'][:100]}"
        for e in emails[:10]
    ])

    overall_prompt = f"""基于以下邮件摘要，用3句话概括今日的主要资讯（直接输出，不要前缀）：

{summaries_text}"""

    overall_summary = analyze(overall_prompt, prefer="gemini")
    if not overall_summary:
        overall_summary = f"今日共收到 {len(emails)} 封邮件"

    # 生成 Telegram 消息
    date_str = datetime.now().strftime("%Y-%m-%d")
    telegram_message = f"""📬 *Gmail 简报 {date_str}*

📊 *今日概览*
{overall_summary}

"""

    # 添加每封邮件的摘要
    for i, email in enumerate(emails[:10], 1):
        # 清理发件人名称
        sender = email['sender'].split('<')[0].strip().strip('"')
        if len(sender) > 20:
            sender = sender[:20] + '...'

        telegram_message += f"""*{i}. {email['subject'][:50]}*
📤 {sender}
{email['summary'][:150]}
🔗 [查看原文]({email['gmail_link']})

"""

    if len(emails) > 10:
        telegram_message += f"_...还有 {len(emails) - 10} 封邮件_"

    return {
        'emails': emails,
        'overall_summary': overall_summary,
        'telegram_message': telegram_message
    }


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)

    print("测试 Gmail 读取...")
    emails = fetch_gmail_emails()
    print(f"获取到 {len(emails)} 封邮件")

    if emails:
        print(f"\n第一封邮件:")
        print(f"  主题: {emails[0]['subject']}")
        print(f"  发件人: {emails[0]['sender']}")
