"""通用工具：翻译、Telegram 推送、状态持久化、可中断等待。

被 API 轮询版(main.py)与 RSS 版(rss_monitor.py)共同复用。
"""
from __future__ import annotations

import json
import logging
import os
import time

import requests

logger = logging.getLogger("x_monitor")

TELEGRAM_API = "https://api.telegram.org"
HTTP_TIMEOUT = 15  # 秒

# 由主程序在收到停止信号时置为 True
shutdown_flag = {"stop": False}


def request_shutdown() -> None:
    shutdown_flag["stop"] = True


def is_shutting_down() -> bool:
    return shutdown_flag["stop"]


def interruptible_sleep(seconds: int) -> None:
    """收到停止信号时可提前退出的 sleep。"""
    for _ in range(seconds):
        if shutdown_flag["stop"]:
            return
        time.sleep(1)


# ---------------------------------------------------------------------------
# 状态（最后处理的条目 ID）持久化
# ---------------------------------------------------------------------------
def load_state(state_file: str) -> dict[str, str]:
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
            logger.warning("状态文件格式不正确，将以空状态启动。")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("读取状态文件失败：%s，将以空状态启动。", exc)
    return {}


def save_state(state_file: str, data: dict[str, str]) -> None:
    """通过临时文件原子写入，防止文件损坏。"""
    tmp = f"{state_file}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, state_file)
    except OSError as exc:
        logger.error("保存状态文件失败：%s", exc)


# ---------------------------------------------------------------------------
# 翻译
# ---------------------------------------------------------------------------
def translate_text(text: str, target_language: str) -> str:
    """使用 Google 非官方翻译接口翻译，失败时返回原文。"""
    if not target_language or not text:
        return text
    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": target_language,
        "dt": "t",
        "q": text,
    }
    try:
        resp = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params=params,
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        segments = resp.json()[0]
        return "".join(seg[0] for seg in segments if seg and seg[0])
    except (requests.RequestException, ValueError, IndexError, TypeError) as exc:
        logger.warning("翻译失败（改用原文）：%s", exc)
        return text


def _redact(text: str, bot_token: str) -> str:
    """将日志中出现的 bot token 打码，避免凭证泄露。"""
    if bot_token and bot_token in text:
        return text.replace(bot_token, "***")
    return text


# ---------------------------------------------------------------------------
# Telegram 推送
# ---------------------------------------------------------------------------
def send_to_telegram(
    bot_token: str,
    chat_id: str,
    message: str,
    pin_message: bool = False,
) -> None:
    send_url = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(send_url, json=payload, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Telegram 发送错误：%s", _redact(str(exc), bot_token))
        return

    if resp.status_code != 200:
        logger.error("Telegram 发送失败 %s：%s", resp.status_code, resp.text[:300])
        return

    if pin_message:
        message_id = resp.json().get("result", {}).get("message_id")
        if message_id:
            _pin_message(bot_token, chat_id, message_id)


def _pin_message(bot_token: str, chat_id: str, message_id: int) -> None:
    pin_url = f"{TELEGRAM_API}/bot{bot_token}/pinChatMessage"
    payload = {"chat_id": chat_id, "message_id": message_id}
    try:
        resp = requests.post(pin_url, json=payload, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("置顶消息失败：%s", resp.text[:200])
    except requests.RequestException as exc:
        logger.warning("置顶通信错误：%s", _redact(str(exc), bot_token))
