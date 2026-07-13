"""监听指定用户的 X(Twitter)，将新推文自动推送到 Telegram。

- 配置从 .env 读取（见 config.py）
- 使用 since_id 获取上次之后的推文，避免漏推
- 对限流(429)和网络错误进行等待与重试，保证稳定运行

注意：此版本使用官方 X API，需要付费额度。
若无 API 额度，请改用 rss_monitor.py（基于第三方 RSS 源的替代方案）。
"""
from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Any

import requests

import notifier
from config import Config, ConfigError, load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("x_monitor")

TWITTER_API = "https://api.twitter.com/2"
HTTP_TIMEOUT = 15  # 秒


def _handle_signal(signum: int, _frame: Any) -> None:
    logger.info("收到信号 %s，正在安全退出……", signum)
    notifier.request_shutdown()


# ---------------------------------------------------------------------------
# Twitter API 调用（支持限流处理）
# ---------------------------------------------------------------------------
def twitter_get(cfg: Config, path: str, params: dict[str, Any] | None = None) -> dict | None:
    """调用 Twitter API GET。遇到 429 时等待到 reset 再返回 None。"""
    url = f"{TWITTER_API}/{path}"
    headers = {"Authorization": f"Bearer {cfg.bearer_token}"}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Twitter API 通信错误 (%s)：%s", path, exc)
        return None

    if resp.status_code == 200:
        return resp.json()

    if resp.status_code == 429:
        reset = resp.headers.get("x-rate-limit-reset")
        wait = 60
        if reset and reset.isdigit():
            wait = max(5, int(reset) - int(time.time()) + 1)
        logger.warning("已触发限流，将等待 %d 秒。", wait)
        notifier.interruptible_sleep(wait)
        return None

    logger.error("Twitter API 错误 %s (%s)：%s", resp.status_code, path, resp.text[:300])
    return None


# ---------------------------------------------------------------------------
# 业务逻辑
# ---------------------------------------------------------------------------
def get_user_id(cfg: Config, username: str) -> str | None:
    data = twitter_get(cfg, f"users/by/username/{username}")
    if data:
        return data.get("data", {}).get("id")
    return None


def fetch_new_tweets(cfg: Config, user_id: str, since_id: str | None) -> list[dict]:
    """返回 since_id 之后的新推文，按从旧到新排序。"""
    params: dict[str, Any] = {
        "max_results": 5,
        "tweet.fields": "created_at",
        "exclude": "retweets,replies",
    }
    if since_id:
        params["since_id"] = since_id
    data = twitter_get(cfg, f"users/{user_id}/tweets", params)
    if not data:
        return []
    tweets = data.get("data", [])
    # API 返回按从新到旧排序，推送时改为从旧到新
    return list(reversed(tweets))


def build_message(cfg: Config, username: str, tweet: dict) -> str:
    text = tweet.get("text", "")
    tweet_id = tweet["id"]
    tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"
    parts = [f"用户 @{username} 的最新推文：", "", f"原文：{text}"]
    if cfg.translate_to:
        translated = notifier.translate_text(text, cfg.translate_to)
        parts += ["", f"翻译：{translated}"]
    parts += ["", f"推文链接：{tweet_url}"]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------
def resolve_user_ids(cfg: Config) -> dict[str, str]:
    user_ids: dict[str, str] = {}
    for username in cfg.usernames:
        user_id = get_user_id(cfg, username)
        if user_id:
            user_ids[username] = user_id
            logger.info("监听对象：@%s (id=%s)", username, user_id)
        else:
            logger.error("无法获取 @%s 的用户 ID，已跳过。", username)
    return user_ids


def poll_once(cfg: Config, user_ids: dict[str, str], state: dict[str, str]) -> None:
    for username, user_id in user_ids.items():
        if notifier.is_shutting_down():
            return
        since_id = state.get(username)
        tweets = fetch_new_tweets(cfg, user_id, since_id)
        for tweet in tweets:
            logger.info("新推文 @%s：%s", username, tweet["id"])
            message = build_message(cfg, username, tweet)
            notifier.send_to_telegram(
                cfg.telegram_bot_token, cfg.telegram_chat_id, message, cfg.pin_message
            )
            state[username] = tweet["id"]
            notifier.save_state(cfg.state_file, state)
        notifier.interruptible_sleep(cfg.request_delay)


def run() -> int:
    try:
        cfg = load_config()
    except ConfigError as exc:
        logger.error("配置错误：%s", exc)
        return 1

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    user_ids = resolve_user_ids(cfg)
    if not user_ids:
        logger.error("没有可监听的用户，程序退出。")
        return 1

    state = notifier.load_state(cfg.state_file)
    logger.info("开始监听（间隔 %d 秒）。按 Ctrl+C 停止。", cfg.poll_interval)

    while not notifier.is_shutting_down():
        poll_once(cfg, user_ids, state)
        notifier.interruptible_sleep(cfg.poll_interval)

    logger.info("已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(run())
