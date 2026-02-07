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
print(f"온비드 주차장 물건 알리미")
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
    
    # 3. 담보물 부동산 페이지로 직접 이동
    print("\n=== 3. 담보물 > 부동산 물건 페이지 직접 이동 ===")
    
    target_url = 'https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do'
    print(f"목표 URL: {target_url}")
    
    page.goto(target_url, timeout=60000)
    print("페이지 로딩 대기 중...")
    time.sleep(10)
    
    try:
        page.wait_for_load_state('domcontentloaded', timeout=30000)
        print("✓ DOM 로딩 완료")
    except:
        print("⚠️ DOM 로딩 타임아웃")
    
    time.sleep(5)
    
    try:
        page.wait_for_load_state('networkidle', timeout=30000)
        print("✓ 네트워크 로딩 완료")
    except:
        print("⚠️ 네트워크 타임아웃 (계속 진행)")
    
    print(f"✓ 현재 URL: {page.url}")
    
    # 4. 물건명 검색창에 주차장 입력
    print("\n=== 4. 물건명 검색: 주차장 ===")
    
    search_result = page.evaluate("""() => {
        const searchInput = document.getElementById('searchCltrNm');
        
        if (!searchInput) {
            return { success: false, error: 'searchCltrNm not found' };
        }
        
        searchInput.value = '주차장';
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
        searchInput.dispatchEvent(new Event('change', { bubbles: true }));
        
        let searchBtn = document.getElementById('searchBtn');
        
        if (!searchBtn) {
            const buttons = document.querySelectorAll('button, input[type="button"], input[type="submit"]');
            for (let btn of buttons) {
                const text = (btn.innerText || btn.value || '').trim();
                const btnId = btn.id || '';
                
                if (text.includes('검색') || text.includes('조회') || btnId.toLowerCase().includes('search')) {
                    searchBtn = btn;
                    break;
                }
            }
        }
        
        if (searchBtn) {
            searchBtn.click();
            return { success: true, method: 'button click' };
        }
        
        return { success: false, error: 'no search button' };
    }""")
    
    print(f"검색 실행 결과: {json.dumps(search_result, ensure_ascii=False)}")
    
    if search_result.get('success'):
        print(f"✓ 검색 방법: {search_result.get('method')}")
        time.sleep(12)
        
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
            print("✓ 검색 결과 로딩 완료")
        except:
            print("⚠️ 로딩 타임아웃")
    
    # 5. JavaScript 함수 확인 (디버깅)
    print("\n=== 5. JavaScript 함수 확인 (디버깅) ===")
    
    # fn_movePublicAnnounce 함수 정의 확인
    func_definition = page.evaluate("""() => {
        if (typeof fn_movePublicAnnounce === 'function') {
            return fn_movePublicAnnounce.toString();
        }
        return null;
    }""")
    
    if func_definition:
        print(f"fn_movePublicAnnounce 함수 정의:")
        print(func_definition[:500])  # 처음 500자만 출력
    else:
        print("⚠️ fn_movePublicAnnounce 함수를 찾을 수 없음")
    
    # 공고등록 버튼 정보 수집
    announce_buttons = page.evaluate("""() => {
        const buttons = document.querySelectorAll('a[onclick*="fn_movePublicAnnounce"]');
        const results = [];
        
        for (let i = 0; i < Math.min(3, buttons.length); i++) {
            const btn = buttons[i];
            results.push({
                onclick: btn.getAttribute('onclick'),
                href: btn.getAttribute('href'),
                title: btn.getAttribute('title'),
                text: btn.innerText
            });
        }
        
        return results;
    }""")
    
    print(f"\n공고등록 버튼 정보 ({len(announce_buttons)}개 샘플):")
    for idx, btn_info in enumerate(announce_buttons):
        print(f"\n[버튼 {idx+1}]")
        print(f"  onclick: {btn_info.get('onclick')}")
        print(f"  href: {btn_info.get('href')}")
        print(f"  title: {btn_info.get('title')}")
        print(f"  text: {btn_info.get('text')}")
    
    # 첫 번째 공고등록 버튼 클릭 테스트
    if len(announce_buttons) > 0:
        print("\n=== 6. 첫 번째 공고등록 버튼 클릭 테스트 ===")
        
        original_url = page.url
        print(f"클릭 전 URL: {original_url}")
        
        # 버튼 클릭
        page.evaluate("""() => {
            const btn = document.querySelector('a[onclick*="fn_movePublicAnnounce"]');
            if (btn) {
                btn.click();
            }
        }""")
        
        # URL 변화 대기
        print("URL 변화 대기 중...")
        time.sleep(5)
        
        # 새 페이지나 팝업 확인
        all_pages = browser.contexts[0].pages
        print(f"\n열린 페이지 수: {len(all_pages)}")
        
        for page_idx, p in enumerate(all_pages):
            print(f"  페이지 {page_idx}: {p.url}")
        
        # 새 페이지가 열렸다면
        if len(all_pages) > 1:
            announce_page = all_pages[-1]
            announce_url = announce_page.url
            announce_title = announce_page.evaluate("() => document.title")
            
            print(f"\n✓ 공고 페이지 발견!")
            print(f"  URL: {announce_url}")
            print(f"  제목: {announce_title}")
            
            # URL 패턴 분석
            if '?' in announce_url:
                base_url = announce_url.split('?')[0]
                params = announce_url.split('?')[1]
                print(f"  베이스 URL: {base_url}")
                print(f"  파라미터: {params}")
            
            # 스크린샷
            try:
                announce_page.screenshot(path='onbid_announce.png', full_page=True)
                print("  스크린샷: onbid_announce.png")
            except:
                pass
            
            announce_page.close()
        else:
            final_url = page.url
            print(f"\n같은 페이지에서 전환: {final_url}")
            
            if final_url != original_url:
                print("✓ URL 변경됨")
                
                # URL 패턴 분석
                if '?' in final_url:
                    base_url = final_url.split('?')[0]
                    params = final_url.split('?')[1]
                    print(f"  베이스 URL: {base_url}")
                    print(f"  파라미터: {params}")
    
    # 7. 목록으로 돌아가서 데이터 크롤링
    print("\n=== 7. 목록으로 돌아가서 주차장 데이터 크롤링 ===")
    
    # 목록 페이지로 돌아가기
    page.goto(target_url, timeout=60000)
    time.sleep(3)
    
    # 다시 검색
    page.evaluate("""() => {
        const searchInput = document.getElementById('searchCltrNm');
        if (searchInput) {
            searchInput.value = '주차장';
            const searchBtn = document.getElementById('searchBtn');
            if (searchBtn) {
                searchBtn.click();
            }
        }
    }""")
    time.sleep(8)
    
    # 주차장 데이터 크롤링 (공고등록 버튼 파라미터 포함)
    table_data = page.evaluate("""() => {
        const results = [];
        const tables = document.querySelectorAll('table');
        
        tables.forEach((table, tableIdx) => {
            const rows = table.querySelectorAll('tbody tr, tr');
            
            rows.forEach((row, rowIdx) => {
                const cells = Array.from(row.querySelectorAll('td, th'));
                if (cells.length >= 3) {
                    const texts = cells.map(cell => cell.innerText.trim());
                    const rowText = texts.join(' ');
                    
                    if (rowText.includes('주차') || rowText.includes('주차장')) {
                        // 상세이동 버튼의 title에서 공고번호
                        let detailBtn = row.querySelector('a.cm_btn_sint3[title], a[title*="-"]');
                        let gonggoNo = '';
                        
                        if (detailBtn) {
                            gonggoNo = detailBtn.getAttribute('title') || '';
                        }
                        
                        // 공고등록 버튼에서 파라미터 추출
                        let announceBtn = row.querySelector('a[onclick*="fn_movePublicAnnounce"]');
                        let announceParams = null;
                        
                        if (announceBtn) {
                            const onclick = announceBtn.getAttribute('onclick') || '';
                            const match = onclick.match(/fn_movePublicAnnounce\\(['"](\\d+)['"]\\s*,\\s*['"](\\d+)['"]\\)/);
                            if (match) {
                                announceParams = {
                                    param1: match[1],
                                    param2: match[2]
                                };
                            }
                        }
                        
                        let imgSrc = '';
                        const imgElem = row.querySelector('img');
                        if (imgElem) {
                            imgSrc = imgElem.src;
                        }
                        
                        results.push({
                            texts: texts,
                            imgSrc: imgSrc,
                            rowText: rowText,
                            gonggoNoFromBtn: gonggoNo,
                            announceParams: announceParams
                        });
                    }
                }
            });
        });
        
        return results;
    }""")
    
    print(f"✓ {len(table_data)}개 주차장 항목 발견")
    
    # 데이터 정리
    for idx, item in enumerate(table_data):
        try:
            texts = item['texts']
            row_text = item['rowText']
            
            # 제외 키워드
            if any(kw in row_text for kw in ['일반공고', '공유재산', '위수탁', '취소공고']):
                continue
            
            # 공고번호
            gonggo_no = item.get('gonggoNoFromBtn', '')
            
            if not gonggo_no:
                for text in texts:
                    for line in text.split('\n'):
                        if '-' in line and sum(c.isdigit() for c in line) >= 8:
                            gonggo_no = line.strip()
                            break
                    if gonggo_no:
                        break
            
            # 주소/물건명 추출
            address = ''
            for text in texts:
                if ('주차' in text or '주차장' in text) and len(text) > 10:
                    lines = text.split('\n')
                    for line in lines:
                        if ('주차' in line or '도' in line or '시' in line or '구' in line) and len(line) > 5:
                            address = line.strip()
                            break
                    if not address:
                        address = text.strip()
                    break
            
            if not address:
                for text in texts:
                    if '주차' in text:
                        address = text.strip()
                        break
            
            if not address:
                address = row_text[:200].strip()
            
            # 면적 정보
            area = ''
            for text in texts:
                if '㎡' in text or 'm²' in text:
                    for line in text.split('\n'):
                        if '㎡' in line or 'm²' in line:
                            area = line.strip()
                            break
                if area:
                    break
            
            # 공고 URL 생성 (추측 - 디버깅 결과에 따라 수정 필요)
            announce_url = ''
            announce_params = item.get('announceParams')
            if announce_params:
                # 여러 가능한 URL 패턴 시도
                announce_url = f"https://www.onbid.co.kr/op/cta/pbancmn/viewPublicAnnounce.do?pblancSeq={announce_params['param1']}&pblancNo={announce_params['param2']}"
            
            parking_info = {
                '공고번호': gonggo_no or '번호미확인',
                '물건명주소': address,
                '면적': area,
                '입찰기간': texts[1] if len(texts) > 1 and texts[1] != address else '',
                '최저입찰가': texts[2] if len(texts) > 2 else '',
                '물건상태': texts[3] if len(texts) > 3 else '',
                '조회수': texts[4] if len(texts) > 4 else '',
                '공고링크': announce_url,
                '이미지': item['imgSrc']
            }
            
            all_parking_data.append(parking_info)
            print(f"  ✓ 추가: {parking_info['공고번호']} - {parking_info['물건명주소'][:50]}")
            if parking_info['공고링크']:
                print(f"     공고링크: {parking_info['공고링크']}")
        
        except Exception as e:
            print(f"  ✗ 파싱 오류: {e}")
            continue
    
    print(f"\n{'='*70}")
    print(f"총 {len(all_parking_data)}개 주차장 발견")
    print(f"{'='*70}")
    
    # 8. 슬랙 전송
    if slack_webhook_url and len(all_parking_data) > 0:
        print("\n=== 8. 슬랙 전송 ===")
        
        header = {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "🆕 온비드 주차장 물건", "emoji": True}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')} (KST)*\n\n주차장 *{len(all_parking_data)}개* 발견!"}},
                {"type": "divider"}
            ]
        }
        
        requests.post(slack_webhook_url, json=header)
        time.sleep(1)
        
        for idx, parking in enumerate(all_parking_data[:20], 1):
            blocks = {
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": f"🅿️ {idx}. {parking['공고번호']}", "emoji": True}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*📍 소재지*\n{parking['물건명주소'][:300]}"}},
                ]
            }
            
            if parking['면적']:
                blocks["blocks"].append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*📏 면적*\n{parking['면적']}"}
                })
            
            blocks["blocks"].append({
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*📅 입찰기간*\n{parking['입찰기간'] or '-'}"},
                    {"type": "mrkdwn", "text": f"*💰 최저입찰가*\n{parking['최저입찰가'] or '-'}"}
                ]
            })
            
            blocks["blocks"].append({
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*🏷️ 물건상태*\n{parking['물건상태'] or '-'}"},
                    {"type": "mrkdwn", "text": f"*👁️ 조회수*\n{parking['조회수'] or '-'}"}
                ]
            })
            
            # 공고 링크 (있을 경우)
            if parking['공고링크']:
                blocks["blocks"].append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"🔗 <{parking['공고링크']}|공고 상세보기>"}
                })
            else:
                # 링크가 없으면 검색 방법 안내
                search_info = f"🔍 온비드 담보물 부동산에서 공고번호로 검색: `{parking['공고번호']}`"
                blocks["blocks"].append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": search_info}
                })
            
            blocks["blocks"].append({"type": "divider"})
            
            requests.post(slack_webhook_url, json=blocks)
            time.sleep(1)
            print(f"  ✓ {idx}/{len(all_parking_data)} 전송")
        
        print("✓ 슬랙 전송 완료")
    
    elif slack_webhook_url:
        no_result = {
            "blocks": [{
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"📅 *{datetime.now(KST).strftime('%Y년 %m월 %d일 %H:%M')}*\n\n오늘은 주차장 물건이 없습니다."}
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
