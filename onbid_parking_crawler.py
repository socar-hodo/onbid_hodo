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
    
    # 3. 메뉴를 통해 부동산 > 담보물 > 부동산 물건 페이지로 이동
    print("\n=== 3. 메뉴 네비게이션: 부동산 > 담보물 > 부동산 ===")
    
    # 3-1. 부동산 메뉴 찾기 및 클릭
    menu_nav = page.evaluate("""
        () => {
            // 부동산 메뉴 찾기
            const links = document.querySelectorAll('a');
            let realEstateLink = null;
            
            for (let link of links) {
                const text = link.innerText.trim();
                const href = link.href || '';
                
                // "부동산" 텍스트 또는 /op/dsa/ 경로
                if (text === '부동산' || href.includes('/op/dsa/') || href.includes('1stSubMinList')) {
                    realEstateLink = link;
                    console.log('부동산 메뉴 발견:', {text: text, href: href});
                    break;
                }
            }
            
            if (realEstateLink) {
                realEstateLink.click();
                return { success: true, text: realEstateLink.innerText, href: realEstateLink.href };
            }
            
            return { success: false, error: '부동산 메뉴를 찾을 수 없음' };
        }
    """)
    
    print(f"부동산 메뉴 클릭: {json.dumps(menu_nav, ensure_ascii=False)}")
    
    if menu_nav.get('success'):
        time.sleep(3)
        print(f"✓ 현재 URL: {page.url}")
    else:
        print("⚠️ 직접 URL로 이동 시도")
        page.goto('https://www.onbid.co.kr/op/dsa/main/1stSubMinList.do', timeout=60000)
        time.sleep(3)
    
    # 3-2. 담보물 > 부동산 메뉴 찾기 및 클릭
    print("\n=== 3-2. 담보물 > 부동산 메뉴 클릭 ===")
    
    collateral_nav = page.evaluate("""
        () => {
            const links = document.querySelectorAll('a');
            let collateralLink = null;
            
            for (let link of links) {
                const text = link.innerText.trim();
                const href = link.href || '';
                
                // "담보물" 또는 "부동산" 관련 링크
                if (text.includes('담보물') || text.includes('물건') || 
                    href.includes('collateralRealEstateList') || 
                    href.includes('/op/cta/') ||
                    href.includes('nftmf')) {
                    collateralLink = link;
                    console.log('담보물/부동산 링크 발견:', {text: text, href: href});
                    break;
                }
            }
            
            if (collateralLink) {
                collateralLink.click();
                return { success: true, text: collateralLink.innerText, href: collateralLink.href };
            }
            
            return { success: false, error: '담보물 메뉴를 찾을 수 없음' };
        }
    """)
    
    print(f"담보물 메뉴 클릭: {json.dumps(collateral_nav, ensure_ascii=False)}")
    
    if collateral_nav.get('success'):
        time.sleep(5)
        print(f"✓ 현재 URL: {page.url}")
    else:
        print("⚠️ 직접 URL로 이동 시도")
        page.goto('https://www.onbid.co.kr/op/cta/nftmf/collateralRealEstateList.do', timeout=60000)
        time.sleep(5)
    
    # 페이지 완전 로딩 대기
    try:
        page.wait_for_load_state('networkidle', timeout=30000)
        print("✓ 네트워크 로딩 완료")
    except:
        print("⚠️ 네트워크 타임아웃 (계속 진행)")
    
    print(f"✓ 최종 URL: {page.url}")
    
    # 4. 물건명 검색창에 주차장 입력
    print("\n=== 4. 물건명 검색: 주차장 ===")
    
    # 페이지 구조 확인
    page_info = page.evaluate("""
        () => {
            const allInputs = Array.from(document.querySelectorAll('input'));
            const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'));
            
            return {
                inputs: allInputs.map(inp => ({
                    type: inp.type,
                    id: inp.id,
                    name: inp.name,
                    placeholder: inp.placeholder,
                    visible: inp.offsetParent !== null
                })).filter(inp => inp.visible),
                buttons: buttons.map(btn => ({
                    id: btn.id,
                    text: (btn.innerText || btn.value || '').slice(0, 30),
                    className: btn.className
                })).filter(btn => btn.text)
            };
        }
    """)
    
    print(f"보이는 input: {len(page_info['inputs'])}개")
    print(f"버튼: {len(page_info['buttons'])}개")
    
    if page_info['inputs']:
        print("\ninput 목록:")
        for inp in page_info['inputs'][:5]:
            print(f"  {json.dumps(inp, ensure_ascii=False)}")
    
    if page_info['buttons']:
        print("\n버튼 목록:")
        for btn in page_info['buttons'][:5]:
            print(f"  {json.dumps(btn, ensure_ascii=False)}")
    
    # 검색 실행
    search_result = page.evaluate("""
        () => {
            // 모든 보이는 input 찾기
            const allInputs = Array.from(document.querySelectorAll('input')).filter(
                inp => inp.offsetParent !== null && inp.type !== 'hidden'
            );
            
            let searchInput = null;
            
            // 방법 1: 속성으로 찾기
            for (let input of allInputs) {
                const id = (input.id || '').toLowerCase();
                const name = (input.name || '').toLowerCase();
                const placeholder = (input.placeholder || '').toLowerCase();
                
                if (id.includes('ctr') || id.includes('nm') || id.includes('search') ||
                    name.includes('ctr') || name.includes('nm') || name.includes('search') ||
                    placeholder.includes('물건') || placeholder.includes('검색')) {
                    searchInput = input;
                    break;
                }
            }
            
            // 방법 2: 주변 텍스트로 찾기
            if (!searchInput) {
                const labels = document.querySelectorAll('label, th, span, div');
                for (let label of labels) {
                    if (label.innerText.includes('물건명') || label.innerText.includes('물건 명')) {
                        const parent = label.closest('tr, div, form');
                        if (parent) {
                            const nearby = parent.querySelector('input[type="text"], input:not([type])');
                            if (nearby && nearby.offsetParent !== null) {
                                searchInput = nearby;
                                break;
                            }
                        }
                    }
                }
            }
            
            // 방법 3: 첫 번째 보이는 text input
            if (!searchInput && allInputs.length > 0) {
                searchInput = allInputs[0];
            }
            
            if (!searchInput) {
                return { 
                    success: false, 
                    error: 'no visible input found',
                    inputCount: allInputs.length
                };
            }
            
            // 검색어 입력
            searchInput.focus();
            searchInput.value = '주차장';
            searchInput.dispatchEvent(new Event('input', { bubbles: true }));
            searchInput.dispatchEvent(new Event('change', { bubbles: true }));
            
            // 검색 버튼 찾기
            const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'));
            let searchBtn = null;
            
            for (let btn of buttons) {
                const text = (btn.innerText || btn.value || '').trim();
                const id = (btn.id || '').toLowerCase();
                
                if (text.includes('검색') || text.includes('조회') || 
                    id.includes('search') || id.includes('btn')) {
                    searchBtn = btn;
                    break;
                }
            }
            
            if (searchBtn) {
                searchBtn.click();
                return { 
                    success: true, 
                    method: 'button click',
                    inputId: searchInput.id,
                    inputName: searchInput.name,
                    buttonText: searchBtn.innerText || searchBtn.value
                };
            }
            
            // form submit
            const form = searchInput.closest('form');
            if (form) {
                form.submit();
                return { success: true, method: 'form submit' };
            }
            
            // Enter 키
            const enterEvent = new KeyboardEvent('keydown', {
                key: 'Enter',
                keyCode: 13,
                which: 13,
                bubbles: true
            });
            searchInput.dispatchEvent(enterEvent);
            
            return { success: true, method: 'enter key' };
        }
    """)
    
    print(f"\n검색 실행: {json.dumps(search_result, ensure_ascii=False)}")
    
    if search_result.get('success'):
        print(f"✓ 검색 방법: {search_result.get('method')}")
        time.sleep(10)
        
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
        except:
            pass
    else:
        print(f"⚠️ 검색 실패")
    
    print(f"✓ 검색 후 URL: {page.url}")
    
    # 5. 주차장 물건 크롤링
    print("\n=== 5. 주차장 물건 크롤링 ===")
    
    # 페이지 텍스트 확인
    page_text = page.evaluate("() => document.body.innerText")
    has_parking = '주차' in page_text or '주차장' in page_text
    print(f"페이지에 '주차장' 텍스트: {'✓' if has_parking else '✗'}")
    
    if has_parking:
        print(f"텍스트 샘플: {page_text[:300]}")
    
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
                    if (cells.length >= 3) {
                        const texts = cells.map(cell => cell.innerText.trim());
                        const rowText = texts.join(' ');
                        
                        if (rowText.includes('주차') || rowText.includes('주차장')) {
                            console.log(`[테이블${tableIdx}-행${rowIdx}] 주차장 발견`);
                            
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
                                texts: texts,
                                link: link,
                                imgSrc: imgSrc,
                                rowText: rowText
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
            row_text = item['rowText']
            
            # 제외 키워드
            if any(kw in row_text for kw in ['일반공고', '공유재산', '위수탁', '취소공고']):
                continue
            
            # 컬럼 파싱
            mulgun_info = texts[0] if texts[0] else ''
            lines = mulgun_info.split('\n')
            
            # 공고번호 추출
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
                    address = text.strip()
                    break
            if not address and len(lines) > 1:
                address = lines[1]
            
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
                '물건명주소': address or row_text[:150],
                '면적': area,
                '입찰기간': texts[1] if len(texts) > 1 else '',
                '최저입찰가': texts[2] if len(texts) > 2 else '',
                '물건상태': texts[3] if len(texts) > 3 else '',
                '조회수': texts[4] if len(texts) > 4 else '',
                '공고링크': item['link'],
                '이미지': item['imgSrc']
            }
            
            all_parking_data.append(parking_info)
            print(f"  🅿️ {parking_info['공고번호'][:50]}")
        
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
