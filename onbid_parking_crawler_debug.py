import os
import time
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

# ==============================
# 기본 설정
# ==============================
BASE_URL = "https://www.onbid.co.kr"
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

TEST_LIMIT = 5   # ✅ 슬랙으로 보낼 주차장 공고 개수 (검증용)

# ==============================
# Slack
# ==============================
def send_slack(blocks):
    if not SLACK_WEBHOOK_URL:
        print("[DEBUG] SLACK_WEBHOOK_URL 없음")
        return
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
                "text": f"🔗 <{data.get('url','')}>"
            }
        },
        {"type": "divider"}
    ]

# ==============================
# Crawling Functions
# ==============================
def go_to_list(page):
    url = f"{BASE_URL}/op/opi/opip/gonggoList.do?searchWord=주차장"
    print(f"[DEBUG] 목록 페이지 이동: {url}")
    page.goto(url)
    page.wait_for_load_state("networkidle")
    page.screenshot(path="debug_list.png", full_page=True)

def collect_links(page):
    results = []
    rows = page.locator("table tbody tr").all()

    print(f"[DEBUG] 목록 row 수: {len(rows)}")

    for i, row in enumerate(rows):
        text = row.inner_text()
        if "주차장" not in text:
            continue

        link = row.locator("a").first
        href = link.get_attribute("href")
        title = link.inner_text().strip()

        print(f"[DEBUG] 주차장 row 발견 {i}")
        print(f"        제목: {title}")
        print(f"        href: {href}")

        if href:
            results.append({
                "공고명": title,
                "url": BASE_URL + href
            })

    print(f"[DEBUG] 주차장 공고 수집 결과: {len(results)}")
    return results

def parse_detail(page):
    data = {}
    rows = page.locator("div.info-row").all()

    print(f"[DEBUG] 상세 info-row 수: {len(rows)}")

    for row in rows:
        try:
            key = row.locator(".info-tit").inner_text().strip()
            val = row.locator(".info-txt").inner_text().strip()
            data[key] = val
        except:
            continue

    return data

# ==============================
# Main (DEBUG MODE)
# ==============================
def main():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()

    try:
        print("=" * 60)
        print("[DEBUG] 온비드 주차장 크롤링 검증 시작")
        print("=" * 60)

        go_to_list(page)
        items = collect_links(page)

        if not items:
            send_slack([{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "❌ 주차장 공고 목록을 찾지 못했습니다"}
            }])
            return

        send_slack([
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🧪 온비드 주차장 공고 크롤링 검증",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"총 *{len(items)}건* 중 상위 *{TEST_LIMIT}건*을 테스트 전송합니다"
                }
            },
            {"type": "divider"}
        ])

        for i, item in enumerate(items[:TEST_LIMIT], 1):
            print(f"\n[DEBUG] 상세 페이지 진입 {i}")
            print(f"        URL: {item['url']}")

            page.goto(item["url"])
            page.wait_for_load_state("networkidle")
            page.screenshot(path=f"debug_detail_{i}.png", full_page=True)

            detail = parse_detail(page)

            print("[DEBUG] 파싱 결과:")
            for k, v in detail.items():
                print(f"   {k}: {v[:80]}")

            detail["공고명"] = item["공고명"]
            detail["url"] = item["url"]

            send_slack(build_slack_blocks(detail, i))
            time.sleep(1)

        print("\n[DEBUG] 검증용 슬랙 전송 완료")

    finally:
        browser.close()
        playwright.stop()

if __name__ == "__main__":
    main()
