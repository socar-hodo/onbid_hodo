import os
import time
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.onbid.co.kr"

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
ONBID_ID = os.environ.get("ONBID_ID", "")
ONBID_PW = os.environ.get("ONBID_PW", "")

TEST_LIMIT = 5   # 🔍 검증용: 슬랙으로 보낼 공고 수 제한

# -------------------------------------------------
# Slack
# -------------------------------------------------
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
    url = f"{BASE_URL}/op/opi/opip/gonggoList.do?searchWord=주차장"
    print(f"[DEBUG] 목록 페이지 이동: {url}")
    page.goto(url)
    page.wait_for_load_state("networkidle")

def collect_links(page):
    results = []
    rows = page.locator("table tbody tr").all()

    print(f"[DEBUG] 목록 row 수: {len(rows)}")

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

# -------------------------------------------------
# Main (검증 모드)
# -------------------------------------------------
def main():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()

    try:
        print("=" * 70)
        print("온비드 주차장 크롤링 검증 모드 시작")
        print("=" * 70)

        login(page)
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
                    "text": f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                            f"총 *{len(items)}건* 중 상위 *{TEST_LIMIT}건* 전송"
                }
            },
            {"type": "divider"}
        ])

        for i, item in enumerate(items[:TEST_LIMIT], 1):
            print(f"\n[DEBUG] 상세 페이지 진입 {i}")
            print(f"        URL: {item['url']}")

            page.goto(item["url"])
            page.wait_for_load_state("networkidle")

            detail = parse_detail(page)

            print("[DEBUG] 파싱 결과")
            for k, v in detail.items():
                print(f"   {k}: {v[:80]}")

            detail["공고명"] = item["공고명"]
            detail["url"] = item["url"]

            send_slack(build_slack_blocks(detail, i))
            time.sleep(1)

        print("\n✓ 검증용 슬랙 전송 완료")

    finally:
        browser.close()
        playwright.stop()

if __name__ == "__main__":
    main()

