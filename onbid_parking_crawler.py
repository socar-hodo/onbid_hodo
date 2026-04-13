import os
import time
import json
import re
import requests
from urllib.parse import quote
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
if os.path.exists(SAVED_FILE):
    with open(SAVED_FILE, "r", encoding="utf-8") as f:
        sent_gonggos = set(json.load(f))
else:
    sent_gonggos = set()

all_parking_data = []
new_gonggos = set()
total_found = 0

# ===============================
# Slack 함수
# ===============================
def slack_send(blocks):
    if slack_webhook_url:
        requests.post(slack_webhook_url, json=blocks)
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

    # ===============================
    # 로그인 (홈페이지 UI 개편 대응: 로그인 페이지로 직접 이동)
    # 기존에는 page.click("text=로그인")로 홈페이지 로그인 링크를 눌렀으나,
    # 개편 이후 해당 텍스트가 숨겨진 메뉴/드롭다운에만 남아 클릭 불가능해짐.
    # 로그인 URL로 직접 이동하면 UI 변경에 영향받지 않아 안정적.
    # ===============================
    if onbid_id and onbid_pw:
        print("로그인 페이지로 직접 이동")
        page.goto(
            "https://www.onbid.co.kr/op/meminf/lgnmng/prtllgn/PrtlLgnController/prtlLgn.do",
            timeout=60000,
        )
        page.wait_for_load_state("networkidle")

        # 아이디/비밀번호 입력 — 사이트 변경에 대비해 여러 셀렉터 fallback
        id_input = page.locator(
            'input[name="userId"], input[id="userId"], input[name="mberId"], input[type="text"]:visible'
        ).first
        pw_input = page.locator(
            'input[name="password"], input[id="password"], input[type="password"]:visible'
        ).first
        id_input.fill(onbid_id)
        pw_input.fill(onbid_pw)

        # 로그인 제출 — 보이는(visible) 요소만 매칭해 숨은 중복 요소 문제 회피
        page.locator(
            'button:has-text("로그인"):visible, a:has-text("로그인"):visible, input[type="submit"]:visible'
        ).first.click()
        page.wait_for_load_state("networkidle", timeout=30000)
        print("로그인 완료")
    else:
        page.goto("https://www.onbid.co.kr", timeout=60000)
        time.sleep(2)

    # ===============================
    # 담보물 부동산 목록 이동
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
    # 페이지 반복 수집
    # ===============================
    while True:
        print(f"{page_num}페이지 수집 중...")

        rows = page.query_selector_all("tbody tr")

        for row in rows:
            full_text = row.inner_text()

            if "주차" not in full_text:
                continue

            total_found += 1

            # ===============================
            # ✅ 공고번호 추출 (가장 안정적)
            # ===============================
            gonggo_match = re.search(r"\d{4}-\d{4}-\d{6}", full_text)
            if not gonggo_match:
                continue

            gonggo_no = gonggo_match.group()

            # 중복이면 스킵
            if gonggo_no in sent_gonggos:
                continue

            # ===============================
            # 주소 추출
            # ===============================
            lines = [l.strip() for l in full_text.split("\n") if l.strip()]
            address = ""

            for i, line in enumerate(lines):
                if gonggo_no in line and i + 1 < len(lines):
                    address = lines[i + 1]
                    break

            address = address.replace("새 창 열기", "").replace("지도보기", "").strip()

            # ===============================
            # 면적
            # ===============================
            area_match = re.search(r"\[.*?㎡\]", full_text)
            area = area_match.group() if area_match else "-"

            # ===============================
            # 입찰기간
            # ===============================
            period_match = re.findall(r"\d{4}-\d{2}-\d{2}.*?\d{2}:\d{2}", full_text)
            period = " ~ ".join(period_match[:2]) if period_match else "-"

            # ===============================
            # 최저입찰가
            # ===============================
            price_match = re.search(r"\d{1,3}(,\d{3})+", full_text)
            price = price_match.group() if price_match else "-"

            # ===============================
            # 조회수
            # ===============================
            view_match = re.search(r"조회수\s*(\d+)", full_text)
            view = view_match.group(1) if view_match else "-"

            # ===============================
            # 물건상태
            # ===============================
            status_match = re.search(r"(인터넷입찰진행중|일반경쟁|제한경쟁|임대\(대부\))", full_text)
            status = status_match.group() if status_match else "-"

            # ===============================
            # ✅ 상세 페이지로 바로가는 1-click 링크 구성
            # ===============================
            link_main = "https://www.onbid.co.kr"

            html_content = row.inner_html()
            detail_match = re.search(r"fn_selectDetail\('([^']+)','([^']+)','([^']+)','([^']+)','([^']+)','([^']+)'", html_content)
            
            if detail_match:
                p1, p2, p3, p4, p5, p6 = detail_match.groups()
                link_search = (
                    f"https://www.onbid.co.kr/op/cta/cltrdtl/collateralRealEstateDetail.do?"
                    f"cltrHstrNo={p1}&cltrNo={p2}&plnmNo={p3}&pbctNo={p4}&scrnGrpCd={p5}&pbctCdtnNo={p6}"
                )
            else:
                link_search = link_main

            # 신규 데이터 저장
            all_parking_data.append({
                "gonggo": gonggo_no,
                "address": address,
                "area": area,
                "period": period,
                "price": price,
                "status": status,
                "view": view,
                "link_main": link_main,
                "link_search": link_search
            })

            new_gonggos.add(gonggo_no)

        # ===============================
        # 다음 페이지 이동
        # ===============================
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
                    # ✅ 링크 2개 제공
                    {"type": "section",
                     "text": {"type": "mrkdwn",
                              "text":
                                  f"🔗 <{item['link_main']}|온비드 홈 먼저 클릭>\n"
                                  f"➡️ <{item['link_search']}|공고 검색 바로가기>"
                              }},
                    {"type": "divider"}
                ]
            })

    else:
        slack_send({
            "blocks": [
                {"type": "header",
                 "text": {"type": "plain_text",
                          "text": "📭 오늘 신규 주차장 공고 없음",
                          "emoji": True}},
                {"type": "section",
                 "text": {"type": "mrkdwn",
                          "text": f"📅 {now.strftime('%Y-%m-%d %H:%M')} (KST)\n오늘 신규 공고가 없습니다."}}
            ]
        })

    # ===============================
    # 요약 리포트
    # ===============================
    slack_send({
        "blocks": [
            {"type": "divider"},
            {"type": "section",
             "text": {"type": "mrkdwn",
                      "text": f"""
📊 *온비드 크롤링 요약*

- 총 검색 건수: *{total_found}건*
- 신규 공고: *{신규건수}건*
- 누적 발송 기록: *{len(sent_gonggos) + len(new_gonggos)}건*

⏰ 실행시간: {now.strftime('%Y-%m-%d %H:%M')} (KST)
""" }}
        ]
    })

    # ===============================
    # 신규 발송 성공 후 기록 저장
    # ===============================
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
