import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from datetime import datetime


class OnbidParkingCrawler:
    def __init__(self):
        self.driver = None
        self.onbid_id = os.environ.get('ONBID_ID', '')
        self.onbid_pw = os.environ.get('ONBID_PW', '')
        self.slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
        self.parking_data = []
        
    def setup_driver(self):
        """Chrome 드라이버 설정"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # 백그라운드 실행
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(10)
        
    def login(self):
        """온비드 로그인"""
        try:
            self.driver.get('https://www.onbid.co.kr')
            
            # 로그인 버튼 클릭
            login_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[href*="login"]'))
            )
            login_btn.click()
            
            # 아이디/비밀번호 입력
            id_input = self.driver.find_element(By.ID, 'id')
            pw_input = self.driver.find_element(By.ID, 'pw')
            
            id_input.send_keys(self.onbid_id)
            pw_input.send_keys(self.onbid_pw)
            
            # 로그인 버튼 클릭
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
            submit_btn.click()
            
            time.sleep(2)
            print("✓ 온비드 로그인 완료")
            
        except Exception as e:
            print(f"✗ 로그인 실패: {e}")
            raise
    
    def navigate_to_parking_list(self):
        """주차장 목록 페이지로 이동"""
        try:
            # 부동산 메뉴 클릭
            real_estate = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.LINK_TEXT, '부동산'))
            )
            real_estate.click()
            time.sleep(1)
            
            # 공고 클릭
            gonggo = self.driver.find_element(By.LINK_TEXT, '공고')
            gonggo.click()
            time.sleep(1)
            
            # 검색 조건 설정 (주차장 필터)
            # 물건 종류에서 '주차장' 체크
            parking_checkbox = self.driver.find_element(By.XPATH, "//input[@value='주차장']")
            if not parking_checkbox.is_selected():
                parking_checkbox.click()
            
            # 검색 버튼 클릭
            search_btn = self.driver.find_element(By.CSS_SELECTOR, 'button.search')
            search_btn.click()
            
            time.sleep(2)
            print("✓ 주차장 목록 페이지 이동 완료")
            
        except Exception as e:
            print(f"✗ 페이지 이동 실패: {e}")
            raise
    
    def extract_parking_info(self, row_index):
        """주차장 정보 추출"""
        try:
            # 공고 테이블의 특정 행에서 정보 추출
            row = self.driver.find_elements(By.CSS_SELECTOR, 'table.list tbody tr')[row_index]
            
            cells = row.find_elements(By.TAG_NAME, 'td')
            
            parking_info = {
                '공고번호': cells[0].text.strip(),
                '사건번호': cells[1].text.strip(),
                '물건종류': cells[2].text.strip(),
                '소재지': cells[3].text.strip(),
                '감정가': cells[4].text.strip(),
                '최저가': cells[5].text.strip(),
                '입찰일시': cells[6].text.strip(),
                '상태': cells[7].text.strip(),
            }
            
            # 주차장만 필터링
            if '주차장' in parking_info['물건종류']:
                return parking_info
            
            return None
            
        except Exception as e:
            print(f"✗ 정보 추출 실패 (행 {row_index}): {e}")
            return None
    
    def get_detail_info(self, announce_no):
        """공고 상세 정보 가져오기"""
        try:
            # 공고번호 클릭하여 상세 페이지로 이동
            detail_link = self.driver.find_element(
                By.XPATH, 
                f"//td[contains(text(), '{announce_no}')]/a"
            )
            detail_link.click()
            
            time.sleep(2)
            
            # 상세 정보 추출
            detail_info = {}
            
            # 물건명
            try:
                detail_info['물건명'] = self.driver.find_element(
                    By.CSS_SELECTOR, 
                    '.detail-title'
                ).text.strip()
            except:
                detail_info['물건명'] = '정보 없음'
            
            # 주소
            try:
                detail_info['상세주소'] = self.driver.find_element(
                    By.CSS_SELECTOR, 
                    '.address'
                ).text.strip()
            except:
                detail_info['상세주소'] = '정보 없음'
            
            # 면적
            try:
                detail_info['면적'] = self.driver.find_element(
                    By.XPATH, 
                    "//th[contains(text(), '면적')]/following-sibling::td"
                ).text.strip()
            except:
                detail_info['면적'] = '정보 없음'
            
            # 상세 페이지 URL
            detail_info['상세페이지'] = self.driver.current_url
            
            self.driver.back()
            time.sleep(1)
            
            return detail_info
            
        except Exception as e:
            print(f"✗ 상세 정보 가져오기 실패: {e}")
            return {}
    
    def crawl_parking_list(self):
        """주차장 목록 크롤링"""
        print("=" * 60)
        print(f"주차장 크롤링 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        try:
            # 100개씩 보기 설정
            select_100 = self.driver.find_element(By.CSS_SELECTOR, 'select[name="pageSize"]')
            select_100.click()
            option_100 = self.driver.find_element(By.CSS_SELECTOR, 'option[value="100"]')
            option_100.click()
            time.sleep(2)
            
            page = 1
            
            while True:
                print(f"\n현재 페이지: {page}")
                
                # 현재 페이지의 모든 행 개수
                rows = self.driver.find_elements(By.CSS_SELECTOR, 'table.list tbody tr')
                
                for i in range(len(rows)):
                    parking_info = self.extract_parking_info(i)
                    
                    if parking_info:
                        print(f"  ✓ 주차장 발견: {parking_info['소재지']}")
                        
                        # 상세 정보 가져오기
                        detail_info = self.get_detail_info(parking_info['공고번호'])
                        parking_info.update(detail_info)
                        
                        self.parking_data.append(parking_info)
                
                # 다음 페이지로 이동
                try:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, 'a.next')
                    if 'disabled' in next_btn.get_attribute('class'):
                        break
                    next_btn.click()
                    time.sleep(2)
                    page += 1
                except:
                    break
            
            print(f"\n총 {len(self.parking_data)}개 주차장 발견")
            
        except Exception as e:
            print(f"✗ 크롤링 중 오류: {e}")
    
    def format_slack_message(self, parking_info):
        """슬랙 메시지 포맷"""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🅿️ {parking_info.get('물건명', '주차장')}",
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
                        "text": f"*소재지*\n{parking_info['소재지']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*상세주소*\n{parking_info.get('상세주소', '정보 없음')}"
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
                        "text": f"*면적*\n{parking_info.get('면적', '정보 없음')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*입찰일시*\n{parking_info['입찰일시']}"
                    }
                ]
            }
        ]
        
        # 상세 페이지 링크
        if parking_info.get('상세페이지'):
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🔗 상세 정보 보기",
                            "emoji": True
                        },
                        "url": parking_info['상세페이지'],
                        "style": "primary"
                    }
                ]
            })
        
        blocks.append({"type": "divider"})
        
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
        for parking in self.parking_data:
            blocks = self.format_slack_message(parking)
            requests.post(self.slack_webhook_url, json={"blocks": blocks})
            time.sleep(1)  # API 제한 고려
        
        print(f"✓ 슬랙 전송 완료: {len(self.parking_data)}개")
    
    def run(self):
        """크롤러 실행"""
        try:
            self.setup_driver()
            self.login()
            self.navigate_to_parking_list()
            self.crawl_parking_list()
            self.send_to_slack()
            
        except Exception as e:
            print(f"✗ 실행 중 오류: {e}")
            
            # 에러 메시지를 슬랙으로 전송
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
            if self.driver:
                self.driver.quit()
                print("✓ 브라우저 종료")


if __name__ == '__main__':
    crawler = OnbidParkingCrawler()
    crawler.run()
