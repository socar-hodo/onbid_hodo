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
            # 로그인 링크 클릭
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
            
            # 아이디 입력
            page.fill('input[type="text"]', onbid_id)
            time.sleep(1)
            
            # 비밀번호 입력
            page.fill('input[type="password"]', onbid_pw)
            time.sleep(1)
            
            # 로그인 버튼 클릭
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
    time.sleep(3)
    print("✓ 홈페이지 로딩")
    
    # 4. 통합검색창에서 주차장 검색
    print("\n=== 4. 통합검색창에서 '주차장' 검색 ===")
    try:
        # 검색창 찾기 (여러 방법 시도)
        search_input = None
        
        # 방법 1: placeholder로 찾기
        inputs = page.locator('input[placeholder*="검색"]').all()
        if len(inputs) > 0:
            search_input = inputs[0]
        
        # 방법 2: 모든 text input 중에서
        if not search_input:
            all_inputs = page.locator('input[type="text"]').all()
            for inp in all_inputs:
                try:
                    placeholder = inp.get_attribute('placeholder')
                    if placeholder and '검색' in placeholder:
                        search_input = inp
                        break
                except:
                    continue
        
        if search_input:
            search_input.fill('주차장')
            print("✓ 검색어 입력: 주차장")
            time.sleep(1)
            
            # 엔터 또는 검색 버튼 클릭
            try:
                search_input.press('Enter')
                print("✓ 검색 실행 (Enter)")
            except:
                # 검색 버튼 찾기
                search_buttons = page.locator('button, a').all()
                for btn in search_buttons:
                    try:
                        if '검색' in btn.inner_text() or 'search' in btn.get_attribute('class') or '':
                            btn.click()
                            print("✓ 검색 실행 (버튼)")
                            break
                    except:
                        continue
            
            time.sleep(10)
            print(f"✓ 검색 완료, URL: {page.url}")
        else:
            print("⚠️ 검색창을 찾을 수 없음")
    
    except Exception as e:
        print(f"⚠️ 검색 실패: {e}")
    
    # 5. 입찰물건 탭 클릭
    print("\n=== 5. 입찰물건 탭 클릭 ===")
    
    # 탭 존재 확인 및 클릭
    tab_clicked = page.evaluate("""
        () => {
            // 입찰물건 탭 찾기
            const allElements = Array.from(document.querySelectorAll('li, a, button, div, span'));
            
            for (let elem of allElements) {
                const text = elem.textContent?.trim();
                if (text === '입찰물건') {
                    console.log('입찰물건 탭 발견:', elem.tagName);
                    
                    // 클릭 가능한 요소 찾기
                    if (elem.tagName === 'A') {
                        elem.click();
                        return 'clicked-a';
                    }
                    
                    // li 안의 a 찾기
                    const link = elem.querySelector('a');
                    if (link) {
                        link.click();
                        return 'clicked-link';
                    }
                    
                    // 그냥 클릭
                    elem.click();
                    return 'clicked-elem';
                }
            }
            
            // data-tab으로 찾기
            const tab3 = document.querySelector('li[data-tab="tab-3"]');
            if (tab3) {
                const link = tab3.querySelector('a');
                if (link) link.click();
                return 'clicked-tab-3';
            }
            
            // w 속성으로 찾기
            const catalog = document.querySelector('li[w="catalog"]');
            if (catalog) {
                const link = catalog.querySelector('a');
                if (link) link.click();
                return 'clicked-catalog';
            }
            
            return false;
        }
    """)
    
    if tab_clicked:
        print(f"✓ 입찰물건 탭 클릭: {tab_clicked}")
        time.sleep(10)
    else:
        print("⚠️ 입찰물건 탭을 찾을 수 없음")
    
    print(f"✓ 현재 URL: {page.url}")
    
    # 6. 주차장 물건 크롤링
    print("\n=== 6. 주차장 물건 크롤링 ===")
    
    # 페이지에 주차장 텍스트 있는지 확인
    page_text = page.evaluate("() => document.body.innerText")
    has_parking = '주차' in page_text or '주차장' in page_text
    print(f"페이지에 '주차장' 텍스트: {'✓' if has_parking else '✗'}")
    
    # JavaScript로 테이블 데이터 추출
    table_data = page.evaluate("""
        () => {
            const results = [];
            const tables = document.querySelectorAll('table');
            
            tables.forEach((table) => {
                const rows = table.querySelectorAll('tbody tr, tr');
                
                rows.forEach((row) => {
                    const cells = Array.from(row.querySelectorAll('td'));
                    if (cells.length >= 3) {
                        const texts = cells.map(cell => cell.innerText.trim());
                        const rowText = texts.join(' ');
                        
                        // 주차장 키워드 확인
                        if (rowText.includes('주차') || rowText.includes('주차장')) {
                            results.push(texts);
                        }
                    }
                });
            });
            
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
                print(f"  ⏭️  제외: {texts[0][:30]}")
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
    
    # 샘플 출력
    if len(all_parking_data) > 0:
        print("\n=== 첫 번째 데이터 ===")
        sample = all_parking_data[0]
        for key, value in sample.items():
            print(f"{key}: {value[:100] if value else '-'}")
    
    # 7. 슬랙 전송
    if slack_webhook_url and len(all_parking_data) > 0:
        print("\n=== 7. 슬랙 전송 ===")
        
        header = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🆕 온비드 주차장 경매",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')} (KST)*\n\n주차장 *{len(all_parking_data)}개* 발견!"
                    }
                },
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
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"🅿️ {idx}. 주차장 경매",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*공고번호*\n`{parking['공고번호']}`"},
                            {"type": "mrkdwn", "text": f"*회차/사건*\n{parking['회차사건'] or '-'}"}
                        ]
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*소재지*\n{location[:300]}"}
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*입찰일시*\n{parking['입찰일시'] or '-'}"}
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*감정가*\n{parking['감정가'] or '-'}"},
                            {"type": "mrkdwn", "text": f"*상태*\n{parking['상태'] or '-'}"}
                        ]
                    },
                    {"type": "divider"}
                ]
            }
            
            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)
        
        print("✓ 슬랙 전송 완료")
    
    elif slack_webhook_url:
        no_result = {
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')}*\n\n오늘은 주차장 경매가 없습니다."
                }
            }]
        }
        requests.post(slack_webhook_url, json=no_result)

except Exception as e:
    print(f"\n✗ 오류: {e}")
    import traceback
    traceback.print_exc()
    
    if slack_webhook_url:
        error_blocks = {
            "blocks": [{
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"⚠️ *크롤링 오류*\n```{str(e)[:300]}```"}
            }]
        }
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
