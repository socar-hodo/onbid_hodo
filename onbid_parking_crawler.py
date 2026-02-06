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
    # 로그인
    print("\n=== 로그인 ===")
    page.goto('https://www.onbid.co.kr', timeout=60000)
    time.sleep(5)
    
    if onbid_id and onbid_pw:
        try:
            login_links = page.locator('a').all()
            for link in login_links:
                try:
                    if '로그인' in link.inner_text():
                        link.click()
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
    
    # 통합검색으로 주차장 검색
    print("\n=== 주차장 검색 ===")
    search_url = 'https://www.onbid.co.kr/op/dsa/main/main.do?searchWord=%EC%A3%BC%EC%B0%A8%EC%9E%A5'
    page.goto(search_url, timeout=60000)
    
    # 페이지 완전 로딩 대기
    page.wait_for_load_state('networkidle', timeout=30000)
    time.sleep(10)
    print(f"✓ 검색 페이지 로딩 완료")
    
    # 입찰물건 탭 찾기 및 클릭
    print("\n=== 입찰물건 탭 클릭 ===")
    
    # 먼저 탭이 존재하는지 확인
    tab_exists = page.evaluate("""
        () => {
            const tab = document.querySelector('li[data-tab="tab-3"]');
            if (tab) {
                return {
                    exists: true,
                    text: tab.innerText,
                    visible: tab.offsetParent !== null
                };
            }
            return { exists: false };
        }
    """)
    
    print(f"탭 존재 여부: {tab_exists}")
    
    if tab_exists.get('exists'):
        try:
            # JavaScript로 강제 클릭
            page.evaluate("""
                () => {
                    const tab = document.querySelector('li[data-tab="tab-3"] a');
                    if (tab) {
                        tab.click();
                        return true;
                    }
                    
                    // 함수 직접 호출
                    if (typeof menuChange !== 'undefined') {
                        menuChange('catalog');
                        return true;
                    }
                    
                    return false;
                }
            """)
            print("✓ 입찰물건 탭 클릭 (JavaScript)")
            time.sleep(10)
        except Exception as e:
            print(f"⚠️ 탭 클릭 실패: {e}")
    else:
        print("⚠️ 입찰물건 탭을 찾을 수 없음")
    
    print(f"✓ 현재 URL: {page.url}")
    
    # 탭 전환 후 콘텐츠 로딩 대기
    time.sleep(5)
    
    # 결과 크롤링
    print("\n=== 데이터 수집 ===")
    
    # 페이지의 모든 텍스트 확인
    page_text = page.evaluate("() => document.body.innerText")
    has_parking = '주차' in page_text or '주차장' in page_text
    print(f"페이지에 '주차장' 텍스트: {'✓' if has_parking else '✗'}")
    
    # JavaScript로 모든 테이블 데이터 추출 (더 상세하게)
    table_data = page.evaluate("""
        () => {
            const results = [];
            
            // 모든 테이블 찾기
            const tables = document.querySelectorAll('table');
            console.log('테이블 개수:', tables.length);
            
            tables.forEach((table, tableIdx) => {
                const rows = table.querySelectorAll('tbody tr, tr');
                console.log(`테이블 ${tableIdx} 행 개수:`, rows.length);
                
                rows.forEach((row, rowIdx) => {
                    const cells = Array.from(row.querySelectorAll('td'));
                    if (cells.length >= 3) {
                        const texts = cells.map(cell => cell.innerText.trim());
                        const rowText = texts.join(' ');
                        
                        // 주차장 키워드 확인
                        if (rowText.includes('주차') || rowText.includes('주차장')) {
                            console.log('주차장 발견:', rowText.substring(0, 100));
                            results.push({
                                tableIndex: tableIdx,
                                rowIndex: rowIdx,
                                cells: texts
                            });
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
    for item in table_data:
        try:
            texts = item['cells']
            row_text = ' '.join(texts)
            
            # 제외 키워드
            if any(kw in row_text for kw in ['일반공고', '공유재산', '위수탁', '취소공고']):
                print(f"  ⏭️  제외: {texts[0][:50]}")
                continue
            
            # 공고번호 추출
            gonggo_no = ''
            for text in texts:
                # 2025-1100-084260 같은 형태
                if '-' in text and sum(c.isdigit() for c in text) >= 8:
                    gonggo_no = text.split('\n')[0].strip()
                    break
            
            if not gonggo_no and texts[0]:
                gonggo_no = texts[0].split('\n')[0].strip()
            
            # 물건명 찾기
            mulgun_name = ''
            for text in texts:
                if '주차장' in text or '주차' in text:
                    mulgun_name = text
                    break
            
            if not mulgun_name:
                mulgun_name = texts[0] if texts[0] else ''
            
            parking_info = {
                '공고번호': gonggo_no,
                '물건명': mulgun_name,
                '전체데이터': texts
            }
            
            if gonggo_no and len(gonggo_no) >= 5:
                all_parking_data.append(parking_info)
                print(f"  🅿️ {gonggo_no}")
        
        except Exception as e:
            print(f"  ⚠️ 데이터 처리 오류: {e}")
            continue
    
    print(f"\n{'='*70}")
    print(f"총 {len(all_parking_data)}개 주차장 발견")
    print(f"{'='*70}")
    
    # 샘플 출력
    if len(all_parking_data) > 0:
        print("\n=== 첫 번째 데이터 ===")
        sample = all_parking_data[0]
        print(f"공고번호: {sample['공고번호']}")
        print(f"물건명: {sample['물건명'][:200]}")
        print(f"전체: {sample['전체데이터']}")
    
    # 슬랙 전송
    if slack_webhook_url and len(all_parking_data) > 0:
        print("\n=== 슬랙 전송 ===")
        
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
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*공고번호*\n`{parking['공고번호']}`"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*물건명*\n{parking['물건명'][:500]}"
                        }
                    },
                    {"type": "divider"}
                ]
            }
            
            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)
        
        print("✓ 슬랙 전송 완료")
    
    elif slack_webhook_url:
        no_result = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')}*\n\n오늘은 주차장 경매가 없습니다."
                    }
                }
            ]
        }
        requests.post(slack_webhook_url, json=no_result)

except Exception as e:
    print(f"\n✗ 오류: {e}")
    import traceback
    traceback.print_exc()
    
    if slack_webhook_url:
        error_blocks = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚠️ *크롤링 오류*\n```{str(e)[:300]}```"
                    }
                }
            ]
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
