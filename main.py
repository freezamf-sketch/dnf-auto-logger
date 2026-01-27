import os
import json
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import gspread
from google.oauth2.service_account import Credentials
from pyvirtualdisplay import Display

# ==========================================
# 📋 [사용자 설정 영역]
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1FpHGeP8bnyla86QA8fqQiAFVatNk-lDG9oNPdR9hldc/edit?gid=1075685695#gid=1075685695"

# 여기에 URL 4개를 꼼꼼히 채워주세요
ITEMS = [
    {"url": "http://dnfnow.xyz/item?item_idx=bfc7bb0aefe4d0c432ebf77836e68e3c", "sheet_name": "Sheet1"},
    {"url": "http://dnfnow.xyz/item?item_idx=4a737b2ae337a57260ca4663ce6a9bb0s3", "sheet_name": "Sheet2"},
    {"url": "http://dnfnow.xyz/item?item_idx=fac4ce61d490d3a006025c797abb5950", "sheet_name": "Sheet3"},
    {"url": "http://dnfnow.xyz/item?item_idx=bb5a6aeb6b44bbdce835679bef4335b5", "sheet_name": "Sheet4"}
]

START_ROW = 5
START_COL = 2
# ==========================================

# 가상 디스플레이는 한 번만 켭니다
display = Display(visible=0, size=(1920, 1080))
display.start()

def get_data_from_url(target_url):
    """
    브라우저를 매번 새로 띄워서 데이터를 가져오는 함수 (안정성 최우선)
    """
    print(f"🔄 브라우저 시작: {target_url}")
    
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # 메모리 부족 방지 옵션 추가
    chrome_options.add_argument("--disable-gpu")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        driver.get(target_url)
        wait = WebDriverWait(driver, 30)
        
        # 24시간 행이 로딩될 때까지 대기
        row_24h_xpath = "//td[contains(text(), '24시간내')]/parent::tr"
        wait.until(EC.presence_of_element_located((By.XPATH, row_24h_xpath)))
        
        # [중요] 페이지 로딩 후 3초 강제 대기 (데이터 렌더링 시간 확보)
        time.sleep(3)

        def clean_text(text):
            return re.sub(r'[^\d]', '', text)

        row_24 = driver.find_element(By.XPATH, row_24h_xpath)
        cols_24 = row_24.find_elements(By.TAG_NAME, "td")
        data_24 = [clean_text(cols_24[i].text) for i in range(1, 4)]

        row_72_xpath = "//td[contains(text(), '72시간내')]/parent::tr"
        row_72 = driver.find_element(By.XPATH, row_72_xpath)
        cols_72 = row_72.find_elements(By.TAG_NAME, "td")
        data_72 = [clean_text(cols_72[i].text) for i in range(1, 4)]
        
        return data_24 + data_72

    except Exception as e:
        print(f"⚠️ 크롤링 에러 ({target_url}): {e}")
        return None
    finally:
        # 작업 끝나면 브라우저를 확실히 종료
        driver.quit()

def run():
    if 'GDRIVE_API_KEY' not in os.environ:
        print("❌ Secret 키 없음")
        return

    json_key = json.loads(os.environ['GDRIVE_API_KEY'])
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(json_key, scopes=scope)
    client = gspread.authorize(creds)
    
    try:
        doc = client.open_by_url(SHEET_URL)
    except Exception as e:
        print(f"❌ 시트 접속 실패: {e}")
        return

    # 아이템 목록 순회
    for i, item in enumerate(ITEMS):
        if "여기에" in item['url']:
            print(f"⏭️ [Skip] {item['sheet_name']} URL 미설정")
            continue

        print(f"\n--- [{i+1}/4] 처리 중: {item['sheet_name']} ---")
        
        # 1. 데이터 가져오기 (브라우저 열고 닫기 포함)
        data = get_data_from_url(item['url'])
        
        if data:
            # 2. 시트 저장
            try:
                worksheet = doc.worksheet(item['sheet_name'])
                
                col_values = worksheet.col_values(START_COL)
                next_row = max(START_ROW, len(col_values) + 1)
                
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                final_data = [now_str] + data
                
                cell_range = f"B{next_row}:H{next_row}"
                worksheet.update(range_name=cell_range, values=[final_data])
                print(f"✅ 저장 완료")
                
            except Exception as e:
                print(f"❌ 저장 실패: {e}")
        else:
            print(f"❌ 데이터 수집 실패")
        
        # [중요] 다음 아이템 넘어가기 전 5초 휴식 (봇 탐지 방지 및 API 보호)
        time.sleep(5)

    display.stop()

if __name__ == "__main__":
    run()
