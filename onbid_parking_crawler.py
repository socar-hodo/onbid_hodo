import os
import time
import json
import re
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone

# ===============================
# 기본 설정
# ===============================
KST = timezone(timedelta(hours=9))
now = datetime.now(KST)

slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
onbid_id = os.environ.get("ONBID_ID", "")
onbid_pw = os.environ.get("ONBID_PW", "")

SAVED_FILE = "sent_gonggo.json"

# ===============================
# 기존 발송 공고 불러오기
# ===============================
#if os.path.exists(SAVED_FILE):
#    with open(SAVED_FILE, "r", encoding="utf-8") as f:
#        sent_gonggos = set(json.load(f))
#else:
#    sent_gonggos = set()
#
#all_parking_data = []
#new_gonggos = set()
#total_found = 0

# ===============================
# Slack 함수
# ===============================
def slack_send(payload):
    if slack_webhook_url:
        requests.post(slack_webhook_url, json=payload)
        time.sleep(1)

def slack_error(msg):
    slack_send({
        "blocks": [
            {"type": "header",
             "text": {"type": "plain_text", "text": "⚠️ 온비드 크롤러 오류", "emoji": True}},
            {"type": "section",
             "text": {"type": "mrkdwn", "text": f"```{msg}```"}}
        ]
    })

# ===============================
# Playwright 시작
# ===============================
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
page = browser.new_page()

try:
    print("===== 온비드 접속 =====")
    page.goto("https://www.onbid.co.kr", timeout=60000)
    time.sleep(3)

    # ===============================
    # 로그인
    # ===============================
    if onbid_id and onbid_pw:
        print("로그인 시도")
        page.click("text=로그인")
        time.sleep(2)

        page.fill('input[type="text"]', onbid_id)
        page.fill('input[type="password"]', onbid_pw)

        page.click("text=로그인")
        time.sleep(5)
        print("로그인 완료")

    # ===============================
    # 목록 이동
    # ===============================
    target_url = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do"
    page.goto(target_url)
    time.sleep(5)

    # ===============================
    # "주차장" 검색
    # ===============================
    page.evaluate("""
        () => {
            const input = document.getElementById("searchCltrNm");
            if (input) input.value = "주차장";
            const btn = document.getElementById("searchBtn");
            if (btn) btn.click();
        }
    """)
    time.sleep(8)
    print("검색 완료")

    page_num = 1

    # ===============================
    # 페이지 반복
    # ===============================
    while True:
        print(f"{page_num}페이지 수집 중...")

        rows = page.query_selector_all("tbody tr")

        for row in rows:
            full_text = row.inner_text()

            #if "주차" not in full_text:
            #    continue

            #total_found += 1

            # 공고번호
            gonggo_match = re.search(r"\d{4}-\d{4}-\d{6}", full_text)
            if not gonggo_match:
                continue

            gonggo_no = gonggo_match.group()

            if gonggo_no in sent_gonggos:
                continue

            # 주소
            lines = [l.strip() for l in full_text.split("\n") if l.strip()]
            address = ""
            for i, line in enumerate(lines):
                if gonggo_no in line and i + 1 < len(lines):
                    address = lines[i + 1]
                    break

            address = address.replace("새 창 열기", "").replace("지도보기", "").strip()

            # 면적
            area_match = re.search(r"\[.*?㎡\]", full_text)
            area = area_match.group() if area_match else "-"

            # 입찰기간
            period_match = re.findall(r"\d{4}-\d{2}-\d{2}.*?\d{2}:\d{2}", full_text)
            period = " ~ ".join(period_match[:2]) if period_match else "-"

            # 가격
            price_match = re.search(r"\d{1,3}(,\d{3})+", full_text)
            price = price_match.group() if price_match else "-"

            # 조회수
            view_match = re.search(r"조회수\s*(\d+)", full_text)
            view = view_match.group(1) if view_match else "-"

            # 상태
            status_match = re.search(r"(인터넷입찰진행중|일반경쟁|제한경쟁|임대\(대부\))", full_text)
            status = status_match.group() if status_match else "-"

            # ===============================
            # 상세 링크 생성 (핵심 부분)
            # ===============================
            detail_link = "-"

            anchor = row.query_selector("a[href*='fn_selectDetail']")
            if anchor:
                href = anchor.get_attribute("href")

                if href:
                    match = re.search(
                        r"fn_selectDetail\('([^']+)','([^']+)','([^']+)','([^']+)','([^']+)','([^']+)'\)",
                        href
                    )

                    if match:
                        cltrNo, plnmNo, pbctNo, scrnGrpCd, pbctCd, cltrHstrNo = match.groups()

                        detail_link = (
                            "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstate.do"
                            f"?cltrNo={cltrNo}"
                            f"&plnmNo={plnmNo}"
                            f"&pbctNo={pbctNo}"
                            f"&scrnGrpCd={scrnGrpCd}"
                            f"&pbctCd={pbctCd}"
                            f"&cltrHstrNo={cltrHstrNo}"
                        )

            print("상세 URL:", detail_link)

            all_parking_data.append({
                "gonggo": gonggo_no,
                "address": address,
                "area": area,
                "period": period,
                "price": price,
                "status": status,
                "view": view,
                "detail_link": detail_link
            })

            new_gonggos.add(gonggo_no)

        # 다음 페이지
        next_btn = page.locator(f"a[onclick*='fn_paging({page_num+1})']")
        if next_btn.count() == 0:
            break

        next_btn.click()
        time.sleep(5)
        page_num += 1

    # ===============================
    # Slack 발송
    # ===============================
    신규건수 = len(all_parking_data)

    if 신규건수 > 0:
        slack_send({
            "blocks": [
                {"type": "header",
                 "text": {"type": "plain_text",
                          "text": f"🆕 온비드 신규 주차장 공고 ({신규건수}건)",
                          "emoji": True}},
                {"type": "divider"}
            ]
        })

        for idx, item in enumerate(all_parking_data[:20], 1):
            slack_send({
                "blocks": [
                    {"type": "header",
                     "text": {"type": "plain_text",
                              "text": f"🅿️ {idx}. {item['address']}",
                              "emoji": True}},
                    {"type": "section",
                     "text": {"type": "mrkdwn",
                              "text": f"*🔢 공고번호*\n{item['gonggo']}"}},
                    {"type": "section",
                     "text": {"type": "mrkdwn",
                              "text": f"*📏 면적*\n{item['area']}"}},
                    {"type": "section",
                     "fields": [
                         {"type": "mrkdwn",
                          "text": f"*📅 입찰기간*\n{item['period']}"},
                         {"type": "mrkdwn",
                          "text": f"*💰 최저입찰가*\n{item['price']}"}
                     ]},
                    {"type": "section",
                     "fields": [
                         {"type": "mrkdwn",
                          "text": f"*🏷 물건상태*\n{item['status']}"},
                         {"type": "mrkdwn",
                          "text": f"*👁 조회수*\n{item['view']}"}
                     ]},
                    {"type": "section",
                     "text": {"type": "mrkdwn",
                              "text": f"🔗 <{item['detail_link']}|상세페이지 바로가기>"}},
                    {"type": "divider"}
                ]
            })

    sent_gonggos.update(new_gonggos)

    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_gonggos), f, ensure_ascii=False, indent=2)

except Exception as e:
    slack_error(str(e))
    raise

finally:
    browser.close()
    playwright.stop()

print("===== 완료 =====")
