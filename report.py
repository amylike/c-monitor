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


def get_recent_runs() -> list[dict]:
    result = subprocess.run(
        ["gh", "run", "list", "--repo", REPO, "--workflow", "monitor.yml",
         "--limit", "20", "--json", "createdAt,updatedAt,conclusion,status"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def read_state(target_id: str) -> str:
    try:
        with open(os.path.join(STATE_DIR, f"{target_id}.txt")) as f:
            return f.read().strip() or "(none)"
    except FileNotFoundError:
        return "(none)"


def fmt_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}분"
    return f"{minutes // 60}h {minutes % 60}m"


def main() -> None:
    now = datetime.now(timezone.utc)
    runs = get_recent_runs()

    in_progress = [r for r in runs if r["status"] in ("in_progress", "queued")]
    completed = [r for r in runs if r["status"] == "completed"]

    failed_24h = sum(
        1 for r in completed
        if r["conclusion"] == "failure"
        and datetime.fromisoformat(r["updatedAt"].replace("Z", "+00:00")) >= now - timedelta(hours=24)
    )

    if in_progress:
        run = max(in_progress, key=lambda r: r["createdAt"])
        started = datetime.fromisoformat(run["createdAt"].replace("Z", "+00:00"))
        elapsed = int((now - started).total_seconds() / 60)
        health = "✅"
        status_line = f"• 모니터링: <b>실행 중</b> ({fmt_duration(elapsed)}째 폴링)"
    elif completed:
        last = max(completed, key=lambda r: r["updatedAt"])
        ended = datetime.fromisoformat(last["updatedAt"].replace("Z", "+00:00"))
        gap = int((now - ended).total_seconds() / 60)
        if gap < 30:
            health = "⚠️"
            status_line = f"• 모니터링: <b>휴지 중</b> (종료 {fmt_duration(gap)} 전, 큐 인계 대기 가능)"
        else:
            health = "❌"
            status_line = f"• 모니터링: <b>중단됨</b> (마지막 종료 {fmt_duration(gap)} 전)"
    else:
        health = "❌"
        status_line = "• 모니터링: <b>실행 기록 없음</b>"

    state_lines = [
        f"  • {name}: <b>{read_state(tid)}</b>"
        for tid, name in TARGETS
    ]

    msg = (
        f"{health} <b>c- 모니터링 리포트</b>\n"
        f"{status_line}\n"
        f"• 최근 24시간 실패: {failed_24h}회\n"
        f"• 현재 상태:\n" + "\n".join(state_lines)
    )
    send_telegram(msg)
    print(msg)


if __name__ == "__main__":
    main()
