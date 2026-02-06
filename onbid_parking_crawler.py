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
    time.sleep(3)
    
    if onbid_id and onbid_pw:
        try:
            if page.locator('a:has-text("로그인")').count() > 0:
                page.click('a:has-text("로그인")')
                time.sleep(3)
            
            page.fill('input[type="text"]', onbid_id)
            time.sleep(1)
            
            page.fill('input[type="password"]', onbid_pw)
            time.sleep(1)
            
            page.click('button[type="submit"]')
            time.sleep(5)
            
            print("✓ 로그인 완료")
        except Exception as e:
            print(f"⚠️ 로그인 실패: {e}")
    
    # 부동산 페이지 이동
    print("\n=== 부동산 페이지 이동 ===")
    page.goto('https://www.onbid.co.kr/op/sb/sbList.do', timeout=60000)
    time.sleep(5)
    print(f"✓ URL: {page.url}")
    
    # 검색 필터 설정
    print("\n=== 검색 필터 설정 ===")
    try:
        # 1. 일대(국내) 라디오 버튼 (value="10100")
        page.check('input[name="firstCtarId"][value="10100"]')
        print("✓ 일대(국내) 선택")
        time.sleep(1)
        
        # 2. 입찰기간 설정
        today = datetime.now(KST)
        end_date = today + timedelta(days=7)
        
        # 시작일 (name 확인 필요)
        if page.locator('input[name="fromDtm"]').count() > 0:
            page.fill('input[name="fromDtm"]', today.strftime('%Y-%m-%d'))
            print(f"✓ 시작일: {today.strftime('%Y-%m-%d')}")
        
        # 종료일
        if page.locator('input[name="toDtm"]').count() > 0:
            page.fill('input[name="toDtm"]', end_date.strftime('%Y-%m-%d'))
            print(f"✓ 종료일: {end_date.strftime('%Y-%m-%d')}")
        
        time.sleep(1)
        
        # 3. 주차장 체크박스 (value="10116")
        page.check('input[name="secondCtarId"][value="10116"]')
        print("✓ 주차장 선택")
        time.sleep(1)
        
        # 4. 검색 버튼 클릭
        # 검색 버튼 찾기 (여러 방법 시도)
        search_selectors = [
            'a:has-text("검색")',
            'button:has-text("검색")',
            'input[type="submit"][value*="검색"]',
            'a.btn_search'
        ]
        
        clicked = False
        for selector in search_selectors:
            if page.locator(selector).count() > 0:
                page.click(selector)
                clicked = True
                print("✓ 검색 버튼 클릭")
                break
        
        if not clicked:
            print("⚠️ 검색 버튼을 찾을 수 없음")
        
        time.sleep(5)
        
    except Exception as e:
        print(f"⚠️ 필터 설정 실패: {e}")
        import traceback
        traceback.print_exc()
    
    # 결과 크롤링
    print("\n=== 데이터 수집 ===")
    
    # 테이블 찾기
    table_selectors = [
        'table.tbl_list tbody tr',
        'div.list_area tbody tr',
        'table tbody tr'
    ]
    
    all_tr = []
    for selector in table_selectors:
        all_tr = page.locator(selector).all()
        if len(all_tr) > 0:
            print(f"✓ '{selector}'로 {len(all_tr)}개 행 발견")
            break
    
    if len(all_tr) == 0:
        print("⚠️ 결과 테이블을 찾을 수 없음")
    
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
                
                # 정부재산공개/일반공고 제외
                if any(keyword in row_text for keyword in ['일반공고', '공유재산', '위수탁', '취소공고', '매각제한재산']):
                    print(f"  ⏭️  행 {idx+1}: 제외")
                    continue
                
                # 데이터 추출
                if len(lines) > 3:
                    gonggo_no = lines[0]
                    mulgun_name = '\n'.join(lines[1:])
                else:
                    gonggo_no = texts[0]
                    mulgun_name = texts[1] if len(texts) > 1 else ''
                
                parking_info = {
                    '공고번호': gonggo_no,
                    '물건명': mulgun_name,
                    '회차/사건': texts[1] if len(texts) > 1 else '',
                    '입찰일시': texts[2] if len(texts) > 2 else '',
                    '감정가정보': texts[3] if len(texts) > 3 else '',
                    '상태': texts[4] if len(texts) > 4 else '',
                }
                
                # 중복 체크
                if gonggo_no:
                    current_gonggo.add(gonggo_no)
                    
                    if gonggo_no not in previous_gonggo:
                        all_parking_data.append(parking_info)
                        new_count += 1
                        print(f"  🆕 새로운 주차장: {gonggo_no}")
                    else:
                        duplicate_count += 1
        
        except Exception as e:
            continue
    
    print(f"\n{'='*70}")
    print(f"총 {len(current_gonggo)}개 주차장 발견")
    print(f"  - 새로운 공고: {new_count}개 🆕")
    print(f"  - 이미 알림: {duplicate_count}개 ⏭️")
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
                {"type": "divider"}
            ]
        }
        
        requests.post(slack_webhook_url, json=header)
        time.sleep(1)
        
        # 각 주차장 정보
        for idx, parking in enumerate(all_parking_data[:20], 1):
            mulgun_lines = parking['물건명'].split('\n')
            location = mulgun_lines[0] if len(mulgun_lines) > 0 else parking['물건명']
            
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
                                "text": f"*⚖️ 회차/사건*\n{parking['회차/사건'] or '-'}"
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*📍 소재지*\n{location[:200]}"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*📅 입찰일시*\n{parking['입찰일시'] or '-'}"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*💰 감정가*\n{parking['감정가정보'] or '-'}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*🏷️ 상태*\n{parking['상태'] or '-'}"
                            }
                        ]
                    },
                    {"type": "divider"}
                ]
            }
            
            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)
            print(f"  ✓ {idx}/{len(all_parking_data)} 전송 완료")
        
        print("✓ 슬랙 전송 완료")
        
        # 알림 기록 저장
        updated_gonggo = previous_gonggo.union(current_gonggo)
        save_current_gonggo(updated_gonggo)
    
    elif slack_webhook_url and len(all_parking_data) == 0:
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
        print("✓ 알림 전송")
        
        updated_gonggo = previous_gonggo.union(current_gonggo)
        save_current_gonggo(updated_gonggo)

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
