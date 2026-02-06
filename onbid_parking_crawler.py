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
            page.click('a:has-text("로그인")', timeout=10000)
            time.sleep(3)
            
            page.fill('input[type="text"]', onbid_id, timeout=10000)
            time.sleep(1)
            
            page.fill('input[type="password"]', onbid_pw, timeout=10000)
            time.sleep(1)
            
            page.click('button[type="submit"]', timeout=10000)
            time.sleep(5)
            
            print("✓ 로그인 완료")
        except Exception as e:
            print(f"⚠️ 로그인 실패 (계속 진행): {e}")
    
    # 통합검색으로 주차장 검색
    print("\n=== 통합검색: 주차장 ===")
    page.goto('https://www.onbid.co.kr', timeout=60000)
    time.sleep(3)
    
    # 검색창에 주차장 입력
    search_input = page.locator('input[placeholder*="검색"], input[type="text"]').first
    search_input.fill('주차장')
    print("✓ 검색어 입력: 주차장")
    time.sleep(1)
    
    # 검색 버튼 클릭 (엔터 또는 버튼)
    try:
        search_input.press('Enter')
        print("✓ 검색 실행")
    except:
        page.click('button:has-text("검색"), a:has-text("검색")')
        print("✓ 검색 버튼 클릭")
    
    time.sleep(5)
    
    # 통합검색 탭 클릭
    print("\n=== 통합검색 탭으로 이동 ===")
    try:
        if page.locator('a:has-text("통합검색"), button:has-text("통합검색")').count() > 0:
            page.click('a:has-text("통합검색"), button:has-text("통합검색")')
            time.sleep(3)
            print("✓ 통합검색 탭 클릭")
    except:
        print("⚠️ 이미 통합검색 결과 페이지")
    
    print(f"✓ 현재 URL: {page.url}")
    
    # 입찰물건 탭 클릭
    print("\n=== 입찰물건 탭 클릭 ===")
    try:
        page.click('a:has-text("입찰물건"), button:has-text("입찰물건")', timeout=10000)
        time.sleep(5)
        print("✓ 입찰물건 탭으로 이동")
    except Exception as e:
        print(f"⚠️ 입찰물건 탭 클릭 실패: {e}")
    
    # 결과 크롤링
    print("\n=== 데이터 수집 ===")
    
    # 모든 테이블 행 추출
    rows = page.locator('tr').all()
    print(f"✓ {len(rows)}개 행 발견")
    
    for idx, row in enumerate(rows):
        try:
            # 모든 셀 추출
            cells = row.locator('td').all()
            if len(cells) < 3:
                continue
            
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
                # 제외 키워드
                if any(kw in row_text for kw in ['일반공고', '공유재산', '위수탁', '취소공고']):
                    continue
                
                # 공고번호 추출 (첫 번째 셀)
                gonggo_no = texts[0].split('\n')[0] if texts[0] else ''
                
                # 물건명 추출
                mulgun_info = texts[0] if texts[0] else ''
                
                parking_info = {
                    '공고번호': gonggo_no,
                    '물건정보': mulgun_info,
                    '회차_사건': texts[1] if len(texts) > 1 else '',
                    '입찰일시': texts[2] if len(texts) > 2 else '',
                    '감정가': texts[3] if len(texts) > 3 else '',
                    '상태': texts[4] if len(texts) > 4 else '',
                }
                
                # 공고번호가 있는 것만 저장
                if gonggo_no and len(gonggo_no) > 5:
                    all_parking_data.append(parking_info)
                    print(f"  🅿️ 주차장 발견: {gonggo_no}")
        
        except Exception as e:
            continue
    
    print(f"\n{'='*70}")
    print(f"총 {len(all_parking_data)}개 주차장 발견")
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
        
        # 각 주차장 정보
        for idx, parking in enumerate(all_parking_data[:20], 1):
            # 물건정보에서 위치와 면적 추출
            lines = parking['물건정보'].split('\n')
            location = lines[1] if len(lines) > 1 else ''
            area = ''
            for line in lines:
                if '㎡' in line or 'm²' in line:
                    area = line
                    break
            
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
                            {
                                "type": "mrkdwn",
                                "text": f"*📋 공고번호*\n`{parking['공고번호']}`"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*⚖️ 회차/사건*\n{parking['회차_사건'] or '-'}"
                            }
                        ]
                    }
                ]
            }
            
            # 위치 정보
            if location:
                blocks["blocks"].append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📍 소재지*\n{location[:200]}"
                    }
                })
            
            # 면적 정보
            if area:
                blocks["blocks"].append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📏 면적*\n{area}"
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
                        "text": f"*💰 감정가*\n{parking['감정가'] or '-'}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*🏷️ 상태*\n{parking['상태'] or '-'}"
                    }
                ]
            })
            
            blocks["blocks"].append({"type": "divider"})
            
            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)
            print(f"  ✓ {idx}/{len(all_parking_data)} 전송 완료")
        
        print("✓ 슬랙 전송 완료")
    
    elif slack_webhook_url:
        print("\n=== 주차장 없음 ===")
        no_result = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')} (KST)*\n\n오늘은 주차장 경매 공고가 없습니다. ✅"
                    }
                }
            ]
        }
        requests.post(slack_webhook_url, json=no_result)
        print("✓ 알림 전송")

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
                        "text": f"⚠️ *온비드 크롤링 오류*\n```{str(e)[:300]}```"
                    }
                }
            ]
        }
        requests.post(slack_webhook_url, json=error_blocks)

finally:
    browser.close()
    playwright.stop()
    
    print("\n" + "=" * 70)
    print("완료")
    print("=" * 70)
