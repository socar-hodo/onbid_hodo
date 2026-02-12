import os
import time
import json
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone

# ==============================
# 기본 설정
# ==============================

KST = timezone(timedelta(hours=9))
current_time = datetime.now(KST)
weekday = current_time.weekday()

# 주말 실행 방지
if weekday >= 5:
    print("주말 실행 안함")
    exit(0)

slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
onbid_id = os.environ.get("ONBID_ID", "")
onbid_pw = os.environ.get("ONBID_PW", "")

SAVED_FILE = "sent_gonggo.json"

# 기존 발송 공고번호 로드
if os.path.exists(SAVED_FILE):
    with open(SAVED_FILE, "r", encoding="utf-8") as f:
        sent_gonggos = set(json.load(f))
else:
    sent_gonggos = set()

print(f"기존 발송 공고 수: {len(sent_gonggos)}")

all_parking_data = []

# ==============================
# Playwright 시작
# ==============================

playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
page = browser.new_page()

try:
    # 1. 온비드 접속
    page.goto("https://www.onbid.co.kr", timeout=60000)
    time.sleep(3)

    # 2. 로그인
    if onbid_id and onbid_pw:
        page.click("text=로그인")
        time.sleep(2)
        page.fill('input[type="text"]', onbid_id)
        page.fill('input[type="password"]', onbid_pw)
        page.click("text=로그인")
        time.sleep(5)

    # 3. 담보물 부동산 페이지 이동
    target_url = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do"
    page.goto(target_url)
    time.sleep(5)

    # 4. "주차장" 검색
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

    # ==============================
    # 전체 페이지 순회
    # ==============================

    page_num = 1

    while True:

        print(f"{page_num}페이지 수집 중...")

        table_data = page.evaluate("""
        () => {
            const results = [];
            const rows = document.querySelectorAll("tbody tr");

            rows.forEach(row => {

                const cells = Array.from(row.querySelectorAll("td"));
                if (cells.length < 5) return;

                const texts = cells.map(td => td.innerText.trim());
                const rowText = texts.join(" ");

                if (!rowText.includes("주차")) return;

                let gonggoNo = "";
                const titleBtn = row.querySelector("a[title*='-']");
                if (titleBtn) {
                    gonggoNo = titleBtn.getAttribute("title") || "";
                }

                results.push({
                    texts,
                    gonggoNo
                });
            });

            return results;
        }
        """)

        for item in table_data:

            gonggo_no = item["gonggoNo"]
            if not gonggo_no:
                continue

            if gonggo_no in sent_gonggos:
                continue

            texts = item["texts"]

            # 안전한 값 추출
            address = texts[0] if len(texts) > 0 else ""
            area = next((t for t in texts if "㎡" in t), "")
            bid_period = next((t for t in texts if "~" in t), "")
            price = next((t for t in texts if "," in t and "원" not in t), "")
            status = next((t for t in texts if "진행" in t or "경쟁" in t), "")
            view_cnt = next((t for t in texts if t.isdigit()), "")

            # ✅ 세션 없이 열리는 상세 링크
            detail_url = (
                "https://www.onbid.co.kr/op/cta/cltrdtl/"
                f"collateralDetailRealEstateList.do?search={gonggo_no}"
            )

            parking_info = {
                "공고번호": gonggo_no,
                "물건명주소": address,
                "면적": area,
                "입찰기간": bid_period,
                "최저입찰가": price,
                "물건상태": status,
                "조회수": view_cnt,
                "공고링크": detail_url
            }

            all_parking_data.append(parking_info)
            sent_gonggos.add(gonggo_no)

        # 다음 페이지 이동
        next_page = page_num + 1
        next_btn = page.locator(f"a[onclick*='fn_paging({next_page})']")

        if next_btn.count() == 0:
            break

        next_btn.click()
        time.sleep(5)
        page_num += 1

    print(f"신규 공고 {len(all_parking_data)}개 발견")

    # ==============================
    # Slack 전송 (처음 구조 유지)
    # ==============================

    if slack_webhook_url and len(all_parking_data) > 0:

        header = {
            "blocks": [
                {"type": "header",
                 "text": {"type": "plain_text",
                          "text": "🆕 온비드 주차장 물건",
                          "emoji": True}},
                {"type": "divider"}
            ]
        }

        requests.post(slack_webhook_url, json=header)
        time.sleep(1)

        for idx, parking in enumerate(all_parking_data[:20], 1):

            blocks = {
                "blocks": [
                    {"type": "header",
                     "text": {"type": "plain_text",
                              "text": f"🅿️ {idx}. {parking['물건명주소'][:50]}",
                              "emoji": True}},
                    {"type": "section",
                     "text": {"type": "mrkdwn",
                              "text": f"*🔢 공고번호*\n{parking['공고번호']}"}}
                ]
            }

            if parking["면적"]:
                blocks["blocks"].append({
                    "type": "section",
                    "text": {"type": "mrkdwn",
                             "text": f"*📏 면적*\n{parking['면적']}"}
                })

            blocks["blocks"].append({
                "type": "section",
                "fields": [
                    {"type": "mrkdwn",
                     "text": f"*📅 입찰기간*\n{parking['입찰기간'] or '-'}"},
                    {"type": "mrkdwn",
                     "text": f"*💰 최저입찰가*\n{parking['최저입찰가'] or '-'}"}
                ]
            })

            blocks["blocks"].append({
                "type": "section",
                "fields": [
                    {"type": "mrkdwn",
                     "text": f"*🏷️ 물건상태*\n{parking['물건상태'] or '-'}"},
                    {"type": "mrkdwn",
                     "text": f"*👁️ 조회수*\n{parking['조회수'] or '-'}"}
                ]
            })

            blocks["blocks"].append({
                "type": "section",
                "text": {"type": "mrkdwn",
                         "text": f"🔗 <{parking['공고링크']}|공고 상세보기>"}
            })

            blocks["blocks"].append({"type": "divider"})

            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)

    # 신규 공고 저장
    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_gonggos), f, ensure_ascii=False, indent=2)

finally:
    browser.close()
    playwright.stop()
    print("완료")


