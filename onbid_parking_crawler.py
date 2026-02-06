import os
import time
import json
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone

# 한국 시간
KST = timezone(timedelta(hours=9))

slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
onbid_id = os.environ.get('ONBID_ID', '')
onbid_pw = os.environ.get('ONBID_PW', '')

print("=" * 70)
print(f"온비드 주차장 경매 알리미")
print(f"실행 시간(KST): {datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M:%S')}")
print("=" * 70)

# Playwright 시작
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
page = browser.new_page()

all_parking_data = []

try:
    # 1. 온비드 홈페이지 접속
    print("\n=== 1. 온비드 홈페이지 접속 ===")
    page.goto('https://www.onbid.co.kr', timeout=60000)
    time.sleep(5)
    print("✓ 홈페이지 로딩 완료")
    
    # 2. 로그인
    print("\n=== 2. 로그인 ===")
    if onbid_id and onbid_pw:
        try:
            login_links = page.locator('a').all()
            for link in login_links:
                try:
                    if '로그인' in link.inner_text():
                        link.click()
                        print("✓ 로그인 페이지 이동")
                        break
                except:
                    continue
            
            time.sleep(3)
            page.fill('input[type="text"]', onbid_id)
            time.sleep(1)
            page.fill('input[type="password"]', onbid_pw)
            time.sleep(1)
            
            login_buttons = page.locator('button, input[type="submit"], a').all()
            for btn in login_buttons:
                try:
                    if '로그인' in btn.inner_text():
                        btn.click()
                        break
                except:
                    continue
            
            time.sleep(5)
            print("✓ 로그인 완료")
        except Exception as e:
            print(f"⚠️ 로그인 실패: {e}")
    
    # 3. 홈페이지로 돌아가기
    print("\n=== 3. 홈페이지로 돌아가기 ===")
    page.goto('https://www.onbid.co.kr', timeout=60000)
    time.sleep(5)
    print("✓ 홈페이지 로딩")
    
    # 4. 통합검색창에서 주차장 검색
    print("\n=== 4. 통합검색창에서 '주차장' 검색 ===")
    
    search_result = page.evaluate("""
        () => {
            // id="query"로 검색창 찾기
            const searchInput = document.getElementById('query');
            if (!searchInput) {
                return { success: false, error: 'query input not found' };
            }
            
            // 검색어 입력
            searchInput.value = '주차장';
            console.log('검색어 입력:', searchInput.value);
            
            // 검색 버튼 클릭 (id="_submit")
            const submitBtn = document.getElementById('_submit');
            if (submitBtn) {
                submitBtn.click();
                return { success: true, method: 'submit button' };
            }
            
            // 또는 sch_btn 클래스로 찾기
            const schBtn = document.querySelector('.sch_btn');
            if (schBtn) {
                schBtn.click();
                return { success: true, method: 'sch_btn class' };
            }
            
            // form submit
            const form = searchInput.closest('form');
            if (form) {
                form.submit();
                return { success: true, method: 'form submit' };
            }
            
            return { success: false, error: 'submit button not found' };
        }
    """)
    
    print(f"검색 결과: {search_result}")
    
    if search_result.get('success'):
        print(f"✓ 검색 실행: {search_result.get('method')}")
        time.sleep(10)
    else:
        print(f"⚠️ 검색 실패: {search_result.get('error')}")
    
    print(f"✓ 검색 후 URL: {page.url}")
    
    # 5. 입찰물건 탭 클릭
    print("\n=== 5. 입찰물건 탭 클릭 ===")
    
    tab_clicked = page.evaluate("""
        () => {
            // 모든 요소에서 "입찰물건" 텍스트 찾기
            const allElements = Array.from(document.querySelectorAll('*'));
            
            for (let elem of allElements) {
                const text = elem.textContent?.trim();
                
                // "입찰물건" 정확히 매칭
                if (text === '입찰물건') {
                    console.log('입찰물건 발견:', elem.tagName, elem.className);
                    
                    // a 태그면 클릭
                    if (elem.tagName === 'A') {
                        elem.click();
                        return { success: true, method: 'a-tag', tag: elem.tagName };
                    }
                    
                    // span 안에 a가 있는 경우
                    if (elem.tagName === 'SPAN') {
                        const parent = elem.parentElement;
                        if (parent && parent.tagName === 'A') {
                            parent.click();
                            return { success: true, method: 'span>parent-a', tag: parent.tagName };
                        }
                    }
                    
                    // li 안의 a 찾기
                    const link = elem.querySelector('a');
                    if (link) {
                        link.click();
                        return { success: true, method: 'elem>a', tag: elem.tagName };
                    }
                    
                    // 부모 찾기
                    let current = elem;
                    for (let i = 0; i < 5; i++) {
                        current = current.parentElement;
                        if (!current) break;
                        
                        if (current.tagName === 'A') {
                            current.click();
                            return { success: true, method: 'ancestor-a', tag: current.tagName };
                        }
                        
                        const parentLink = current.querySelector('a');
                        if (parentLink) {
                            parentLink.click();
                            return { success: true, method: 'ancestor>a', tag: current.tagName };
                        }
                    }
                    
                    // 직접 클릭 시도
                    elem.click();
                    return { success: true, method: 'direct-click', tag: elem.tagName };
                }
            }
            
            // data-tab으로 찾기
            const tab3 = document.querySelector('[data-tab="tab-3"]');
            if (tab3) {
                const link = tab3.querySelector('a');
                if (link) {
                    link.click();
                    return { success: true, method: 'data-tab-3' };
                }
            }
            
            return { success: false, error: 'tab not found' };
        }
    """)
    
    print(f"탭 클릭 결과: {tab_clicked}")
    
    if tab_clicked.get('success'):
        print(f"✓ 입찰물건 탭 클릭: {tab_clicked.get('method')}")
        time.sleep(10)
    else:
        print(f"⚠️ 입찰물건 탭 클릭 실패: {tab_clicked.get('error')}")
    
    print(f"✓ 현재 URL: {page.url}")
    
    # 6. 주차장 물건 크롤링
    print("\n=== 6. 주차장 물건 크롤링 ===")
    
    page_text = page.evaluate("() => document.body.innerText")
    has_parking = '주차' in page_text or '주차장' in page_text
    print(f"페이지에 '주차장' 텍스트: {'✓' if has_parking else '✗'}")
    
    # JavaScript로 테이블 데이터 추출
    table_data = page.evaluate("""
        () => {
            const results = [];
            const tables = document.querySelectorAll('table');
            
            console.log('테이블 개수:', tables.length);
            
            tables.forEach((table) => {
                const rows = table.querySelectorAll('tbody tr, tr');
                
                rows.forEach((row) => {
                    const cells = Array.from(row.querySelectorAll('td'));
                    if (cells.length >= 3) {
                        const texts = cells.map(cell => cell.innerText.trim());
                        const rowText = texts.join(' ');
                        
                        if (rowText.includes('주차') || rowText.includes('주차장')) {
                            console.log('주차장 발견:', rowText.substring(0, 50));
                            results.push(texts);
                        }
                    }
                });
            });
            
            console.log('총 결과:', results.length);
            return results;
        }
    """)
    
    print(f"✓ {len(table_data)}개 주차장 행 발견")
    
    # 데이터 정리
    for idx, texts in enumerate(table_data):
        try:
            row_text = ' '.join(texts)
            
            # 제외 키워드
            if any(kw in row_text for kw in ['일반공고', '공유재산', '위수탁', '취소공고']):
                continue
            
            # 공고번호 추출
            gonggo_no = ''
            for text in texts:
                if '-' in text and sum(c.isdigit() for c in text) >= 8:
                    gonggo_no = text.split('\n')[0].strip()
                    break
            
            if not gonggo_no and texts[0]:
                lines = texts[0].split('\n')
                gonggo_no = lines[0].strip()
            
            parking_info = {
                '공고번호': gonggo_no,
                '물건명': texts[0] if texts[0] else '',
                '회차사건': texts[1] if len(texts) > 1 else '',
                '입찰일시': texts[2] if len(texts) > 2 else '',
                '감정가': texts[3] if len(texts) > 3 else '',
                '상태': texts[4] if len(texts) > 4 else '',
            }
            
            if gonggo_no and len(gonggo_no) >= 5:
                all_parking_data.append(parking_info)
                print(f"  🅿️ {gonggo_no}")
        
        except Exception as e:
            continue
    
    print(f"\n{'='*70}")
    print(f"총 {len(all_parking_data)}개 주차장 발견")
    print(f"{'='*70}")
    
    # 슬랙 전송
    if slack_webhook_url and len(all_parking_data) > 0:
        print("\n=== 슬랙 전송 ===")
        
        header = {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "🆕 온비드 주차장 경매", "emoji": True}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')}*\n\n주차장 *{len(all_parking_data)}개* 발견!"}},
                {"type": "divider"}
            ]
        }
        
        requests.post(slack_webhook_url, json=header)
        time.sleep(1)
        
        for idx, parking in enumerate(all_parking_data[:20], 1):
            lines = parking['물건명'].split('\n')
            location = lines[1] if len(lines) > 1 else lines[0] if lines else ''
            
            blocks = {
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": f"🅿️ {idx}. 주차장", "emoji": True}},
                    {"type": "section", "fields": [
                        {"type": "mrkdwn", "text": f"*공고번호*\n`{parking['공고번호']}`"},
                        {"type": "mrkdwn", "text": f"*회차/사건*\n{parking['회차사건'] or '-'}"}
                    ]},
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*소재지*\n{location[:300]}"}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*입찰일시*\n{parking['입찰일시'] or '-'}"}},
                    {"type": "section", "fields": [
                        {"type": "mrkdwn", "text": f"*감정가*\n{parking['감정가'] or '-'}"},
                        {"type": "mrkdwn", "text": f"*상태*\n{parking['상태'] or '-'}"}
                    ]},
                    {"type": "divider"}
                ]
            }
            
            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)
        
        print("✓ 슬랙 전송 완료")
    
    elif slack_webhook_url:
        no_result = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')}*\n\n주차장 경매가 없습니다."}}]}
        requests.post(slack_webhook_url, json=no_result)

except Exception as e:
    print(f"\n✗ 오류: {e}")
    import traceback
    traceback.print_exc()
    
    if slack_webhook_url:
        error_blocks = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"⚠️ *오류*\n```{str(e)[:300]}```"}}]}
        requests.post(slack_webhook_url, json=error_blocks)

finally:
    try:
        page.screenshot(path='onbid_result.png', full_page=True)
        print("\n✓ 스크린샷: onbid_result.png")
    except:
        pass
    
    browser.close()
    playwright.stop()
    
    print("\n" + "=" * 70)
    print("완료")
    print("=" * 70)
