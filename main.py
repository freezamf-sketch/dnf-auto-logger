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
# 구글 시트 전체 주소
SHEET_URL = "https://docs.google.com/spreadsheets/d/1lKwU5aY6WGywhPRN1uIbCNjX8wQ7hcUNcGstgvoBeFI/edit"

# 수집할 아이템 4개 목록
# sheet_name은 구글 시트 아래쪽 탭 이름과 똑같아야 합니다.
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
    사이트에 접속해서 이미지에 있는 '실제 거래된 가격' 표만 쏙 뽑아오는 함수
    """
    print(f"🔄 접속 시도: {target_url}")
    
    # 브라우저 옵션 설정
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    
    # 매번 깨끗한 브라우저 새로 띄우기 (오류 방지)
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        driver.get(target_url)
        wait = WebDriverWait(driver, 30)
        
        # 1. '24시간내'라는 글자가 있는 줄 찾기
        row_24_xpath = "//td[contains(text(), '24시간내')]/parent::tr"
        wait.until(EC.presence_of_element_located((By.XPATH, row_24_xpath)))
        
        # 페이지 로딩 후 3초 기다림 (데이터가 늦게 뜨는 것 방지)
        time.sleep(3)

        # 숫자만 남기는 청소기 함수 (이 정규식이 핵심입니다!)
        def clean_text(text):
            return re.sub(r'[^\d]', '', text)

        # 2. 24시간 데이터 추출 (물량, 총거래액, 평균)
        row_24_elem = driver.find_element(By.XPATH, row_24_xpath)
        cols_24 = row_24_elem.find_elements(By.TAG_NAME, "td")
        # [0]은 '24시간내' 글자이므로 [1], [2], [3]만 가져옴
        data_24 = [clean_text(cols_24[i].text) for i in range(1, 4)]

        # 3. 72시간 데이터 추출 (물량, 총거래액, 평균)
        row_72_xpath = "//td[contains(text(), '72시간내')]/parent::tr"
        row_72_elem = driver.find_element(By.XPATH, row_72_xpath)
        cols_72 = row_72_elem.find_elements(By.TAG_NAME, "td")
        data_72 = [clean_text(cols_72[i].text) for i in range(1, 4)]
        
        # 데이터 6개 합쳐서 반환
        return data_24 + data_72

    except Exception as e:
        print(f"⚠️ 수집 실패 ({target_url}): {e}")
        return None
    finally:
        # 다 썼으면 브라우저 닫기
        driver.quit()

def run():
    # 깃허브 Secret 키 확인
    if 'GDRIVE_API_KEY' not in os.environ:
        print("❌ 에러: GDRIVE_API_KEY가 없습니다. 설정에서 확인해주세요.")
        return

    # 구글 시트 로그인
    json_key = json.loads(os.environ['GDRIVE_API_KEY'])
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(json_key, scopes=scope)
    client = gspread.authorize(creds)
    
    try:
        doc = client.open_by_url(SHEET_URL)
        print(f"✅ 구글 시트 연결 성공: {doc.title}")
    except Exception as e:
        print(f"❌ 구글 시트 주소가 틀렸거나 권한이 없습니다: {e}")
        return

    # --- 아이템 4개 순서대로 작업 시작 ---
    for i, item in enumerate(ITEMS):
        # 주소가 "여기에..." 그대로면 건너뜀
        if "여기에" in item['url']:
            print(f"⏭️ [Pass] {item['sheet_name']} (주소 미입력)")
            continue

        print(f"\n--- [{i+1}/4] {item['sheet_name']} 작업 중 ---")
        
        # 1. 크롤링
        result_data = get_dnf_data(item['url'])
        
        if result_data:
            try:
                # 2. 해당 탭(Sheet) 열기
                worksheet = doc.worksheet(item['sheet_name'])
                
                # 3. 빈 줄 찾기 (B열 기준)
                col_values = worksheet.col_values(START_COL)
                next_row = max(START_ROW, len(col_values) + 1)
                
                # 4. 저장 [시간 + 데이터 6개]
                now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                final_row = [now_time] + result_data
                
                # B열 ~ H열까지 한 줄에 기록
                cell_range = f"B{next_row}:H{next_row}"
                worksheet.update(range_name=cell_range, values=[final_row])
                
                print(f"💾 저장 완료: {final_row}")
                
            except gspread.exceptions.WorksheetNotFound:
                print(f"❌ 에러: 시트 하단에 '{item['sheet_name']}' 탭이 없습니다. 탭을 먼저 만들어주세요.")
            except Exception as e:
                print(f"❌ 저장 중 에러 발생: {e}")
        else:
            print("❌ 데이터를 가져오지 못했습니다.")
        
        # 다음 아이템 넘어가기 전 5초 휴식 (필수)
        time.sleep(5)

    display.stop()
    print("\n🎉 모든 작업 종료")

if __name__ == "__main__":
    run()
