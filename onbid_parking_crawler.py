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
    
    # 발견된 URL로 직접 이동
    target_url = 'https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateList.do'
    print(f"목표 URL: {target_url}")
    
    page.goto(target_url, timeout=60000)
    time.sleep(8)
    
    # 페이지 완전 로딩 대기
    try:
        page.wait_for_load_state('networkidle', timeout=30000)
        print("✓ 네트워크 로딩 완료")
    except:
        print("⚠️ 네트워크 타임아웃 (계속 진행)")
    
    print(f"✓ 현재 URL: {page.url}")
    
    # 페이지가 제대로 로드되었는지 확인
    page_title = page.evaluate("() => document.title")
    print(f"✓ 페이지 제목: {page_title}")
    
    # 4. 물건명 검색창에 주차장 입력
    print("\n=== 4. 물건명 검색: 주차장 ===")
    
    # 페이지 구조 확인
    page_info = page.evaluate("""
        () => {
            const allInputs = Array.from(document.querySelectorAll('input'));
            const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'));
            const forms = Array.from(document.querySelectorAll('form'));
            
            // 보이는 input만 필터링
            const visibleInputs = allInputs.filter(inp => {
                return inp.offsetParent !== null && inp.type !== 'hidden';
            });
            
            return {
                totalInputs: allInputs.length,
                visibleInputs: visibleInputs.length,
                inputs: visibleInputs.map(inp => ({
                    type: inp.type,
                    id: inp.id,
                    name: inp.name,
                    placeholder: inp.placeholder,
                    className: inp.className
                })),
                buttons: buttons.filter(btn => btn.offsetParent !== null).map(btn => ({
                    id: btn.id,
                    text: (btn.innerText || btn.value || '').slice(0, 30),
                    className: btn.className
                })),
                forms: forms.length,
                bodySnippet: document.body.innerText.slice(0, 500)
            };
        }
    """)
    
    print(f"\n페이지 요소 정보:")
    print(f"- 전체 input: {page_info['totalInputs']}개")
    print(f"- 보이는 input: {page_info['visibleInputs']}개")
    print(f"- 버튼: {len(page_info['buttons'])}개")
    print(f"- form: {page_info['forms']}개")
    
    if page_info['inputs']:
        print(f"\n보이는 input 목록:")
        for inp in page_info['inputs']:
            print(f"  {json.dumps(inp, ensure_ascii=False)}")
    
    if page_info['buttons']:
        print(f"\n버튼 목록:")
        for btn in page_info['buttons']:
            print(f"  {json.dumps(btn, ensure_ascii=False)}")
    
    print(f"\n페이지 텍스트 샘플:")
    print(page_info['bodySnippet'])
    
    # 검색 실행
    search_result = page.evaluate("""
        () => {
            // 모든 보이는 input 찾기
            const allInputs = Array.from(document.querySelectorAll('input')).filter(
                inp => inp.offsetParent !== null && inp.type !== 'hidden'
            );
            
            console.log('보이는 input 개수:', allInputs.length);
            
            let searchInput = null;
            
            // 방법 1: 속성으로 검색창 찾기
            for (let input of allInputs) {
                const id = (input.id || '').toLowerCase();
                const name = (input.name || '').toLowerCase();
                const placeholder = (input.placeholder || '').toLowerCase();
                const className = (input.className || '').toLowerCase();
                
                console.log('input 확인:', {id, name, placeholder, className});
                
                // ctr, nm, search, mulgun 등 키워드
                if (id.includes('ctr') || id.includes('nm') || id.includes('search') || id.includes('mulgun') ||
                    name.includes('ctr') || name.includes('nm') || name.includes('search') || name.includes('mulgun') ||
                    placeholder.includes('물건') || placeholder.includes('검색') || placeholder.includes('명칭') ||
                    className.includes('search')) {
                    searchInput = input;
                    console.log('검색창 발견 (속성):', {id: input.id, name: input.name});
                    break;
                }
            }
            
            // 방법 2: label, th, td 텍스트로 찾기
            if (!searchInput) {
                const labels = document.querySelectorAll('label, th, td, span, div');
                for (let label of labels) {
                    const text = label.innerText || '';
                    if (text.includes('물건명') || text.includes('물건 명') || text === '물건명칭' || text === '명칭') {
                        console.log('label 텍스트 발견:', text);
                        
                        // 같은 tr, div, form 내의 input 찾기
                        const parent = label.closest('tr, div, form, td');
                        if (parent) {
                            const nearby = parent.querySelector('input[type="text"], input:not([type])');
                            if (nearby && nearby.offsetParent !== null && nearby.type !== 'hidden') {
                                searchInput = nearby;
                                console.log('검색창 발견 (label):', {id: nearby.id, name: nearby.name});
                                break;
                            }
                        }
                        
                        // 다음 형제 요소에서 input 찾기
                        let next = label.nextElementSibling;
                        while (next) {
                            if (next.tagName === 'INPUT' && next.type !== 'hidden' && next.offsetParent !== null) {
                                searchInput = next;
                                console.log('검색창 발견 (nextSibling):', {id: next.id, name: next.name});
                                break;
                            }
                            const nestedInput = next.querySelector('input[type="text"], input:not([type])');
                            if (nestedInput && nestedInput.offsetParent !== null) {
                                searchInput = nestedInput;
                                console.log('검색창 발견 (nested):', {id: nestedInput.id, name: nestedInput.name});
                                break;
                            }
                            next = next.nextElementSibling;
                        }
                        if (searchInput) break;
                    }
                }
            }
            
            // 방법 3: 첫 번째 보이는 text input
            if (!searchInput && allInputs.length > 0) {
                for (let input of allInputs) {
                    if (input.type === 'text' || input.type === '') {
                        searchInput = input;
                        console.log('기본 검색창 사용:', {id: input.id, name: input.name});
                        break;
                    }
                }
            }
            
            if (!searchInput) {
                return { 
                    success: false, 
                    error: 'no input found',
                    inputCount: allInputs.length,
                    inputDetails: allInputs.map(inp => ({
                        id: inp.id,
                        name: inp.name,
                        type: inp.type,
                        placeholder: inp.placeholder
                    }))
                };
            }
            
            // 검색어 입력
            console.log('검색어 입력 시작');
            searchInput.focus();
            searchInput.value = '주차장';
            
            // 다양한 이벤트 발생
            searchInput.dispatchEvent(new Event('input', { bubbles: true }));
            searchInput.dispatchEvent(new Event('change', { bubbles: true }));
            searchInput.dispatchEvent(new Event('blur', { bubbles: true }));
            
            console.log('검색어 입력 완료:', searchInput.value);
            
            // 검색 버튼 찾기
            const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], a[role="button"]'));
            let searchBtn = null;
            
            for (let btn of buttons) {
                if (btn.offsetParent === null) continue;
                
                const text = (btn.innerText || btn.value || '').trim();
                const id = (btn.id || '').toLowerCase();
                const className = (btn.className || '').toLowerCase();
                
                console.log('버튼 확인:', {text, id, className});
                
                if (text.includes('검색') || text.includes('조회') || text.includes('Search') ||
                    id.includes('search') || id.includes('btn') || id.includes('inquiry') ||
                    className.includes('search') || className.includes('btn')) {
                    searchBtn = btn;
                    console.log('검색 버튼 발견:', {id: btn.id, text: text});
                    break;
                }
            }
            
            // 검색 실행
            if (searchBtn) {
                console.log('버튼 클릭');
                searchBtn.click();
                return { 
                    success: true, 
                    method: 'button click',
                    inputId: searchInput.id,
                    inputName: searchInput.name,
                    buttonId: searchBtn.id,
                    buttonText: searchBtn.innerText || searchBtn.value
                };
            }
            
            // form submit 시도
            const form = searchInput.closest('form');
            if (form) {
                console.log('form submit');
                form.submit();
                return { 
                    success: true, 
                    method: 'form submit',
                    inputId: searchInput.id,
                    inputName: searchInput.name
                };
            }
            
            // Enter 키 시뮬레이션
            console.log('Enter 키 전송');
            const events = ['keydown', 'keypress', 'keyup'];
            events.forEach(eventType => {
                const evt = new KeyboardEvent(eventType, {
                    key: 'Enter',
                    code: 'Enter',
                    keyCode: 13,
                    which: 13,
                    bubbles: true,
                    cancelable: true
                });
                searchInput.dispatchEvent(evt);
            });
            
            return { 
                success: true, 
                method: 'enter key simulation',
                inputId: searchInput.id,
                inputName: searchInput.name
            };
        }
    """)
    
    print(f"\n검색 실행 결과: {json.dumps(search_result, ensure_ascii=False)}")
    
    if search_result.get('success'):
        print(f"✓ 검색 방법: {search_result.get('method')}")
        print(f"  input: {search_result.get('inputId')} / {search_result.get('inputName')}")
        if search_result.get('buttonText'):
            print(f"  button: {search_result.get('buttonText')}")
        
        time.sleep(12)
        
        # 로딩 대기
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
            print("✓ 검색 결과 로딩 완료")
        except:
            print("⚠️ 로딩 타임아웃")
    else:
        print(f"⚠️ 검색 실패: {search_result.get('error')}")
        if 'inputDetails' in search_result:
            print("\n사용 가능한 input 상세:")
            for inp in search_result['inputDetails']:
                print(f"  {json.dumps(inp, ensure_ascii=False)}")
    
    print(f"✓ 검색 후 URL: {page.url}")
    
    # 5. 주차장 물건 크롤링
    print("\n=== 5. 주차장 물건 크롤링 ===")
    
    # 페이지 텍스트 확인
    page_text = page.evaluate("() => document.body.innerText")
    has_parking = '주차' in page_text or '주차장' in page_text
    print(f"페이지에 '주차장' 텍스트: {'✓' if has_parking else '✗'}")
    
    if has_parking:
        print(f"텍스트 샘플 (주차장 포함):")
        # 주차장이 있는 부분 찾기
        idx = page_text.find('주차')
        if idx >= 0:
            print(page_text[max(0, idx-100):idx+200])
    
    # JavaScript로 테이블 데이터 추출
    table_data = page.evaluate("""
        () => {
            const results = [];
            
            // 모든 테이블 찾기
            const tables = document.querySelectorAll('table');
            console.log('테이블 개수:', tables.length);
            
            // div, ul, article 등 다른 컨테이너도 확인
            const containers = document.querySelectorAll('div[class*="list"], div[class*="item"], ul[class*="list"], article');
            console.log('리스트 컨테이너 개수:', containers.length);
            
            // 테이블에서 검색
            tables.forEach((table, tableIdx) => {
                const rows = table.querySelectorAll('tbody tr, tr');
                console.log(`테이블 ${tableIdx} 행 개수:`, rows.length);
                
                rows.forEach((row, rowIdx) => {
                    const cells = Array.from(row.querySelectorAll('td, th'));
                    if (cells.length >= 3) {
                        const texts = cells.map(cell => cell.innerText.trim());
                        const rowText = texts.join(' ');
                        
                        if (rowText.includes('주차') || rowText.includes('주차장')) {
                            console.log(`[테이블${tableIdx}-행${rowIdx}] 주차장 발견:`, rowText.slice(0, 100));
                            
                            let link = '';
                            const linkElem = row.querySelector('a[href]');
                            if (linkElem) {
                                link = linkElem.href;
                            }
                            
                            let imgSrc = '';
                            const imgElem = row.querySelector('img');
                            if (imgElem) {
                                imgSrc = imgElem.src;
                            }
                            
                            results.push({
                                source: 'table',
                                texts: texts,
                                link: link,
                                imgSrc: imgSrc,
                                rowText: rowText
                            });
                        }
                    }
                });
            });
            
            // div/ul 리스트에서도 검색
            containers.forEach((container, idx) => {
                const text = container.innerText || '';
                if ((text.includes('주차') || text.includes('주차장')) && text.length < 2000) {
                    console.log(`[컨테이너${idx}] 주차장 발견:`, text.slice(0, 100));
                    
                    let link = '';
                    const linkElem = container.querySelector('a[href]');
                    if (linkElem) {
                        link = linkElem.href;
                    }
                    
                    results.push({
                        source: 'container',
                        texts: [text],
                        link: link,
                        imgSrc: '',
                        rowText: text
                    });
                }
            });
            
            console.log('총 주차장 발견:', results.length);
            return results;
        }
    """)
    
    print(f"✓ {len(table_data)}개 주차장 항목 발견")
    
    # 데이터 정리
    for idx, item in enumerate(table_data):
        try:
            texts = item['texts']
            row_text = item['rowText']
            
            print(f"\n[{idx+1}] 처리 중: {row_text[:150]}")
            
            # 제외 키워드
            if any(kw in row_text for kw in ['일반공고', '공유재산', '위수탁', '취소공고']):
                print("  → 제외됨")
                continue
            
            # 공고번호 추출 (숫자-숫자 패턴)
            gonggo_no = ''
            for text in texts:
                for line in text.split('\n'):
                    if '-' in line and sum(c.isdigit() for c in line) >= 8:
                        gonggo_no = line.strip()
                        break
                if gonggo_no:
                    break
            
            # 주소 추출
            address = ''
            for text in texts:
                if '주차' in text and len(text) > 10:
                    # 주소 부분만 추출
                    lines = text.split('\n')
                    for line in lines:
                        if '주차' in line or '도' in line or '시' in line or '구' in line:
                            address = line.strip()
                            break
                    if not address:
                        address = text.strip()
                    break
            
            if not address:
                address = row_text[:200]
            
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
            
            parking_info = {
                '공고번호': gonggo_no or '번호미확인',
                '물건명주소': address,
                '면적': area,
                '입찰기간': texts[1] if len(texts) > 1 else '',
                '최저입찰가': texts[2] if len(texts) > 2 else '',
                '물건상태': texts[3] if len(texts) > 3 else '',
                '조회수': texts[4] if len(texts) > 4 else '',
                '공고링크': item['link'],
                '이미지': item['imgSrc']
            }
            
            all_parking_data.append(parking_info)
            print(f"  ✓ 추가: {parking_info['공고번호']}")
        
        except Exception as e:
            print(f"  ✗ 파싱 오류: {e}")
            continue
    
    print(f"\n{'='*70}")
    print(f"총 {len(all_parking_data)}개 주차장 발견")
    print(f"{'='*70}")
    
    # 샘플 출력
    if len(all_parking_data) > 0:
        print("\n=== 샘플 데이터 ===")
        sample = all_parking_data[0]
        for key, value in sample.items():
            display_value = value[:100] if isinstance(value, str) and len(value) > 100 else value
            print(f"{key}: {display_value}")
    
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
