import os
import json
import time
import re
from datetime import datetime
from zoneinfo import ZoneInfo
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

# 수집할 아이템 5개 목록 (Sheet1~Sheet5)
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
    },
    {
        "url": "http://dnfnow.xyz/item?item_idx=55be75a1c024aac3ef84ed3bed5b8db9", 
        "sheet_name": "Sheet5"
    }
]

# 투자 그래프 URL (Sheet6에 저장)
INVEST_URL = "http://dnfnow.xyz/invest"
INVEST_SHEET_NAME = "Sheet6"

# 데이터 기록 시작 위치 (B5 셀부터 아래로)
START_ROW = 5
START_COL = 2
# ==========================================

def get_dnf_data(target_url):
    """
    사이트에 접속해서 '실제 거래된 가격' 표의 숫자만 쏙 뽑아오는 함수
    """
    print(f"🔄 접속 시도: {target_url}")
    
    driver = None
    try:
        # 브라우저 옵션 설정
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--headless")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        driver.get(target_url)
        
        wait = WebDriverWait(driver, 30)
        
        # 1. '24시간내'라는 글자가 있는 줄 찾기
        row_24_xpath = "//td[contains(text(), '24시간내')]/parent::tr"
        wait.until(EC.presence_of_element_located((By.XPATH, row_24_xpath)))
        
        time.sleep(3) # 데이터 로딩 대기

        # 텍스트 청소기 함수
        def clean_text(text):
            text = text.replace("'", "").replace("<<", "").replace(",", "")
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
        if driver:
            try:
                driver.quit()
            except:
                pass


def get_today_buy_price():
    """
    투자 그래프에서 오늘 날짜의 '구매' 가격만 추출
    """
    print(f"🔄 투자 그래프 '구매' 가격 수집 시작")
    
    driver = None
    try:
        # 브라우저 옵션 설정
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--headless")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        driver.get(INVEST_URL)
        
        wait = WebDriverWait(driver, 30)
        
        # 차트가 로드될 때까지 대기
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "canvas")))
        time.sleep(5)  # 차트 렌더링 완료 대기
        
        # JavaScript로 그래프의 '구매' 데이터만 추출
        get_buy_price_script = """
        try {
            var canvas = document.querySelector('canvas');
            if (canvas && typeof Chart !== 'undefined') {
                var chartInstance = Chart.getChart(canvas);
                if (chartInstance && chartInstance.data) {
                    var labels = chartInstance.data.labels;
                    var datasets = chartInstance.data.datasets;
                    
                    // '구매' 데이터셋 찾기
                    var buyDataset = null;
                    for (var i = 0; i < datasets.length; i++) {
                        var label = datasets[i].label;
                        if (label && (label.includes('구매') || label.includes('buy') || label === '구매')) {
                            buyDataset = datasets[i];
                            break;
                        }
                    }
                    
                    if (buyDataset && buyDataset.data.length > 0) {
                        // 가장 최신 데이터 포인트 (오늘 날짜)
                        var latestIndex = labels.length - 1;
                        return {
                            success: true,
                            date: labels[latestIndex],
                            price: buyDataset.data[latestIndex]
                        };
                    }
                }
            }
            return {success: false, error: '구매 데이터를 찾을 수 없습니다'};
        } catch(e) {
            return {success: false, error: e.toString()};
        }
        """
        
        result = driver.execute_script(get_buy_price_script)
        
        if result and result.get('success'):
            print(f"✅ 구매가격 수집 성공: {result.get('date')} - {result.get('price')}원")
            return result
        else:
            error_msg = result.get('error', '알 수 없는 오류') if result else '데이터 없음'
            print(f"⚠️ 구매가격 추출 실패: {error_msg}")
            return None
            
    except Exception as e:
        print(f"❌ 투자 그래프 수집 실패: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def save_buy_price_to_sheet(doc, buy_data):
    """
    구매 가격을 Sheet6에 저장
    """
    if not buy_data or not buy_data.get('success'):
        print("⚠️ 저장할 구매 데이터가 없습니다 (스킵)")
        return
    
    try:
        # Sheet6 열기 또는 생성
        try:
            worksheet = doc.worksheet(INVEST_SHEET_NAME)
            print(f"✅ '{INVEST_SHEET_NAME}' 시트 연결 완료")
        except:
            worksheet = doc.add_worksheet(title=INVEST_SHEET_NAME, rows=1000, cols=10)
            headers = ['수집시간', '그래프날짜', '구매가격(원)']
            worksheet.update('A1:C1', [headers])
            print(f"✅ '{INVEST_SHEET_NAME}' 시트 생성 완료")
        
        # 다음 행 찾기
        try:
            col_values = worksheet.col_values(1)
            next_row = max(2, len(col_values) + 1)
        except:
            next_row = 2
        
        # 현재 시간 (한국 시간)
        kst = ZoneInfo("Asia/Seoul")
        collection_time = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
        
        # 데이터 준비
        graph_date = str(buy_data.get('date', ''))
        price = buy_data.get('price', 0)
        
        # 시트에 저장
        row_data = [collection_time, graph_date, price]
        worksheet.update(f'A{next_row}:C{next_row}', [row_data])
        
        print(f"💾 구매가격 저장 완료: {collection_time} | {graph_date} | {price}원")
        
    except Exception as e:
        print(f"❌ 구매가격 저장 실패: {e}")


def run():
    display = None
    
    try:
        # 가상 모니터 켜기
        display = Display(visible=0, size=(1920, 1080))
        display.start()
        print("✅ 가상 디스플레이 시작")
    except Exception as e:
        print(f"⚠️ 가상 디스플레이 시작 실패 (무시): {e}")
    
    try:
        # 깃허브 Secret 키 확인
        if 'GDRIVE_API_KEY' not in os.environ:
            print("❌ 에러: GDRIVE_API_KEY가 없습니다.")
            return

        # 구글 시트 로그인
        json_key = json.loads(os.environ['GDRIVE_API_KEY'])
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(json_key, scopes=scope)
        client = gspread.authorize(creds)
        
        # URL로 시트 열기
        doc = client.open_by_url(SHEET_URL)
        print(f"✅ 구글 시트 연결 성공: {doc.title}")

        # ==========================================
        # 1️⃣ 아이템 데이터 수집 (Sheet1~Sheet5)
        # ==========================================
        print("\n" + "="*50)
        print("📦 아이템 데이터 수집 시작 (Sheet1~Sheet5)")
        print("="*50)
        
        for i, item in enumerate(ITEMS):
            if "여기에" in item['url']:
                continue

            print(f"\n--- [{i+1}/5] {item['sheet_name']} 작업 중 ---")
            
            result_data = get_dnf_data(item['url'])
            
            if result_data:
                try:
                    worksheet = doc.worksheet(item['sheet_name'])
                    col_values = worksheet.col_values(START_COL)
                    next_row = max(START_ROW, len(col_values) + 1)
                    
                    kst = ZoneInfo("Asia/Seoul")
                    now_time = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
                    
                    final_row = [now_time] + result_data
                    
                    cell_range = f"B{next_row}:H{next_row}"
                    worksheet.update(range_name=cell_range, values=[final_row])
                    print(f"💾 저장 완료: {final_row}")
                    
                except Exception as e:
                    print(f"❌ 저장 에러: {e}")
            else:
                print("❌ 데이터 수집 실패")
            
            time.sleep(5)

        # ==========================================
        # 2️⃣ 투자 그래프 구매가격 수집 (Sheet6)
        # ==========================================
        print("\n" + "="*50)
        print("💰 투자 그래프 '구매' 가격 수집 시작 (Sheet6)")
        print("="*50)
        
        buy_price_data = get_today_buy_price()
        save_buy_price_to_sheet(doc, buy_price_data)
        
        # ==========================================
        # 3️⃣ 작업 종료
        # ==========================================
        print("\n" + "="*50)
        print("🎉 모든 작업 완료!")
        print("="*50)
        print(f"✅ Sheet1~5: 아이템 거래 데이터 수집 완료")
        print(f"✅ Sheet6: 투자 구매가격 수집 완료")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ 프로그램 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 가상 디스플레이 종료
        if display:
            try:
                display.stop()
                print("✅ 가상 디스플레이 종료")
            except:
                pass

if __name__ == "__main__":
    run()
