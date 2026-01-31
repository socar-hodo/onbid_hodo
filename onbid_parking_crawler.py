import os
import time
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime


class OnbidParkingCrawler:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.onbid_id = os.environ.get('ONBID_ID', '')
        self.onbid_pw = os.environ.get('ONBID_PW', '')
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
            print("✓ Playwright 브라우저 설정 완료")
        except Exception as e:
            print(f"✗ 브라우저 설정 실패: {e}")
            raise
    
    def login(self):
        """온비드 로그인"""
        try:
            print("온비드 로그인 시도 중...")
            self.page.goto('https://www.onbid.co.kr', wait_until='networkidle')
            time.sleep(2)
            
            # 로그인 버튼 찾아서 클릭
            login_selector = 'a[href*="login"], button:has-text("로그인")'
            self.page.click(login_selector, timeout=10000)
            time.sleep(2)
            
            # 아이디/비밀번호 입력
            self.page.fill('input[name="id"], input#id, input[type="text"]', self.onbid_id)
            self.page.fill('input[name="pw"], input#pw, input[type="password"]', self.onbid_pw)
            
            # 로그인 버튼 클릭
            self.page.click('button[type="submit"], button:has-text("로그인")')
            time.sleep(3)
            
            print("✓ 온비드 로그인 완료")
            
        except Exception as e:
            print(f"✗ 로그인 실패: {e}")
            # 스크린샷 저장
            self.page.screenshot(path='login_error.png')
            raise
    
    def navigate_to_parking_list(self):
        """주차장 목록 페이지로 이동"""
        try:
            print("주차장 목록 페이지로 이동 중...")
            
            # 부동산 메뉴 클릭
            self.page.click('text=부동산', timeout=10000)
            time.sleep(1)
            
            # 공고 클릭
            self.page.click('text=공고', timeout=10000)
            time.sleep(2)
            
            # 주차장 체크박스 찾아서 클릭
            # 여러 가능한 선택자 시도
            parking_selectors = [
                'input[value="주차장"]',
                'input[type="checkbox"]:has-text("주차장")',
                'label:has-text("주차장") input'
            ]
            
            for selector in parking_selectors:
                try:
                    if self.page.locator(selector).count() > 0:
                        self.page.check(selector)
                        print(f"✓ 주차장 필터 체크 완료")
                        break
                except:
                    continue
            
            # 검색 버튼 클릭
            self.page.click('button:has-text("검색"), button.search', timeout=10000)
            time.sleep(2)
            
            print("✓ 주차장 목록 페이지 이동 완료")
            
        except Exception as e:
            print(f"✗ 페이지 이동 실패: {e}")
            self.page.screenshot(path='navigation_error.png')
            raise
    
    def extract_parking_from_table(self):
        """현재 페이지에서 주차장 정보 추출"""
        try:
            # 테이블 행 가져오기
            rows = self.page.locator('table tbody tr').all()
            
            if not rows:
                print("테이블에서 행을 찾을 수 없습니다.")
                return []
            
            page_parkings = []
            
            for row in rows:
                try:
                    cells = row.locator('td').all()
                    
                    if len(cells) < 8:
                        continue
                    
                    parking_info = {
                        '공고번호': cells[0].inner_text().strip(),
                        '사건번호': cells[1].inner_text().strip(),
                        '물건종류': cells[2].inner_text().strip(),
                        '소재지': cells[3].inner_text().strip(),
                        '감정가': cells[4].inner_text().strip(),
                        '최저가': cells[5].inner_text().strip(),
                        '입찰일시': cells[6].inner_text().strip(),
                        '상태': cells[7].inner_text().strip(),
                    }
                    
                    # 주차장만 필터링
                    if '주차장' in parking_info['물건종류']:
                        print(f"  ✓ 주차장 발견: {parking_info['소재지']}")
                        page_parkings.append(parking_info)
                
                except Exception as e:
                    print(f"  행 추출 중 에러: {e}")
                    continue
            
            return page_parkings
            
        except Exception as e:
            print(f"✗ 테이블 추출 실패: {e}")
            return []
    
    def crawl_parking_list(self):
        """주차장 목록 크롤링"""
        print("=" * 60)
        print(f"주차장 크롤링 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        try:
            # 100개씩 보기 설정
            try:
                self.page.select_option('select[name="pageSize"]', '100')
                time.sleep(2)
            except:
                print("100개씩 보기 설정 실패, 기본값 사용")
            
            page_num = 1
            
            while True:
                print(f"\n현재 페이지: {page_num}")
                
                # 현재 페이지에서 주차장 추출
                page_parkings = self.extract_parking_from_table()
                self.parking_data.extend(page_parkings)
                
                # 다음 페이지 버튼 찾기
                try:
                    next_btn = self.page.locator('a.next, a:has-text("다음")').first
                    
                    if next_btn.is_visible() and not next_btn.get_attribute('class') or 'disabled' not in next_btn.get_attribute('class'):
                        next_btn.click()
                        time.sleep(2)
                        page_num += 1
                    else:
                        break
                except:
                    print("다음 페이지 없음 또는 마지막 페이지")
                    break
                
                # 안전을 위해 최대 10페이지까지만
                if page_num > 10:
                    print("최대 페이지 도달 (10페이지)")
                    break
            
            print(f"\n총 {len(self.parking_data)}개 주차장 발견")
            
        except Exception as e:
            print(f"✗ 크롤링 중 오류: {e}")
            self.page.screenshot(path='crawling_error.png')
    
    def format_slack_message(self, parking_info):
        """슬랙 메시지 포맷"""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🅿️ 주차장 경매",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*공고번호*\n{parking_info['공고번호']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*사건번호*\n{parking_info['사건번호']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*물건종류*\n{parking_info['물건종류']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*소재지*\n{parking_info['소재지']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*감정가*\n{parking_info['감정가']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*최저가*\n{parking_info['최저가']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*입찰일시*\n{parking_info['입찰일시']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*상태*\n{parking_info['상태']}"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]
        
        return blocks
    
    def send_to_slack(self):
        """슬랙으로 결과 전송"""
        if not self.parking_data:
            # 결과 없을 때 메시지
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🅿️ 온비드 주차장 경매 정보",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{datetime.now().strftime('%Y년 %m월 %d일')}*\n\n검색된 주차장이 없습니다."
                    }
                }
            ]
            requests.post(self.slack_webhook_url, json={"blocks": blocks})
            return
        
        # 헤더 전송
        header_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🅿️ 온비드 주차장 경매 정보",
                    "emoji": True
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"📅 {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')} | 총 {len(self.parking_data)}개 발견"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]
        
        requests.post(self.slack_webhook_url, json={"blocks": header_blocks})
        time.sleep(1)
        
        # 각 주차장 정보 전송
        for parking in self.parking_data[:20]:  # 최대 20개까지만
            blocks = self.format_slack_message(parking)
            requests.post(self.slack_webhook_url, json={"blocks": blocks})
            time.sleep(1)
        
        print(f"✓ 슬랙 전송 완료: {len(self.parking_data)}개 (최대 20개 표시)")
    
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
            self.setup_browser()
            self.login()
            self.navigate_to_parking_list()
            self.crawl_parking_list()
            self.send_to_slack()
            
        except Exception as e:
            print(f"✗ 실행 중 오류: {e}")
            
            # 에러 메시지를 슬랙으로 전송
            if self.slack_webhook_url:
                error_blocks = [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "⚠️ 크롤링 오류 발생",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"```{str(e)}```"
                        }
                    }
                ]
                requests.post(self.slack_webhook_url, json={"blocks": error_blocks})
            
        finally:
            self.cleanup()


if __name__ == '__main__':
    crawler = OnbidParkingCrawler()
    crawler.run()
