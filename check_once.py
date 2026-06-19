#!/usr/bin/env python3
"""Sanity check: fetch target + reference URL, print detected state, send telegram."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monitor
from monitor import fetch_html, detect_state, send_telegram, URL

REFERENCE_URL = "https://www.cartier.com/ko-kr/%EC%8B%9C%EA%B3%84/%EC%BB%AC%EB%A0%89%EC%85%98/%EC%82%B0%ED%86%A0%EC%8A%A4-%EB%93%9C-%EA%B9%8C%EB%A5%B4%EB%9D%A0%EC%97%90/%EC%82%B0%ED%86%A0%EC%8A%A4-%EB%92%A4%EB%AA%BD-%EC%9B%8C%EC%B9%98-CRW2SA0046.html"


def fetch(url):
    monitor.URL = url
    return fetch_html()


# Target (current: should be 'consult')
monitor.URL = URL
target_html = fetch_html()
target_state = detect_state(target_html)
print(f"target  ({URL[-30:]}): {target_state}")

# Reference (should be 'available')
monitor.URL = REFERENCE_URL
ref_html = fetch_html()
ref_state = detect_state(ref_html)
print(f"ref     ({REFERENCE_URL[-30:]}): {ref_state}")

# Restore + send telegram test message
monitor.URL = URL
ok = send_telegram(
    f"🧪 검출 테스트\n"
    f"• 타겟 상품: <b>{target_state}</b> (예상: consult)\n"
    f"• 레퍼런스(구매가능): <b>{ref_state}</b> (예상: available)"
)
print(f"telegram ok: {ok}")
