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
    page.wait_for_load_state('networkidle')
    time.sleep(5)
    
    if onbid_id and onbid_pw:
        try:
            # 로그인 링크 클릭
            page.click('a:has-text("로그인")', timeout=10000)
            time.sleep(3)
            
            # 아이디 입력
            id_input = page.locator('input[type="text"]').first
            id_input.fill(onbid_id)
            time.sleep(1)
            
            # 비밀번호 입력
            pw_input = page.locator('input[type="password"]').first
            pw_input.fill(onbid_pw)
            time.sleep(1)
            
            # 로그인 버튼
            page.click('button[type="submit"]', timeout=10000)
            time.sleep(5)
            
            print("✓ 로그인 완료")
        except Exception as e:
            print(f"⚠️ 로그인 실패 (계속 진행): {e}")
    
    # 부동산 페이지 이동
    print("\n=== 부동산 페이지 이동 ===")
    page.goto('https://www.onbid.co.kr/op/sb/sbList.do', timeout=60000)
    page.wait_for_load_state('networkidle')
    time.sleep(10)  # 충분한 대기
    print(f"✓ URL: {page.url}")
    
    # 페이지 HTML 확인
    print("\n=== 페이지 요소 확인 ===")
    html = page.content()
    
    # firstCtarId 확인
    if 'firstCtarId' in html:
        print("✓ firstCtarId 발견")
    else:
        print("⚠️ firstCtarId 없음")
    
    # secondCtarId 확인
    if 'secondCtarId' in html:
        print("✓ secondCtarId 발견")
    else:
        print("⚠️ secondCtarId 없음")
    
    # JavaScript로 체크박스 선택
    print("\n=== JavaScript로 필터 설정 ===")
    try:
        # 1. 일대(국내) 선택
        page.evaluate("""
            () => {
                const radio = document.querySelector('input[name="firstCtarId"][value="10100"]');
                if (radio) {
                    radio.checked = true;
                    radio.click();
                }
            }
        """)
        print("✓ 일대(국내) 선택")
        time.sleep(2)
        
        # 2. 주차장 체크
        page.evaluate("""
            () => {
                const checkbox = document.querySelector('input[name="secondCtarId"][value="10116"]');
                if (checkbox) {
                    checkbox.checked = true;
                    checkbox.click();
                }
            }
        """)
        print("✓ 주차장 체크")
        time.sleep(2)
        
        # 3. 입찰기간 설정
        today = datetime.now(KST).strftime('%Y-%m-%d')
        end_date = (datetime.now(KST) + timedelta(days=7)).strftime('%Y-%m-%d')
        
        page.evaluate(f"""
            () => {{
                const fromDtm = document.querySelector('input[name="fromDtm"]');
                const toDtm = document.querySelector('input[name="toDtm"]');
                if (fromDtm) fromDtm.value = '{today}';
                if (toDtm) toDtm.value = '{end_date}';
            }}
        """)
        print(f"✓ 입찰기간: {today} ~ {end_date}")
        time.sleep(2)
        
        # 4. 검색 버튼 클릭
        page.evaluate("""
            () => {
                const buttons = document.querySelectorAll('a, button');
                for (let btn of buttons) {
                    if (btn.textContent.includes('검색')) {
                        btn.click();
                        break;
                    }
                }
            }
        """)
        print("✓ 검색 실행")
        time.sleep(10)
        
    except Exception as e:
        print(f"⚠️ 필터 설정 실패: {e}")
    
    # 결과 크롤링
    print("\n=== 데이터 수집 ===")
    
    # JavaScript로 테이블 데이터 추출
    result = page.evaluate("""
        () => {
            const rows = Array.from(document.querySelectorAll('tbody tr'));
            return rows.map(row => {
                const cells = Array.from(row.querySelectorAll('td'));
                return cells.map(cell => cell.textContent.trim());
            }).filter(row => row.length >= 3);
        }
    """)
    
    print(f"✓ {len(result)}개 행 추출")
    
    for idx, texts in enumerate(result):
        try:
            row_text = ' '.join(texts)
            
            # 주차장 키워드 확인
            if '주차' in row_text or '주차장' in row_text:
                # 제외 키워드
                if any(keyword in row_text for keyword in ['일반공고', '공유재산', '위수탁', '취소공고']):
                    continue
                
                parking_info = {
                    '공고번호': texts[0] if len(texts) > 0 else '',
                    '물건명': texts[1] if len(texts) > 1 else '',
                    '회차/사건': texts[2] if len(texts) > 2 else '',
                    '입찰일시': texts[3] if len(texts) > 3 else '',
                    '감정가정보': texts[4] if len(texts) > 4 else '',
                    '상태': texts[5] if len(texts) > 5 else '',
                }
                
                all_parking_data.append(parking_info)
                print(f"  🅿️ 주차장 발견: {parking_info['공고번호']}")
        
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
                        "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')}*\n\n주차장 *{len(all_parking_data)}개* 발견!"
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
                            "text": f"🅿️ {idx}. 주차장",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*공고번호*\n`{parking['공고번호']}`"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*회차/사건*\n{parking['회차/사건'] or '-'}"
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*물건명*\n{parking['물건명'][:200]}"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*입찰일시*\n{parking['입찰일시'] or '-'}"
                        }
                    },
                    {"type": "divider"}
                ]
            }
            
            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)
        
        print("✓ 슬랙 전송 완료")

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
    # 스크린샷 저장 (디버깅용)
    try:
        page.screenshot(path='onbid_debug.png', full_page=True)
        print("\n✓ 디버깅 스크린샷 저장: onbid_debug.png")
    except:
        pass
    
    browser.close()
    playwright.stop()
    
    print("\n" + "=" * 70)
    print("완료")
    print("=" * 70)
