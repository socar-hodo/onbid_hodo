import os
import re
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

# =========================
# 설정
# =========================
KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)

TEST_MODE = False  # True: 중복 무시하고 모두 발송(링크 테스트용)
SENT_FILE = "sent_gonggo.json"

HOME_URL = "https://www.onbid.co.kr"
LIST_URL = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do"
SEARCH_URL = "https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do?search="

EXCLUDE_KEYWORDS = ["일반공고", "공유재산", "위수탁", "취소공고"]


# =========================
# 저장(중복 방지)
# =========================
def load_sent():
    if not os.path.exists(SENT_FILE):
        return set()
    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return set(data)
        return set()
    except:
        return set()


def save_sent(sent_set):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(sent_set)), f, ensure_ascii=False, indent=2)


# =========================
# Slack
# =========================
def slack_send(webhook, blocks):
    if not webhook:
        return
    r = requests.post(webhook, json={"blocks": blocks})
    print("Slack:", r.status_code)
    time.sleep(0.8)


def slack_error(webhook, msg):
    slack_send(webhook, [
        {"type": "header", "text": {"type": "plain_text", "text": "⚠️ 온비드 크롤러 오류", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"```{msg[:900]}```"}}
    ])


# =========================
# 로그인(초기 코드 스타일: 안정)
# =========================
def do_login(page, onbid_id, onbid_pw):
    # 홈에서 로그인 링크 클릭
    page.goto(HOME_URL, timeout=60000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)

    # "로그인" 들어간 링크/버튼 찾기
    clicked = False
    candidates = page.locator("a, button, input[type='button'], input[type='submit']")
    n = candidates.count()

    for i in range(min(n, 200)):
        el = candidates.nth(i)
        try:
            txt = (el.inner_text() or "").strip()
        except:
            txt = ""
        try:
            val = (el.get_attribute("value") or "").strip()
        except:
            val = ""
        label = (txt + " " + val).strip()

        if "로그인" in label:
            try:
                el.click(timeout=3000)
                clicked = True
                break
            except:
                continue

    if not clicked:
        raise RuntimeError("로그인 버튼/링크를 찾지 못했습니다.")

    # 로그인 폼 입력 (type=text 첫번째, password 첫번째)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(1)

    page.locator("input[type='text']").first.fill(onbid_id)
    page.locator("input[type='password']").first.fill(onbid_pw)

    # 로그인 제출 버튼 찾기(텍스트 기반 X, 클릭 가능한 요소 스캔)
    submit_clicked = False
    candidates = page.locator("button, input[type='submit'], input[type='button'], a")
    n = candidates.count()

    for i in range(min(n, 200)):
        el = candidates.nth(i)
        try:
            txt = (el.inner_text() or "").strip()
        except:
            txt = ""
        try:
            val = (el.get_attribute("value") or "").strip()
        except:
            val = ""
        label = (txt + " " + val).strip()

        if "로그인" in label:
            try:
                el.click(timeout=3000)
                submit_clicked = True
                break
            except:
                continue

    if not submit_clicked:
        # 엔터 제출 fallback
        page.locator("input[type='password']").first.press("Enter")

    # 로그인 후 로딩 대기
    time.sleep(4)


# =========================
# 메인
# =========================
def main():
    # 평일만(원하면 제거 가능)
    if NOW.weekday() >= 5:
        print("주말 실행 안 함")
        return

    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    onbid_id = os.environ.get("ONBID_ID", "")
    onbid_pw = os.environ.get("ONBID_PW", "")

    if not onbid_id or not onbid_pw:
        raise RuntimeError("ONBID_ID / ONBID_PW 환경변수가 비어있습니다.")

    sent = load_sent()
    print(f"기존 발송 기록: {len(sent)}")

    all_found = 0
    new_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        try:
            print("===== 온비드 접속 =====")
            print("로그인 시도")
            do_login(page, onbid_id, onbid_pw)
            print("로그인 완료")

            # 목록 이동 + 검색
            page.goto(LIST_URL, timeout=60000)
            time.sleep(4)

            # 검색어 입력 + 검색 버튼 클릭
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

                    # 상세이동 링크 (javascript:fn_selectDetail(...))
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

                    # 검색 링크(항상 열리는 fallback)
                    search_url = SEARCH_URL + gonggo_no

                    # 소재지 (지도보기/새 창 열기 제거)
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

                    # 입찰기간 (2개 날짜)
                    dates = re.findall(r"\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}", row_text)
                    bid_period = " ~ ".join(dates[:2]) if len(dates) >= 2 else "-"

                    # 최저입찰가(중복 표기 방지: 첫 값만)
                    price_match = re.search(r"\d{1,3}(?:,\d{3})+", row_text)
                    price = price_match.group(0) if price_match else "-"

                    # 물건상태(있으면)
                    status = "-"
                    st = re.search(r"(임대\(대부\)|매각|인터넷입찰진행중|입찰진행중|개찰완료|유찰)", row_text)
                    if st:
                        status = st.group(1)

                    # 조회수
                    views = "-"
                    vm = re.search(r"조회수\s*(\d+)", row_text)
                    if vm:
                        views = vm.group(1)

                    new_items.append({
                        "gonggo": gonggo_no,
                        "location": location,
                        "area": area,
                        "bid": bid_period,
                        "price": price,
                        "status": status,
                        "views": views,
                        "detail_url": detail_url,
                        "search_url": search_url
                    })

                # 다음 페이지: div.paging 안의 "다음" 또는 다음 숫자 클릭
                paging = page.query_selector("div.paging")
                if not paging:
                    break

                # 1) "다음" 버튼 우선
                next_link = paging.query_selector("a:has-text('다음')")
                if next_link:
                    try:
                        next_link.click(timeout=3000)
                        time.sleep(4)
                        page_no += 1
                        continue
                    except:
                        pass

                # 2) 활성 페이지 다음 숫자 (a.active + a)
                next_btn = paging.query_selector("a.active + a")
                if not next_btn:
                    break

                try:
                    next_btn.click(timeout=3000)
                except PWTimeoutError:
                    break

                time.sleep(4)
                page_no += 1

        except Exception as e:
            browser.close()
            slack_error(slack_webhook_url, str(e))
            raise

        browser.close()

    # =========================
    # Slack 발송
    # =========================
    if slack_webhook_url:
        if len(new_items) == 0:
            slack_send(slack_webhook_url, [
                {"type": "header", "text": {"type": "plain_text", "text": "📭 오늘 신규 주차장 공고 없음", "emoji": True}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"📅 {NOW.strftime('%Y-%m-%d %H:%M')} (KST)\n오늘 신규 공고가 없습니다."}},
                {"type": "divider"},
                {"type": "section", "text": {"type": "mrkdwn",
                                             "text": f"📊 요약\n- 총 검색(주차 포함): *{all_found}건*\n- 신규 발송: *0건*\n- 누적 발송 기록: *{len(sent)}건*"}}
            ])
        else:
            slack_send(slack_webhook_url, [
                {"type": "header", "text": {"type": "plain_text", "text": f"🆕 온비드 주차장 공고 ({len(new_items)}건)", "emoji": True}},
                {"type": "divider"}
            ])

            for idx, item in enumerate(new_items[:20], 1):
                blocks = [
                    {"type": "header", "text": {"type": "plain_text", "text": f"🅿️ {idx}. {item['location']}", "emoji": True}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*🔢 공고번호*\n{item['gonggo']}"}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*📏 면적*\n{item['area']}"}},
                    {"type": "section", "fields": [
                        {"type": "mrkdwn", "text": f"*📅 입찰기간*\n{item['bid']}"},
                        {"type": "mrkdwn", "text": f"*💰 최저입찰가*\n{item['price']}"},
                    ]},
                    {"type": "section", "fields": [
                        {"type": "mrkdwn", "text": f"*🏷️ 상태*\n{item['status']}"},
                        {"type": "mrkdwn", "text": f"*👁️ 조회수*\n{item['views']}"},
                    ]},
                ]

                if item["detail_url"]:
                    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"🔗 <{item['detail_url']}|상세 바로가기 (로그인 세션 필요)>"}}
                                  )
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"🔎 <{item['search_url']}|공고번호 검색으로 보기 (항상 열림)>"}}
                              )
                blocks.append({"type": "divider"})
                slack_send(slack_webhook_url, blocks)

            # 항상 요약
            slack_send(slack_webhook_url, [
                {"type": "section", "text": {"type": "mrkdwn",
                                             "text": f"📊 요약\n- 총 검색(주차 포함): *{all_found}건*\n- 신규 발송: *{len(new_items)}건*\n- 실행시간: {NOW.strftime('%Y-%m-%d %H:%M')} (KST)"}}
            ])

    # =========================
    # 중복 기록 저장
    # =========================
    if not TEST_MODE and len(new_items) > 0:
        for item in new_items:
            sent.add(item["gonggo"])
        save_sent(sent)

    print("===== 완료 =====")


if __name__ == "__main__":
    main()
