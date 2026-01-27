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

# --- [중요] 가상 디스플레이 설정 ---
from pyvirtualdisplay import Display
display = Display(visible=0, size=(1920, 1080))
display.start()

# --- 설정 ---
TARGET_URL = "http://dnfnow.xyz/item?item_idx=bfc7bb0aefe4d0c432ebf77836e68e3c"
SPREADSHEET_NAME = 'DNF_Data_Log'
START_ROW = 5
START_COL = 2

def get_dnf_data():
    print("브라우저 시작 중...")
    
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # headless 옵션을 뺍니다. (가상 디스플레이가 있으므로)
    chrome_options.add_argument("--window-size=1920,1080")
    
    # 크롬 드라이버는 시스템 경로에서 자동 탐색
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print(f"사이트 접속: {TARGET_URL}")
        driver.get(TARGET_URL)
        wait = WebDriverWait(driver, 30)
        
        row_24h_xpath = "//td[contains(text(), '24시간내')]/parent::tr"
        wait.until(EC.presence_of_element_located((By.XPATH, row_24h_xpath)))
        time.sleep(5) 

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
    if 'GDRIVE_API_KEY' not in os.environ:
        print("에러: Secret 설정 확인 필요")
        return

    json_key = json.loads(os.environ['GDRIVE_API_KEY'])
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(json_key, scopes=scope)
    client = gspread.authorize(creds)
    
    try:
        sh = client.open(SPREADSHEET_NAME).sheet1
    except Exception as e:
        print(f"시트 접속 에러: {e}")
        return
    
    data = get_dnf_data()
    if data:
        col_values = sh.col_values(START_COL)
        next_row = max(START_ROW, len(col_values) + 1)
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_data = [now_str] + data
        
        cell_range = f"B{next_row}:H{next_row}"
        sh.update(range_name=cell_range, values=[final_data])
        print(f"저장 완료: {cell_range}")

if __name__ == "__main__":
    run()
