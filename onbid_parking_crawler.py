import os
import time
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
ONBID_ID = os.environ.get("ONBID_ID", "")
ONBID_PW = os.environ.get("ONBID_PW", "")

print("=" * 70)
print("온비드 주차장 크롤러 시작")
print("=" * 70)

playwright = sync_playwright().start()
browser = playwright.chromium.launch(
    headless=True,
    args=["--no-sandbox"]
)
page = browser.new_page()

try:
    # -------------------------------------------------
    # 0. 메인 페이지
    # -------------------------------------------------
    page.goto("https://www.onbid.co.kr", timeout=60000)
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    # -------------------------------------------------
    # 1. 로그인 (있을 경우)
    # -------------------------------------------------
    if ONBID_ID and ONBID_PW:
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

    # -------------------------------------------------
    # 2. 부동산 → 공고 (메뉴 클릭)
    # -------------------------------------------------
    if page.locator('a:has-text("부동산")').count():
        page.click('a:has-text("부동산")')
        time.sleep(2)

    # 공고 메뉴는 직접 URL 이동 (가시성 이슈 회피)
    page.goto(
        "https://www.onbid.co.kr/op/ppa/plnmmn/publicAnnounceRlstList.do",
        timeout=60000
    )
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    # -------------------------------------------------
    # 3. 검색어 입력
    # -------------------------------------------------
    for s in [
        'input[name="searchWord"]',
        'input[placeholder*="검색"]'
    ]:
        if page.locator(s).count():
            page.fill(s, "주차장")
            break

    # -------------------------------------------------
    # 4. 검색 실행
    # -------------------------------------------------
    for s in ['button:has-text("검색")', 'input[type="submit"]']:
        if page.locator(s).count():
            page.click(s)
            break

    page.wait_for_load_state("networkidle")
    time.sleep(3)

    # -------------------------------------------------
    # 5. 결과 테이블 파싱 (⭐ 필드 정확 버전)
    # -------------------------------------------------
    rows = page.locator("tr").all()
    parking_data = []

    KEYWORDS = ["주차", "주차장", "주차시설"]

    for row in rows:
        cells = row.locator("td").all()
        if len(cells) < 6:
            continue

        # 컬럼 추출
        gonggo_no = cells[0].inner_text().strip()      # 공고번호
        info_text = cells[1].inner_text().strip()     # 제목 + 소재지
        bid_period = cells[3].inner_text().strip()    # 입찰기간
        min_price = cells[4].inner_text().strip()     # 최저입찰가
        status = cells[6].inner_text().strip() if len(cells) > 6 else ""

        # 제목 / 소재지 분리
        info_lines = info_text.split("\n")
        title = info_lines[0]
        address = " ".join(info_lines[1:]) if len(info_lines) > 1 else ""

        # 주차장 관련 필터
        if not any(k in (title + address) for k in KEYWORDS):
            continue

        parking_data.append({
            "공고번호": gonggo_no,
            "공고명": title,
            "소재지": address,
            "입찰기간": bid_period,
            "최저입찰가": min_price,
            "상태": status
        })

    # -------------------------------------------------
    # 6. Slack 전송
    # -------------------------------------------------
    if SLACK_WEBHOOK_URL:
        requests.post(SLACK_WEBHOOK_URL, json={
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🅿️ 온비드 주차장 공고",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                                f"총 *{len(parking_data)}건*"
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
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{i}. 주차장*"
                        }
                    },
                    {
                        "type": "section",
                        "fields": fields
                    },
                    {"type": "divider"}
                ]
            })
            time.sleep(1)

except Exception as e:
    print("오류 발생:", e)

finally:
    browser.close()
    playwright.stop()
    print("완료")
