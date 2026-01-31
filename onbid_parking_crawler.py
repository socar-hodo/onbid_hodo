import os
import time
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
ONBID_ID = os.environ.get("ONBID_ID", "")
ONBID_PW = os.environ.get("ONBID_PW", "")

BASE_URL = "https://www.onbid.co.kr"

# -----------------------------
# Slack
# -----------------------------
def send_slack(blocks):
    requests.post(SLACK_WEBHOOK_URL, json={"blocks": blocks})

def build_slack_blocks(data, idx):
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{idx}. 🅿️ {data.get('공고명','주차장 공고')}*"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*공고번호*\n{data.get('공고번호','-')}"},
                {"type": "mrkdwn", "text": f"*입찰기간*\n{data.get('입찰기간','-')}"},
                {"type": "mrkdwn", "text": f"*소재지*\n{data.get('소재지','-')[:120]}"},
                {"type": "mrkdwn", "text": f"*감정가*\n{data.get('감정가','-')}"},
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔗 <{data.get('url')}>"
            }
        },
        {"type": "divider"}
    ]

# -----------------------------
# Onbid Crawling
# -----------------------------
def login(page):
    if not ONBID_ID or not ONBID_PW:
        print("로그인 정보 없음 → 비로그인 진행")
        return

    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    page.click('a:has-text("로그인")')
    time.sleep(2)

    page.fill('input[type="text"]', ONBID_ID)
    page.fill('input[type="password"]', ONBID_PW)
    page.click('button:has-text("로그인")')

    page.wait_for_load_state("networkidle")
    print("✓ 로그인 완료")

def go_to_parking_list(page):
    page.goto(
        f"{BASE_URL}/op/opi/opip/gonggoList.do?searchWord=주차장"
    )
    page.wait_for_load_state("networkidle")
    page.screenshot(path="list_page.png", full_page=True)

def collect_parking_links(page):
    results = []

    rows = page.locator("table tbody tr").all()
    for row in rows:
        text = row.inner_text()
        if "주차장" not in text:
            continue

        link = row.locator("a").first
        href = link.get_attribute("href")
        title = link.inner_text().strip()

        if href:
            results.append({
                "공고명": title,
                "url": BASE_URL + href
            })

    print(f"✓ 주차장 공고 {len(results)}건 수집")
    return results

def parse_detail(page):
    data = {}

    rows = page.locator("div.info-row").all()
    for row in rows:
        try:
            key = row.locator(".info-tit").inner_text().strip()
            val = row.locator(".info-txt").inner_text().strip()
            data[key] = val
        except:
            continue

    return data

# -----------------------------
# Main
# -----------------------------
def main():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()

    try:
        login(page)
        go_to_parking_list(page)

        parking_items = collect_parking_links(page)
        results = []

        for item in parking_items:
            page.goto(item["url"])
            page.wait_for_load_state("networkidle")
            page.screenshot(path="detail_page.png", full_page=True)

            detail = parse_detail(page)
            detail["공고명"] = item["공고명"]
            detail["url"] = item["url"]

            results.append(detail)
            time.sleep(1)

        # Slack Header
        send_slack([
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🅿️ 온비드 주차장 공고 알림",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n총 *{len(results)}건*"
                }
            },
            {"type": "divider"}
        ])

        for i, data in enumerate(results, 1):
            send_slack(build_slack_blocks(data, i))
            time.sleep(1)

        print("✓ 슬랙 전송 완료")

    finally:
        browser.close()
        playwright.stop()

if __name__ == "__main__":
    main()
