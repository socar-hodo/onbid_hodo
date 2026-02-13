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

TEST_MODE = False   # True면 중복 무시하고 전부 발송

SENT_FILE = "sent_gonggo.json"

ONBID_URL = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do"

# =========================
# sent_gonggo.json 로드
# =========================
def load_sent():
    if not os.path.exists(SENT_FILE):
        return []

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_sent(sent_list):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(sent_list, f, ensure_ascii=False, indent=2)

# =========================
# Slack 전송
# =========================
def send_slack(webhook, blocks):
    requests.post(webhook, json={"blocks": blocks})
    time.sleep(0.5)

# =========================
# 실행 시작
# =========================
current_time = datetime.now(KST)

weekday = current_time.weekday()
if weekday >= 5:
    print("주말에는 실행 안 함")
    exit(0)

slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
onbid_id = os.environ.get("ONBID_ID")
onbid_pw = os.environ.get("ONBID_PW")

sent_gonggos = load_sent()
print(f"기존 발송 공고 수: {len(sent_gonggos)}")

all_results = []
new_results = []

# =========================
# Playwright 시작
# =========================
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    print("===== 온비드 접속 =====")
    page.goto("https://www.onbid.co.kr", timeout=60000)
    time.sleep(3)

    # 로그인
    print("로그인 시도")
    page.click("text=로그인")
    time.sleep(2)

    page.fill("input[type=text]", onbid_id)
    page.fill("input[type=password]", onbid_pw)

    page.click("button:has-text('로그인')")
    time.sleep(4)

    print("로그인 완료")

    # 부동산 담보물 페이지 이동
    page.goto(ONBID_URL, timeout=60000)
    time.sleep(5)

    # 검색어 입력
    page.fill("#searchCltrNm", "주차장")
    page.click("#searchBtn")
    time.sleep(5)

    print("검색 완료")

    # =========================
    # 페이지네이션 수집
    # =========================
    page_no = 1

    while True:
        print(f"{page_no}페이지 수집 중...")

        rows = page.query_selector_all("table tbody tr")

        for row in rows:
            row_text = row.inner_text().strip()
            if "주차" not in row_text:
                continue

            # 공고번호 추출
            gonggo_match = re.search(r"\d{4}-\d{4}-\d{6}", row_text)
            if not gonggo_match:
                continue

            gonggo_no = gonggo_match.group(0)

            # TEST_MODE 아니면 중복 제거
            if (not TEST_MODE) and (gonggo_no in sent_gonggos):
                continue

            # 소재지명 추출 (첫번째 줄)
            lines = row_text.split("\n")
            location = ""
            for ln in lines:
                if "주차" in ln and len(ln) > 5:
                    location = ln.strip()
                    break

            # 면적
            area_match = re.search(r"\[.*?㎡\]", row_text)
            area = area_match.group(0) if area_match else "-"

            # 입찰기간
            bid_dates = re.findall(r"\d{4}-\d{2}-\d{2}.*?\d{2}:\d{2}", row_text)
            bid_period = " ~ ".join(bid_dates[:2]) if len(bid_dates) >= 2 else "-"

            # 최저입찰가
            price_match = re.search(r"\d{1,3}(,\d{3})+", row_text)
            price = price_match.group(0) if price_match else "-"

            # 조회수
            view_match = re.search(r"조회수\s*(\d+)", row_text)
            views = view_match.group(1) if view_match else "-"

            # =========================
            # 상세이동 링크 생성
            # =========================
            detail_a = row.query_selector(
                "a[href^='javascript:fn_selectDetail']"
            )

            detail_url = ""
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
                "url": detail_url
            }

            all_results.append(item)
            new_results.append(item)

        # =========================
        # 다음 페이지 버튼 클릭
        # =========================
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
                      "text": f"📊 검색 결과: {len(all_results)}건\n신규: 0건\n누적 발송 기록: {len(sent_gonggos)}건"}}
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

            if item["url"]:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn",
                             "text": f"🔗 <{item['url']}|공고 상세보기>"}
                })

            blocks.append({"type": "divider"})

            send_slack(slack_webhook_url, blocks)

# =========================
# 신규 발송 기록 저장
# =========================
if len(new_results) > 0:
    for item in new_results:
        sent_gonggos.append(item["gonggo"])

    sent_gonggos = list(set(sent_gonggos))
    save_sent(sent_gonggos)

print("===== 완료 =====")

