import os
import time
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime

slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')

print("=" * 70)
print("온비드 주차장 크롤러 시작")
print("=" * 70)

# Playwright 시작
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
page = browser.new_page()

try:
    # 1단계: 부동산 공고 목록 페이지 접속
    print("\n1. 온비드 부동산 공고 페이지 접속...")
    page.goto('https://www.onbid.co.kr/op/svc/getSvcGonggoList.do', timeout=60000)
    page.wait_for_load_state('networkidle')
    time.sleep(3)
    print(f"✓ 페이지 로드 완료: {page.url}")
    
    page.screenshot(path='step1_initial.png', full_page=True)
    
    # 2단계: 검색창 찾아서 '주차장' 입력
    print("\n2. 검색창에 '주차장' 입력...")
    
    search_selectors = [
        'input[name="searchWord"]',
        'input[id="searchWord"]',
        'input[placeholder*="검색"]',
        'input.search-input'
    ]
    
    search_success = False
    for selector in search_selectors:
        try:
            if page.locator(selector).count() > 0:
                page.fill(selector, '주차장')
                print(f"✓ 검색창 입력 성공: {selector}")
                search_success = True
                time.sleep(1)
                break
        except:
            continue
    
    if not search_success:
        print("⚠️ 검색창을 찾을 수 없습니다")
        print("\n페이지 HTML (처음 3000자):")
        print(page.content()[:3000])
    
    page.screenshot(path='step2_search_input.png', full_page=True)
    
    # 3단계: 검색 버튼 클릭
    print("\n3. 검색 실행...")
    
    search_btn_selectors = [
        'button:has-text("검색")',
        'a:has-text("검색")',
        'button.btn-search',
        'button[onclick*="search"]'
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
        print("검색 버튼을 못 찾아서 Enter 키 입력")
        page.keyboard.press('Enter')
    
    time.sleep(5)
    page.wait_for_load_state('networkidle')
    print(f"✓ 검색 완료 - 현재 URL: {page.url}")
    
    page.screenshot(path='step3_search_results.png', full_page=True)
    
    # 4단계: HTML 분석
    print("\n4. 페이지 HTML 분석...")
    html = page.content()
    print(f"페이지 HTML 길이: {len(html)} 문자")
    print(f"'주차장' 키워드: {'✓ 발견' if '주차장' in html else '✗ 없음'}")
    print(f"<table> 태그: {html.count('<table')}개")
    print(f"<tr> 태그: {html.count('<tr')}개")
    print(f"<td> 태그: {html.count('<td')}개")
    
    # HTML 샘플 출력
    print("\n5. HTML 시작 부분 (3000자):")
    print("=" * 70)
    print(html[:3000])
    print("=" * 70)
    
    # 6단계: 데이터 추출
    print("\n6. 데이터 추출 시도...")
    all_tr = page.locator('tr').all()
    print(f"총 {len(all_tr)}개 tr 발견")
    
    parking_data = []
    
    for idx, row in enumerate(all_tr[:30]):  # 처음 30개 행
        try:
            cells = row.locator('td').all()
            
            if len(cells) >= 3:
                texts = []
                for cell in cells[:8]:  # 최대 8개 셀
                    try:
                        text = cell.inner_text().strip()
                        texts.append(text)
                    except:
                        texts.append('')
                
                row_text = ' '.join(texts)
                
                # 처음 10개는 무조건 출력
                if idx < 10:
                    print(f"\n행 {idx+1} ({len(cells)}개 셀):")
                    for i, t in enumerate(texts[:5]):
                        if t:
                            print(f"  셀{i+1}: {t[:50]}")
                
                # 주차장 키워드 확인
                if '주차' in row_text or '駐車' in row_text:
                    print(f"\n★★★ 행 {idx+1}: 주차장 발견! ★★★")
                    
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
            if idx < 10:
                print(f"행 {idx+1} 에러: {e}")
    
    print(f"\n✓ 총 {len(parking_data)}개 주차장 발견")
    
    # 7단계: 슬랙 전송
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
        time.sleep(1)
        
        # 각 주차장 정보 전송
        for idx, parking in enumerate(parking_data[:20], 1):
            fields = []
            for key, value in parking.items():
                if value:
                    fields.append({
                        "type": "mrkdwn",
                        "text": f"*{key}*\n{value[:100]}"
                    })
            
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{idx}. 주차장 정보*"
                    }
                },
                {
                    "type": "section",
                    "fields": fields[:8]
                },
                {"type": "divider"}
            ]
            
            requests.post(slack_webhook_url, json={"blocks": blocks})
            time.sleep(1)
        
        print("✓ 슬랙 전송 완료")

except Exception as e:
    print(f"\n✗ 오류 발생: {e}")
    import traceback
    traceback.print_exc()
    
    # 에러 발생 시에도 스크린샷
    try:
        page.screenshot(path='error.png', full_page=True)
        print("에러 스크린샷 저장: error.png")
    except:
        pass

finally:
    # 정리
    browser.close()
    playwright.stop()
    
    print("\n" + "=" * 70)
    print("크롤링 완료")
    print("=" * 70)
