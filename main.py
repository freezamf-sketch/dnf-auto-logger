import os
import json
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
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
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        driver.get(TARGET_URL)
        wait = WebDriverWait(driver, 20)
        
        row_24h_xpath = "//td[contains(text(), '24시간내')]/parent::tr"
        wait.until(EC.presence_of_element_located((By.XPATH, row_24h_xpath)))
        time.sleep(3) # 데이터 로딩 대기

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
        print(f"Error: {e}")
        return None
    finally:
        driver.quit()

def run():
    # GitHub Secret에서 키 가져오기
    json_key = json.loads(os.environ['GDRIVE_API_KEY'])
    
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(json_key, scopes=scope)
    client = gspread.authorize(creds)
    
    sh = client.open(SPREADSHEET_NAME).sheet1
    
    data = get_dnf_data()
    if data:
        col_values = sh.col_values(START_COL)
        next_row = max(START_ROW, len(col_values) + 1)
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_data = [now_str] + data
        
        # 행 단위 업데이트
        sh.update(f"B{next_row}:H{next_row}", [final_data])
        print("Update Success")

if __name__ == "__main__":
    run()
