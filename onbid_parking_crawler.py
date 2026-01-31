import os
import time
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone

# 한국 시간
KST = timezone(timedelta(hours=9))

slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
onbid_id = os.environ.get('ONBID_ID', '')
onbid_pw = os.environ.get('ONBID_PW', '')

print("=" * 70)
print(f"온비드 주차장 크롤러 (검증 모드)")
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
    page.wait_for_load_state('domcontentloaded')
    time.sleep(3)
    
    if onbid_id and onbid_pw:
        try:
            # 로그인 버튼
            if page.locator('a:has-text("로그인")').count() > 0:
                page.click('a:has-text("로그인")', timeout=5000)
                time.sleep(3)
            
            # 아이디 입력
            if page.locator('input[type="text"]').count() > 0:
                page.fill('input[type="text"]', onbid_id, timeout=5000)
            
            # 비밀번호 입력
            if page.locator('input[type="password"]').count() > 0:
                page.fill('input[type="password"]', onbid_pw, timeout=5000)
            
            # 로그인 제출
            if page.locator('button[type="submit"]').count() > 0:
                page.click('button[type="submit"]', timeout=5000)
            
            time.sleep(5)
            print("✓ 로그인 완료")
        except Exception as e:
            print(f"⚠️ 로그인 실패 (계속 진행): {e}")
    
    # 부동산 > 공고
    print("\n=== 공고 페이지 이동 ===")
    try:
        if page.locator('a:has-text("부동산")').count() > 0:
            page.click('a:has-text("부동산")', timeout=5000)
            time.sleep(2)
        
        if page.locator('a:has-text("공고")').count() > 0:
            page.click('a:has-text("공고")', timeout=5000)
            time.sleep(3)
        
        print(f"✓ 현재 URL: {page.url}")
    except Exception as e:
        print(f"⚠️ 메뉴 이동 실패: {e}")
    
    # 검색
    print("\n=== 주차장 검색 ===")
    try:
        if page.locator('input[placeholder*="검색"]').count() > 0:
            page.fill('input[placeholder*="검색"]', '주차장', timeout=5000)
            print("✓ 검색어 입력")
        
        if page.locator('a:has-text("검색")').count() > 0:
            page.click('a:has-text("검색")', timeout=5000)
            print("✓ 검색 실행")
        
        time.sleep(5)
    except Exception as e:
        print(f"⚠️ 검색 실패: {e}")
    
    # 크롤링
    print("\n=== 데이터 수집 ===")
    all_tr = page.locator('tr').all()
    print(f"총 {len(all_tr)}개 행 발견")
    
    found_count = 0
    
    for idx, row in enumerate(all_tr):
        try:
            cells = row.locator('td').all()
            
            if len(cells) < 3:
                continue
            
            # 모든 셀 텍스트 추출
            texts = []
            for cell in cells:
                try:
                    text = cell.inner_text().strip()
                    texts.append(text)
                except:
                    texts.append('')
            
            row_text = ' '.join(texts)
            
            # 주차장 키워드 확인
            if '주차' in row_text or '주차장' in row_text:
                print(f"\n★ 행 {idx+1}: 주차장 발견!")
                
                # 첫 번째 셀에서 정보 추출
                mulgun_info = texts[0] if len(texts) > 0 else ''
                lines = mulgun_info.split('\n')
                
                gonggo_no = lines[0] if len(lines) > 0 else ''
                mulgun_name = '\n'.join(lines[1:]) if len(lines) > 1 else ''
                
                print(f"   공고번호: {gonggo_no}")
                print(f"   물건명: {mulgun_name[:60]}")
                
                parking_info = {
                    '공고번호': gonggo_no,
                    '물건명': mulgun_name,
                    '회차/사건': texts[1] if len(texts) > 1 else '',
                    '입찰일시': texts[2] if len(texts) > 2 else '',
                    '감정가정보': texts[3] if len(texts) > 3 else '',
                    '상태': texts[4] if len(texts) > 4 else '',
                }
                
                if gonggo_no:
                    all_parking_data.append(parking_info)
                    found_count += 1
                    print(f"   ✓ 수집 완료 ({found_count}개)")
        
        except Exception as e:
            continue
    
    print(f"\n{'='*70}")
    print(f"총 {len(all_parking_data)}개 주차장 수집 완료")
    print(f"{'='*70}")
    
    # 슬랙 전송
    if slack_webhook_url and len(all_parking_data) > 0:
        print("\n=== 슬랙 전송 ===")
        
        # 헤더
        header = {
            "blocks": [
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
                        "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')} (KST)*\n\n총 *{len(all_parking_data)}개* 주차장 발견"
                    }
                },
                {"type": "divider"}
            ]
        }
        
        requests.post(slack_webhook_url, json=header)
        time.sleep(1)
        
        # 각 주차장 정보
        for idx, parking in enumerate(all_parking_data[:20], 1):
            # 물건명에서 위치 정보 추출
            mulgun_lines = parking['물건명'].split('\n')
            location = mulgun_lines[0] if len(mulgun_lines) > 0 else parking['물건명']
            area_info = ''
            
            for line in mulgun_lines:
                if '㎡' in line or '토지' in line:
                    area_info = line
                    break
            
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
                                "text": f"*📋 공고번호*\n`{parking['공고번호']}`"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*⚖️ 회차/사건*\n{parking['회차/사건']}"
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*📍 소재지*\n{location[:200]}"
                        }
                    }
                ]
            }
            
            # 면적 정보
            if area_info:
                blocks["blocks"].append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📏 면적*\n{area_info}"
                    }
                })
            
            # 입찰일시
            if parking['입찰일시']:
                blocks["blocks"].append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📅 입찰일시*\n{parking['입찰일시']}"
                    }
                })
            
            # 감정가와 상태
            blocks["blocks"].append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*💰 감정가*\n{parking['감정가정보']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*🏷️ 상태*\n{parking['상태']}"
                    }
                ]
            })
            
            blocks["blocks"].append({"type": "divider"})
            
            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)
            print(f"  ✓ {idx}/{len(all_parking_data)} 전송 완료")
        
        print("✓ 슬랙 전송 완료")
    
    elif slack_webhook_url:
        no_result = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')} (KST)*\n\n검색된 주차장이 없습니다."
                    }
                }
            ]
        }
        requests.post(slack_webhook_url, json=no_result)

except Exception as e:
    print(f"\n✗ 오류: {e}")
    import traceback
    traceback.print_exc()

finally:
    browser.close()
    playwright.stop()
    
    print("\n" + "=" * 70)
    print("완료")
    print("=" * 70)
