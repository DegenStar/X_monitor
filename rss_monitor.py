"""通过 RSS 监听 X(Twitter) 用户，将新条目推送到 Telegram。

这是不依赖付费 X API 的替代方案：借助第三方 RSS 源
（Nitter / RSSHub / rss.app 等），轮询 feed 并推送新条目。

配置见 config.py 的 load_rss_config()：
- RSS_FEEDS：直接给出完整 feed URL（逗号分隔，可用 `名称|URL`）
- 或 RSS_BASE_URL + USERNAMES_TO_TRACK：按模板为每个用户拼接 URL
"""
from __future__ import annotations

import html
import logging
import signal
import sys
from typing import Any

import feedparser
import requests

import notifier
from config import ConfigError, RSSConfig, load_rss_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("x_monitor")

HTTP_TIMEOUT = 15  # 秒
MAX_NEW_PER_POLL = 5  # 单个 feed 每轮最多推送数，避免首次或积压时刷屏
# 部分实例（如 xcancel）会检查请求头，仅对“RSS 客户端”返回内容，
# 浏览器 UA 反而被拒（400: This URL only works inside an RSS client）。
# 因此使用 RSS 阅读器风格的 UA，并声明接受 RSS/XML。
USER_AGENT = "FreshRSS/1.24 (Linux; https://freshrss.org)"
FEED_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}


def _handle_signal(signum: int, _frame: Any) -> None:
    logger.info("收到信号 %s，正在安全退出……", signum)
    notifier.request_shutdown()


def fetch_feed(url: str) -> feedparser.FeedParserDict | None:
    """抓取并解析单个 feed，失败返回 None。"""
    try:
        resp = requests.get(url, headers=FEED_HEADERS, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("抓取 RSS 失败 %s：%s", url, exc)
        return None

    if resp.status_code != 200:
        # 附带响应体片段，便于定位 400/403 等的具体原因
        body = resp.text[:200].replace("\n", " ").strip()
        logger.error("抓取 RSS 返回 %s：%s ｜ 响应：%s", resp.status_code, url, body)
        return None

    # 部分实例（如 xcancel）返回的 XML 带前导空白/BOM，先去掉再解析
    content = resp.content.lstrip()
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        logger.error("解析 RSS 失败 %s：%s", url, parsed.bozo_exception)
        return None
    return parsed


def fetch_first_available(urls: tuple[str, ...]) -> feedparser.FeedParserDict | None:
    """依次尝试候选镜像，返回第一个成功且含条目的 feed。"""
    for url in urls:
        parsed = fetch_feed(url)
        if parsed and parsed.entries:
            if len(urls) > 1:
                logger.info("使用镜像：%s", url)
            return parsed
    return None


def entry_id(entry: feedparser.FeedParserDict) -> str:
    """取条目的稳定唯一标识。"""
    return str(entry.get("id") or entry.get("link") or entry.get("title", ""))


def clean_text(raw: str) -> str:
    """去掉 HTML 标签与转义，得到纯文本。"""
    import re

    text = re.sub(r"<[^>]+>", "", raw or "")
    return html.unescape(text).strip()


def build_message(cfg: RSSConfig, display_name: str, entry: feedparser.FeedParserDict) -> str:
    summary = clean_text(entry.get("summary") or entry.get("title", ""))
    link = entry.get("link", "")
    parts = [f"用户 {display_name} 的最新推文：", "", f"原文：{summary}"]
    if cfg.translate_to:
        translated = notifier.translate_text(summary, cfg.translate_to)
        parts += ["", f"翻译：{translated}"]
    if link:
        parts += ["", f"链接：{link}"]
    return "\n".join(parts)


def poll_feed(
    cfg: RSSConfig,
    display_name: str,
    state_key: str,
    urls: tuple[str, ...],
    state: dict[str, str],
) -> None:
    parsed = fetch_first_available(urls)
    if not parsed:
        return

    entries = list(parsed.entries)
    if not entries:
        return

    last_seen = state.get(state_key)

    # feedparser 通常按从新到旧排列；收集 last_seen 之前的新条目
    new_entries = []
    for entry in entries:
        eid = entry_id(entry)
        if eid == last_seen:
            break
        new_entries.append(entry)

    if last_seen is None:
        # 首次运行：只记录最新条目，不回推历史，避免刷屏
        state[state_key] = entry_id(entries[0])
        notifier.save_state(cfg.state_file, state)
        logger.info("初始化 %s，记录最新条目为基线。", display_name)
        return

    if not new_entries:
        return

    # 从旧到新推送，并限制单轮数量
    for entry in reversed(new_entries[:MAX_NEW_PER_POLL]):
        logger.info("新条目 %s：%s", display_name, entry_id(entry))
        message = build_message(cfg, display_name, entry)
        notifier.send_to_telegram(
            cfg.telegram_bot_token, cfg.telegram_chat_id, message, cfg.pin_message
        )
        state[state_key] = entry_id(entry)
        notifier.save_state(cfg.state_file, state)

    if len(new_entries) > MAX_NEW_PER_POLL:
        logger.warning(
            "%s 本轮有 %d 条新内容，仅推送最新 %d 条。",
            display_name,
            len(new_entries),
            MAX_NEW_PER_POLL,
        )
        # 将基线更新到最新，避免下轮重复处理被跳过的旧条目
        state[state_key] = entry_id(entries[0])
        notifier.save_state(cfg.state_file, state)


def run() -> int:
    try:
        cfg = load_rss_config()
    except ConfigError as exc:
        logger.error("配置错误：%s", exc)
        return 1

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    for name, _key, urls in cfg.feeds:
        logger.info("监听 RSS：%s -> %s", name, "，".join(urls))

    state = notifier.load_state(cfg.state_file)
    logger.info("开始监听（间隔 %d 秒）。按 Ctrl+C 停止。", cfg.poll_interval)

    while not notifier.is_shutting_down():
        for name, key, urls in cfg.feeds:
            if notifier.is_shutting_down():
                break
            poll_feed(cfg, name, key, urls, state)
            notifier.interruptible_sleep(cfg.request_delay)
        notifier.interruptible_sleep(cfg.poll_interval)

    logger.info("已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(run())
