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
import math

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

# 투자 페이지 URL (Sheet6에 저장)
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


def get_today_buy_price_from_chart():
    """
    투자 페이지 그래프에서 오늘 날짜의 '구매' 가격 추출
    여러 방법을 순차적으로 시도
    """
    print(f"🔄 투자 그래프에서 오늘 구매가격 추출 시작")
    
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
        
        # 페이지 로딩 대기
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(10)  # 차트 완전 로딩 대기 (시간 증가)
        
        # 오늘 날짜
        kst = ZoneInfo("Asia/Seoul")
        today = datetime.now(kst)
        today_yyyymmdd = today.strftime("%Y%m%d")
        today_dash = today.strftime("%Y-%m-%d")
        
        print(f"📅 오늘 날짜: {today_yyyymmdd} ({today_dash})")
        
        # 방법 1: Chart.js에서 최신 데이터 가져오기 (가장 확실한 방법)
        print(f"📊 방법 1: Chart.js에서 최신 구매가격 추출 시도...")
        
        get_latest_price_script = """
        try {
            if (typeof Chart === 'undefined') {
                return {success: false, method: 1, error: 'Chart.js 없음'};
            }
            
            var canvas = document.querySelector('canvas');
            if (!canvas) {
                return {success: false, method: 1, error: 'Canvas 없음'};
            }
            
            var chart = Chart.getChart(canvas);
            if (!chart || !chart.data || !chart.data.datasets) {
                return {success: false, method: 1, error: 'Chart 데이터 없음'};
            }
            
            var datasets = chart.data.datasets;
            var labels = chart.data.labels;
            
            // 구매 데이터셋 찾기
            for (var i = 0; i < datasets.length; i++) {
                var label = (datasets[i].label || '').toLowerCase();
                if (label.includes('구매') || label === '구매' || label.includes('buy')) {
                    var data = datasets[i].data;
                    if (data && data.length > 0) {
                        var lastPrice = data[data.length - 1];
                        var lastLabel = labels[labels.length - 1];
                        return {
                            success: true,
                            method: 1,
                            price: Math.floor(lastPrice),
                            raw_price: lastPrice,
                            label: String(lastLabel),
                            total: data.length
                        };
                    }
                }
            }
            
            return {success: false, method: 1, error: '구매 데이터셋 없음'};
        } catch(e) {
            return {success: false, method: 1, error: e.toString()};
        }
        """
        
        result = driver.execute_script(get_latest_price_script)
        
        if result and result.get('success'):
            print(f"✅ 방법 1 성공!")
            print(f"   그래프 레이블: {result.get('label')}")
            print(f"   원본 가격: {result.get('raw_price')}")
            print(f"   버림 처리: {result.get('price')}원")
            
            return {
                'success': True,
                'date': today_yyyymmdd,
                'price': result.get('price'),
                'method': 'Chart.js 최신값'
            }
        
        print(f"⚠️ 방법 1 실패: {result.get('error') if result else 'Unknown'}")
        
        # 방법 2: window 객체에서 전역 차트 변수 찾기
        print(f"📊 방법 2: window 객체에서 차트 데이터 검색...")
        
        find_chart_in_window_script = """
        try {
            var allKeys = Object.keys(window);
            for (var i = 0; i < allKeys.length; i++) {
                var obj = window[allKeys[i]];
                if (obj && typeof obj === 'object' && obj.data && obj.data.datasets) {
                    var datasets = obj.data.datasets;
                    for (var j = 0; j < datasets.length; j++) {
                        var label = (datasets[j].label || '').toLowerCase();
                        if (label.includes('구매') || label === '구매') {
                            var data = datasets[j].data;
                            if (data && data.length > 0) {
                                return {
                                    success: true,
                                    method: 2,
                                    price: Math.floor(data[data.length - 1]),
                                    raw_price: data[data.length - 1]
                                };
                            }
                        }
                    }
                }
            }
            return {success: false, method: 2, error: 'window 객체에서 차트 못찾음'};
        } catch(e) {
            return {success: false, method: 2, error: e.toString()};
        }
        """
        
        result2 = driver.execute_script(find_chart_in_window_script)
        
        if result2 and result2.get('success'):
            print(f"✅ 방법 2 성공!")
            print(f"   원본 가격: {result2.get('raw_price')}")
            print(f"   버림 처리: {result2.get('price')}원")
            
            return {
                'success': True,
                'date': today_yyyymmdd,
                'price': result2.get('price'),
                'method': 'window 객체'
            }
        
        print(f"⚠️ 방법 2 실패: {result2.get('error') if result2 else 'Unknown'}")
        
        # 방법 3: 페이지 소스 스크린샷 저장 (디버깅용)
        print(f"📊 방법 3: 페이지 HTML 분석...")
        page_html = driver.page_source
        
        # Chart 관련 스크립트 태그 찾기
        if 'Chart' in page_html and 'canvas' in page_html:
            print(f"✅ 페이지에 Chart.js와 Canvas 존재 확인")
        else:
            print(f"❌ 페이지에 Chart.js 또는 Canvas 없음")
        
        print(f"❌ 모든 방법 실패 - 수동 확인 필요")
        return None
            
    except Exception as e:
        print(f"❌ 투자 페이지 접속 실패: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def save_invest_price_to_sheet(doc, price_data):
    """
    투자 구매가격을 Sheet6에 저장 (B5 셀부터 시작)
    """
    if not price_data or not price_data.get('success'):
        print("❌ Sheet6: 저장할 데이터가 없습니다")
        return False
    
    try:
        # Sheet6 열기
        try:
            worksheet = doc.worksheet(INVEST_SHEET_NAME)
            print(f"✅ '{INVEST_SHEET_NAME}' 시트 연결 완료")
        except Exception as e:
            print(f"❌ '{INVEST_SHEET_NAME}' 시트 열기 실패: {e}")
            return False
        
        # B열의 데이터 개수 확인
        try:
            col_values = worksheet.col_values(START_COL)
            next_row = max(START_ROW, len(col_values) + 1)
        except Exception as e:
            print(f"⚠️ B열 값 읽기 실패, 기본값 사용: {e}")
            next_row = START_ROW
        
        # 현재 시간 (한국 시간)
        kst = ZoneInfo("Asia/Seoul")
        collection_time = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
        
        # 데이터 준비
        date_str = price_data.get('date')
        price = int(price_data.get('price', 0))
        
        # 저장할 데이터
        row_data = [collection_time, date_str, price]
        cell_range = f"B{next_row}:D{next_row}"
        
        print(f"💾 Sheet6 저장 시도...")
        print(f"   위치: {cell_range}")
        print(f"   데이터: {row_data}")
        
        # 시트에 저장
        worksheet.update(range_name=cell_range, values=[row_data])
        
        print(f"✅ Sheet6 저장 성공!")
        return True
        
    except Exception as e:
        print(f"❌ Sheet6 저장 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


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
        # 2️⃣ 투자 그래프에서 오늘 구매가격 수집 (Sheet6)
        # ==========================================
        print("\n" + "="*50)
        print("💰 투자 그래프 오늘 구매가격 수집 (Sheet6)")
        print("="*50)
        
        today_price_data = get_today_buy_price_from_chart()
        
        if today_price_data:
            save_success = save_invest_price_to_sheet(doc, today_price_data)
            if not save_success:
                print("⚠️ Sheet6 저장 재시도...")
                time.sleep(3)
                save_invest_price_to_sheet(doc, today_price_data)
        else:
            print("❌ Sheet6: 구매가격 데이터를 가져올 수 없습니다")
        
        # ==========================================
        # 3️⃣ 작업 종료
        # ==========================================
        print("\n" + "="*50)
        print("🎉 모든 작업 완료!")
        print("="*50)
        print(f"✅ Sheet1~5: 아이템 거래 데이터 수집 완료")
        if today_price_data and today_price_data.get('success'):
            print(f"✅ Sheet6: 투자 구매가격 수집 완료 ({today_price_data.get('price')}원)")
        else:
            print(f"❌ Sheet6: 투자 구매가격 수집 실패")
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
