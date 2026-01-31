import os
import time
import json
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime

slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
onbid_id = os.environ.get('ONBID_ID', '')
onbid_pw = os.environ.get('ONBID_PW', '')

print("=" * 70)
print("온비드 주차장 크롤러 v2.0 (NEW만 + 중복제거 + 다중페이지)")
print("=" * 70)

# 이전 크롤링 데이터 저장용
STORAGE_KEY = 'onbid_parking_history'

def load_previous_gonggo():
    """이전에 크롤링한 공고번호 불러오기"""
    try:
        import window
        result = window.storage.get(STORAGE_KEY, shared=False)
        if result and result.value:
            data = json.loads(result.value)
            print(f"✓ 이전 크롤링 기록: {len(data)}개 공고")
            return set(data)
        return set()
    except:
        # storage API 사용 불가 시 빈 set 반환
        return set()

def save_current_gonggo(gonggo_numbers):
    """현재 크롤링한 공고번호 저장"""
    try:
        import window
        data = json.dumps(list(gonggo_numbers))
        window.storage.set(STORAGE_KEY, data, shared=False)
        print(f"✓ 현재 크롤링 기록 저장: {len(gonggo_numbers)}개")
    except Exception as e:
        print(f"⚠️ 저장 실패 (무시): {e}")

# Playwright 시작
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
page = browser.new_page()

try:
    # 이전 크롤링 기록 불러오기
    previous_gonggo = load_previous_gonggo()
    
    # 로그인
    print("\n=== 로그인 ===")
    page.goto('https://www.onbid.co.kr', timeout=60000)
    page.wait_for_load_state('domcontentloaded')
    time.sleep(3)
    
    if onbid_id and onbid_pw:
        try:
            # 로그인 버튼 클릭
            login_selectors = [
                'a:has-text("로그인")',
                'button:has-text("로그인")',
                'a[href*="login"]',
                '.login'
            ]
            
            login_clicked = False
            for selector in login_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.click(selector, timeout=5000)
                        print(f"✓ 로그인 버튼 클릭: {selector}")
                        login_clicked = True
                        break
                except:
                    continue
            
            if not login_clicked:
                print("⚠️ 로그인 버튼을 찾을 수 없습니다")
            
            time.sleep(3)
            page.wait_for_load_state('domcontentloaded')
            
            # 아이디 입력 (더 유연하게)
            id_filled = False
            id_selectors = [
                'input[name="id"]',
                'input#id',
                'input#userId',
                'input[name="userId"]',
                'input[type="text"]'
            ]
            
            for selector in id_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.fill(selector, onbid_id, timeout=5000)
                        print(f"✓ 아이디 입력: {selector}")
                        id_filled = True
                        break
                except Exception as e:
                    print(f"  {selector} 실패: {e}")
                    continue
            
            # 비밀번호 입력
            pw_filled = False
            pw_selectors = [
                'input[type="password"]',
                'input[name="pw"]',
                'input#pw',
                'input[name="password"]'
            ]
            
            for selector in pw_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.fill(selector, onbid_pw, timeout=5000)
                        print(f"✓ 비밀번호 입력: {selector}")
                        pw_filled = True
                        break
                except Exception as e:
                    print(f"  {selector} 실패: {e}")
                    continue
            
            if not id_filled or not pw_filled:
                print("⚠️ 로그인 정보 입력 실패")
                print("로그인 없이 계속 진행...")
            else:
                time.sleep(1)
                
                # 로그인 제출
                submit_selectors = [
                    'button[type="submit"]',
                    'button:has-text("로그인")',
                    'input[type="submit"]',
                    'a:has-text("로그인")'
                ]
                
                for selector in submit_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.click(selector, timeout=5000)
                            print(f"✓ 로그인 제출: {selector}")
                            break
                    except:
                        continue
                
                time.sleep(5)
                page.wait_for_load_state('domcontentloaded')
                print("✓ 로그인 완료")
        
        except Exception as e:
            print(f"⚠️ 로그인 중 에러 (계속 진행): {e}")
    else:
        print("⚠️ ONBID_ID 또는 ONBID_PW 미설정")
    
    # 부동산 > 공고 페이지로 이동
    print("\n=== 공고 페이지 이동 ===")
    
    try:
        # 부동산 메뉴
        real_estate_selectors = [
            'a:has-text("부동산")',
            'li:has-text("부동산")',
            '[href*="budongsan"]'
        ]
        
        for selector in real_estate_selectors:
            try:
                if page.locator(selector).count() > 0:
                    page.click(selector, timeout=5000)
                    print(f"✓ 부동산 클릭: {selector}")
                    time.sleep(2)
                    break
            except:
                continue
        
        # 공고 메뉴
        gonggo_selectors = [
            'a:has-text("공고")',
            'li:has-text("공고")',
            '[href*="gonggo"]'
        ]
        
        for selector in gonggo_selectors:
            try:
                if page.locator(selector).count() > 0:
                    page.click(selector, timeout=5000)
                    print(f"✓ 공고 클릭: {selector}")
                    time.sleep(3)
                    break
            except:
                continue
        
        print(f"현재 URL: {page.url}")
        
    except Exception as e:
        print(f"⚠️ 메뉴 이동 실패 (계속 진행): {e}")
    
    # 검색창에 주차장 입력
    print("\n=== 주차장 검색 ===")
    
    try:
        search_selectors = [
            'input[name="searchWord"]',
            'input[id="searchWord"]',
            'input[placeholder*="검색"]',
            'input[type="text"]'
        ]
        
        search_found = False
        for selector in search_selectors:
            try:
                if page.locator(selector).count() > 0:
                    page.fill(selector, '주차장', timeout=5000)
                    print(f"✓ 검색어 입력: {selector}")
                    search_found = True
                    break
            except:
                continue
        
        if not search_found:
            print("⚠️ 검색창을 찾을 수 없습니다")
            print("페이지 스크린샷 저장...")
            page.screenshot(path='no_search_box.png', full_page=True)
        
        time.sleep(1)
        
        # 검색 실행
        search_btn_selectors = [
            'button:has-text("검색")',
            'a:has-text("검색")',
            'button.btn-search',
            'input[type="submit"]'
        ]
        
        btn_clicked = False
        for selector in search_btn_selectors:
            try:
                if page.locator(selector).count() > 0:
                    page.click(selector, timeout=5000)
                    print(f"✓ 검색 버튼 클릭: {selector}")
                    btn_clicked = True
                    break
            except:
                continue
        
        if not btn_clicked:
            print("검색 버튼 못 찾아서 Enter")
            page.keyboard.press('Enter')
        
        time.sleep(5)
        page.wait_for_load_state('domcontentloaded')
        print(f"✓ 검색 완료")
        
    except Exception as e:
        print(f"⚠️ 검색 중 에러: {e}")
    
    # 데이터 수집
    all_parking_data = []
    current_gonggo = set()
    
    # 최대 3페이지 크롤링
    for page_num in range(1, 4):
        print(f"\n=== 페이지 {page_num} 크롤링 ===")
        
        time.sleep(2)
        all_tr = page.locator('tr').all()
        print(f"총 {len(all_tr)}개 행 발견")
        
        page_new_count = 0
        
        for idx, row in enumerate(all_tr):
            try:
                cells = row.locator('td').all()
                
                if len(cells) < 5:
                    continue
                
                # 모든 셀 텍스트 추출
                texts = [cell.inner_text().strip() for cell in cells]
                row_text = ' '.join(texts)
                
                # 주차장이면서 NEW 상태만
                if '주차' in row_text and 'NEW' in row_text:
                    # 데이터 파싱
                    parking_info = {
                        '공고번호': texts[0] if len(texts) > 0 else '',
                        '사건번호': texts[1] if len(texts) > 1 else '',
                        '소재지': texts[2] if len(texts) > 2 else '',
                        '토지/대지': texts[3] if len(texts) > 3 else '',
                        '상태': texts[4] if len(texts) > 4 else '',
                        '입찰정보': texts[5] if len(texts) > 5 else '',
                        '입찰기간': texts[6] if len(texts) > 6 else '',
                        '감정가': texts[7] if len(texts) > 7 else '',
                        '추가정보': texts[8:] if len(texts) > 8 else []
                    }
                    
                    gonggo_no = parking_info['공고번호']
                    
                    # 중복 체크
                    if gonggo_no and gonggo_no not in previous_gonggo:
                        all_parking_data.append(parking_info)
                        current_gonggo.add(gonggo_no)
                        page_new_count += 1
                        print(f"  ✓ NEW 주차장 발견: {gonggo_no} - {parking_info['소재지'][:30]}")
                    elif gonggo_no in previous_gonggo:
                        print(f"  - 이미 크롤링됨 (스킵): {gonggo_no}")
                
            except Exception as e:
                continue
        
        print(f"페이지 {page_num}: {page_new_count}개 NEW 주차장 추가")
        
        # 다음 페이지로 이동
        if page_num < 3:
            try:
                next_btn_selectors = [
                    'a.next:not(.disabled)',
                    'a:has-text("다음"):not(.disabled)',
                    'a[title*="다음"]'
                ]
                
                next_found = False
                for selector in next_btn_selectors:
                    try:
                        btn = page.locator(selector).first
                        if btn.is_visible():
                            btn.click()
                            print(f"→ 페이지 {page_num + 1}로 이동...")
                            time.sleep(3)
                            next_found = True
                            break
                    except:
                        continue
                
                if not next_found:
                    print("더 이상 페이지 없음")
                    break
                    
            except:
                break
    
    print(f"\n{'='*70}")
    print(f"총 {len(all_parking_data)}개 NEW 주차장 발견")
    print(f"이전 크롤링: {len(previous_gonggo)}개")
    print(f"{'='*70}")
    
    # 슬랙 전송
    if slack_webhook_url and len(all_parking_data) > 0:
        print("\n=== 슬랙 전송 ===")
        
        # 헤더
        header_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🆕 온비드 NEW 주차장 경매",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📅 *{datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}*\n\n총 *{len(all_parking_data)}개* 새로운 주차장 발견"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"💾 이전 크롤링: {len(previous_gonggo)}개 | 🔍 중복 제거 완료"
                    }
                ]
            },
            {"type": "divider"}
        ]
        
        requests.post(slack_webhook_url, json={"blocks": header_blocks})
        time.sleep(1)
        
        # 각 주차장 정보 전송
        for idx, parking in enumerate(all_parking_data, 1):
            # 입찰기간 파싱
            bidding_period = parking['입찰기간'].replace('~', ' → ')
            
            # 추가정보 처리
            extra_info = ''
            if parking['추가정보']:
                extra_info = ' | '.join(parking['추가정보'])
            
            blocks = [
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
                            "text": f"*⚖️ 사건번호*\n{parking['사건번호']}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📍 소재지*\n{parking['소재지']}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*📏 토지/대지*\n{parking['토지/대지']}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*🏷️ 상태*\n`NEW`"
                        }
                    ]
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*💰 감정가*\n{parking['감정가']}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*📝 입찰정보*\n{parking['입찰정보']}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📅 입찰기간*\n{bidding_period}"
                    }
                }
            ]
            
            # 추가정보가 있으면 표시
            if extra_info:
                blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"ℹ️ {extra_info}"
                        }
                    ]
                })
            
            blocks.append({"type": "divider"})
            
            requests.post(slack_webhook_url, json={"blocks": blocks})
            time.sleep(1)
            print(f"  ✓ {idx}/{len(all_parking_data)} 전송 완료")
        
        print("✓ 슬랙 전송 완료")
    
    elif slack_webhook_url and len(all_parking_data) == 0:
        # NEW 주차장이 없을 때
        no_new_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📅 *{datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}*\n\n새로운 주차장이 없습니다. ✅"
                }
            }
        ]
        requests.post(slack_webhook_url, json={"blocks": no_new_blocks})
        print("✓ 결과 없음 알림 전송")
    
    # 현재 공고번호 저장 (이전 + 현재)
    all_gonggo = previous_gonggo.union(current_gonggo)
    save_current_gonggo(all_gonggo)

except Exception as e:
    print(f"\n✗ 오류: {e}")
    import traceback
    traceback.print_exc()
    
    if slack_webhook_url:
        error_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ *크롤링 오류 발생*\n```{str(e)[:500]}```"
                }
            }
        ]
        requests.post(slack_webhook_url, json={"blocks": error_blocks})

finally:
    browser.close()
    playwright.stop()
    
    print("\n" + "=" * 70)
    print("완료")
    print("=" * 70)
