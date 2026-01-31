import os
import time
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime

slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
onbid_id = os.environ.get('ONBID_ID', '')
onbid_pw = os.environ.get('ONBID_PW', '')

print("=" * 70)
print("온비드 주차장 크롤러 시작 (로그인 포함)")
print("=" * 70)

# Playwright 시작
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
page = browser.new_page()

try:
    # 0단계: 메인 페이지 접속
    print("\n0. 온비드 메인 페이지 접속...")
    page.goto('https://www.onbid.co.kr', timeout=60000)
    page.wait_for_load_state('networkidle')
    time.sleep(2)
    print(f"✓ 메인 페이지 로드")
    
    # 로그인 체크
    if onbid_id and onbid_pw:
        print("\n1. 로그인 시도...")
        
        # 로그인 페이지로 이동
        try:
            # 로그인 버튼 찾기
            login_selectors = [
                'a:has-text("로그인")',
                'button:has-text("로그인")',
                'a[href*="login"]'
            ]
            
            for selector in login_selectors:
                if page.locator(selector).count() > 0:
                    page.click(selector)
                    print(f"✓ 로그인 버튼 클릭: {selector}")
                    break
            
            time.sleep(3)
            
            # 아이디/비밀번호 입력
            id_selectors = ['input[name="id"]', 'input#id', 'input[name="userId"]']
            pw_selectors = ['input[name="pw"]', 'input#pw', 'input[name="password"]', 'input[type="password"]']
            
            for selector in id_selectors:
                if page.locator(selector).count() > 0:
                    page.fill(selector, onbid_id)
                    print(f"✓ 아이디 입력")
                    break
            
            for selector in pw_selectors:
                if page.locator(selector).count() > 0:
                    page.fill(selector, onbid_pw)
                    print(f"✓ 비밀번호 입력")
                    break
            
            time.sleep(1)
            
            # 로그인 버튼 클릭
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("로그인")',
                'input[type="submit"]'
            ]
            
            for selector in submit_selectors:
                if page.locator(selector).count() > 0:
                    page.click(selector)
                    print(f"✓ 로그인 제출")
                    break
            
            time.sleep(5)
            page.wait_for_load_state('networkidle')
            
            current_url = page.url
            if 'login' not in current_url.lower():
                print("✓ 로그인 성공!")
            else:
                print("⚠️ 로그인 확인 필요")
            
            page.screenshot(path='after_login.png', full_page=True)
            
        except Exception as e:
            print(f"⚠️ 로그인 실패: {e}")
    else:
        print("\n⚠️ ONBID_ID, ONBID_PW가 설정되지 않았습니다")
        print("로그인 없이 계속 진행...")
    
    # 2단계: 부동산 > 공고 페이지로 이동
    print("\n2. 부동산 > 공고 페이지 이동...")
    
    # 부동산 메뉴 클릭
    real_estate_selectors = [
        'a:has-text("부동산")',
        'li:has-text("부동산") a',
        '[href*="budongsan"]'
    ]
    
    for selector in real_estate_selectors:
        try:
            if page.locator(selector).count() > 0:
                page.click(selector, timeout=5000)
                print(f"✓ 부동산 메뉴 클릭")
                time.sleep(2)
                break
        except:
            continue
    
    # 공고 메뉴 클릭
    gonggo_selectors = [
        'a:has-text("공고")',
        'li:has-text("공고") a',
        '[href*="gonggo"]'
    ]
    
    for selector in gonggo_selectors:
        try:
            if page.locator(selector).count() > 0:
                page.click(selector, timeout=5000)
                print(f"✓ 공고 메뉴 클릭")
                time.sleep(3)
                break
        except:
            continue
    
    print(f"현재 URL: {page.url}")
    page.screenshot(path='gonggo_page.png', full_page=True)
    
    # 3단계: 검색창에 주차장 입력
    print("\n3. 검색창에 '주차장' 입력...")
    
    search_selectors = [
        'input[name="searchWord"]',
        'input[id="searchWord"]',
        'input[placeholder*="검색"]',
        'input.search-input'
    ]
    
    search_found = False
    for selector in search_selectors:
        try:
            if page.locator(selector).count() > 0:
                page.fill(selector, '주차장')
                print(f"✓ 검색어 입력 성공: {selector}")
                search_found = True
                time.sleep(1)
                break
        except:
            continue
    
    if not search_found:
        print("⚠️ 검색창을 찾을 수 없습니다")
        print("\n현재 페이지 HTML (처음 2000자):")
        print(page.content()[:2000])
    
    # 4단계: 검색 실행
    print("\n4. 검색 실행...")
    
    search_btn_selectors = [
        'button:has-text("검색")',
        'a:has-text("검색")',
        'button.btn-search',
        'button[onclick*="search"]',
        'input[type="submit"]'
    ]
    
    btn_clicked = False
    for selector in search_btn_selectors:
        try:
            if page.locator(selector).count() > 0:
                page.click(selector)
                print(f"✓ 검색 버튼 클릭: {selector}")
                btn_clicked = True
                break
        except:
            continue
    
    if not btn_clicked:
        print("검색 버튼 못 찾아서 Enter 입력")
        page.keyboard.press('Enter')
    
    time.sleep(5)
    page.wait_for_load_state('networkidle')
    print(f"✓ 검색 완료 - URL: {page.url}")
    
    page.screenshot(path='search_results.png', full_page=True)
    
    # 5단계: 데이터 추출
    print("\n5. 데이터 추출...")
    html = page.content()
    print(f"페이지 HTML 길이: {len(html)} 문자")
    print(f"<table> 태그: {html.count('<table')}개")
    print(f"<tr> 태그: {html.count('<tr')}개")
    
    all_tr = page.locator('tr').all()
    print(f"총 {len(all_tr)}개 tr 발견")
    
    parking_data = []
    
    for idx, row in enumerate(all_tr[:30]):
        try:
            cells = row.locator('td').all()
            
            if len(cells) >= 3:
                texts = [cell.inner_text().strip() for cell in cells[:8]]
                row_text = ' '.join(texts)
                
                if idx < 10:
                    print(f"\n행 {idx+1} ({len(cells)}개 셀):")
                    print(f"  내용: {row_text[:100]}")
                
                if '주차' in row_text:
                    print(f"  ★★★ 주차장 발견! ★★★")
                    
                    parking_info = {}
                    if len(texts) >= 8:
                        parking_info = {
                            '공고번호': texts[0],
                            '사건번호': texts[1],
                            '물건종류': texts[2],
                            '소재지': texts[3],
                            '감정가': texts[4],
                            '최저가': texts[5],
                            '입찰일시': texts[6],
                            '상태': texts[7]
                        }
                    else:
                        for i, t in enumerate(texts):
                            parking_info[f'열{i+1}'] = t
                    
                    parking_data.append(parking_info)
                    
        except Exception as e:
            if idx < 5:
                print(f"행 {idx+1} 에러: {e}")
    
    print(f"\n✓ 총 {len(parking_data)}개 주차장 발견")
    
    # 슬랙 전송
    if slack_webhook_url:
        header_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🅿️ 온비드 주차장 검색 결과",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📅 {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}\n\n총 *{len(parking_data)}개* 주차장 발견"
                }
            },
            {"type": "divider"}
        ]
        
        requests.post(slack_webhook_url, json={"blocks": header_blocks})
        
        for idx, parking in enumerate(parking_data[:20], 1):
            fields = []
            for key, value in parking.items():
                if value:
                    fields.append({"type": "mrkdwn", "text": f"*{key}*\n{value[:100]}"})
            
            blocks = [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*{idx}. 주차장*"}},
                {"type": "section", "fields": fields[:8]},
                {"type": "divider"}
            ]
            
            requests.post(slack_webhook_url, json={"blocks": blocks})
            time.sleep(1)
        
        print("✓ 슬랙 전송 완료")

except Exception as e:
    print(f"\n✗ 오류: {e}")
    import traceback
    traceback.print_exc()
    
    try:
        page.screenshot(path='error.png', full_page=True)
    except:
        pass

finally:
    browser.close()
    playwright.stop()
    
    print("\n" + "=" * 70)
    print("완료")
    print("=" * 70)
