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
# 📋 [사용자 설정 영역] - 여기를 수정하세요
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1lKwU5aY6WGywhPRN1uIbCNjX8wQ7hcUNcGstgvoBeFI/edit"

# 수집할 아이템 4개 목록
ITEMS = [
    {
        "url": "http://dnfnow.xyz/item?item_idx=bfc7bb0aefe4d0c432ebf77836e68e3c", 
        "sheet_name": "Sheet1"
    },
    {
        "url": "http://dnfnow.xyz/item?item_idx=4a737b2ae337a57260ca4663ce6a9bb0s3", 
        "sheet_name": "Sheet2"
    },
    {
        "url": "http://dnfnow.xyz/item?item_idx=fac4ce61d490d3a006025c797abb5950", 
        "sheet_name": "Sheet3"
    },
    {
        "url": "http://dnfnow.xyz/item?item_idx=bb5a6aeb6b44bbdce835679bef4335b5", 
        "sheet_name": "Sheet4"
    }
]

# 데이터 기록 시작 위치 (B5 셀부터 아래로)
START_ROW = 5
START_COL = 2
# ==========================================

# 가상 모니터 켜기 (GitHub Actions용)
display = Display(visible=0, size=(1920, 1080))
display.start()

def get_dnf_data(target_url):
    """
    사이트에 접속해서 '실제 거래된 가격' 표의 숫자만 쏙 뽑아오는 함수
    """
    print(f"🔄 접속 시도: {target_url}")
    
    # 브라우저 옵션 설정
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    
    # 매번 깨끗한 브라우저 새로 띄우기
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        driver.get(target_url)
        wait = WebDriverWait(driver, 30)
        
        # 1. '24시간내'라는 글자가 있는 줄 찾기
        row_24_xpath = "//td[contains(text(), '24시간내')]/parent::tr"
        wait.until(EC.presence_of_element_located((By.XPATH, row_24_xpath)))
        
        time.sleep(3) # 데이터 로딩 대기

        # ========================================================
        # 🧹 [수정된 부분] 텍스트 청소기 함수
        # 1. replace로 ' 와 << 를 먼저 강제로 지웁니다.
        # 2. re.sub로 숫자(0-9)가 아닌 모든 것을 한번 더 지웁니다.
        # ========================================================
        def clean_text(text):
            # 1단계: 찌꺼기 문자 제거
            text = text.replace("'", "").replace("<<", "").replace(",", "")
            # 2단계: 확실하게 숫자만 남기기 (공백 제거 포함)
            return re.sub(r'[^0-9]', '', text).strip()

        # 2. 24시간 데이터 추출
        row_24_elem = driver.find_element(By.XPATH, row_24_xpath)
        cols_24 = row_24_elem.find_elements(By.TAG_NAME, "td")
        data_24 = [clean_text(cols_24[i].text) for i in range(1, 4)]

        # 3. 72시간 데이터 추출
        row_72_xpath = "//td[contains(text(), '72시간내')]/parent::tr"
        row_72_elem = driver.find_element(By.XPATH, row_72_xpath)
        cols_72 = row_72_elem.find_elements(By.TAG_NAME, "td")
        data_72 = [clean_text(cols_72[i].text) for i in range(1, 4)]
        
        return data_24 + data_72

    except Exception as e:
        print(f"⚠️ 수집 실패 ({target_url}): {e}")
        return None
    finally:
        driver.quit()

def run():
    # 깃허브 Secret 키 확인
    if 'GDRIVE_API_KEY' not in os.environ:
        print("❌ 에러: GDRIVE_API_KEY가 없습니다.")
        return

    # 구글 시트 로그인
    json_key = json.loads(os.environ['GDRIVE_API_KEY'])
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(json_key, scopes=scope)
    client = gspread.authorize(creds)
    
    try:
        # URL로 시트 열기
        doc = client.open_by_url(SHEET_URL)
        print(f"✅ 구글 시트 연결 성공: {doc.title}")
    except Exception as e:
        print(f"❌ 구글 시트 연결 실패: {e}")
        return

    # --- 아이템 반복 작업 ---
    for i, item in enumerate(ITEMS):
        if "여기에" in item['url']:
            continue

        print(f"\n--- [{i+1}/4] {item['sheet_name']} 작업 중 ---")
        
        result_data = get_dnf_data(item['url'])
        
        if result_data:
            try:
                worksheet = doc.worksheet(item['sheet_name'])
                col_values = worksheet.col_values(START_COL)
                next_row = max(START_ROW, len(col_values) + 1)
                
                now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                final_row = [now_time] + result_data
                
                cell_range = f"B{next_row}:H{next_row}"
                worksheet.update(range_name=cell_range, values=[final_row])
                print(f"💾 저장 완료: {final_row}")
                
            except Exception as e:
                print(f"❌ 저장 에러: {e}")
        else:
            print("❌ 데이터 수집 실패")
        
        time.sleep(5)

    display.stop()
    print("\n🎉 모든 작업 종료")

if __name__ == "__main__":
    run()
