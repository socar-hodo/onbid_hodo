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

# 저장 키
STORAGE_KEY = 'onbid_parking_history'

def load_previous_gonggo():
    """이전에 알림 보낸 공고번호 불러오기"""
    try:
        import window
        result = window.storage.get(STORAGE_KEY, shared=False)
        if result and result.get('value'):
            data = json.loads(result['value'])
            print(f"✓ 이전 알림 기록: {len(data)}개 공고")
            return set(data)
        return set()
    except:
        print("⚠️ 저장소 접근 불가 (첫 실행 또는 미지원)")
        return set()

def save_current_gonggo(gonggo_set):
    """현재 공고번호 저장"""
    try:
        import window
        data = json.dumps(list(gonggo_set))
        window.storage.set(STORAGE_KEY, data, shared=False)
        print(f"✓ 알림 기록 저장: {len(gonggo_set)}개")
    except Exception as e:
        print(f"⚠️ 저장 실패: {e}")

print("=" * 70)
print(f"온비드 주차장 경매 알리미")
print(f"실행 시간(KST): {datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M:%S')}")
print("=" * 70)

# 이전 알림 기록 불러오기
previous_gonggo = load_previous_gonggo()

# Playwright 시작
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
page = browser.new_page()

all_parking_data = []
current_gonggo = set()

try:
    # 로그인
    print("\n=== 로그인 ===")
    page.goto('https://www.onbid.co.kr', timeout=60000)
    page.wait_for_load_state('domcontentloaded')
    time.sleep(3)
    
    if onbid_id and onbid_pw:
        try:
            if page.locator('a:has-text("로그인")').count() > 0:
                page.click('a:has-text("로그인")', timeout=5000)
                time.sleep(3)
            
            if page.locator('input[type="text"]').count() > 0:
                page.fill('input[type="text"]', onbid_id, timeout=5000)
            
            if page.locator('input[type="password"]').count() > 0:
                page.fill('input[type="password"]', onbid_pw, timeout=5000)
            
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
    
    new_count = 0
    duplicate_count = 0
    
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
                # 첫 번째 셀 분석
                first_cell = texts[0] if len(texts) > 0 else ''
                lines = first_cell.split('\n')
                
                # 데이터 형식 구분
                is_long_format = len(lines) > 3
                
                # 정부재산공개/일반공고 제외 필터
                is_government_property = (
                    
                    '공유재산' in row_text or 
                   
                    '취소공고' in row_text or
                    '매각제한재산' in row_text
                )
                
                if is_government_property:
                    print(f"  ⏭️  행 {idx+1}: 정부재산공개 제외")
                    continue
                
                if is_long_format:
                    # 일반 경매만
                    gonggo_no = lines[0] if len(lines) > 0 else ''
                    mulgun_name = '\n'.join(lines[1:]) if len(lines) > 1 else ''
                    
                    parking_info = {
                        '공고번호': gonggo_no,
                        '물건명': mulgun_name,
                        '회차/사건': texts[1] if len(texts) > 1 else '',
                        '입찰일시': texts[2] if len(texts) > 2 else '',
                        '감정가정보': texts[3] if len(texts) > 3 else '',
                        '상태': texts[4] if len(texts) > 4 else '',
                    }
                else:
                    # 일반공고 형식은 이미 위에서 필터링됨
                    continue
                
                # 중복 체크
                if gonggo_no:
                    current_gonggo.add(gonggo_no)
                    
                    if gonggo_no not in previous_gonggo:
                        all_parking_data.append(parking_info)
                        new_count += 1
                        print(f"  🆕 새로운 주차장 경매: {gonggo_no}")
                    else:
                        duplicate_count += 1
                        print(f"  ⏭️  이미 알림: {gonggo_no}")
        
        except Exception as e:
            continue
    
    print(f"\n{'='*70}")
    print(f"총 {len(current_gonggo)}개 주차장 발견")
    print(f"  - 새로운 공고: {new_count}개 🆕")
    print(f"  - 이미 알림: {duplicate_count}개 ⏭️")
    print(f"{'='*70}")
    
    # 슬랙 전송 (새로운 것만)
    if slack_webhook_url and len(all_parking_data) > 0:
        print("\n=== 슬랙 전송 (새로운 공고만) ===")
        
        # 헤더
        header = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🆕 온비드 새로운 주차장 경매",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')} (KST)*\n\n오늘 새로 등록된 주차장 *{len(all_parking_data)}개* 발견!"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"💾 전체 {len(current_gonggo)}개 중 새로운 공고 {len(all_parking_data)}개"
                        }
                    ]
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
                                "text": f"*⚖️ 회차/사건*\n{parking['회차/사건'] if parking['회차/사건'] else '-'}"
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
                        "text": f"*💰 감정가*\n{parking['감정가정보'] if parking['감정가정보'] else '-'}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*🏷️ 상태*\n{parking['상태'] if parking['상태'] else '-'}"
                    }
                ]
            })
            
            blocks["blocks"].append({"type": "divider"})
            
            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)
            print(f"  ✓ {idx}/{len(all_parking_data)} 전송 완료")
        
        print("✓ 슬랙 전송 완료")
        
        # 알림 기록 저장 (이전 + 현재)
        updated_gonggo = previous_gonggo.union(current_gonggo)
        save_current_gonggo(updated_gonggo)
    
    elif slack_webhook_url and len(all_parking_data) == 0:
        # 새로운 공고가 없을 때
        print("\n=== 새로운 공고 없음 ===")
        no_result = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')} (KST)*\n\n오늘은 새로운 주차장 경매 공고가 없습니다. ✅"
                    }
                }
            ]
        }
        requests.post(slack_webhook_url, json=no_result)
        print("✓ 알림 전송 (새 공고 없음)")
        
        # 기록은 업데이트
        updated_gonggo = previous_gonggo.union(current_gonggo)
        save_current_gonggo(updated_gonggo)

except Exception as e:
    print(f"\n✗ 오류: {e}")
    import traceback
    traceback.print_exc()
    
    # 에러 알림
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
