import os
import time
import json
import re
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
current_time = datetime.now(KST)

if current_time.weekday() >= 5:
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
    page.goto("https://www.onbid.co.kr", timeout=60000)
    time.sleep(3)

    if onbid_id and onbid_pw:
        page.click("text=로그인")
        time.sleep(2)
        page.fill('input[type="text"]', onbid_id)
        page.fill('input[type="password"]', onbid_pw)
        page.click("text=로그인")
        time.sleep(5)

    target_url = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do"
    page.goto(target_url)
    time.sleep(5)

    page.evaluate("""
        () => {
            const input = document.getElementById("searchCltrNm");
            if (input) {
                input.value = "주차장";
                input.dispatchEvent(new Event("change", { bubbles: true }));
            }
            const btn = document.getElementById("searchBtn");
            if (btn) btn.click();
        }
    """)
    time.sleep(8)

    page_num = 1

    while True:

        table_data = page.evaluate("""
        () => {

            const results = [];
            const rows = document.querySelectorAll("tbody tr");

            rows.forEach(row => {

                const fullText = row.innerText;

                if (!fullText.includes("주차")) return;

                const titleBtn = row.querySelector("a[title*='-']");
                if (!titleBtn) return;

                const gonggoNo = titleBtn.getAttribute("title") || "";

                results.push({
                    gonggoNo,
                    fullText
                });
            });

            return results;
        }
        """)

        for item in table_data:

            raw_no = item["gonggoNo"]

            # 🔥 공고번호 정제 (새 창 열기 제거)
            match = re.search(r"\d{4}-\d{4}-\d{6}", raw_no)
            if not match:
                continue

            gonggo_no = match.group()

            if gonggo_no in sent_gonggos:
                continue

            text = item["fullText"]

            # 🔥 필요없는 텍스트 제거
            text = text.replace("지도보기", "")
            text = text.replace("새 창 열기", "")
            text = re.sub(r"\s+", " ", text).strip()

            # 상세 링크
            detail_url = (
                "https://www.onbid.co.kr/op/cta/cltrdtl/"
                f"collateralDetailRealEstateList.do?search={gonggo_no}"
            )

            all_parking_data.append({
                "공고번호": gonggo_no,
                "본문": text,
                "공고링크": detail_url
            })

            sent_gonggos.add(gonggo_no)

        next_page = page_num + 1
        next_btn = page.locator(f"a[onclick*='fn_paging({next_page})']")

        if next_btn.count() == 0:
            break

        next_btn.click()
        time.sleep(5)
        page_num += 1

    # ==============================
    # Slack 출력
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
                            "text": f"🅿️ {idx}. {item['공고번호']}",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": item["본문"]
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🔗 <{item['공고링크']}|공고 상세보기>"
                        }
                    },
                    {"type": "divider"}
                ]
            }

            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)

    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_gonggos), f, ensure_ascii=False, indent=2)

finally:
    browser.close()
    playwright.stop()




