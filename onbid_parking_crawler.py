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

# 중복 방지 파일
SAVED_FILE = "sent_gonggo.json"

# 기존 발송 공고번호 로드
if os.path.exists(SAVED_FILE):
    with open(SAVED_FILE, "r", encoding="utf-8") as f:
        sent_gonggos = set(json.load(f))
else:
    sent_gonggos = set()

print(f"기존 발송 공고 수: {len(sent_gonggos)}")

# 신규 공고 저장 리스트
all_parking_data = []

# ==============================
# Playwright 시작
# ==============================

playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
page = browser.new_page()

try:
    print("\n=== 1. 온비드 접속 ===")
    page.goto("https://www.onbid.co.kr", timeout=60000)
    time.sleep(3)

    # ==============================
    # 로그인
    # ==============================

    print("\n=== 2. 로그인 ===")
    if onbid_id and onbid_pw:
        page.click("text=로그인")
        time.sleep(2)

        page.fill('input[type="text"]', onbid_id)
        page.fill('input[type="password"]', onbid_pw)

        page.click("text=로그인")
        time.sleep(5)

    # ==============================
    # 담보물 부동산 페이지 이동
    # ==============================

    print("\n=== 3. 담보물 부동산 페이지 이동 ===")
    target_url = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do"
    page.goto(target_url, timeout=60000)
    time.sleep(5)

    # ==============================
    # 주차장 검색 실행
    # ==============================

    print("\n=== 4. 주차장 검색 실행 ===")
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
    # 전체 페이지 순회 크롤링
    # ==============================

    print("\n=== 5. 전체 페이지 크롤링 시작 ===")

    page_num = 1

    while True:
        print(f"\n📄 {page_num}페이지 수집 중...")

        # 현재 페이지 테이블 데이터 추출
        table_data = page.evaluate("""
        () => {
            const results = [];
            const rows = document.querySelectorAll("tbody tr");

            rows.forEach(row => {
                const rowText = row.innerText;
                if (!rowText.includes("주차")) return;

                // 공고번호 추출
                let gonggoNo = "";
                const titleBtn = row.querySelector("a[title*='-']");
                if (titleBtn) {
                    gonggoNo = titleBtn.getAttribute("title") || "";
                }

                // 상세이동 fn_selectDetail 파라미터 추출
                let detailParam = null;
                const detailMoveBtn = row.querySelector("a[href*='fn_selectDetail']");
                if (detailMoveBtn) {
                    const href = detailMoveBtn.getAttribute("href") || "";
                    const match = href.match(/fn_selectDetail\\(([^)]+)\\)/);

                    if (match) {
                        const params = match[1]
                            .replace(/'/g, "")
                            .split(",");

                        detailParam = params[params.length - 1]; // 마지막 값
                    }
                }

                // 면적 정보 추출
                let area = "";
                if (rowText.includes("㎡")) {
                    const matchArea = rowText.match(/\\d+(\\.\\d+)?㎡/);
                    if (matchArea) area = matchArea[0];
                }

                results.push({
                    gonggoNo,
                    rowText,
                    detailParam,
                    area
                });
            });

            return results;
        }
        """)

        print(f"  ✓ {len(table_data)}개 row 발견")

        # 신규 공고만 저장
        for item in table_data:
            gonggo_no = item["gonggoNo"]

            if not gonggo_no:
                continue

            if gonggo_no in sent_gonggos:
                continue

            # 상세 링크 생성
            detail_url = ""
            if item["detailParam"]:
                detail_url = (
                    "https://www.onbid.co.kr/op/cta/cltrdtl/"
                    f"collateralDetailRealEstateDetail.do?cltrNo={item['detailParam']}"
                )

            parking_info = {
                "공고번호": gonggo_no,
                "물건명주소": item["rowText"][:180],
                "면적": item["area"],
                "공고링크": detail_url
            }

            all_parking_data.append(parking_info)
            sent_gonggos.add(gonggo_no)

        # ==============================
        # 다음 페이지 이동 (fn_paging 기반)
        # ==============================

        next_page = page_num + 1
        next_btn = page.locator(f"a[onclick*='fn_paging({next_page})']")

        if next_btn.count() == 0:
            print("✅ 마지막 페이지 도달")
            break

        print(f"➡️ {next_page}페이지 이동")
        next_btn.click()
        time.sleep(5)

        page_num += 1

    print(f"\n🎉 신규 공고 {len(all_parking_data)}개 발견!")

    # ==============================
    # Slack 전송 (신규만)
    # ==============================

    if slack_webhook_url and len(all_parking_data) > 0:
        print("\n=== Slack 전송 시작 ===")

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

        for idx, parking in enumerate(all_parking_data[:20], 1):
            msg = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*🅿️ {idx}. {parking['공고번호']}*\n"
                                f"📍 {parking['물건명주소']}\n"
                                f"📏 면적: {parking['면적'] or '-'}\n"
                                f"🔗 <{parking['공고링크']}|공고 상세보기>"
                            )
                        }
                    },
                    {"type": "divider"}
                ]
            }

            requests.post(slack_webhook_url, json=msg)
            time.sleep(1)

        print("✅ Slack 전송 완료")

    else:
        print("오늘은 신규 주차장 공고 없음")

    # ==============================
    # 신규 공고 저장
    # ==============================

    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_gonggos), f, ensure_ascii=False, indent=2)

    print("✅ sent_gonggo.json 저장 완료")

finally:
    browser.close()
    playwright.stop()
    print("\n=== 종료 ===")

