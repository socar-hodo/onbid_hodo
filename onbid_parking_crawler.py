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
    
    # 동적 콘텐츠 로딩 대기
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
    
    # 페이지가 제대로 로드되었는지 확인
    page_title = page.evaluate("() => document.title")
    print(f"✓ 페이지 제목: {page_title}")
    
    # 4. 페이지 구조 상세 확인
    print("\n=== 4. 페이지 구조 상세 확인 ===")
    
    page_structure = page.evaluate("""() => {
        const allInputs = Array.from(document.querySelectorAll('input'));
        const allButtons = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"]'));
        const allForms = Array.from(document.querySelectorAll('form'));
        
        return {
            totalInputs: allInputs.length,
            visibleInputs: allInputs.filter(inp => inp.offsetParent !== null && inp.type !== 'hidden').map(inp => ({
                id: inp.id,
                name: inp.name,
                type: inp.type,
                placeholder: inp.placeholder
            })),
            buttons: allButtons.filter(btn => btn.offsetParent !== null).map(btn => ({
                id: btn.id,
                text: (btn.innerText || btn.value || '').slice(0, 50),
                className: btn.className
            })),
            forms: allForms.length,
            hasSearchCltrNm: !!document.getElementById('searchCltrNm')
        };
    }""")
    
    print(f"\n페이지 요소 정보:")
    print(f"- 전체 input: {page_structure['totalInputs']}개")
    print(f"- 보이는 input: {len(page_structure['visibleInputs'])}개")
    print(f"- searchCltrNm 존재: {page_structure['hasSearchCltrNm']}")
    print(f"- 버튼: {len(page_structure['buttons'])}개")
    print(f"- form: {page_structure['forms']}개")
    
    # 5. 물건명 검색창에 주차장 입력
    print("\n=== 5. 물건명 검색: 주차장 ===")
    
    # searchCltrNm을 사용한 검색
    search_result = page.evaluate("""() => {
        const searchInput = document.getElementById('searchCltrNm');
        
        if (!searchInput) {
            return {
                success: false,
                error: 'searchCltrNm not found'
            };
        }
        
        console.log('검색창 발견:', searchInput.id, searchInput.name);
        
        searchInput.value = '주차장';
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
        searchInput.dispatchEvent(new Event('change', { bubbles: true }));
        
        console.log('검색어 입력 완료:', searchInput.value);
        
        let searchBtn = document.getElementById('searchBtn');
        
        if (!searchBtn) {
            const buttons = document.querySelectorAll('button, input[type="button"], input[type="submit"]');
            for (let btn of buttons) {
                const text = (btn.innerText || btn.value || '').trim();
                const btnId = btn.id || '';
                const onclick = btn.getAttribute('onclick') || '';
                
                if (text.includes('검색') || text.includes('조회') || 
                    btnId.toLowerCase().includes('search') || 
                    onclick.includes('search') || onclick.includes('inquiry')) {
                    searchBtn = btn;
                    console.log('검색 버튼 발견:', btn.id, text);
                    break;
                }
            }
        }
        
        if (searchBtn) {
            console.log('검색 버튼 클릭:', searchBtn.id);
            searchBtn.click();
            return {
                success: true,
                method: 'button click',
                buttonId: searchBtn.id,
                inputId: searchInput.id
            };
        }
        
        const form = searchInput.closest('form');
        if (form) {
            console.log('form submit');
            form.submit();
            return {
                success: true,
                method: 'form submit',
                inputId: searchInput.id
            };
        }
        
        console.log('Enter 키 전송');
        searchInput.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Enter',
            code: 'Enter',
            keyCode: 13,
            which: 13,
            bubbles: true
        }));
        
        return {
            success: true,
            method: 'enter key',
            inputId: searchInput.id
        };
    }""")
    
    print(f"검색 실행 결과: {json.dumps(search_result, ensure_ascii=False)}")
    
    if search_result.get('success'):
        print(f"✓ 검색 방법: {search_result.get('method')}")
        print(f"  input ID: {search_result.get('inputId')}")
        if search_result.get('buttonId'):
            print(f"  button ID: {search_result.get('buttonId')}")
        
        time.sleep(12)
        
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
            print("✓ 검색 결과 로딩 완료")
        except:
            print("⚠️ 로딩 타임아웃")
    else:
        print(f"⚠️ 검색 실패: {search_result.get('error')}")
    
    print(f"✓ 검색 후 URL: {page.url}")
    
    # 6. 주차장 물건 크롤링
    print("\n=== 6. 주차장 물건 크롤링 ===")
    
    # 페이지 텍스트 확인
    page_text = page.evaluate("() => document.body.innerText")
    has_parking = '주차' in page_text or '주차장' in page_text
    print(f"페이지에 '주차장' 텍스트: {'✓' if has_parking else '✗'}")
    
    if has_parking:
        idx = page_text.find('주차')
        if idx >= 0:
            print(f"텍스트 샘플 (주차장 포함):")
            print(page_text[max(0, idx-100):idx+200])
    
    # 7. 링크 디버깅 - 실제 링크 정보 수집
    print("\n=== 7. 링크 디버깅 - 실제 링크 정보 확인 ===")
    
    actual_links = page.evaluate("""() => {
        const results = [];
        const tables = document.querySelectorAll('table');
        
        tables.forEach((table, tableIdx) => {
            const rows = table.querySelectorAll('tbody tr, tr');
            
            rows.forEach((row, rowIdx) => {
                const rowText = row.innerText || '';
                
                if (rowText.includes('주차') || rowText.includes('주차장')) {
                    const linkElem = row.querySelector('a[href], a[onclick], td a, div a');
                    if (linkElem) {
                        results.push({
                            href: linkElem.getAttribute('href'),
                            onclick: linkElem.getAttribute('onclick'),
                            outerHTML: linkElem.outerHTML.slice(0, 200),
                            text: rowText.slice(0, 100)
                        });
                    }
                }
            });
        });
        
        return results.slice(0, 5);
    }""")
    
    print(f"\n실제 링크 정보 ({len(actual_links)}개 샘플):")
    for idx, link_info in enumerate(actual_links):
        print(f"\n[샘플 {idx+1}]")
        print(f"  href: {link_info.get('href')}")
        print(f"  onclick: {link_info.get('onclick')}")
        print(f"  HTML: {link_info.get('outerHTML')}")
        print(f"  텍스트: {link_info.get('text')}")
    
    # 8. 첫 번째 링크 클릭 테스트
    print("\n=== 8. 첫 번째 링크 클릭 테스트 ===")
    
    if len(actual_links) > 0:
        # 새 페이지 이벤트 리스너 설정
        new_page_promise = None
        
        def handle_popup(popup):
            print(f"  → 팝업 열림: {popup.url}")
        
        browser.contexts[0].on("page", handle_popup)
        
        # 링크 클릭
        clicked_result = page.evaluate("""() => {
            const tables = document.querySelectorAll('table');
            
            for (let table of tables) {
                const rows = table.querySelectorAll('tbody tr, tr');
                
                for (let row of rows) {
                    const rowText = row.innerText || '';
                    
                    if (rowText.includes('주차') || rowText.includes('주차장')) {
                        const linkElem = row.querySelector('a[href], a[onclick]');
                        if (linkElem) {
                            linkElem.click();
                            return {
                                clicked: true,
                                href: linkElem.getAttribute('href'),
                                onclick: linkElem.getAttribute('onclick')
                            };
                        }
                    }
                }
            }
            
            return { clicked: false };
        }""")
        
        print(f"클릭 결과: {json.dumps(clicked_result, ensure_ascii=False)}")
        
        if clicked_result.get('clicked'):
            time.sleep(5)
            
            # 열린 모든 페이지 확인
            all_pages = browser.contexts[0].pages
            print(f"\n열린 페이지 수: {len(all_pages)}")
            
            for page_idx, p in enumerate(all_pages):
                print(f"  페이지 {page_idx}: {p.url}")
            
            # 새 페이지가 열렸다면
            if len(all_pages) > 1:
                detail_page = all_pages[-1]
                detail_url = detail_page.url
                detail_title = detail_page.evaluate("() => document.title")
                
                print(f"\n✓ 상세 페이지 발견!")
                print(f"  URL: {detail_url}")
                print(f"  제목: {detail_title}")
                
                # URL 패턴 분석
                if '?' in detail_url:
                    base_url = detail_url.split('?')[0]
                    params = detail_url.split('?')[1]
                    print(f"  베이스 URL: {base_url}")
                    print(f"  파라미터: {params}")
                
                detail_page.close()
            else:
                print("⚠️ 새 페이지가 열리지 않음 - 같은 페이지에서 전환된 것으로 보임")
                print(f"  현재 URL: {page.url}")
    
    # 9. JavaScript로 테이블 데이터 추출
    print("\n=== 9. 주차장 데이터 크롤링 ===")
    
    table_data = page.evaluate("""() => {
        const results = [];
        
        const tables = document.querySelectorAll('table');
        console.log('테이블 개수:', tables.length);
        
        tables.forEach((table, tableIdx) => {
            const rows = table.querySelectorAll('tbody tr, tr');
            console.log('테이블', tableIdx, '행 개수:', rows.length);
            
            rows.forEach((row, rowIdx) => {
                const cells = Array.from(row.querySelectorAll('td, th'));
                if (cells.length >= 3) {
                    const texts = cells.map(cell => cell.innerText.trim());
                    const rowText = texts.join(' ');
                    
                    if (rowText.includes('주차') || rowText.includes('주차장')) {
                        console.log('테이블', tableIdx, '행', rowIdx, '주차장 발견');
                        
                        let link = '';
                        let rawLink = '';
                        
                        const linkElem = row.querySelector('a[href], a[onclick], [onclick*="fn_selectDetail"]');
                        if (linkElem) {
                            const href = linkElem.getAttribute('href') || '';
                            const onclick = linkElem.getAttribute('onclick') || '';
                            
                            rawLink = href || onclick;
                            
                            const searchText = href + ' ' + onclick;
                            const match = searchText.match(/fn_selectDetail\\(['"](\\d+)['"]\\s*,\\s*['"](\\d+)['"]\\s*,\\s*['"](\\d+)['"]\\s*,\\s*['"](\\d+)['"]\\s*,\\s*['"](\\d+)['"]\\s*,\\s*['"](\\d+)['"]\\)/);
                            
                            if (match) {
                                link = 'https://www.onbid.co.kr/op/cta/cltrdtl/collateralDetailRealEstateView.do?' +
                                       'cltrNo=' + match[1] +
                                       '&cltrHstrNo=' + match[2] +
                                       '&plnmNo=' + match[3] +
                                       '&pbctNo=' + match[4] +
                                       '&scrnGrpCd=' + match[5] +
                                       '&pbctCdtnNo=' + match[6];
                                console.log('링크 변환:', link);
                            } else if (href && !href.includes('javascript:')) {
                                link = href;
                            }
                        }
                        
                        let imgSrc = '';
                        const imgElem = row.querySelector('img');
                        if (imgElem) {
                            imgSrc = imgElem.src;
                        }
                        
                        results.push({
                            texts: texts,
                            link: link,
                            rawLink: rawLink,
                            imgSrc: imgSrc,
                            rowText: rowText
                        });
                    }
                }
            });
        });
        
        console.log('총 주차장 발견:', results.length);
        return results;
    }""")
    
    print(f"✓ {len(table_data)}개 주차장 항목 발견")
    
    # 데이터 정리
    for idx, item in enumerate(table_data):
        try:
            texts = item['texts']
            row_text = item['rowText']
            
            print(f"\n[{idx+1}] 처리 중...")
            
            # 제외 키워드
            if any(kw in row_text for kw in ['일반공고', '공유재산', '위수탁', '취소공고']):
                print("  → 제외됨 (키워드 필터)")
                continue
            
            # 공고번호 추출
            gonggo_no = ''
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
            
            parking_info = {
                '공고번호': gonggo_no or '번호미확인',
                '물건명주소': address,
                '면적': area,
                '입찰기간': texts[1] if len(texts) > 1 and texts[1] != address else '',
                '최저입찰가': texts[2] if len(texts) > 2 else '',
                '물건상태': texts[3] if len(texts) > 3 else '',
                '조회수': texts[4] if len(texts) > 4 else '',
                '공고링크': item['link'],
                '원본링크': item['rawLink'],
                '이미지': item['imgSrc']
            }
            
            all_parking_data.append(parking_info)
            print(f"  ✓ 추가: {parking_info['공고번호']} - {parking_info['물건명주소'][:50]}")
            print(f"     원본: {parking_info['원본링크'][:80]}")
            if parking_info['공고링크']:
                print(f"     변환: {parking_info['공고링크'][:80]}")
        
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
    
    # 10. 슬랙 전송
    if slack_webhook_url and len(all_parking_data) > 0:
        print("\n=== 10. 슬랙 전송 ===")
        
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
            
            if parking['공고링크'] and not parking['공고링크'].startswith('javascript:'):
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
