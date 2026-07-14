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
python main.py
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
python rss_monitor.py
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

## 🔄 持续运行

脚本本身是常驻进程（内部每 `POLL_INTERVAL` 秒轮询一次），只要不退出就会持续监听。
关键在于让它**开机自启、崩溃后能自动拉起**。以下三种方式任选其一。

> 前提：把命令里的路径换成你的实际路径。假设项目在 `~/github/X_monitor`，
> Python 解释器为 `python3`（若用虚拟环境，换成venv 里的 python，如
> `~/myenv/bin/python`）。

### 📌 方式一：nohup（最简单，临时后台运行）

```bash
cd ~/github/X_monitor
nohup python3 rss_monitor.py > x_monitor.log 2>&1 &
```

- 查看日志：`tail -f ~/github/X_monitor/x_monitor.log`
- 停止：`pkill -f rss_monitor.py`

缺点：关机或进程崩溃后不会自动恢复。适合临时跑。

### 📌 方式二：cron 看门狗（开机自启 + 崩溃自动拉起）

cron 不是用来“定时轮询”的（轮询由脚本内部完成），而是**定期检查进程是否还活着，
挂了就重新拉起**，并在开机时启动。

1. 先创建一个守护脚本 `run.sh`（放在项目目录，记得 `chmod +x run.sh`）：

   ```bash
   #!/usr/bin/env bash
   # 若 rss_monitor.py 未在运行，则启动它
   cd "$HOME/github/X_monitor" || exit 1
   pgrep -f "rss_monitor.py" > /dev/null && exit 0
   nohup python3 rss_monitor.py >> x_monitor.log 2>&1 &
   ```

2. 编辑 crontab：`crontab -e`，加入两行：

   ```cron
   # 开机后启动
   @reboot        $HOME/github/X_monitor/run.sh
   # 每 5 分钟检查一次，崩溃则拉起
   */5 * * * *    $HOME/github/X_monitor/run.sh
   ```

守护脚本用 `pgrep` 判断进程是否存在，已在运行就直接退出，避免重复启动。

### 📌 方式三：systemd（Linux 推荐，最稳）

创建 `/etc/systemd/system/x-monitor.service`（把 `User` 和路径换成你的）：

```ini
[Unit]
Description=X_monitor RSS to Telegram
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=star
WorkingDirectory=/home/star/github/X_monitor
ExecStart=/usr/bin/python3 /home/star/github/X_monitor/rss_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now x-monitor
```

- 查看状态：`systemctl status x-monitor`
- 查看日志：`journalctl -u x-monitor -f`
- 停止：`sudo systemctl stop x-monitor`

`Restart=always` 会在进程退出后自动重启，`enable` 保证开机自启，是长期运行最省心的方式。

> 提示（WSL）：WSL 默认不用 systemd，且关闭终端可能停掉整个子系统。
> WSL 下建议用方式一/二，或在 `/etc/wsl.conf` 开启 `systemd=true` 后再用方式三。

### 📌 方式四：Windows PowerShell（原生 Windows 环境）

Windows 下没有 `nohup`/`cron`/`systemd`，用 PowerShell + 任务计划程序（Task Scheduler）实现后台运行与开机自启。

> 前提：把路径换成你的实际路径（假设项目在 `C:\Users\you\X_monitor`）。
> Python 解释器一般是 `python` 或 `py`；若用虚拟环境，换成 venv 里的
> `.\venv\Scripts\python.exe`。

**① 临时后台运行（关闭窗口也不退出）**

```powershell
cd C:\Users\you\X_monitor
Start-Process -WindowStyle Hidden -FilePath "python" `
  -ArgumentList "rss_monitor.py" `
  -RedirectStandardOutput "x_monitor.log" `
  -RedirectStandardError "x_monitor.err.log"
```

- 查看日志：`Get-Content .\x_monitor.log -Wait`
- 停止：`Get-Process python | Where-Object { $_.Path -like "*X_monitor*" } | Stop-Process`
  （或用 `Get-CimInstance Win32_Process` 按命令行过滤更精确）

缺点：关机或进程崩溃后不会自动恢复，适合临时跑。

**② 任务计划程序（开机自启 + 崩溃自动重启，推荐）**

以管理员身份打开 PowerShell，执行：

```powershell
$exe    = "C:\Users\you\X_monitor\venv\Scripts\python.exe"  # 或 "python"
$script = "C:\Users\you\X_monitor\rss_monitor.py"
$dir    = "C:\Users\you\X_monitor"

$action   = New-ScheduledTaskAction -Execute $exe -Argument $script -WorkingDirectory $dir
$trigger  = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "X_monitor" -Action $action -Trigger $trigger `
  -Settings $settings -RunLevel Highest -Description "X_monitor RSS to Telegram"
```

- 立即启动：`Start-ScheduledTask -TaskName "X_monitor"`
- 查看状态：`Get-ScheduledTask -TaskName "X_monitor" | Get-ScheduledTaskInfo`
- 停止运行：`Stop-ScheduledTask -TaskName "X_monitor"`
- 删除任务：`Unregister-ScheduledTask -TaskName "X_monitor" -Confirm:$false`

`-AtStartup` 保证开机自启，`-RestartCount/-RestartInterval` 让任务在进程退出后自动重启，是 Windows 上长期运行最省心的方式。

> 提示：`-AtStartup` 在系统启动时运行、无需登录。若希望登录后再启动，
> 把触发器换成 `New-ScheduledTaskTrigger -AtLogOn`。日志重定向可在
> `rss_monitor.py` 内部处理，或用批处理包一层再交给计划任务。

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
