import json
import re
import requests
from urllib.parse import quote
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone

@@ -129,20 +130,6 @@ def slack_error(msg):
            if gonggo_no in sent_gonggos:
                continue

            # ===============================
            # 상세이동 링크 찾기
            # ===============================
            detail_a = row.query_selector("a[href*='fn_selectDetail']")
            if not detail_a:
                continue

            href = detail_a.get_attribute("href")

            # fn_selectDetail 파라미터 추출
            nums = re.findall(r"'([^']+)'", href)
            if len(nums) != 6:
                continue

            # ===============================
            # 주소 추출
            # ===============================
@@ -187,17 +174,14 @@ def slack_error(msg):
            status = status_match.group() if status_match else "-"

            # ===============================
            # ✅ 상세 URL 생성 (View 페이지)
            # ✅ Slack에서 무조건 열리게 하는 링크 (2-step)
            # ===============================
            detail_url = (
            link_main = "https://www.onbid.co.kr"

            link_search = (
                "https://www.onbid.co.kr/op/cta/cltrdtl/"
                "collateralDetailRealEstateView.do?"
                f"cltrHstrNo={nums[0]}"
                f"&plnmNo={nums[1]}"
                f"&pbctNo={nums[2]}"
                f"&cltrNo={nums[3]}"
                f"&rnum={nums[4]}"
                f"&seq={nums[5]}"
                "collateralDetailRealEstateList.do?search="
                + quote(gonggo_no.strip())
            )

            # 신규 데이터 저장
@@ -209,7 +193,8 @@ def slack_error(msg):
                "price": price,
                "status": status,
                "view": view,
                "link": detail_url
                "link_main": link_main,
                "link_search": link_search
            })

            new_gonggos.add(gonggo_no)
@@ -268,9 +253,13 @@ def slack_error(msg):
                         {"type": "mrkdwn",
                          "text": f"*👁 조회수*\n{item['view']}"}
                     ]},
                    # ✅ 링크 2개 제공
                    {"type": "section",
                     "text": {"type": "mrkdwn",
                              "text": f"🔗 <{item['link']}|공고 상세보기>"}},
                              "text":
                                  f"🔗 <{item['link_main']}|온비드 홈 먼저 클릭>\n"
                                  f"➡️ <{item['link_search']}|공고 검색 바로가기>"
                              }},
                    {"type": "divider"}
                ]
            })
