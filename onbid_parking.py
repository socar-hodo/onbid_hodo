"""
온비드 주차장 공고 크롤러 (API 기반 재작성 버전)

2026-04 온비드 전면 리뉴얼로 기존 HTML 스크래핑 방식이 동작하지 않게 되어,
공개 JSON API(`inqCltrClbtRlstClg.do`)를 직접 호출하는 방식으로 재작성.

- Playwright/브라우저 자동화 불필요
- 로그인 불필요 (공개 API)
- 신규 공고를 Slack으로 발송하고 sent_gonggo.json에 기록
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import requests

# ===============================
# 기본 설정
# ===============================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("onbid")

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
SEARCH_KEYWORD = os.environ.get("SEARCH_KEYWORD", "주차장")
SEARCH_DAYS_AHEAD = int(os.environ.get("SEARCH_DAYS_AHEAD", "30"))
SAVED_FILE = "sent_gonggo.json"

BASE_URL = "https://www.onbid.co.kr"
LIST_PAGE_URL = (
    f"{BASE_URL}/op/cltrpbancinf/clbtcltrclg/cltrclbtcltrclg/"
    f"CltrClbtCltrClgController/mvmnCltrRlstClg.do"
)
API_URL = (
    f"{BASE_URL}/op/cltrpbancinf/clbtcltrclg/cltrclbtcltrclg/"
    f"CltrClbtCltrClgController/inqCltrClbtRlstClg.do"
)
# 공고번호로 통합검색 — Slack 바로가기 링크로 사용
SEARCH_DEEP_LINK_FMT = (
    f"{BASE_URL}/op/cltrpbancinf/toppagemng/unfsrch/"
    f"UnfSrchController/mvmnUnfSrchClg.do?swd={{gonggo}}"
)
# 온비드 홈 — 보조 링크
MAIN_LINK = BASE_URL

# 부동산 물건유형 전체
REAL_ESTATE_PRPT_TYPES = [
    "0007", "0010", "0005", "0003", "0013",
    "0002", "0011", "0006", "0008", "0004",
]

# ===============================
# Slack
# ===============================
def slack_send(payload: dict) -> None:
    if not SLACK_WEBHOOK_URL:
        log.warning("SLACK_WEBHOOK_URL not set — skipping send")
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=15)
        time.sleep(1)
    except Exception:
        log.exception("Slack send failed")


def slack_error(msg: str) -> None:
    slack_send({
        "blocks": [
            {"type": "header",
             "text": {"type": "plain_text", "text": "⚠️ 온비드 크롤러 오류", "emoji": True}},
            {"type": "section",
             "text": {"type": "mrkdwn", "text": f"```{msg[:2500]}```"}},
        ]
    })


# ===============================
# 상태 로드
# ===============================
def load_sent() -> set[str]:
    if os.path.exists(SAVED_FILE):
        with open(SAVED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_sent(sent: set[str]) -> None:
    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(sent), f, ensure_ascii=False, indent=2)


# ===============================
# 온비드 API 호출
# ===============================
def fetch_page(session: requests.Session, keyword: str, begin: str, end: str,
               page_index: int, page_unit: int = 100) -> dict:
    params: list[tuple[str, str]] = [
        ("pageIndex", str(page_index)),
        ("pageUnit", str(page_unit)),
        ("srchCltrNm", keyword),
        ("srchBidPerdBgngDt", begin),
        ("srchBidPerdEndDt", end),
        ("srchWordType", "0001"),
        ("srchSortType", "DESC"),
        ("srchCltrType", "0001"),
        ("srchBidPerdType", "0002"),
        ("srchApslEvlAmtType", "001"),
        ("checkMobileUsg", "on"),
        ("checkMobileRgn", "on"),
        ("srchLdarType", "ALL"),
        ("srchBldSqmsType", "ALL"),
        ("srchUsbdNftType", "ALL"),
        ("calBidPerdBgngDt", begin),
        ("calhBidPerdEndDt", end),
    ]
    for t in REAL_ESTATE_PRPT_TYPES:
        params.append(("srchPrptType", t))

    r = session.post(
        API_URL,
        data=params,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
            "Referer": LIST_PAGE_URL,
            "Origin": BASE_URL,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch_all(keyword: str) -> tuple[list[dict], int]:
    """주어진 키워드로 모든 페이지를 수집. (items, rowcount) 반환."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
    })
    # 세션 쿠키 확보
    session.get(LIST_PAGE_URL, timeout=30)

    begin = NOW.date().isoformat()
    end = (NOW + timedelta(days=SEARCH_DAYS_AHEAD)).date().isoformat()

    items: list[dict] = []
    rowcount = 0
    page_index = 1
    page_unit = 100

    while True:
        data = fetch_page(session, keyword, begin, end, page_index, page_unit)
        rows = data.get("cltrInfVOList") or []
        if not rows:
            break
        # rowcount는 각 row의 동일 필드에 들어있음
        rowcount = int(rows[0].get("rowcount") or 0)
        items.extend(rows)
        if page_index * page_unit >= rowcount:
            break
        page_index += 1
        time.sleep(0.5)

    return items, rowcount


# ===============================
# 아이템 정제 (Slack 표기용)
# ===============================
def _num_fmt(v) -> str:
    try:
        n = int(v or 0)
    except (TypeError, ValueError):
        return "-"
    return f"{n:,}원" if n else "-"


def normalize(item: dict) -> dict:
    gonggo = item.get("scrnIndctCltrMngNo") or ""
    land = item.get("landSqms") or 0
    bld = item.get("bldSqms") or 0
    area_parts = []
    if land:
        area_parts.append(f"토지 {land:,.1f}㎡")
    if bld:
        area_parts.append(f"건물 {bld:,.1f}㎡")
    area = " / ".join(area_parts) or "-"

    period_begin = item.get("pbctBegnDtm") or "-"
    period_end = item.get("pbctDdlnDt") or "-"
    period = f"{period_begin} ~ {period_end}"

    tags = [item.get("ctgrFullNm"), item.get("dspsMthodNm"), item.get("cptnMtdNm")]
    tag_str = " / ".join([t for t in tags if t]) or "-"

    return {
        "gonggo": gonggo,
        "name": item.get("onbidCltrNm") or "-",
        "address": item.get("sidoSgkEmd") or "-",
        "area": area,
        "period": period,
        "price": _num_fmt(item.get("lowstBidPrc")),
        "status": item.get("pbancPbctCltrStatNm") or item.get("remainTime") or "-",
        "view": str(item.get("inqCnt") or 0),
        "tag": tag_str,
        "org": item.get("regOrgNm") or "-",
        "link": SEARCH_DEEP_LINK_FMT.format(gonggo=gonggo),
    }


# ===============================
# Slack 메시지 빌더 (기존 포맷 유지: 주소 헤더, 홈+검색 2개 링크)
# ===============================
def send_item(idx: int, it: dict) -> None:
    # 헤더용 주소: 물건명이 더 구체적이면 그걸로, 아니면 광역주소
    header_addr = it["name"] if it["name"] != "-" else it["address"]
    slack_send({
        "blocks": [
            {"type": "header",
             "text": {"type": "plain_text",
                      "text": f"🅿️ {idx}. {header_addr[:70]}", "emoji": True}},
            {"type": "section",
             "text": {"type": "mrkdwn",
                      "text": f"*🔢 공고번호*\n{it['gonggo']}"}},
            {"type": "section",
             "text": {"type": "mrkdwn",
                      "text": f"*📏 면적*\n{it['area']}"}},
            {"type": "section",
             "fields": [
                 {"type": "mrkdwn", "text": f"*📅 입찰기간*\n{it['period']}"},
                 {"type": "mrkdwn", "text": f"*💰 최저입찰가*\n{it['price']}"},
             ]},
            {"type": "section",
             "fields": [
                 {"type": "mrkdwn", "text": f"*🏷 물건상태*\n{it['status']}"},
                 {"type": "mrkdwn", "text": f"*👁 조회수*\n{it['view']}"},
             ]},
            {"type": "section",
             "fields": [
                 {"type": "mrkdwn", "text": f"*🏢 처분기관*\n{it['org']}"},
                 {"type": "mrkdwn", "text": f"*🗂 유형*\n{it['tag']}"},
             ]},
            # ✅ 링크 2개 제공 (기존 포맷 유지)
            {"type": "section",
             "text": {"type": "mrkdwn",
                      "text": (
                          f"🔗 <{MAIN_LINK}|온비드 홈 먼저 클릭>\n"
                          f"➡️ <{it['link']}|공고 검색 바로가기>"
                      )}},
            {"type": "divider"},
        ]
    })


def send_summary(total_found: int, new_count: int, cumulative: int) -> None:
    slack_send({
        "blocks": [
            {"type": "divider"},
            {"type": "section",
             "text": {"type": "mrkdwn", "text": (
                 "📊 *온비드 크롤링 요약*\n\n"
                 f"- 총 검색 건수: *{total_found}건*\n"
                 f"- 신규 공고: *{new_count}건*\n"
                 f"- 누적 발송 기록: *{cumulative}건*\n\n"
                 f"⏰ 실행시간: {NOW.strftime('%Y-%m-%d %H:%M')} (KST)"
             )}},
        ]
    })


# ===============================
# 메인
# ===============================
def main() -> None:
    sent = load_sent()
    log.info(f"기존 발송 기록: {len(sent)}건")

    try:
        raw_items, total_found = fetch_all(SEARCH_KEYWORD)
    except Exception as e:
        log.exception("API 호출 실패")
        slack_error(f"API 호출 실패: {e}")
        raise

    log.info(f"API 응답 총 {total_found}건 (수집 {len(raw_items)}건)")

    new_items: list[dict] = []
    new_gonggos: set[str] = set()
    for raw in raw_items:
        it = normalize(raw)
        if not it["gonggo"] or it["gonggo"] in sent:
            continue
        new_items.append(it)
        new_gonggos.add(it["gonggo"])

    n = len(new_items)
    log.info(f"신규 공고: {n}건")

    if n > 0:
        slack_send({
            "blocks": [
                {"type": "header",
                 "text": {"type": "plain_text",
                          "text": f"🆕 온비드 신규 {SEARCH_KEYWORD} 공고 ({n}건)",
                          "emoji": True}},
                {"type": "divider"},
            ]
        })
        for idx, it in enumerate(new_items[:20], 1):
            send_item(idx, it)
    else:
        slack_send({
            "blocks": [
                {"type": "header",
                 "text": {"type": "plain_text",
                          "text": f"📭 오늘 신규 {SEARCH_KEYWORD} 공고 없음",
                          "emoji": True}},
                {"type": "section",
                 "text": {"type": "mrkdwn",
                          "text": f"📅 {NOW.strftime('%Y-%m-%d %H:%M')} (KST)\n오늘 신규 공고가 없습니다."}},
            ]
        })

    send_summary(total_found, n, len(sent) + len(new_gonggos))

    # 성공 후 상태 저장
    sent.update(new_gonggos)
    save_sent(sent)
    log.info("===== 완료 =====")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        slack_error(str(e))
        raise
