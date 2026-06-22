#!/usr/bin/env python3
import os
import re
import sys
import time
import random
import signal
import logging
import subprocess
from datetime import datetime, timedelta, timezone

TARGETS = [
    {
        "id": "CRWSTA0106",
        "name": "Tank Must de Cartier (CRWSTA0106)",
        "url": "https://www.cartier.com/ko-kr/watches/all-collections/tank/%ED%83%B1%ED%81%AC-%EB%A8%B8%EC%8A%A4%ED%8A%B8-%EB%93%9C-%EA%B9%8C%EB%A5%B4%EB%9D%A0%EC%97%90-%EC%9B%8C%EC%B9%98-CRWSTA0106.html",
    },
    {
        "id": "CRWSTA0136",
        "name": "Tank Must de Cartier (CRWSTA0136)",
        "url": "https://www.cartier.com/ko-kr/watches/all-collections/tank/%ED%83%B1%ED%81%AC-%EB%A8%B8%EC%8A%A4%ED%8A%B8-%EB%93%9C-%EA%B9%8C%EB%A5%B4%EB%9D%A0%EC%97%90-%EC%9B%8C%EC%B9%98-CRWSTA0136.html",
    },
    {
        "id": "CRWSTA0090",
        "name": "Tank Must SolarBeat (CRWSTA0090)",
        "url": "https://www.cartier.com/ko-kr/watches/all-collections/tank/%ED%83%B1%ED%81%AC-%EB%A8%B8%EC%8A%A4%ED%8A%B8-%EC%86%94%EB%9D%BC%EB%B9%84%ED%8A%B8%E2%84%A2-%EC%9B%8C%EC%B9%98-CRWSTA0090.html",
    },
]

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "monitor.log")
STATE_DIR = os.path.join(BASE_DIR, "states")
LAST_REPORT_PATH = os.path.join(STATE_DIR, "_last_report.txt")
os.makedirs(STATE_DIR, exist_ok=True)

KST = timezone(timedelta(hours=9))
REPORT_HOURS_KST = (8, 12, 17)

CURL_HEADERS = [
    "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "-H", "Accept-Language: ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "-H", "Sec-Fetch-Dest: document",
    "-H", "Sec-Fetch-Mode: navigate",
    "-H", "Sec-Fetch-Site: none",
    "-H", "Upgrade-Insecure-Requests: 1",
]

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def send_telegram(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        result = subprocess.run(
            [
                "curl", "-s", "--max-time", "15",
                "-X", "POST", url,
                "--data-urlencode", f"chat_id={TELEGRAM_CHAT_ID}",
                "--data-urlencode", f"text={text}",
                "--data-urlencode", "parse_mode=HTML",
                "--data-urlencode", "disable_web_page_preview=false",
            ],
            capture_output=True, text=True, timeout=20,
        )
        ok = result.returncode == 0 and '"ok":true' in result.stdout
        if not ok:
            logging.error("Telegram send failed rc=%s stdout=%s stderr=%s",
                          result.returncode, result.stdout[:300], result.stderr[:300])
        return ok
    except Exception as e:
        logging.error("Telegram send exception: %s", e)
        return False


def fetch_html(url: str) -> str:
    result = subprocess.run(
        ["curl", "-sSL", "--max-time", "25", "--compressed", *CURL_HEADERS, url],
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed rc={result.returncode}: {result.stderr.decode('utf-8', 'replace')[:300]}")
    return result.stdout.decode("utf-8", errors="replace")


ADD_BUTTON_RE = re.compile(
    r'<[^>]*class="([^"]*)"[^>]*data-product-component="add-button"[^>]*>',
    re.IGNORECASE,
)
AVAIL_STATUS_RE = re.compile(
    r'<[^>]*class="([^"]*)"[^>]*data-product-component="availability-status"[^>]*>',
    re.IGNORECASE,
)


def detect_state(html: str) -> str:
    """Return one of: 'available', 'consult', 'unknown'."""
    add_m = ADD_BUTTON_RE.search(html)
    avail_m = AVAIL_STATUS_RE.search(html)

    add_hidden = ("hidden" in add_m.group(1).split()) if add_m else None
    consult_hidden = ("hidden" in avail_m.group(1).split()) if avail_m else None

    if add_m and add_hidden is False:
        return "available"
    if avail_m and consult_hidden is False:
        return "consult"
    return "unknown"


def state_path(target_id: str) -> str:
    return os.path.join(STATE_DIR, f"{target_id}.txt")


def read_last_state(target_id: str) -> str:
    try:
        with open(state_path(target_id)) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def write_state(target_id: str, state: str) -> None:
    with open(state_path(target_id), "w") as f:
        f.write(state)


def read_last_report_slot() -> str:
    try:
        with open(LAST_REPORT_PATH) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def write_last_report_slot(slot: str) -> None:
    with open(LAST_REPORT_PATH, "w") as f:
        f.write(slot)


def current_report_slot() -> str:
    now_kst = datetime.now(KST)
    if now_kst.hour in REPORT_HOURS_KST:
        return f"{now_kst:%Y-%m-%d}-{now_kst.hour:02d}"
    return ""


def send_report(last_states: dict) -> None:
    now_kst = datetime.now(KST)
    state_lines = [
        f"  • {t['name']}: <b>{last_states.get(t['id']) or '(none)'}</b>"
        for t in TARGETS
    ]
    msg = (
        f"📊 <b>c- 모니터링 리포트</b> ({now_kst:%H:%M} KST)\n"
        "• 모니터링: <b>실행 중</b>\n"
        "• 현재 상태:\n" + "\n".join(state_lines)
    )
    send_telegram(msg)


_running = True


def _stop(signum, frame):
    global _running
    _running = False
    logging.info("Received signal %s, stopping.", signum)


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def check_target(target: dict, last_states: dict) -> None:
    tid = target["id"]
    try:
        html = fetch_html(target["url"])
        state = detect_state(html)
        last = last_states.get(tid, "")
        logging.info("[%s] state=%s (last=%s)", tid, state, last or "(none)")

        if state == "available" and last != "available":
            success_count = 0
            for i in range(1, 21):
                ok = send_telegram(
                    f"🚨🚨🚨 [{i}/20] <b>쇼핑백에 추가하기</b> 버튼이 노출됐습니다!\n"
                    f"제품: <b>{target['name']}</b>\n"
                    f"지금 확인: <a href=\"{target['url']}\">바로가기</a>"
                )
                if ok:
                    success_count += 1
                time.sleep(0.5)
            logging.info("[%s] Notification burst sent: %d/20 ok", tid, success_count)

        if state in ("available", "consult"):
            if state != last:
                write_state(tid, state)
                last_states[tid] = state
    except Exception as e:
        logging.error("[%s] Fetch/parse error: %s", tid, e)
        raise


def main():
    logging.info("Monitor starting. targets=%d", len(TARGETS))
    if not os.environ.get("SKIP_LIFECYCLE_NOTIFY"):
        target_list = "\n".join(f"• {t['name']}" for t in TARGETS)
        send_telegram(
            f"🔔 c- 모니터링 시작 ({len(TARGETS)}개 상품)\n"
            f"{target_list}\n"
            "각 상품의 <b>쇼핑백에 추가하기</b> 노출 시 [1/20]~[20/20] 알림이 옵니다."
        )

    last_states = {t["id"]: read_last_state(t["id"]) for t in TARGETS}
    consecutive_errors = {t["id"]: 0 for t in TARGETS}
    last_report_slot = read_last_report_slot()

    while _running:
        for target in TARGETS:
            if not _running:
                break
            tid = target["id"]
            try:
                check_target(target, last_states)
                consecutive_errors[tid] = 0
            except Exception as e:
                consecutive_errors[tid] += 1
                if consecutive_errors[tid] in (5, 20, 100):
                    send_telegram(f"⚠️ [{tid}] 모니터링 오류 {consecutive_errors[tid]}회 연속: {e}")

            # small pause between targets in the same cycle
            if _running:
                time.sleep(random.uniform(2, 4))

        slot = current_report_slot()
        if slot and slot != last_report_slot:
            send_report(last_states)
            last_report_slot = slot
            write_last_report_slot(slot)

        delay = random.uniform(10, 20)
        end = time.time() + delay
        while _running and time.time() < end:
            time.sleep(min(1.0, end - time.time()))

    logging.info("Monitor stopped.")
    send_telegram("🛑 c- 모니터링 종료")


if __name__ == "__main__":
    main()
