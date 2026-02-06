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
    
    # 3. 부동산 물건 페이지로 직접 이동
    print("\n=== 3. 부동산 물건 페이지 이동 ===")
    page.goto('https://www.onbid.co.kr/op/cta/nftmf/collateralRealEstateList.do', timeout=60000)
    time.sleep(5)
    print(f"✓ 물건 페이지: {page.url}")
    
    # 4. 물건명 검색창에 주차장 입력 (개선된 버전)
    print("\n=== 4. 물건명 검색: 주차장 ===")
    
    # 먼저 페이지 HTML 구조 확인
    page_info = page.evaluate("""
        () => {
            const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
            const forms = Array.from(document.querySelectorAll('form'));
            
            return {
                inputs: inputs.map(inp => ({
                    id: inp.id,
                    name: inp.name,
                    placeholder: inp.placeholder,
                    value: inp.value
                })),
                forms: forms.length,
                bodyText: document.body.innerText.slice(0, 500)
            };
        }
    """)
    
    print(f"페이지 input 요소들: {json.dumps(page_info['inputs'], indent=2, ensure_ascii=False)}")
    
    # 여러 방법으로 검색 시도
    search_result = page.evaluate("""
        () => {
            // 방법 1: placeholder나 label로 검색창 찾기
            let searchInput = null;
            const inputs = document.querySelectorAll('input[type="text"]');
            
            for (let input of inputs) {
                const placeholder = (input.placeholder || '').toLowerCase();
                const id = (input.id || '').toLowerCase();
                const name = (input.name || '').toLowerCase();
                
                // 물건명, 검색, search 등의 키워드로 찾기
                if (placeholder.includes('물건') || placeholder.includes('검색') ||
                    id.includes('search') || id.includes('mulgun') || id.includes('ctr') ||
                    name.includes('search') || name.includes('mulgun') || name.includes('ctr')) {
                    searchInput = input;
                    console.log('찾은 검색창:', {id: input.id, name: input.name, placeholder: input.placeholder});
                    break;
                }
            }
            
            // 방법 2: label 텍스트로 찾기
            if (!searchInput) {
                const labels = document.querySelectorAll('label');
                for (let label of labels) {
                    if (label.innerText.includes('물건명') || label.innerText.includes('검색')) {
                        const forId = label.getAttribute('for');
                        if (forId) {
                            searchInput = document.getElementById(forId);
                            if (searchInput) {
                                console.log('label로 찾은 검색창:', {id: searchInput.id, name: searchInput.name});
                                break;
                            }
                        }
                    }
                }
            }
            
            // 방법 3: 모든 text input 중 첫 번째 것 사용 (최후의 수단)
            if (!searchInput && inputs.length > 0) {
                searchInput = inputs[0];
                console.log('기본 검색창 사용:', {id: searchInput.id, name: searchInput.name});
            }
            
            if (!searchInput) {
                return { 
                    success: false, 
                    error: 'search input not found',
                    availableInputs: Array.from(inputs).map(inp => ({
                        id: inp.id, 
                        name: inp.name, 
                        placeholder: inp.placeholder
                    }))
                };
            }
            
            // 검색어 입력
            searchInput.value = '주차장';
            searchInput.dispatchEvent(new Event('input', { bubbles: true }));
            searchInput.dispatchEvent(new Event('change', { bubbles: true }));
            
            console.log('검색어 입력 완료:', searchInput.value);
            
            // 검색 버튼 찾기
            let searchBtn = null;
            
            // 방법 1: 검색 버튼 ID나 class로 찾기
            const buttons = document.querySelectorAll('button, input[type="submit"], input[type="button"], a.btn');
            for (let btn of buttons) {
                const text = btn.innerText || btn.value || '';
                const id = btn.id || '';
                const className = btn.className || '';
                
                if (text.includes('검색') || text.includes('조회') ||
                    id.toLowerCase().includes('search') || id.toLowerCase().includes('btn') ||
                    className.includes('search') || className.includes('btn')) {
                    searchBtn = btn;
                    console.log('찾은 검색 버튼:', {id: btn.id, text: text});
                    break;
                }
            }
            
            // 검색 실행
            if (searchBtn) {
                searchBtn.click();
                return { success: true, method: 'button click', buttonId: searchBtn.id };
            }
            
            // form submit
            const form = searchInput.closest('form');
            if (form) {
                form.submit();
                return { success: true, method: 'form submit' };
            }
            
            // Enter 키 시뮬레이션
            const enterEvent = new KeyboardEvent('keydown', {
                key: 'Enter',
                code: 'Enter',
                keyCode: 13,
                bubbles: true
            });
            searchInput.dispatchEvent(enterEvent);
            
            return { success: true, method: 'enter key simulation' };
        }
    """)
    
    print(f"검색 결과: {json.dumps(search_result, indent=2, ensure_ascii=False)}")
    
    if search_result.get('success'):
        print(f"✓ 검색 실행: {search_result.get('method')}")
        time.sleep(10)
    else:
        print(f"⚠️ 검색 실패: {search_result.get('error')}")
        if 'availableInputs' in search_result:
            print(f"사용 가능한 input 요소들:")
            for inp in search_result['availableInputs']:
                print(f"  - id: {inp.get('id')}, name: {inp.get('name')}, placeholder: {inp.get('placeholder')}")
    
    print(f"✓ 검색 후 URL: {page.url}")
    
    # 5. 주차장 물건 크롤링
    print("\n=== 5. 주차장 물건 크롤링 ===")
    
    # 페이지 텍스트 확인
    page_text = page.evaluate("() => document.body.innerText")
    has_parking = '주차' in page_text or '주차장' in page_text
    print(f"페이지에 '주차장' 텍스트: {'✓' if has_parking else '✗'}")
    
    # JavaScript로 테이블 데이터 추출
    table_data = page.evaluate("""
        () => {
            const results = [];
            const tables = document.querySelectorAll('table');
            
            console.log('테이블 개수:', tables.length);
            
            tables.forEach((table, tableIdx) => {
                const rows = table.querySelectorAll('tbody tr, tr');
                
                console.log(`테이블 ${tableIdx} 행 개수:`, rows.length);
                
                rows.forEach((row, rowIdx) => {
                    const cells = Array.from(row.querySelectorAll('td'));
                    if (cells.length >= 5) {
                        const texts = cells.map(cell => cell.innerText.trim());
                        const rowText = texts.join(' ');
                        
                        // 주차장 키워드 확인
                        if (rowText.includes('주차') || rowText.includes('주차장')) {
                            console.log(`[테이블${tableIdx}-행${rowIdx}] 주차장 발견`);
                            
                            // 공고 링크 찾기
                            let link = '';
                            const linkElem = row.querySelector('a[href]');
                            if (linkElem) {
                                link = linkElem.href;
                            }
                            
                            // 이미지 찾기
                            let imgSrc = '';
                            const imgElem = row.querySelector('img');
                            if (imgElem) {
                                imgSrc = imgElem.src;
                            }
                            
                            results.push({
                                texts: texts,
                                link: link,
                                imgSrc: imgSrc
                            });
                        }
                    }
                });
            });
            
            console.log('총 주차장:', results.length);
            return results;
        }
    """)
    
    print(f"✓ {len(table_data)}개 주차장 행 발견")
    
    # 데이터 정리
    for idx, item in enumerate(table_data):
        try:
            texts = item['texts']
            row_text = ' '.join(texts)
            
            # 제외 키워드
            if any(kw in row_text for kw in ['일반공고', '공유재산', '위수탁', '취소공고']):
                continue
            
            # 컬럼 파싱
            mulgun_info = texts[0] if texts[0] else ''
            lines = mulgun_info.split('\n')
            
            # 공고번호 추출
            gonggo_no = ''
            for line in lines:
                if '-' in line and sum(c.isdigit() for c in line) >= 8:
                    gonggo_no = line.strip()
                    break
            
            # 주소 추출
            address = ''
            if len(lines) > 1:
                for i, line in enumerate(lines):
                    if gonggo_no in line and i + 1 < len(lines):
                        address = lines[i + 1].strip()
                        break
                if not address:
                    address = lines[1] if len(lines) > 1 else ''
            
            # 면적 정보
            area = ''
            for line in lines:
                if '㎡' in line or 'm²' in line:
                    area = line.strip()
                    break
            
            parking_info = {
                '공고번호': gonggo_no,
                '물건명주소': address,
                '면적': area,
                '입찰기간': texts[1] if len(texts) > 1 else '',
                '최저입찰가': texts[2] if len(texts) > 2 else '',
                '물건상태': texts[3] if len(texts) > 3 else '',
                '조회수': texts[4] if len(texts) > 4 else '',
                '공고링크': item['link'],
                '이미지': item['imgSrc']
            }
            
            if gonggo_no:
                all_parking_data.append(parking_info)
                print(f"  🅿️ {gonggo_no}")
        
        except Exception as e:
            continue
    
    print(f"\n{'='*70}")
    print(f"총 {len(all_parking_data)}개 주차장 발견")
    print(f"{'='*70}")
    
    # 샘플 출력
    if len(all_parking_data) > 0:
        print("\n=== 샘플 데이터 ===")
        sample = all_parking_data[0]
        for key, value in sample.items():
            print(f"{key}: {value[:100] if isinstance(value, str) else value}")
    
    # 6. 슬랙 전송
    if slack_webhook_url and len(all_parking_data) > 0:
        print("\n=== 6. 슬랙 전송 ===")
        
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
            
            # 면적
            if parking['면적']:
                blocks["blocks"].append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*📏 면적*\n{parking['면적']}"}
                })
            
            # 입찰기간, 최저입찰가
            blocks["blocks"].append({
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*📅 입찰기간*\n{parking['입찰기간'] or '-'}"},
                    {"type": "mrkdwn", "text": f"*💰 최저입찰가*\n{parking['최저입찰가'] or '-'}"}
                ]
            })
            
            # 물건상태, 조회수
            blocks["blocks"].append({
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*🏷️ 물건상태*\n{parking['물건상태'] or '-'}"},
                    {"type": "mrkdwn", "text": f"*👁️ 조회수*\n{parking['조회수'] or '-'}"}
                ]
            })
            
            # 공고 링크
            if parking['공고링크']:
                blocks["blocks"].append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"🔗 <{parking['공고링크']}|공고 상세보기>"}
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
