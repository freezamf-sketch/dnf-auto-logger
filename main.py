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
# 📋 [사용자 설정 영역] - 여기만 수정하세요!
# ==========================================
# 구글 시트 전체 주소
SHEET_URL = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"

# 수집할 대상 목록
# 형식: {"url": "아이템URL", "sheet_name": "저장할 탭 이름"}
ITEMS = [
    {
        "url": "http://dnfnow.xyz/item?item_idx=bfc7bb0aefe4d0c432ebf77836e68e3c",
        "sheet_name": "Sheet1"  # 첫 번째 아이템 -> Sheet1에 저장
    },
    {
        "url": "http://dnfnow.xyz/item?item_idx=4a737b2ae337a57260ca4663ce6a9bb0s3",
        "sheet_name": "Sheet2"  # 두 번째 아이템 -> Sheet2에 저장
    },
    {
        "url": "http://dnfnow.xyz/item?item_idx=fac4ce61d490d3a006025c797abb5950",
        "sheet_name": "Sheet3"  # 세 번째 아이템 -> Sheet3에 저장
    },
    {
        "url": "http://dnfnow.xyz/item?item_idx=bb5a6aeb6b44bbdce835679bef4335b5",
        "sheet_name": "Sheet4"  # 세 번째 아이템 -> Sheet4에 저장
    }
]

START_ROW = 5  # 기록 시작 행
START_COL = 2  # 기록 시작 열 (B열)
# ==========================================

# 가상 디스플레이 시작
display = Display(visible=0, size=(1920, 1080))
display.start()

def get_dnf_data(driver, url):
    try:
        print(f"🔄 접속 중: {url}")
        driver.get(url)
        wait = WebDriverWait(driver, 30)
        
        row_24h_xpath = "//td[contains(text(), '24시간내')]/parent::tr"
        wait.until(EC.presence_of_element_located((By.XPATH, row_24h_xpath)))
        time.sleep(3) # 로딩 대기

        def clean_text(text):
            return re.sub(r'[^\d]', '', text)

        # 데이터 추출
        row_24 = driver.find_element(By.XPATH, row_24h_xpath)
        cols_24 = row_24.find_elements(By.TAG_NAME, "td")
        data_24 = [clean_text(cols_24[i].text) for i in range(1, 4)]

        row_72_xpath = "//td[contains(text(), '72시간내')]/parent::tr"
        row_72 = driver.find_element(By.XPATH, row_72_xpath)
        cols_72 = row_72.find_elements(By.TAG_NAME, "td")
        data_72 = [clean_text(cols_72[i].text) for i in range(1, 4)]
        
        return data_24 + data_72

    except Exception as e:
        print(f"⚠️ 수집 실패 ({url}): {e}")
        return None

def run():
    if 'GDRIVE_API_KEY' not in os.environ:
        print("❌ 에러: Secret 설정 확인 필요")
        return

    # 구글 시트 연결
    json_key = json.loads(os.environ['GDRIVE_API_KEY'])
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(json_key, scopes=scope)
    client = gspread.authorize(creds)
    
    try:
        doc = client.open_by_url(SHEET_URL)
        print(f"✅ 시트 접속 성공: {doc.title}")
    except Exception as e:
        print(f"❌ 시트 접속 실패: {e}")
        return

    # 브라우저 설정 (한 번만 켜서 재사용)
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=chrome_options)

    # --- [핵심] 아이템 목록 순회 ---
    try:
        for item in ITEMS:
            # 1. 데이터 수집
            data = get_dnf_data(driver, item['url'])
            
            if data:
                # 2. 해당 시트(탭) 열기
                try:
                    worksheet = doc.worksheet(item['sheet_name'])
                except:
                    print(f"⚠️ 탭 없음: '{item['sheet_name']}' 탭이 시트에 존재하는지 확인하세요.")
                    continue

                # 3. 다음 기록 위치 찾기
                col_values = worksheet.col_values(START_COL)
                next_row = max(START_ROW, len(col_values) + 1)
                
                # 4. 데이터 저장
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                final_data = [now_str] + data
                
                cell_range = f"B{next_row}:H{next_row}"
                worksheet.update(range_name=cell_range, values=[final_data])
                print(f"💾 저장 완료: {item['sheet_name']} (행: {next_row})")
            
            # 너무 빠른 연속 접속 방지
            time.sleep(2)

    finally:
        driver.quit()
        display.stop()

if __name__ == "__main__":
    run()
