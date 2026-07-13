"""从环境变量读取并校验配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 始终加载脚本所在目录的 .env，这样在任意工作目录运行都能读到配置
load_dotenv(Path(__file__).resolve().parent / ".env")


class ConfigError(RuntimeError):
    """当必需配置缺失或不合法时抛出。"""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"环境变量 {name} 未设置，请检查 .env 文件。")
    return value


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"环境变量 {name} 必须是整数：{raw!r}") from exc


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    bearer_token: str
    telegram_bot_token: str
    telegram_chat_id: str
    usernames: tuple[str, ...]
    poll_interval: int
    request_delay: int
    pin_message: bool
    translate_to: str
    state_file: str


def _parse_usernames(raw: str) -> tuple[str, ...]:
    usernames = tuple(
        name.strip().lstrip("@")
        for name in raw.split(",")
        if name.strip()
    )
    if not usernames:
        raise ConfigError("USERNAMES_TO_TRACK 中没有有效的用户名。")
    return usernames


def load_config() -> Config:
    """构建 API 轮询版所需的 Config，如有问题则抛出 ConfigError。"""
    usernames = _parse_usernames(_require("USERNAMES_TO_TRACK"))

    return Config(
        bearer_token=_require("BEARER_TOKEN"),
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_require("TELEGRAM_CHAT_ID"),
        usernames=usernames,
        poll_interval=_get_int("POLL_INTERVAL", 60),
        request_delay=_get_int("REQUEST_DELAY", 2),
        pin_message=_get_bool("PIN_MESSAGE", False),
        translate_to=os.environ.get("TRANSLATE_TO", "zh-CN").strip(),
        state_file=os.environ.get("STATE_FILE", "latest_tweet_ids.json").strip()
        or "latest_tweet_ids.json",
    )


# 一个监听目标：(显示名, 状态键, 候选 feed URL 元组)
# 状态键用于跨镜像稳定记录基线，切换镜像也不丢失去重信息。
Feed = tuple[str, str, tuple[str, ...]]


@dataclass(frozen=True)
class RSSConfig:
    telegram_bot_token: str
    telegram_chat_id: str
    feeds: tuple[Feed, ...]
    poll_interval: int
    request_delay: int
    pin_message: bool
    translate_to: str
    state_file: str


def _build_feeds() -> tuple[Feed, ...]:
    """构建监听目标列表，每个目标含一组候选镜像 URL。

    两种来源，可同时使用：
    1. RSS_FEEDS：直接给出完整 feed URL，逗号分隔。
       可用 `名称|URL` 指定显示名，否则用主机名。
    2. USERNAMES_TO_TRACK + RSS_BASE_URL：用模板为每个用户拼接 URL。
       RSS_BASE_URL 支持逗号分隔的多个模板（多镜像备援）；
       每个模板必须含 {username} 占位符。任一镜像抓到内容即可，
       其余作为该用户失效时的备援。例如：
       RSS_BASE_URL=https://xcancel.com/{username}/rss,https://nitter.net/{username}/rss
    """
    feeds: list[Feed] = []

    raw_feeds = os.environ.get("RSS_FEEDS", "").strip()
    if raw_feeds:
        for item in raw_feeds.split(","):
            item = item.strip()
            if not item:
                continue
            if "|" in item:
                name, url = item.split("|", 1)
                name, url = name.strip(), url.strip()
            else:
                name, url = _host_of(item), item
            feeds.append((name, url, (url,)))

    base_url = os.environ.get("RSS_BASE_URL", "").strip()
    usernames_raw = os.environ.get("USERNAMES_TO_TRACK", "").strip()
    if base_url and usernames_raw:
        templates = [t.strip() for t in base_url.split(",") if t.strip()]
        for tpl in templates:
            if "{username}" not in tpl:
                raise ConfigError(f"RSS_BASE_URL 的每个模板都必须含 {{username}} 占位符：{tpl!r}")
        for username in _parse_usernames(usernames_raw):
            urls = tuple(tpl.replace("{username}", username) for tpl in templates)
            # 状态键用用户名，与具体镜像解耦
            feeds.append((f"@{username}", f"user:{username}", urls))

    if not feeds:
        raise ConfigError(
            "未配置任何 RSS 源。请设置 RSS_FEEDS，或同时设置 "
            "RSS_BASE_URL 与 USERNAMES_TO_TRACK。"
        )
    return tuple(feeds)


def _host_of(url: str) -> str:
    from urllib.parse import urlparse

    host = urlparse(url).netloc
    return host or url


def load_rss_config() -> RSSConfig:
    """构建 RSS 版所需的配置，不需要 BEARER_TOKEN。"""
    return RSSConfig(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_require("TELEGRAM_CHAT_ID"),
        feeds=_build_feeds(),
        poll_interval=_get_int("POLL_INTERVAL", 60),
        request_delay=_get_int("REQUEST_DELAY", 2),
        pin_message=_get_bool("PIN_MESSAGE", False),
        translate_to=os.environ.get("TRANSLATE_TO", "zh-CN").strip(),
        state_file=os.environ.get("STATE_FILE", "latest_rss_ids.json").strip()
        or "latest_rss_ids.json",
    )
