import os
import re
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# =========================
# 설정
# =========================
KST = timezone(timedelta(hours=9))
TEST_MODE = False
SENT_FILE = "sent_gonggo.json"

LIST_URL = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do"
SEARCH_URL = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do?search="

# =========================
# 중복 저장
# =========================
def load_sent():
    if not os.path.exists(SENT_FILE):
        return []
    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_sent(data):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_slack(webhook, blocks):
    requests.post(webhook, json={"blocks": blocks})
    time.sleep(0.5)

# =========================
# 시작
# =========================
current_time = datetime.now(KST)

if current_time.weekday() >= 5:
    print("주말 실행 안함")
    exit(0)

slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
onbid_id = os.environ.get("ONBID_ID")
onbid_pw = os.environ.get("ONBID_PW")

sent_gonggos = load_sent()
print(f"기존 발송 기록: {len(sent_gonggos)}")

all_results = []
new_results = []

# =========================
# 크롤링
# =========================
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    print("===== 온비드 접속 =====")
    page.goto("https://www.onbid.co.kr", timeout=60000)
    time.sleep(3)

    print("로그인 시도")

# 로그인 버튼 클릭 (안전 방식)
page.locator("text=로그인").first.click()
page.wait_for_timeout(2000)

# 아이디/비번 입력
page.locator("input[type='text']").first.fill(onbid_id)
page.locator("input[type='password']").first.fill(onbid_pw)

# 로그인 제출
page.locator("text=로그인").last.click()

page.wait_for_timeout(5000)
print("로그인 완료")

    page.goto(LIST_URL)
    time.sleep(4)

    page.fill("#searchCltrNm", "주차장")
    page.click("#searchBtn")
    time.sleep(5)

    print("검색 완료")

    page_no = 1

    while True:
        print(f"{page_no}페이지 수집")

        rows = page.query_selector_all("table tbody tr")

        for row in rows:
            text = row.inner_text()

            if "주차" not in text:
                continue

            gonggo_match = re.search(r"\d{4}-\d{4}-\d{6}", text)
            if not gonggo_match:
                continue

            gonggo_no = gonggo_match.group(0)

            if (not TEST_MODE) and (gonggo_no in sent_gonggos):
                continue

            # 주소 추출
            lines = text.split("\n")
            location = ""
            for ln in lines:
                if "주차" in ln and len(ln) > 5:
                    location = ln.strip()
                    break

            # 면적
            area_match = re.search(r"\[.*?㎡\]", text)
            area = area_match.group(0) if area_match else "-"

            # 입찰기간
            dates = re.findall(r"\d{4}-\d{2}-\d{2}.*?\d{2}:\d{2}", text)
            bid_period = " ~ ".join(dates[:2]) if len(dates) >= 2 else "-"

            # 가격
            price_match = re.search(r"\d{1,3}(,\d{3})+", text)
            price = price_match.group(0) if price_match else "-"

            # 조회수
            view_match = re.search(r"조회수\s*(\d+)", text)
            views = view_match.group(1) if view_match else "-"

            # ======================
            # 상세 링크 생성
            # ======================
            detail_a = row.query_selector("a[href^='javascript:fn_selectDetail']")
            detail_url = ""
            search_link = SEARCH_URL + gonggo_no

            if detail_a:
                href = detail_a.get_attribute("href")
                nums = re.findall(r"'([^']+)'", href)

                if len(nums) == 6:
                    cltrHstrNo, plnmNo, pbctNo, cltrNo, rnum, seq = nums

                    detail_url = (
                        "https://www.onbid.co.kr/op/cta/cltrdtl/"
                        "collateralDetailRealEstateView.do?"
                        f"cltrHstrNo={cltrHstrNo}"
                        f"&plnmNo={plnmNo}"
                        f"&pbctNo={pbctNo}"
                        f"&cltrNo={cltrNo}"
                        f"&rnum={rnum}"
                        f"&seq={seq}"
                    )

            item = {
                "gonggo": gonggo_no,
                "location": location,
                "area": area,
                "bid": bid_period,
                "price": price,
                "views": views,
                "detail_url": detail_url,
                "search_url": search_link
            }

            all_results.append(item)
            new_results.append(item)

        # 다음 페이지
        paging = page.query_selector("div.paging")
        if not paging:
            break

        next_btn = paging.query_selector("a.active + a")
        if not next_btn:
            break

        next_btn.click()
        time.sleep(4)
        page_no += 1

    browser.close()

# =========================
# Slack 출력
# =========================
if slack_webhook_url:

    if len(new_results) == 0:
        send_slack(slack_webhook_url, [
            {"type": "header",
             "text": {"type": "plain_text",
                      "text": "📭 오늘 신규 주차장 공고 없음",
                      "emoji": True}},
            {"type": "section",
             "text": {"type": "mrkdwn",
                      "text": f"📅 {current_time.strftime('%Y-%m-%d %H:%M')} (KST)\n\n오늘 신규 공고가 없습니다."}},
            {"type": "divider"},
            {"type": "section",
             "text": {"type": "mrkdwn",
                      "text": f"📊 총 검색: {len(all_results)}건\n신규: 0건\n누적 발송 기록: {len(sent_gonggos)}건"}}
        ])

    else:
        send_slack(slack_webhook_url, [
            {"type": "header",
             "text": {"type": "plain_text",
                      "text": f"🆕 온비드 신규 주차장 공고 ({len(new_results)}건)",
                      "emoji": True}},
            {"type": "divider"}
        ])

        for idx, item in enumerate(new_results[:20], 1):

            blocks = [
                {"type": "header",
                 "text": {"type": "plain_text",
                          "text": f"🅿️ {idx}. {item['location']}",
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
                      "text": f"*📅 입찰기간*\n{item['bid']}"},
                     {"type": "mrkdwn",
                      "text": f"*💰 최저입찰가*\n{item['price']}"}
                 ]},

                {"type": "section",
                 "fields": [
                     {"type": "mrkdwn",
                      "text": f"*👁️ 조회수*\n{item['views']}"},
                     {"type": "mrkdwn",
                      "text": f"*🏷️ 상태*\n진행중"}
                 ]},
            ]

            # 두 가지 링크 모두 제공
            if item["detail_url"]:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn",
                             "text": f"🔗 <{item['detail_url']}|상세 바로가기 (로그인 필요)>"}}
                )

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn",
                         "text": f"🔎 <{item['search_url']}|공고번호 검색으로 보기>"}}
            )

            blocks.append({"type": "divider"})

            send_slack(slack_webhook_url, blocks)

# =========================
# 중복 저장
# =========================
if len(new_results) > 0:
    for item in new_results:
        sent_gonggos.append(item["gonggo"])
    sent_gonggos = list(set(sent_gonggos))
    save_sent(sent_gonggos)

print("===== 완료 =====")

