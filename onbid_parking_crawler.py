import os
import time
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime

SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
ONBID_ID = os.environ.get('ONBID_ID', '')
ONBID_PW = os.environ.get('ONBID_PW', '')

print("=" * 70)
print("온비드 주차장 크롤러 (검증용 / 기존 정상 루트)")
print("=" * 70)

playwright = sync_playwright().start()
browser = playwright.chromium.launch(
    headless=True,
    args=['--no-sandbox']
)
page = browser.new_page()

try:
    # 0. 메인 페이지
    print("\n[0] 메인 페이지 접속")
    page.goto("https://www.onbid.co.kr", timeout=60000)
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    # 1. 로그인 (옵션)
    if ONBID_ID and ONBID_PW:
        print("\n[1] 로그인 시도")
        for s in ['a:has-text("로그인")', 'button:has-text("로그인")']:
            if page.locator(s).count():
                page.click(s)
                break
        time.sleep(2)

        for s in ['input[name="id"]', 'input[name="userId"]']:
            if page.locator(s).count():
                page.fill(s, ONBID_ID)
                break

        for s in ['input[name="pw"]', 'input[type="password"]']:
            if page.locator(s).count():
                page.fill(s, ONBID_PW)
                break

        for s in ['button[type="submit"]', 'button:has-text("로그인")']:
            if page.locator(s).count():
                page.click(s)
                break

        page.wait_for_load_state("networkidle")
        time.sleep(3)
        print("✓ 로그인 처리 완료")
    else:
        print("\n[1] 로그인 정보 없음 → 비로그인 진행")

    # 2. 부동산 → 공고
    print("\n[2] 부동산 → 공고 이동")
    for s in ['a:has-text("부동산")']:
        if page.locator(s).count():
            page.click(s)
            break
    time.sleep(2)

    for s in ['a:has-text("공고")']:
        if page.locator(s).count():
            page.click(s)
            break
    time.sleep(3)

    page.screenshot(path="gonggo_page.png", full_page=True)
    print("✓ 공고 페이지 진입")

    # 3. 검색어 입력
    print("\n[3] 검색어 입력: 주차장")
    for s in [
        'input[name="searchWord"]',
        'input[placeholder*="검색"]'
    ]:
        if page.locator(s).count():
            page.fill(s, "주차장")
            break

    # 4. 검색 실행
    for s in ['button:has-text("검색")', 'input[type="submit"]']:
        if page.locator(s).count():
            page.click(s)
            break

    page.wait_for_load_state("networkidle")
    time.sleep(3)
    page.screenshot(path="search_results.png", full_page=True)
    print("✓ 검색 완료")

    # 5. 테이블 기반 결과 추출 (⭐ 핵심)
    print("\n[5] 테이블 결과 파싱")
    rows = page.locator("tr").all()
    print(f"총 tr 개수: {len(rows)}")

    parking_data = []

    for row in rows:
        cells = row.locator("td").all()
        if len(cells) < 4:
            continue

        texts = [c.inner_text().strip() for c in cells]
        row_text = " ".join(texts)

        if "주차" not in row_text:
            continue

        parking_data.append({
            "공고번호": texts[0],
            "물건정보": texts[2],
            "소재지": texts[3],
            "입찰기간": texts[6] if len(texts) > 6 else "",
            "상태": texts[-1]
        })

    print(f"✓ 주차장 공고 발견: {len(parking_data)}건")

    # 6. Slack 전송
    if SLACK_WEBHOOK_URL:
        requests.post(SLACK_WEBHOOK_URL, json={
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🅿️ 온비드 주차장 공고 (검증)",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n총 *{len(parking_data)}건*"
                    }
                },
                {"type": "divider"}
            ]
        })

        for i, p in enumerate(parking_data[:10], 1):
            fields = [
                {"type": "mrkdwn", "text": f"*{k}*\n{v}"}
                for k, v in p.items() if v
            ]
            requests.post(SLACK_WEBHOOK_URL, json={
                "blocks": [
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*{i}. 주차장*"}},
                    {"type": "section", "fields": fields},
                    {"type": "divider"}
                ]
            })
            time.sleep(1)

        print("✓ 슬랙 전송 완료")

except Exception as e:
    print("✗ 오류 발생:", e)
    page.screenshot(path="error.png", full_page=True)

finally:
    browser.close()
    playwright.stop()
    print("\n완료")
