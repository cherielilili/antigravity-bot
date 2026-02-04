# Antigravity Cloud Agent v2.0

云端运行的投研助手 Telegram Bot - 支持定时推送 + AI 分析

## 功能特性

### 每日推送 (中国时间)
- 📊 **Market Monitor** (10:00 AM) - 市场宽度追踪
- 🚀 **Momentum 50** (10:05 AM) - 动量股票榜单

### Telegram 命令
| 命令 | 功能 |
|------|------|
| `/mm` | 立即获取 Market Monitor |
| `/m50` | 立即获取 Momentum 50 |
| `/push` | 手动触发所有推送 |
| `/ask 问题` | AI 回答投资问题 |
| `/analyze TICKER` | AI 深度分析标的 |
| `/status TICKER` | 查看标的状态 |
| `/week` | 本周市场关注 |
| `/jobs` | 查看定时任务状态 |
| `/ping` | 测试连接 |

### AI 功能
- Gemini AI 分析（优先，带限流）
- Claude AI 备用
- 自然语言对话

## 快速部署到 Railway

### 1. 准备工作

- [x] 创建 Telegram Bot，获取 Token
- [x] 注册 Railway 账号
- [ ] 配置 Gemini API Key

### 2. 部署步骤

#### 方式一：通过 GitHub（推荐）

1. 把这个文件夹推送到你的 GitHub 仓库
2. 登录 Railway → New Project → Deploy from GitHub repo
3. 选择你的仓库
4. 添加环境变量（见下方）
5. 点击 Deploy

#### 方式二：通过 Railway CLI

```bash
# 安装 Railway CLI
npm install -g @railway/cli

# 登录
railway login

# 初始化项目
railway init

# 部署
railway up
```

### 3. 环境变量配置

在 Railway 控制台添加以下环境变量：

| 变量名 | 值 | 必填 |
|--------|-----|------|
| TELEGRAM_TOKEN | 你的 Bot Token | ✅ |
| TELEGRAM_CHAT_ID | 你的 Chat ID | ✅ |
| GEMINI_API_KEY | Gemini API Key | ✅ |
| ANTHROPIC_API_KEY | Claude API Key | 可选(备用) |
| TIMEZONE | Asia/Shanghai | 可选(默认中国时间) |

### 4. 获取你的 Chat ID

1. 部署成功后，在 Telegram 找到你的 Bot
2. 发送 /start
3. 查看 Railway 日志，会显示你的 Chat ID
4. 把 Chat ID 填入环境变量

### 5. 测试

在 Telegram 发送：
- `/ping` - 测试连接
- `/mm` - 手动获取 Market Monitor
- `/m50` - 手动获取 Momentum 50

## 文件说明

```
09_CloudAgent/
├── bot.py                    # Telegram Bot 主程序
├── scrapers/
│   ├── market_monitor.py     # Market Monitor 数据抓取
│   └── momentum50.py         # Momentum 50 数据抓取
├── utils/
│   ├── ai_analyzer.py        # AI 分析模块（带限流）
│   └── daily_push.py         # MD 生成 + Telegram 推送
├── requirements.txt          # Python 依赖
├── Procfile                  # Railway 启动配置
├── railway.json              # Railway 项目配置
├── .env.example              # 环境变量示例
└── README.md                 # 本文件
```

## 数据源

| 数据源 | 来源 | 说明 |
|--------|------|------|
| Market Monitor | [Stockbee](https://stockbee.blogspot.com/p/mm.html) | 市场宽度指标 |
| Momentum 50 | [Google Sheets](https://docs.google.com/spreadsheets/d/1xjbe9SF0HsxwY_Uy3NC2tT92BqK0nhArUaYU16Q0p9M) | 每日动量股票 |

## Obsidian 同步

推送会生成 Markdown 文件，包含 Obsidian URI 链接。
点击 Telegram 消息中的链接可直接在 Obsidian 中打开。

文件存储在云端 `./data` 目录：
- `data/MarketMonitor/YYYY-MM-DD.md`
- `data/Momentum50/YYYY-MM-DD.md`

## 开发进度

- [x] Telegram Bot 基础功能
- [x] Gemini AI 集成 + 限流
- [x] Market Monitor 数据抓取
- [x] Momentum 50 数据抓取
- [x] 定时推送功能
- [x] MD 文件生成
- [ ] Obsidian 云同步
- [ ] Finnhub 实时价格
- [ ] 更多数据源接入

## 注意事项

1. **Gemini 限流**: 已内置限流机制，避免触发 API 限制
2. **时区**: 定时任务使用中国时间 (Asia/Shanghai)
3. **数据更新**: Market Monitor 和 Momentum 50 仅工作日更新
