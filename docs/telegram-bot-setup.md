# 创建 Telegram Bot 指南

本文指导你创建一个 Telegram 机器人，并获取 X_monitor 所需的两个配置：
`TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`。

## 一、创建机器人，获取 Bot Token

1. 在 Telegram 中搜索并打开 [@BotFather](https://t.me/BotFather)（官方机器人，带蓝色认证）。
2. 发送 `/newbot`。
3. 按提示输入：
   - **机器人名称**（display name）：随意，如 `X Monitor`。
   - **用户名**（username）：必须以 `bot` 结尾，如 `my_x_monitor_bot`。
4. 创建成功后，BotFather 会返回一段类似这样的 Token：

   ```
   8853032121:AAG0nq0plcOl6oVDRTAzgzAGI3QjlIXv9qI
   ```

   这就是 `TELEGRAM_BOT_TOKEN`。**妥善保存，不要泄露**——拿到它的人可以完全控制你的机器人。

## 二、获取 Chat ID

Chat ID 是消息要发送到的目标（你个人、某个群组或某个频道）。根据目标类型选择对应方法。

### 方法 A：发给你个人

1. 在 Telegram 搜索你刚创建的机器人（用它的 username），打开对话。
2. 给它随便发一条消息（如 `hi`）。**这一步必须做**——机器人无法主动给从未联系过它的人发消息。
3. 在浏览器打开（把 `<TOKEN>` 换成你的 Bot Token）：

   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

4. 在返回的 JSON 里找到 `"chat":{"id":...}`，那个数字就是你的 `TELEGRAM_CHAT_ID`，例如：

   ```json
   "chat": { "id": 7765138435, "first_name": "...", "type": "private" }
   ```

   个人 Chat ID 是**正整数**。

> 也可以直接用 [@userinfobot](https://t.me/userinfobot)：打开它并发送任意消息，它会回复你的 user id（即个人 Chat ID）。

### 方法 B：发到群组

1. 把你的机器人**添加进群组**。
2. 在群里发一条消息（可以 @ 一下机器人）。
3. 同样访问 `https://api.telegram.org/bot<TOKEN>/getUpdates`。
4. 找到群组对应的 `"chat":{"id":...}`。群组 Chat ID 通常是**负数**，如 `-1001234567890`。

> 如果 getUpdates 返回空，检查群里是否开启了机器人隐私模式：向 BotFather 发送 `/setprivacy` → 选择你的机器人 → `Disable`，然后重新在群里发消息。

### 方法 C：发到频道

1. 把机器人添加为频道的**管理员**（至少给发消息权限）。
2. 在频道里发一条消息。
3. 访问 getUpdates，找到 `"channel_post"` 里的 `"chat":{"id":...}`，频道 ID 形如 `-1001234567890`。

## 三、填入 .env

把拿到的两个值填进项目根目录的 `.env`：

```dotenv
TELEGRAM_BOT_TOKEN=8853032121:AAG0nq0plcOl6oVDRTAzgzAGI3QjlIXv9qI
TELEGRAM_CHAT_ID=7765138435
```

## 四、验证推送是否成功

在项目目录运行以下命令，发送一条测试消息：

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from config import load_rss_config
import notifier
cfg = load_rss_config()
notifier.send_to_telegram(cfg.telegram_bot_token, cfg.telegram_chat_id, '✅ X_monitor 测试消息，推送通道正常')
print('已发送，请检查 Telegram')
"
```

Telegram 收到消息即配置成功。

## 常见问题

- **`Unauthorized` / 401**：Bot Token 错误或已失效，检查是否复制完整。
- **`chat not found` / 400**：Chat ID 不对，或你（个人）从未给机器人发过消息（见方法 A 第 2 步）。
- **`Forbidden: bot was blocked by the user`**：你把机器人拉黑了，去对话里解除。
- **群里收不到**：多为隐私模式导致，见方法 B 的提示。

## 安全提醒

- Bot Token 等同于机器人的完整控制权，**切勿**提交到 git 或写进 `.env.example`。
- 本项目的 `.env` 已被 `.gitignore` 排除。
- 若 Token 疑似泄露，向 BotFather 发送 `/revoke` 立即吊销并重新生成。
