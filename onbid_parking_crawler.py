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

# 평일만 실행
weekday = now.weekday()
if weekday >= 5:
    print(f"주말({now.strftime('%A')})에는 실행하지 않습니다.")
    exit(0)

slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
onbid_id = os.environ.get("ONBID_ID", "")
onbid_pw = os.environ.get("ONBID_PW", "")

SAVED_FILE = "sent_gonggo.json"

# 기존 발송 공고 불러오기
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
    print("===== 온비드 접속 (리뉴얼 버전) =====")
    
    # 메인 페이지 접속
    page.goto("https://www.onbid.co.kr/op/meminf/lgnmng/prtllgn/PrtlLgnController/main.do", timeout=60000)
    time.sleep(3)

    # 로그인 (필요시)
    if onbid_id and onbid_pw:
        print("로그인 시도...")
        try:
            # 로그인 페이지로 직접 이동
            page.goto('https://www.onbid.co.kr/op/meminf/lgnmng/prtllgn/PrtlLgnController/prtlLgn.do', timeout=30000)
            time.sleep(2)

            page.fill('input[type="text"]', onbid_id)
            page.fill('input[type="password"]', onbid_pw)
            
            page.locator('button:has-text("로그인"), input[type="submit"]:has-text("로그인")').first.click()
            time.sleep(5)
            print("✓ 로그인 완료")
        except Exception as e:
            print(f"⚠️ 로그인 실패 (비로그인으로 진행): {e}")

    # 메인 페이지로 돌아가기
    page.goto("https://www.onbid.co.kr/op/meminf/lgnmng/prtllgn/PrtlLgnController/main.do", timeout=60000)
    time.sleep(2)

    # ===============================
    # 검색창에 "주차장" 입력 및 검색
    # ===============================
    print("주차장 검색 중...")
    
    search_result = page.evaluate("""() => {
        const searchInput = document.querySelector('input[placeholder="검색어를 입력하세요."]');
        if (!searchInput) return { success: false, error: 'search input not found' };
        
        searchInput.value = '주차장';
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
        
        // 검색 버튼 클릭
        const searchBtn = searchInput.nextElementSibling || document.querySelector('button[type="button"]');
        if (searchBtn) {
            searchBtn.click();
            return { success: true };
        }
        
        return { success: false, error: 'search button not found' };
    }""")
    
    if not search_result.get('success'):
        raise Exception(f"검색 실패: {search_result.get('error')}")
    
    time.sleep(3)
    
    # 최근 검색어에서 "주차장" 클릭
    page.evaluate("""() => {
        const recentSearch = Array.from(document.querySelectorAll('*')).find(el => 
            el.textContent.trim() === '주차장' && el.tagName !== 'INPUT'
        );
        if (recentSearch) {
            recentSearch.click();
        }
    }""")
    
    time.sleep(5)
    print("✓ 통합검색 페이지 이동 완료")

    # ===============================
    # 페이지 반복 수집 (최대 5페이지)
    # ===============================
    page_num = 1
    max_pages = 5

    while page_num <= max_pages:
        print(f"\n{page_num}페이지 수집 중...")
        
        # 페이지 로딩 대기
        time.sleep(3)
        
        # 물건 데이터 추출
        items_data = page.evaluate("""() => {
            const items = [];
            const rows = document.querySelectorAll('tbody tr');
            
            rows.forEach((row) => {
                const fullText = row.innerText || '';
                
                // 주차장 관련 행만 필터
                if (!fullText.includes('주차')) return;
                
                // 공고번호 추출
                const gonggoMatch = fullText.match(/\\d{4}-\\d{4}-\\d{6}/);
                const gonggo = gonggoMatch ? gonggoMatch[0] : '';
                
                if (!gonggo) return;
                
                // 소재지 추출
                const lines = fullText.split('\\n').map(l => l.trim()).filter(l => l);
                let address = '';
                for (let i = 0; i < lines.length; i++) {
                    if (lines[i].includes(gonggo) && i + 1 < lines.length) {
                        address = lines[i + 1];
                        break;
                    }
                }
                
                // 입찰기간 추출
                const dateMatches = fullText.match(/\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}/g);
                const bidPeriod = dateMatches && dateMatches.length >= 2 
                    ? `${dateMatches[0]} ~ ${dateMatches[1]}` 
                    : '';
                
                // 감정평가금액 추출
                const priceMatch = fullText.match(/(\d{1,3}(,\d{3})+)/g);
                const price = priceMatch ? priceMatch[priceMatch.length - 1] : '';
                
                // 면적 추출
                const areaMatch = fullText.match(/([\\d,]+)㎡/);
                const area = areaMatch ? `[토지 ${areaMatch[1]}㎡]` : '';
                
                // 물건상태 추출
                let status = '';
                if (fullText.includes('입찰중')) status = '입찰중';
                else if (fullText.includes('낙찰')) status = '낙찰';
                else if (fullText.includes('유찰')) status = '유찰';
                
                // 재산유형 추출
                let propertyType = '';
                if (fullText.includes('공유재산')) propertyType = '공유재산';
                else if (fullText.includes('압류재산')) propertyType = '압류재산';
                else if (fullText.includes('국유재산')) propertyType = '국유재산';
                
                items.push({
                    gonggo,
                    address,
                    area,
                    bidPeriod,
                    price,
                    status,
                    propertyType
                });
            });
            
            return items;
        }""")
        
        # 데이터 처리
        for item in items_data:
            gonggo_no = item['gonggo']
            
            # 중복 체크
            if gonggo_no in sent_gonggos:
                continue
            
            total_found += 1
            
            # 신규 데이터 저장
            all_parking_data.append({
                "gonggo": gonggo_no,
                "address": item['address'],
                "area": item['area'],
                "period": item['bidPeriod'],
                "price": item['price'],
                "status": item['status'],
                "propertyType": item['propertyType'],
                "link_main": "https://www.onbid.co.kr",
                "link_search": f"https://www.onbid.co.kr/op/cltrpbancinf/toppagemng/unfsrch/UnfSrchController/mvmnUnfSrchClg.do"
            })
            
            new_gonggos.add(gonggo_no)
            print(f"  ✓ 추가: {gonggo_no} - {item['address'][:40]}")
        
        print(f"  페이지 {page_num} 완료: {len(items_data)}개 수집")
        
        # 다음 페이지로 이동 (무한 스크롤 방식인 경우)
        # 또는 페이지 버튼 클릭
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # 더 이상 데이터가 없으면 종료
        if len(items_data) == 0:
            print("  더 이상 데이터가 없습니다")
            break
        
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
            # 소재지명을 제목으로 (최대 50자)
            location_title = item['address'][:50]
            if len(item['address']) > 50:
                location_title += "..."
            
            slack_send({
                "blocks": [
                    {"type": "header",
                     "text": {"type": "plain_text",
                              "text": f"🅿️ {idx}. {location_title}",
                              "emoji": True}},
                    {"type": "section",
                     "text": {"type": "mrkdwn",
                              "text": f"*📍 전체 소재지*\n{item['address']}"}},
                    {"type": "section",
                     "text": {"type": "mrkdwn",
                              "text": f"*🔢 공고번호*\n{item['gonggo']}"}},
                    {"type": "section",
                     "text": {"type": "mrkdwn",
                              "text": f"*📏 면적*\n{item['area'] or '-'}"}},
                    {"type": "section",
                     "fields": [
                         {"type": "mrkdwn",
                          "text": f"*📅 입찰기간*\n{item['period'] or '-'}"},
                         {"type": "mrkdwn",
                          "text": f"*💰 최저입찰가*\n{item['price'] or '-'}원"}
                     ]},
                    {"type": "section",
                     "fields": [
                         {"type": "mrkdwn",
                          "text": f"*🏷 재산유형*\n{item['propertyType'] or '-'}"},
                         {"type": "mrkdwn",
                          "text": f"*📊 상태*\n{item['status'] or '-'}"}
                     ]},
                    {"type": "section",
                     "text": {"type": "mrkdwn",
                              "text": f"🔗 <{item['link_main']}|온비드 홈 먼저 클릭>\n➡️ <{item['link_search']}|주차장 검색 페이지>"}},
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

    # 요약 리포트
    slack_send({
        "blocks": [
            {"type": "divider"},
            {"type": "section",
             "text": {"type": "mrkdwn",
                      "text": f"""
📊 *온비드 크롤링 요약 (리뉴얼 버전)*

- 총 검색 건수: *{total_found}건*
- 신규 공고: *{신규건수}건*
- 누적 발송 기록: *{len(sent_gonggos) + len(new_gonggos)}건*

⏰ 실행시간: {now.strftime('%Y-%m-%d %H:%M')} (KST)
🔄 시스템: 차세대 온비드 (2026년 버전)
""" }}
        ]
    })

    # 신규 발송 성공 후 기록 저장
    sent_gonggos.update(new_gonggos)

    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_gonggos), f, ensure_ascii=False, indent=2)

except Exception as e:
    slack_error(str(e))
    import traceback
    traceback.print_exc()
    raise

finally:
    try:
        page.screenshot(path='onbid_renewal_result.png', full_page=True)
        print("\n✓ 스크린샷: onbid_renewal_result.png")
    except:
        pass
    
    browser.close()
    playwright.stop()

print("\n===== 완료 (리뉴얼 버전) =====")
