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
            inputs: allInputs.map(inp => ({
                id: inp.id,
                name: inp.name,
                type: inp.type,
                placeholder: inp.placeholder,
                value: inp.value,
                visible: inp.offsetParent !== null,
                className: inp.className
            })),
            buttons: allButtons.filter(btn => btn.offsetParent !== null).map(btn => ({
                id: btn.id,
                text: (btn.innerText || btn.value || '').slice(0, 50),
                className: btn.className,
                onclick: (btn.getAttribute('onclick') || '').slice(0, 100)
            })),
            forms: allForms.length,
            hasSearchCtrNm: !!document.getElementById('searchCtrNm'),
            bodyText: document.body.innerText.slice(0, 1000)
        };
    }""")
    
    print(f"\n페이지 요소 정보:")
    print(f"- 전체 input: {page_structure['totalInputs']}개")
    print(f"- searchCtrNm 존재: {page_structure['hasSearchCtrNm']}")
    print(f"- 버튼: {len(page_structure['buttons'])}개")
    print(f"- form: {page_structure['forms']}개")
    
    print(f"\n모든 input 목록:")
    for inp in page_structure['inputs']:
        print(f"  {json.dumps(inp, ensure_ascii=False)}")
    
    if page_structure['buttons']:
        print(f"\n버튼 목록:")
        for btn in page_structure['buttons']:
            print(f"  {json.dumps(btn, ensure_ascii=False)}")
    
    print(f"\n페이지 텍스트 샘플:")
    print(page_structure['bodyText'][:500])
    
    # 5. 물건명 검색창에 주차장 입력
    print("\n=== 5. 물건명 검색: 주차장 ===")
    
    # iframe 확인
    iframe_count = len(page.frames)
    print(f"iframe 개수: {iframe_count}")
    
    search_result = {'success': False}
    
    if iframe_count > 1:
        print("iframe 내부 확인 중...")
        for idx, frame in enumerate(page.frames):
            try:
                frame_url = frame.url
                print(f"  iframe {idx}: {frame_url}")
                
                # iframe 내부에서 searchCtrNm 찾기
                has_search = frame.evaluate("""() => {
                    return !!document.getElementById('searchCtrNm');
                }""")
                
                if has_search:
                    print(f"  → searchCtrNm 발견!")
                    
                    # iframe 내부에서 검색 실행
                    search_result = frame.evaluate("""() => {
                        const searchInput = document.getElementById('searchCtrNm');
                        if (!searchInput) return { success: false, error: 'not found in iframe' };
                        
                        searchInput.value = '주차장';
                        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
                        searchInput.dispatchEvent(new Event('change', { bubbles: true }));
                        
                        let searchBtn = document.getElementById('searchBtn');
                        if (!searchBtn) {
                            const buttons = document.querySelectorAll('button, input[type="button"], input[type="submit"]');
                            for (let btn of buttons) {
                                const text = (btn.innerText || btn.value || '').trim();
                                if (text.includes('검색') || text.includes('조회')) {
                                    searchBtn = btn;
                                    break;
                                }
                            }
                        }
                        
                        if (searchBtn) {
                            searchBtn.click();
                            return { success: true, method: 'button in iframe', inputId: searchInput.id };
                        }
                        
                        const form = searchInput.closest('form');
                        if (form) {
                            form.submit();
                            return { success: true, method: 'form in iframe' };
                        }
                        
                        return { success: false, error: 'no submit method in iframe' };
                    }""")
                    
                    print(f"iframe 검색 결과: {json.dumps(search_result, ensure_ascii=False)}")
                    
                    if search_result.get('success'):
                        print(f"✓ iframe에서 검색 성공!")
                        break
            except Exception as e:
                print(f"  iframe {idx} 오류: {e}")
    
    # 메인 페이지에서 검색 시도
    if not search_result.get('success'):
        search_result = page.evaluate("""() => {
            const searchInput = document.getElementById('searchCtrNm');
            
            if (!searchInput) {
                const altInput = document.querySelector('input[name="searchCtrNm"]');
                if (!altInput) {
                    const visibleInputs = Array.from(document.querySelectorAll('input')).filter(
                        inp => inp.type === 'text' && inp.offsetParent !== null
                    );
                    
                    return {
                        success: false,
                        error: 'searchCtrNm not found',
                        visibleTextInputs: visibleInputs.map(inp => ({
                            id: inp.id,
                            name: inp.name,
                            placeholder: inp.placeholder
                        }))
                    };
                }
            }
            
            const targetInput = searchInput || document.querySelector('input[name="searchCtrNm"]');
            
            targetInput.value = '주차장';
            targetInput.dispatchEvent(new Event('input', { bubbles: true }));
            targetInput.dispatchEvent(new Event('change', { bubbles: true }));
            
            let searchBtn = document.getElementById('searchBtn');
            
            if (!searchBtn) {
                const buttons = document.querySelectorAll('button, input[type="button"], input[type="submit"]');
                for (let btn of buttons) {
                    const text = (btn.innerText || btn.value || '').trim();
                    if (text.includes('검색') || text.includes('조회')) {
                        searchBtn = btn;
                        break;
                    }
                }
            }
            
            if (searchBtn) {
                searchBtn.click();
                return { success: true, method: 'button click', inputId: targetInput.id };
            }
            
            const form = targetInput.closest('form');
            if (form) {
                form.submit();
                return { success: true, method: 'form submit' };
            }
            
            return { success: false, error: 'no submit method' };
        }""")
        
        print(f"메인 페이지 검색 결과: {json.dumps(search_result, ensure_ascii=False)}")
    
    if search_result.get('success'):
        print(f"✓ 검색 방법: {search_result.get('method')}")
        time.sleep(12)
        
        try:
            page.wait_for_load_state('networkidle', timeout=20000)
            print("✓ 검색 결과 로딩 완료")
        except:
            print("⚠️ 로딩 타임아웃")
    else:
        print(f"⚠️ 검색 실패: {search_result.get('error')}")
        if 'visibleTextInputs' in search_result:
            print("\n보이는 text input 목록:")
            for inp in search_result.get('visibleTextInputs', []):
                print(f"  {json.dumps(inp, ensure_ascii=False)}")
    
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
    
    # JavaScript로 테이블 데이터 추출
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
        
        const listItems = document.querySelectorAll('div[class*="list"] > div, ul[class*="list"] > li, article');
        console.log('리스트 아이템 개수:', listItems.length);
        
        listItems.forEach((item, idx) => {
            const text = item.innerText || '';
            if ((text.includes('주차') || text.includes('주차장')) && text.length > 20 && text.length < 2000) {
                console.log('리스트', idx, '주차장 발견');
                
                let link = '';
                const linkElem = item.querySelector('a[href]');
                if (linkElem) {
                    link = linkElem.href;
                }
                
                const lines = text.split('\\n').map(line => line.trim()).filter(line => line);
                
                results.push({
                    texts: lines,
                    link: link,
                    imgSrc: '',
                    rowText: text
                });
            }
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
                '이미지': item['imgSrc']
            }
            
            all_parking_data.append(parking_info)
            print(f"  ✓ 추가: {parking_info['공고번호']} - {parking_info['물건명주소'][:50]}")
        
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
    
    # 7. 슬랙 전송
    if slack_webhook_url and len(all_parking_data) > 0:
        print("\n=== 7. 슬랙 전송 ===")
        
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
