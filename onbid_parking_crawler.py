from selenium import webdriver
from ONBID.webpage import gonggo
from ONBID.webpage import common
from ONBID.webpage import mulgun
from ONBID.webpage.gonggo import mulgun_detail, gonggo_detail_info  # 물건 상세 정보
from ONBID.webpage.gonggo import mulgun_area  # 면적 정보
from ONBID.webpage.gonggo import mulgun_locate_myungdo  # 위치 및 명도책임
from ONBID.webpage.gonggo import mulgun_gamjung  # 감정평가서
from ONBID.webpage.gonggo import mulgun_baebun  # 배분 정보
from ONBID.webpage.gonggo import mulgun_imdae  # 임대차 정보
from ONBID.webpage.gonggo import mulgun_file  # 사진, 위치도, 지적도 파일
from ONBID.webpage.gonggo import mulgun_ipchal_history  # 입찰 이력
from ONBID.webpage.gonggo import mulgun_ipcahl  # 회차별 입찰 정보


class ONBID_GONGGO:
    def __init__(self):
        self.driver: webdriver.Chrome = common.setup.get_driver()
        self.ID: str = ''  # 온비드 아이디 입력
        self.PW: str = ''  # 온비드 비밀번호 입력

    def pre_ipchal(self, announce_no: str) -> None:
        """
        :desc 입찰이력 페이지
        :param announce_no: 공고번호
        :return:
        """
        gonggo.setup.click_pre_ipchal(self.driver)

        gonggo.mulgun_ipchal_history.get_data(self.driver, announce_no)

        self.driver.back()

    def mulgun_detail(self, mulgun_index: int, announce_no: str) -> None:
        """
        :desc 물건 세부 정보 페이지
        :param mulgun_index: 물건 테이블 index
        :param announce_no: 해당 물건의 공고번호
        :return:
        """
        gonggo.setup.open_mulgun_detail_tab(self.driver, mulgun_index)

        mulgun_detail.get_data(self.driver, announce_no)  # 세부정보

        mulgun_area.get_data(self.driver, announce_no)  # 면적정보

        mulgun_locate_myungdo.get_data(self.driver, announce_no)  # 위치 및 부근현황, 명도이전책임

        mulgun_gamjung.get_data(self.driver, announce_no)  # 감정평가서

        mulgun_baebun.get_data(self.driver, announce_no)  # 배분

        mulgun_imdae.get_data(self.driver, announce_no)  # 임대

        mulgun_file.get_data(self.driver, announce_no)  # 사진, 지적도, 위치도

        mulgun_ipcahl.get_data(self.driver, announce_no)  # 회차별 입찰정보

        self.pre_ipchal(announce_no)  # 입찰 이력

        self.driver.back()
        gonggo.setup.move_to_mulgun_table(self.driver)

    def scan_mulgun_table(self, announce_no: str) -> None:
        """
        :desc 물건 테이블 페이지, 부동산 카테고리가 아닌 물건은 PASS
        :param announce_no: 공고번호
        :return: None
        """
        mulgun_index: int = 0

        while True:
            if mulgun.setup.is_table_end(self.driver, mulgun_index):
                break

            if gonggo.setup.is_mulgun_budongsan(self.driver, mulgun_index):
                self.mulgun_detail(mulgun_index, announce_no)

            mulgun_index = mulgun_index + 1

    def gonggo_mulgun_table(self, announce_no: str) -> None:
        """
        :desc 공고 물건 목록 테이블에 존재하는 물건 하나씩 방문
        :param announce_no: 공고 번호
        :return: None
        """
        gonggo.setup.open_gonggo_mulgun_table_tab(self.driver)
        gonggo.setup.set_elem_hundred(self.driver)

        while True:
            self.scan_mulgun_table(announce_no)
            if common.setup.next_page(self.driver):
                break

        gonggo.setup.close_gonggo_mulgun_table_tab(self.driver)

    def gonggo_detail(self, gonggo_index: int, gonggo_basic: dict) -> None:
        """
        :desc 공고 상세 정보 저장 -> 해당 공고 물건 목록 보기로 이동
        :param gonggo_index: 공고 테이블 몇번째에 있는지
        :param gonggo_basic: 공고 기본 정보 dictionary
        :return: None
        """
        gonggo.setup.gonggo_detail_click(self.driver, gonggo_index)

        gonggo_detail_info.get_data(self.driver, gonggo_basic)

        self.gonggo_mulgun_table(gonggo_basic['ANNOUNCE_NO'])

        self.driver.back()

    def gonggo_table(self) -> None:
        """
        :desc 공고 정보 저장 -> 공고 상세로 이동
        :return: None
        """
        gonggo_index: int = 0

        while True:
            if gonggo.setup.is_table_end(self.driver, gonggo_index):
                break

            if not gonggo.setup.is_cancel_gonggo(self.driver, gonggo_index):

                gonggo_basic: dict = gonggo.basic_info.get_data(self.driver, gonggo_index)

                self.gonggo_detail(gonggo_index, gonggo_basic)

            gonggo_index = gonggo_index + 1

    def home_page(self) -> None:
        """
        :desc 부동산 -> 공고 -> 공고목록 -> 공고일자 설정 후 검색 -> 100줄씩 정렬 -> 공고 목록 테이블 Loop
        :return: None
        """
        common.setup.click_budongsan(self.driver)

        gonggo.setup.click_gonggo(self.driver)

        gonggo.setup.set_gonggo_date(self.driver)

        gonggo.setup.search(self.driver)

        gonggo.setup.set_elem_hundred(self.driver)

        while True:
            self.gonggo_table()

            if common.setup.next_page(self.driver):
                break

    def start(self) -> None:
        """
        :desc 프로그램 전체 동작
        :return: None
        """
        common.setup.main_page(self.driver)

        common.login.login(self.driver, self.ID, self.PW)

        self.home_page()

        self.driver.close()
        self.driver.quit()


if __name__ == '__main__':
    func = ONBID_GONGGO()
    func.start()
