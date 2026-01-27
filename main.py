import os
import json
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import gspread
from google.oauth2.service_account import Credentials

# --- 설정 ---
TARGET_URL = "http://dnfnow.xyz/item?item_idx=bfc7bb0aefe4d0c432ebf77836e68e3c"
SPREADSHEET_NAME = 'DNF_Data_Log'
START_ROW = 5
START_COL = 2

def get_dnf_data():
    print("브라우저 시작 중...")
    
    # [중요] GitHub Actions 환경을 위한 강력한 옵션
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") # 최신 헤드리스 모드
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # 드라이버 자동 설치 및 실행
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        print(f"사이트 접속: {TARGET_URL}")
        driver.get(TARGET_URL)
        wait = WebDriverWait(driver, 30) # 대기 시간 30초로 증가
        
        row_24h_xpath = "//td[contains(text(), '24시간내')]/parent::tr"
        wait.until(EC.presence_of_element_located((By.XPATH, row_24h_xpath)))
        time.sleep(5) # 데이터 로딩 넉넉히 대기

        def clean_text(text):
            return re.sub(r'[^\d]', '', text)

        row_24 = driver.find_element(By.XPATH, row_24h_xpath)
        cols_24 = row_24.find_elements(By.TAG_NAME, "td")
        data_24 = [clean_text(cols_24[i].text) for i in range(1, 4)]

        row_72_xpath = "//td[contains(text(), '72시간내')]/parent::tr"
        row_72 = driver.find_element(By.XPATH, row_72_xpath)
        cols_72 = row_72.find_elements(By.TAG_NAME, "td")
        data_72 = [clean_text(cols_72[i].text) for i in range(1, 4)]
        
        print("데이터 수집 성공")
        return data_24 + data_72

    except Exception as e:
        print(f"Error 발생: {e}")
        return None
    finally:
        driver.quit()

def run():
    print("스크립트 실행 시작")
    if 'GDRIVE_API_KEY' not in os.environ:
        print("에러: GDRIVE_API_KEY가 없습니다. Secret 설정을 확인하세요.")
        return

    json_key = json.loads(os.environ['GDRIVE_API_KEY'])
    
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(json_key, scopes=scope)
    client = gspread.authorize(creds)
    
    try:
        sh = client.open(SPREADSHEET_NAME).sheet1
    except Exception as e:
        print(f"에러: 구글 시트 '{SPREADSHEET_NAME}'를 찾을 수 없거나 권한이 없습니다.")
        print(f"상세 에러: {e}")
        return
    
    data = get_dnf_data()
    if data:
        col_values = sh.col_values(START_COL)
        next_row = max(START_ROW, len(col_values) + 1)
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_data = [now_str] + data
        
        # 행 단위 업데이트 (범위 지정 방식 수정)
        cell_range = f"B{next_row}:H{next_row}"
        sh.update(range_name=cell_range, values=[final_data])
        print(f"구글 시트 저장 완료: {cell_range}")
    else:
        print("데이터 수집 실패로 인해 저장하지 않았습니다.")

if __name__ == "__main__":
    run()
