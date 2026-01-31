import os
import time
import json
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.onbid.co.kr"

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
ONBID_ID = os.environ.get("ONBID_ID", "")
ONBID_PW = os.environ.get("ONBID_PW", "")

SEEN_FILE = "seen_ids.json"

# -------------------------------------------------
# Seen IDs (신규 공고 필터)
# -------------------------------------------------
def load_seen_ids():
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))

def save_seen_ids(seen_ids):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen_ids)), f, ensure_ascii=False, indent=2)

# -------------------------------------------------
# Slack
# -------------------------------------------------
def send_slack(blocks):
    if not SLACK_WEBHOOK_URL:
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
                "text": f"🔗 <{data.get('url')}>"
            }
        },
        {"type": "divider"}
    ]

# -------------------------------------------------
# Login (안전 버전)
# -------------------------------------------------
def login(page):
    if not ONBID_ID or not ONBID_PW:
        print("로그인 정보 없음 → 비로그인 진행")
        return

    page.goto(BASE_URL, timeout=60000)
    page.wait_for_load_state("networkidle")

    login_selectors = [
        'a:has-text("로그인")',
        'button:has-text("로그인")',
        'input[value*="로그인"]'
    ]

    clicked = False
    for s in login_selectors:
        try:
            if page.locator(s).count() > 0:
                page.click(s, timeout=5000)
                clicked = True
                break
        except:
            continue

    if not clicked:
        print("로그인 버튼 없음 → 스킵")
        return

    page.wait_for_timeout(2000)

    for s in ['input[name="id"]', 'input[name="userId"]', 'input[type="text"]']:
        if page.locator(s).count() > 0:
            page.fill(s, ONBID_ID)
            break

    for s in ['input[name="pw"]', 'input[name="password"]', 'input[type="password"]']:
        if page.locator(s).count() > 0:
            page.fill(s, ONBID_PW)
            break

    for s in ['button:has-text("로그인")', 'input[type="submit"]']:
        if page.locator(s).count() > 0:
            page.click(s)
            break

    page.wait_for_timeout(3000)
    page.wait_for_load_state("networkidle")
    print("✓ 로그인 시도 완료")

# -------------------------------------------------
# Crawling
# -------------------------------------------------
def go_to_list(page):
    page.goto(f"{BASE_URL}/op/opi/opip/gonggoList.do?searchWord=주차장")
    page.wait_for_load_state("networkidle")

def collect_links(page):
    results = []
    rows = page.locator("table tbody tr").all()

    for row in rows:
        if "주차장" not in row.inner_text():
            continue

        link = row.locator("a").first
        href = link.get_attribute("href")
        title = link.inner_text().strip()

        if href:
            results.append({
                "공고명": title,
                "url": BASE_URL + href
            })

    print(f"✓ 목록 {len(results)}건")
    return results

def parse_detail(page):
    data = {}
    rows = page.locator("div.info-row").all()

    for row in rows:
        try:
            k = row.locator(".info-tit").inner_text().strip()
            v = row.locator(".info-txt").inner_text().strip()
            data[k] = v
        except:
            continue

    return data

# -------------------------------------------------
# Main
# -------------------------------------------------
def main():
    seen_ids = load_seen_ids()
    new_results = []

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()

    try:
        login(page)
        go_to_list(page)

        items = collect_links(page)

        for item in items:
            page.goto(item["url"])
            page.wait_for_load_state("networkidle")

            detail = parse_detail(page)
            gonggo_no = detail.get("공고번호")

            if not gonggo_no or gonggo_no in seen_ids:
                continue

            detail["공고명"] = item["공고명"]
            detail["url"] = item["url"]

            new_results.append(detail)
            seen_ids.add(gonggo_no)
            time.sleep(1)

        if not new_results:
            send_slack([{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "🅿️ 신규 주차장 공고 없음"}
            }])
            return

        send_slack([
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🅿️ 신규 온비드 주차장 공고",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n총 *{len(new_results)}건*"
                }
            },
            {"type": "divider"}
        ])

        for i, data in enumerate(new_results, 1):
            send_slack(build_slack_blocks(data, i))
            time.sleep(1)

        save_seen_ids(seen_ids)
        print("✓ 신규 공고 알림 완료")

    finally:
        browser.close()
        playwright.stop()

if __name__ == "__main__":
    main()

