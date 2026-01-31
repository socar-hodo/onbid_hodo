import os
import time
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime


class OnbidParkingCrawler:
    """온비드 통합검색으로 주차장 크롤링"""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
        self.parking_data = []
        
    def setup_browser(self):
        """Playwright 브라우저 설정"""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            self.page = self.browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            self.page.set_default_timeout(30000)
            print("✓ 브라우저 설정 완료")
        except Exception as e:
            print(f"✗ 브라우저 설정 실패: {e}")
            raise
    
    def search_parking(self):
        """온비드 부동산 공고 페이지에서 주차장 검색"""
        try:
            print("\n=== 온비드 부동산 공고 페이지 접속 ===")
            
            # 부동산 공고 목록 페이지로 직접 이동
            search_url = 'https://www.onbid.co.kr/op/svc/getSvcGonggoList.do?searchWord=%EC%A3%BC%EC%B0%A8%EC%9E%A5'
            # URL 인코딩: 주차장 = %EC%A3%BC%EC%B0%A8%EC%9E%A5
            
            print(f"URL: {search_url}")
            self.page.goto(search_url, timeout=60000)
            self.page.wait_for_load_state('networkidle')
            time.sleep(5)
            
            print(f"✓ 페이지 로드 완료 - 현재 URL: {self.page.url}")
            
            # 페이지 스크린샷
            self.page.screenshot(path='search_page.png', full_page=True)
            print("스크린샷 저장: search_page.png")
            
            # URL에 검색어가 포함되어 있는지 확인
            if 'getSvcGonggoList' in self.page.url:
                print("✓ 공고 목록 페이지 접근 성공")
                return True
            else:
                print(f"⚠️ 예상과 다른 페이지: {self.page.url}")
                return False
            
        except Exception as e:
            print(f"✗ 페이지 접속 실패: {e}")
            try:
                self.page.screenshot(path='search_error.png', full_page=True)
            except:
                pass
            return False
    
    def extract_parking_data(self):
        """검색 결과에서 주차장 데이터 추출"""
        try:
            print("\n=== 검색 결과 데이터 추출 ===")
            
            # 100개씩 보기 설정 시도
            try:
                page_size_selectors = [
                    'select[name="pageSize"]',
                    'select.page-size'
                ]
                for selector in page_size_selectors:
                    if self.page.locator(selector).count() > 0:
                        self.page.select_option(selector, '100')
                        print("✓ 100개씩 보기 설정")
                        time.sleep(2)
                        break
            except:
                print("100개씩 보기 설정 실패 (기본값 사용)")
            
            page_num = 1
            total_extracted = 0
            
            while page_num <= 5:  # 최대 5페이지까지
                print(f"\n--- 페이지 {page_num} 처리 중 ---")
                
                # 테이블 찾기
                table_selectors = [
                    'table.tbl-list tbody',
                    'table.list tbody',
                    'table tbody',
                    '.list-table tbody'
                ]
                
                table_found = None
                for selector in table_selectors:
                    if self.page.locator(selector).count() > 0:
                        table_found = selector
                        print(f"✓ 테이블 발견: {selector}")
                        break
                
                if not table_found:
                    print("⚠️ 테이블을 찾을 수 없습니다")
                    break
                
                # 행 추출
                rows = self.page.locator(f'{table_found} tr').all()
                print(f"총 {len(rows)}개 행 발견")
                
                page_count = 0
                for idx, row in enumerate(rows):
                    try:
                        cells = row.locator('td').all()
                        
                        if len(cells) < 5:
                            continue
                        
                        # 텍스트 추출
                        cell_texts = []
                        for cell in cells:
                            try:
                                text = cell.inner_text().strip()
                                cell_texts.append(text)
                            except:
                                cell_texts.append('')
                        
                        # 주차장 키워드 확인
                        row_text = ' '.join(cell_texts)
                        if '주차' in row_text or '駐車' in row_text:
                            print(f"  ✓ 주차장 발견 (행 {idx+1})")
                            
                            # 데이터 구조화 (온비드 테이블 구조에 맞게)
                            parking_info = {
                                '데이터': cell_texts
                            }
                            
                            # 일반적인 온비드 테이블 구조 (8-10열)
                            if len(cell_texts) >= 8:
                                parking_info = {
                                    '공고번호': cell_texts[0] if len(cell_texts) > 0 else '',
                                    '사건번호': cell_texts[1] if len(cell_texts) > 1 else '',
                                    '물건종류': cell_texts[2] if len(cell_texts) > 2 else '',
                                    '소재지': cell_texts[3] if len(cell_texts) > 3 else '',
                                    '감정가': cell_texts[4] if len(cell_texts) > 4 else '',
                                    '최저가': cell_texts[5] if len(cell_texts) > 5 else '',
                                    '입찰일시': cell_texts[6] if len(cell_texts) > 6 else '',
                                    '상태': cell_texts[7] if len(cell_texts) > 7 else '',
                                }
                            else:
                                # 열이 적으면 유연하게 처리
                                parking_info = {
                                    '정보1': cell_texts[0] if len(cell_texts) > 0 else '',
                                    '정보2': cell_texts[1] if len(cell_texts) > 1 else '',
                                    '정보3': cell_texts[2] if len(cell_texts) > 2 else '',
                                    '정보4': cell_texts[3] if len(cell_texts) > 3 else '',
                                    '정보5': cell_texts[4] if len(cell_texts) > 4 else '',
                                }
                            
                            self.parking_data.append(parking_info)
                            page_count += 1
                            total_extracted += 1
                    
                    except Exception as e:
                        print(f"  행 처리 중 에러: {e}")
                        continue
                
                print(f"페이지 {page_num}에서 {page_count}개 추출 (누적: {total_extracted}개)")
                
                # 다음 페이지로 이동
                try:
                    next_selectors = [
                        'a.next:not(.disabled)',
                        'a:has-text("다음"):not(.disabled)',
                        '.pagination a.next'
                    ]
                    
                    next_found = False
                    for selector in next_selectors:
                        try:
                            next_btn = self.page.locator(selector).first
                            if next_btn.is_visible():
                                print("다음 페이지로 이동 중...")
                                next_btn.click()
                                time.sleep(3)
                                self.page.wait_for_load_state('networkidle')
                                next_found = True
                                break
                        except:
                            continue
                    
                    if not next_found:
                        print("더 이상 페이지 없음")
                        break
                    
                except Exception as e:
                    print(f"페이지 이동 실패: {e}")
                    break
                
                page_num += 1
            
            print(f"\n✓ 총 {len(self.parking_data)}개 주차장 데이터 수집 완료")
            
        except Exception as e:
            print(f"✗ 데이터 추출 실패: {e}")
    
    def send_to_slack(self):
        """슬랙으로 결과 전송"""
        if not self.slack_webhook_url:
            print("⚠️ Slack Webhook URL이 설정되지 않았습니다")
            return
        
        try:
            # 헤더 전송
            header_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🅿️ 온비드 주차장 검색 결과",
                        "emoji": True
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"📅 {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')} | 검색어: *주차장*"
                        }
                    ]
                }
            ]
            
            if not self.parking_data:
                header_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚠️ 검색된 주차장이 없습니다.\nGitHub Actions의 Artifacts에서 스크린샷을 확인해주세요."
                    }
                })
            else:
                header_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"✅ 총 *{len(self.parking_data)}개* 주차장 발견 (최대 20개 표시)"
                    }
                })
            
            header_blocks.append({"type": "divider"})
            
            requests.post(self.slack_webhook_url, json={"blocks": header_blocks}, timeout=10)
            time.sleep(1)
            
            # 각 주차장 정보 전송 (최대 20개)
            for idx, parking in enumerate(self.parking_data[:20], 1):
                fields = []
                
                for key, value in parking.items():
                    if value and value.strip():
                        fields.append({
                            "type": "mrkdwn",
                            "text": f"*{key}*\n{value[:100]}"
                        })
                
                blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{idx}. 주차장 정보*"
                        }
                    },
                    {
                        "type": "section",
                        "fields": fields[:8]  # 최대 8개 필드
                    },
                    {"type": "divider"}
                ]
                
                requests.post(self.slack_webhook_url, json={"blocks": blocks}, timeout=10)
                time.sleep(1)
            
            print("✓ 슬랙 전송 완료")
            
        except Exception as e:
            print(f"✗ 슬랙 전송 실패: {e}")
    
    def cleanup(self):
        """리소스 정리"""
        try:
            if self.page:
                self.page.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            print("✓ 브라우저 종료")
        except Exception as e:
            print(f"정리 중 에러: {e}")
    
    def run(self):
        """크롤러 실행"""
        try:
            print("=" * 70)
            print(f"온비드 주차장 크롤링 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 70)
            
            self.setup_browser()
            
            if self.search_parking():
                self.extract_parking_data()
                self.send_to_slack()
            else:
                print("✗ 검색 실패")
                if self.slack_webhook_url:
                    error_blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "⚠️ 온비드 검색 실패\nGitHub Actions의 Artifacts에서 스크린샷을 확인해주세요."
                            }
                        }
                    ]
                    requests.post(self.slack_webhook_url, json={"blocks": error_blocks})
            
            print("\n" + "=" * 70)
            print("크롤링 완료")
            print("=" * 70)
            
        except Exception as e:
            print(f"\n✗ 치명적 오류: {e}")
            
            # 에러 메시지를 슬랙으로 전송
            if self.slack_webhook_url:
                try:
                    error_blocks = [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": "⚠️ 크롤링 오류",
                                "emoji": True
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"```{str(e)[:500]}```"
                            }
                        }
                    ]
                    requests.post(self.slack_webhook_url, json={"blocks": error_blocks})
                except:
                    pass
            
        finally:
            self.cleanup()


if __name__ == '__main__':
    crawler = OnbidParkingCrawler()
    crawler.run()
