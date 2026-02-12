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
    # ==============================
    # 1. 온비드 접속
    # ==============================
    page.goto("https://www.onbid.co.kr", timeout=60000)
    time.sleep(3)

    # ==============================
    # 2. 로그인
    # ==============================
    if onbid_id and onbid_pw:
        page.click("text=로그인")
        time.sleep(2)
        page.fill('input[type="text"]', onbid_id)
        page.fill('input[type="password"]', onbid_pw)
        page.click("text=로그인")
        time.sleep(5)

    # ==============================
    # 3. 담보물 부동산 이동
    # ==============================
    target_url = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do"
    page.goto(target_url)
    time.sleep(5)

    # ==============================
    # 4. "주차장" 검색
    # ==============================
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
    # 5. 전체 페이지 순회 크롤링
    # ==============================

    page_num = 1

    while True:

        print(f"{page_num}페이지 수집 중...")

        table_data = page.evaluate("""
        () => {

            const results = [];
            const rows = document.querySelectorAll("tbody tr");

            rows.forEach(row => {

                // 공고번호는 title 속성에서만 가져오기
                const titleBtn = row.querySelector("a[title*='-']");
                if (!titleBtn) return;

                const gonggoNo = titleBtn.getAttribute("title") || "";

                // 주소는 공고번호 링크가 있는 td의 텍스트에서 추출
                const parentTd = titleBtn.closest("td");
                if (!parentTd) return;

                let fullText = parentTd.innerText;

                // 불필요한 텍스트 제거
                fullText = fullText
                    .replace("지도보기", "")
                    .replace("새 창 열기", "")
                    .replace(gonggoNo, "")
                    .replace(/\\s+/g, " ")
                    .trim();

                // 주차장 관련만 남김
                if (!fullText.includes("주차")) return;

                results.push({
                    gonggoNo,
                    address: fullText
                });
            });

            return results;
        }
        """)

        # 신규 공고만 저장
        for item in table_data:

            gonggo_no = item["gonggoNo"]
            address = item["address"]

            if gonggo_no in sent_gonggos:
                continue

            # ✅ 세션 없이 열리는 상세 링크
            detail_url = (
                "https://www.onbid.co.kr/op/cta/cltrdtl/"
                f"collateralDetailRealEstateList.do?search={gonggo_no}"
            )

            parking_info = {
                "공고번호": gonggo_no,
                "물건명주소": address,
                "공고링크": detail_url
            }

            all_parking_data.append(parking_info)
            sent_gonggos.add(gonggo_no)

        # ==============================
        # 다음 페이지 이동
        # ==============================

        next_page = page_num + 1
        next_btn = page.locator(f"a[onclick*='fn_paging({next_page})']")

        if next_btn.count() == 0:
            break

        next_btn.click()
        time.sleep(5)
        page_num += 1

    print(f"신규 공고 {len(all_parking_data)}개 발견")

    # ==============================
    # 6. Slack 전송 (깔끔한 구조)
    # ==============================

    if slack_webhook_url and len(all_parking_data) > 0:

        header = {
            "blocks": [
                {"type": "header",
                 "text": {"type": "plain_text",
                          "text": "🆕 온비드 신규 주차장 공고",
                          "emoji": True}},
                {"type": "divider"}
            ]
        }

        requests.post(slack_webhook_url, json=header)
        time.sleep(1)

        for idx, parking in enumerate(all_parking_data[:20], 1):

            blocks = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"🅿️ {idx}. {parking['물건명주소'][:60]}",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*🔢 공고번호*\n{parking['공고번호']}"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🔗 <{parking['공고링크']}|공고 상세보기>"
                        }
                    },
                    {"type": "divider"}
                ]
            }

            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)

    else:
        print("오늘은 신규 공고 없음")

    # ==============================
    # 7. 신규 공고 저장
    # ==============================

    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_gonggos), f, ensure_ascii=False, indent=2)

finally:
    browser.close()
    playwright.stop()
    print("완료")



