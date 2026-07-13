#!/usr/bin/env bash
# X_monitor 守护脚本：若 rss_monitor.py 未在运行则启动它。
# 供 cron 看门狗使用（见 README「持续运行」）。
#
# crontab 示例：
#   @reboot     $HOME/github/X_monitor/run.sh
#   */5 * * * * $HOME/github/X_monitor/run.sh

set -euo pipefail

PROJECT_DIR="$HOME/github/X_monitor"
# 若使用虚拟环境，把 python3 换成 venv 里的解释器，例如：
#   PYTHON="$HOME/myenv/bin/python"
PYTHON="python3"

cd "$PROJECT_DIR" || exit 1

# 已在运行则直接退出，避免重复启动
if pgrep -f "rss_monitor.py" > /dev/null; then
    exit 0
fi

nohup "$PYTHON" rss_monitor.py >> x_monitor.log 2>&1 &
echo "$(date '+%Y-%m-%d %H:%M:%S') 已启动 rss_monitor.py" >> x_monitor.log
