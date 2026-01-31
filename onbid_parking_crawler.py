import os
import time
import re
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.onbid.co.kr"
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
TEST_LIMIT = 5

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
# 검색 → iframe 진입
# -------------------------------------------------
def go_to_search_frame(page):
    print("[DEBUG] 메인 페이지 접속")
    page.goto(BASE_URL, timeout=60000)
    page.wait_for_load_state("networkidle")

    # 검색어 입력 후 Enter
    page.fill('input[type="text"]', "주차장")
    page.keyboard.press("Enter")

    time.sleep(3)

    # iframe 탐색
    frames = page.frames
    print(f"[DEBUG] 발견된 iframe 수: {len(frames)}")

    for f in frames:
        try:
            html = f.content()
            if "입찰물건" in html or "공고" in html:
                print("[DEBUG] 검색 결과 iframe 발견")
                return f
        except:
            continue

    print("[DEBUG] 검색 결과 iframe 못 찾음")
    return None

# -------------------------------------------------
# 목록 수집 (iframe 내부)
# -------------------------------------------------
def collect_links(frame):
    results = []
    items = frame.locator('[onclick]').all()

    print(f"[DEBUG] iframe 내 onclick 요소 수: {len(items)}")

    for el in items:
        try:
            onclick = el.get_attribute("onclick")
            text = el.inner_text()

            if not onclick or "주차장" not in text:
                continue

            m = re.search(r'\d{4}-\d{4}-\d{6}', onclick)
            if not m:
                continue

            gonggo_no = m.group(0)
            url = f"{BASE_URL}/op/opi/opip/gonggoDetail.do?gonggoNo={gonggo_no}"
            title = text.split("\n")[0].strip()

            results.append({
                "공고명": title,
                "url": url
            })

        except:
            continue

    print(f"[DEBUG] 최종 주차장 공고 수: {len(results)}")
    return results

# -------------------------------------------------
# 상세 페이지
# -------------------------------------------------
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
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()

    try:
        print("=== 온비드 주차장 크롤링 검증 시작 ===")

        frame = go_to_search_frame(page)
        if not frame:
            send_slack([{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "❌ 검색 결과 iframe을 찾지 못했습니다"}
            }])
            return

        items = collect_links(frame)

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
                    "text": f"총 *{len(items)}건* 중 상위 *{TEST_LIMIT}건* 전송"
                }
            },
            {"type": "divider"}
        ])

        for i, item in enumerate(items[:TEST_LIMIT], 1):
            page.goto(item["url"])
            page.wait_for_load_state("networkidle")

            detail = parse_detail(page)
            detail["공고명"] = item["공고명"]
            detail["url"] = item["url"]

            send_slack(build_slack_blocks(detail, i))
            time.sleep(1)

    finally:
        browser.close()
        playwright.stop()

if __name__ == "__main__":
    main()



