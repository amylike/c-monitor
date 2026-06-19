#!/usr/bin/env python3
"""Send hourly summary of monitor.yml runs + current detected state."""
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

REPO = "amylike/c-monitor"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TARGETS = [
    ("CRWSTA0106", "Tank Must de Cartier (CRWSTA0106)"),
    ("CRWSTA0136", "Tank Must de Cartier (CRWSTA0136)"),
    ("CRWSTA0090", "Tank Must SolarBeat (CRWSTA0090)"),
]

STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "states")


def send_telegram(text: str) -> None:
    subprocess.run(
        [
            "curl", "-s", "--max-time", "15",
            "-X", "POST",
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            "--data-urlencode", f"chat_id={TELEGRAM_CHAT_ID}",
            "--data-urlencode", f"text={text}",
            "--data-urlencode", "parse_mode=HTML",
        ],
        check=False,
    )


def get_recent_runs(hours: int = 1) -> list[dict]:
    result = subprocess.run(
        ["gh", "run", "list", "--repo", REPO, "--workflow", "monitor.yml",
         "--limit", "50", "--json", "createdAt,conclusion,status"],
        capture_output=True, text=True, check=True,
    )
    runs = json.loads(result.stdout)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [
        r for r in runs
        if datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")) >= cutoff
    ]


def read_state(target_id: str) -> str:
    try:
        with open(os.path.join(STATE_DIR, f"{target_id}.txt")) as f:
            return f.read().strip() or "(none)"
    except FileNotFoundError:
        return "(none)"


def main() -> None:
    runs = get_recent_runs(hours=1)
    success = sum(1 for r in runs if r["conclusion"] == "success")
    failed = sum(1 for r in runs if r["conclusion"] == "failure")
    running = sum(1 for r in runs if r["status"] in ("in_progress", "queued"))
    expected = 12

    state_lines = [
        f"  • {name}: <b>{read_state(tid)}</b>"
        for tid, name in TARGETS
    ]

    if failed > 0:
        health = "⚠️"
    elif success + running >= expected - 2:
        health = "✅"
    else:
        health = "ℹ️"

    msg = (
        f"{health} <b>지난 1시간 c- 모니터링 리포트</b>\n"
        f"• 실행: 성공 {success} / 실패 {failed} / 진행중 {running} (기대 {expected})\n"
        f"• 현재 상태:\n" + "\n".join(state_lines)
    )
    send_telegram(msg)
    print(msg)


if __name__ == "__main__":
    main()
