import os
import time
import json
import re
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)

if now.weekday() >= 5:
    exit(0)

slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
onbid_id = os.environ.get("ONBID_ID", "")
onbid_pw = os.environ.get("ONBID_PW", "")

SAVED_FILE = "sent_gonggo.json"

if os.path.exists(SAVED_FILE):
    with open(SAVED_FILE, "r", encoding="utf-8") as f:
        sent_gonggos = set(json.load(f))
else:
    sent_gonggos = set()

all_parking_data = []

playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
page = browser.new_page()

try:
    page.goto("https://www.onbid.co.kr")
    time.sleep(3)

    if onbid_id and onbid_pw:
        page.click("text=로그인")
        time.sleep(2)
        page.fill('input[type="text"]', onbid_id)
        page.fill('input[type="password"]', onbid_pw)
        page.click("text=로그인")
        time.sleep(5)

    target = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do"
    page.goto(target)
    time.sleep(5)

    page.evaluate("""
        () => {
            const input = document.getElementById("searchCltrNm");
            if (input) input.value = "주차장";
            const btn = document.getElementById("searchBtn");
            if (btn) btn.click();
        }
    """)
    time.sleep(8)

    page_num = 1

    while True:

        rows = page.query_selector_all("tbody tr")

        for row in rows:

            text = row.inner_text()

            if "주차" not in text:
                continue

            text = text.replace("지도보기", "").replace("새 창 열기", "")

            gonggo_match = re.search(r"\d{4}-\d{4}-\d{6}", text)
            if not gonggo_match:
                continue

            gonggo_no = gonggo_match.group()

            if gonggo_no in sent_gonggos:
                continue

            # 주소 (공고번호 바로 아래 줄)
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            address = ""
            for i, line in enumerate(lines):
                if gonggo_no in line and i + 1 < len(lines):
                    address = lines[i + 1]
                    break

            # 면적
            area = ""
            area_match = re.search(r"\[.*?㎡\]", text)
            if area_match:
                area = area_match.group()

            # 입찰기간
            period_match = re.findall(r"\d{4}-\d{2}-\d{2}.*?\d{2}:\d{2}", text)
            period = " ~ ".join(period_match) if period_match else "-"

            # 최저입찰가
            price_match = re.search(r"\d{1,3}(,\d{3})+", text)
            price = price_match.group() if price_match else "-"

            # 조회수
            view_match = re.search(r"조회수\s*(\d+)", text)
            view = view_match.group(1) if view_match else "-"

            # 물건상태
            status_match = re.search(r"(인터넷입찰진행중|일반경쟁|제한경쟁)", text)
            status = status_match.group() if status_match else "-"

            detail_url = (
                "https://www.onbid.co.kr/op/cta/cltrdtl/"
                f"collateralDetailRealEstateList.do?search={gonggo_no}"
            )

            all_parking_data.append({
                "gonggo": gonggo_no,
                "address": address,
                "area": area,
                "period": period,
                "price": price,
                "status": status,
                "view": view,
                "link": detail_url
            })

            sent_gonggos.add(gonggo_no)

        next_btn = page.locator(f"a[onclick*='fn_paging({page_num+1})']")
        if next_btn.count() == 0:
            break

        next_btn.click()
        time.sleep(5)
        page_num += 1

    # ==============================
    # Slack 출력 (깔끔한 2열 구조)
    # ==============================

    if slack_webhook_url and all_parking_data:

        header = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🆕 온비드 신규 주차장 공고",
                        "emoji": True
                    }
                },
                {"type": "divider"}
            ]
        }

        requests.post(slack_webhook_url, json=header)
        time.sleep(1)

        for idx, item in enumerate(all_parking_data[:20], 1):

            blocks = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"🅿️ {idx}. {item['address']}",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*🔢 공고번호*\n{item['gonggo']}"
                        }
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*📏 면적*\n{item['area']}"}
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*📅 입찰기간*\n{item['period']}"},
                            {"type": "mrkdwn", "text": f"*💰 최저입찰가*\n{item['price']}"}
                        ]
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*🏷 물건상태*\n{item['status']}"},
                            {"type": "mrkdwn", "text": f"*👁 조회수*\n{item['view']}"}
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🔗 <{item['link']}|공고 상세보기>"
                        }
                    },
                    {"type": "divider"}
                ]
            }

            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)

    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_gonggos), f, ensure_ascii=False)

finally:
    browser.close()
    playwright.stop()





