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
NOW = datetime.now(KST)

TEST_MODE = False  # True면 중복 무시하고 전부 발송

SENT_FILE = "sent_gonggo.json"

LOGIN_URL = "https://www.onbid.co.kr/op/login/login.do"
LIST_URL = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do"
SEARCH_URL = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do?search="

EXCLUDE_KEYWORDS = ["일반공고", "공유재산", "위수탁", "취소공고"]


# =========================
# 발송 기록 저장
# =========================
def load_sent():
    if not os.path.exists(SENT_FILE):
        return set()

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data) if isinstance(data, list) else set()
    except:
        return set()


def save_sent(sent_set):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(sent_set)), f, ensure_ascii=False, indent=2)


# =========================
# Slack 전송
# =========================
def slack_send(webhook, blocks):
    if not webhook:
        return
    requests.post(webhook, json={"blocks": blocks})
    time.sleep(0.8)


def slack_error(webhook, msg):
    slack_send(webhook, [
        {"type": "header",
         "text": {"type": "plain_text", "text": "⚠️ 온비드 크롤러 오류", "emoji": True}},
        {"type": "section",
         "text": {"type": "mrkdwn", "text": f"```{msg[:900]}```"}}
    ])


# =========================
# 로그인 (안정 버전)
# =========================
def do_login(page, user_id, user_pw):
    print("로그인 페이지 직접 이동")
    page.goto(LOGIN_URL, timeout=60000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)

    # 아이디/비번 입력
    page.fill("input[name='userId']", user_id)
    page.fill("input[name='userPw']", user_pw)

    # 로그인 버튼 클릭
    page.click("button[type='submit']")
    time.sleep(4)

    # 로그인 성공 여부 체크
    if "login" in page.url.lower():
        raise RuntimeError("로그인 실패: 로그인 페이지에서 벗어나지 못함")

    print("로그인 성공")


# =========================
# 메인 실행
# =========================
def main():
    if NOW.weekday() >= 5:
        print("주말 실행 안함")
        return

    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    onbid_id = os.environ.get("ONBID_ID", "")
    onbid_pw = os.environ.get("ONBID_PW", "")

    if not onbid_id or not onbid_pw:
        raise RuntimeError("ONBID_ID / ONBID_PW 환경변수가 비어있음")

    sent = load_sent()
    print(f"기존 발송 기록: {len(sent)}")

    all_found = 0
    new_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        try:
            print("===== 온비드 접속 =====")
            do_login(page, onbid_id, onbid_pw)

            # 목록 이동
            page.goto(LIST_URL, timeout=60000)
            time.sleep(4)

            # 검색 실행
            page.evaluate("""
                () => {
                    const input = document.getElementById('searchCltrNm');
                    if (input) {
                        input.value = '주차장';
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    const btn = document.getElementById('searchBtn');
                    if (btn) btn.click();
                }
            """)
            time.sleep(6)

            print("검색 완료")

            # =========================
            # 페이지네이션 수집
            # =========================
            page_no = 1
            while True:
                print(f"{page_no}페이지 수집 중...")

                rows = page.query_selector_all("table tbody tr")

                for row in rows:
                    row_text = (row.inner_text() or "").strip()
                    if not row_text:
                        continue

                    if any(kw in row_text for kw in EXCLUDE_KEYWORDS):
                        continue

                    if "주차" not in row_text:
                        continue

                    gonggo_match = re.search(r"\d{4}-\d{4}-\d{6}", row_text)
                    if not gonggo_match:
                        continue

                    gonggo_no = gonggo_match.group(0)
                    all_found += 1

                    # 중복 방지
                    if (not TEST_MODE) and (gonggo_no in sent):
                        continue

                    # 소재지 추출 (지도보기/새창열기 제거)
                    lines = [l.strip() for l in row_text.split("\n") if l.strip()]
                    location = ""
                    for ln in lines:
                        cleaned = ln.replace("지도보기", "").replace("새 창 열기", "").strip()
                        if "주차" in cleaned and len(cleaned) > 5:
                            location = cleaned
                            break
                    if not location:
                        location = gonggo_no

                    # 면적
                    area_match = re.search(r"\[.*?㎡\]", row_text)
                    area = area_match.group(0) if area_match else "-"

                    # 입찰기간
                    dates = re.findall(r"\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}", row_text)
                    bid_period = " ~ ".join(dates[:2]) if len(dates) >= 2 else "-"

                    # 최저입찰가
                    price_match = re.search(r"\d{1,3}(?:,\d{3})+", row_text)
                    price = price_match.group(0) if price_match else "-"

                    # 조회수
                    views = "-"
                    vm = re.search(r"조회수\s*(\d+)", row_text)
                    if vm:
                        views = vm.group(1)

                    # 상세 URL 생성
                    detail_a = row.query_selector("a[href^='javascript:fn_selectDetail']")
                    detail_url = ""
                    if detail_a:
                        href = detail_a.get_attribute("href") or ""
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

                    search_url = SEARCH_URL + gonggo_no

                    new_items.append({
                        "gonggo": gonggo_no,
                        "location": location,
                        "area": area,
                        "bid": bid_period,
                        "price": price,
                        "views": views,
                        "detail_url": detail_url,
                        "search_url": search_url
                    })

                # 다음 페이지 이동
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

        except Exception as e:
            browser.close()
            slack_error(slack_webhook_url, str(e))
            raise

    # =========================
    # Slack 발송
    # =========================
    if slack_webhook_url:
        if len(new_items) == 0:
            slack_send(slack_webhook_url, [
                {"type": "header",
                 "text": {"type": "plain_text", "text": "📭 오늘 신규 주차장 공고 없음", "emoji": True}},
                {"type": "section",
                 "text": {"type": "mrkdwn",
                          "text": f"📅 {NOW.strftime('%Y-%m-%d %H:%M')} (KST)\n오늘 신규 공고가 없습니다."}},
                {"type": "divider"},
                {"type": "section",
                 "text": {"type": "mrkdwn",
                          "text": f"📊 총 검색: {all_found}건\n신규: 0건\n누적 발송 기록: {len(sent)}건"}}
            ])

        else:
            slack_send(slack_webhook_url, [
                {"type": "header",
                 "text": {"type": "plain_text",
                          "text": f"🆕 온비드 신규 주차장 공고 ({len(new_items)}건)", "emoji": True}},
                {"type": "divider"}
            ])

            for idx, item in enumerate(new_items[:20], 1):
                blocks = [
                    {"type": "header",
                     "text": {"type": "plain_text", "text": f"🅿️ {idx}. {item['location']}", "emoji": True}},
                    {"type": "section",
                     "text": {"type": "mrkdwn", "text": f"*🔢 공고번호*\n{item['gonggo']}"}},
                    {"type": "section",
                     "text": {"type": "mrkdwn", "text": f"*📏 면적*\n{item['area']}"}},
                    {"type": "section",
                     "fields": [
                         {"type": "mrkdwn", "text": f"*📅 입찰기간*\n{item['bid']}"},
                         {"type": "mrkdwn", "text": f"*💰 최저입찰가*\n{item['price']}"},
                     ]},
                    {"type": "section",
                     "fields": [
                         {"type": "mrkdwn", "text": f"*👁️ 조회수*\n{item['views']}"},
                         {"type": "mrkdwn", "text": "*🏷️ 상태*\n진행중"},
                     ]},
                ]

                if item["detail_url"]:
                    blocks.append({
                        "type": "section",
                        "text": {"type": "mrkdwn",
                                 "text": f"🔗 <{item['detail_url']}|상세 바로가기 (로그인 필요)>"}
                    })

                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn",
                             "text": f"🔎 <{item['search_url']}|공고번호 검색으로 보기 (항상 열림)>"}
                })

                blocks.append({"type": "divider"})

                slack_send(slack_webhook_url, blocks)

    # =========================
    # 발송 기록 저장
    # =========================
    if not TEST_MODE and len(new_items) > 0:
        for item in new_items:
            sent.add(item["gonggo"])
        save_sent(sent)

    print("===== 완료 =====")


if __name__ == "__main__":
    main()
