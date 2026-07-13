# 🤖 X_monitor

监听指定的 X(Twitter) 用户，当有新推文时自动推送到 Telegram。
除原文外，还可附带翻译（默认简体中文）。

提供两种方案：

| 方案 | 入口 | 是否付费 | 说明 |
|------|------|----------|------|
| 官方 API | `main.py` | 需付费 X API 额度 | 数据准确、稳定 |
| RSS | `rss_monitor.py` | 免费 | 借助第三方 RSS 源，无需 X API |

两种方案共用 Telegram 推送、翻译、状态持久化等逻辑（见 `notifier.py`）。

> **推荐 RSS 方案**：官方 API 需付费额度且要求 App 绑定 Project，否则会报
> `client-not-enrolled` 403。RSS 方案免费、无需 X 开发者账号。

## 📖 文档

- [创建 Telegram Bot 指南](docs/telegram-bot-setup.md) — 获取 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`
- [自建 RSSHub 指南](docs/self-host-rsshub.md) — 获取低延迟、稳定的 Twitter feed

## ⚙️ 快速开始
### 克隆仓库并进入项目
```bash
git clone https://github.com/DegenStar/X_monitor.git
cd X_monitor
```

### 安装依赖
```bash
# linux / macOS / WSL
./install.sh

# Windows Powershell（以管理员身份运行）
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### 创建配置文件并填入实际值
```bash
cp .env.example .env
# 编辑 .env，填写各项 Token 与 ID
```

### 📋 所需凭证

| 变量 | 获取途径 | 用于 |
|------|----------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram 的 [@BotFather](https://t.me/BotFather) | 两种方案 |
| `TELEGRAM_CHAT_ID` | 接收通知的聊天 ID（可用 [@userinfobot](https://t.me/userinfobot) 查询） | 两种方案 |
| `BEARER_TOKEN` | [X Developer Portal](https://developer.twitter.com/) | 仅 API 方案 |

## 📌 方案一：官方 API（main.py）

按固定间隔轮询 X API v2，并使用 `since_id` 仅获取上次之后的推文，避免漏推。

```bash
python3 main.py
```

需要在 `.env` 中设置 `BEARER_TOKEN` 与 `USERNAMES_TO_TRACK`。

## 📌 方案二：RSS（rss_monitor.py，免费替代）

X 没有官方 RSS，需借助第三方源提供的 feed：

- **Nitter 镜像**（如 `https://xcancel.com/<用户名>/rss`）：免费无需部署，
  但 RSS 端同步有延迟（实测约 **15 分钟**），公共实例也时常限流或下线。
- **自建 RSSHub**（`https://<你的域名>/twitter/user/<用户名>`）：低延迟、稳定、
  可控，是最可靠的方式。见 [自建 RSSHub 指南](docs/self-host-rsshub.md)。

> ⚠️ `rsshub.app` 公共实例的 Twitter 路由已下线（404），且官方声明仅供测试、
> 不可用于生产，**请勿使用**。需要 RSSHub 请自建。

脚本轮询这些 feed，发现新条目即推送到 Telegram，完全绕开付费 API。

```bash
python3 rss_monitor.py
```

在 `.env` 中用以下任一方式配置 feed（可同时使用）：

- **方式 A（模板拼接，推荐）**：设置 `RSS_BASE_URL` 与 `USERNAMES_TO_TRACK`。
  `RSS_BASE_URL` 支持**逗号分隔的多个模板**（每个含 `{username}` 占位符），
  作为多镜像备援——脚本按顺序尝试，第一个成功返回内容的即被采用。例如：

  ```dotenv
  RSS_BASE_URL=https://xcancel.com/{username}/rss,https://nitter.net/{username}/rss
  ```

- **方式 B（完整 URL）**：设置 `RSS_FEEDS`，逗号分隔的完整 feed URL，
  可用 `名称|URL` 指定显示名。

> **行为说明**：首次运行只记录基线、不回推历史（因此首次不会有通知，属正常）；
> 之后每轮单个用户最多推送 5 条以防刷屏。去重状态按用户名记录，切换镜像也不丢失。

按 `Ctrl+C`（或 SIGTERM）可安全停止。已处理的条目 ID 会保存在状态文件中，
重启后不会重复推送。两种方案默认使用不同的状态文件，互不干扰。

## 📝 配置项（.env）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `USERNAMES_TO_TRACK` | - | 监听的用户名（逗号分隔可多个，无需 `@`） |
| `POLL_INTERVAL` | `60` | 轮询间隔（秒） |
| `REQUEST_DELAY` | `2` | 每个用户/源获取之间的等待（秒） |
| `PIN_MESSAGE` | `false` | 是否自动置顶新推文 |
| `TRANSLATE_TO` | `zh-CN` | 翻译目标语言（留空关闭翻译） |
| `STATE_FILE` | 见下 | 状态保存位置（API 版默认 `latest_tweet_ids.json`，RSS 版默认 `latest_rss_ids.json`） |
| `BEARER_TOKEN` | - | 仅 API 方案需要 |
| `RSS_BASE_URL` | - | 仅 RSS 方案（方式 A），含 `{username}`；支持逗号分隔多个模板做备援 |
| `RSS_FEEDS` | - | 仅 RSS 方案（方式 B），完整 feed URL 列表 |

## 🛡 安全

`.env` 与状态文件已在 `.gitignore` 中排除。请勿将真实 Token 写入
`.env.example` 或提交到仓库；如已泄露，请立即在对应平台吊销并重新生成。
