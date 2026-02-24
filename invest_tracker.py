import os
import json
import time
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
SHEET_URL         = "https://docs.google.com/spreadsheets/d/1lKwU5aY6WGywhPRN1uIbCNjX8wQ7hcUNcGstgvoBeFI/edit"
INVEST_URL        = "http://dnfnow.xyz/invest"
INVEST_SHEET_NAME = "Sheet6"
START_ROW         = 5
START_COL         = 2
MAX_RETRIES       = 3
# ==========================================


def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(40)
    return driver


def quit_driver(driver):
    try:
        if driver:
            driver.quit()
    except Exception as e:
        print(f"⚠️ 드라이버 종료 실패 (무시): {e}")


EXTRACT_JS = """
try {
    var chart = null;

    if (typeof Chart !== 'undefined' && Chart.instances) {
        var keys = Object.keys(Chart.instances);
        if (keys.length > 0) chart = Chart.instances[keys[0]];
    }

    if (!chart) {
        var canvases = document.querySelectorAll('canvas');
        for (var i = 0; i < canvases.length; i++) {
            if (canvases[i].__chart__) { chart = canvases[i].__chart__; break; }
            if (canvases[i].chart)     { chart = canvases[i].chart;     break; }
        }
    }

    if (!chart || !chart.data || !chart.data.datasets)
        return {success: false, error: 'Chart 인스턴스 없음'};

    var datasets = chart.data.datasets;
    var labels   = chart.data.labels || [];

    for (var d = 0; d < datasets.length; d++) {
        var lbl = (datasets[d].label || '').toLowerCase();
        if (lbl.includes('구매') || lbl === 'buy') {
            var data = datasets[d].data;
            if (data && data.length > 0) {
                return {
                    success   : true,
                    price     : Math.floor(data[data.length - 1]),
                    lastLabel : String(labels[labels.length - 1] || ''),
                    total     : data.length
                };
            }
        }
    }

    var datasetLabels = datasets.map(function(d){ return d.label; });
    return {success: false, error: '구매 데이터셋 없음', datasetLabels: JSON.stringify(datasetLabels)};

} catch(e) {
    return {success: false, error: e.toString()};
}
"""


def get_today_buy_price(max_retries: int = MAX_RETRIES):
    kst       = ZoneInfo("Asia/Seoul")
    today_str = datetime.now(kst).strftime("%Y%m%d")

    for attempt in range(max_retries):
        driver = None
        try:
            print(f"🔄 [{attempt+1}/{max_retries}] Selenium 투자 페이지 접속")
            driver = create_driver()
            driver.get(INVEST_URL)

            WebDriverWait(driver, 35).until(
                EC.presence_of_element_located((By.TAG_NAME, "canvas"))
            )
            print("✅ canvas 감지 완료. 8초 대기 (Chart.js 렌더링)...")
            time.sleep(8)

            result = driver.execute_script(EXTRACT_JS)
            print(f"📊 JS 결과: {result}")

            if result and result.get('success'):
                price = result['price']
                print(f"✅ 구매가 추출 성공: {price}원 (레이블: {result.get('lastLabel')}, 총 {result.get('total')}개 데이터)")
                return {'success': True, 'date': today_str, 'price': price}
            else:
                raise ValueError(f"JS 추출 실패: {result.get('error') if result else 'None'} / 데이터셋: {result.get('datasetLabels') if result else ''}")

        except Exception as e:
            print(f"⚠️ [{attempt+1}/{max_retries}] 실패: {e}")
            if attempt < max_retries - 1:
                print("   10초 후 재시도...")
                time.sleep(10)
            else:
                import traceback
                traceback.print_exc()
                return None
        finally:
            quit_driver(driver)


def update_sheet_with_retry(worksheet, cell_range, values, max_retries=3):
    for attempt in range(max_retries):
        try:
            worksheet.update(range_name=cell_range, values=values)
            return True
        except Exception as e:
            error_msg = str(e)
            if any(code in error_msg for code in ['RATE_LIMIT_EXCEEDED', '429', '500', '503']):
                wait_time = 2 ** attempt
                print(f"⚠️ Sheets API 에러 [{attempt+1}/{max_retries}]: {error_msg[:100]}")
                if attempt < max_retries - 1:
                    print(f"   {wait_time}초 후 재시도...")
                    time.sleep(wait_time)
            else:
                print(f"❌ 재시도 불가 에러: {e}")
                raise
    return False


def run():
    try:
        if 'GDRIVE_API_KEY' not in os.environ:
            print("❌ GDRIVE_API_KEY 없음")
            sys.exit(1)

        json_key = json.loads(os.environ['GDRIVE_API_KEY'])
        scope    = ['https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive']
        creds    = Credentials.from_service_account_info(json_key, scopes=scope)
        client   = gspread.authorize(creds)
        doc      = client.open_by_url(SHEET_URL)
        print(f"✅ 구글 시트 연결 성공: {doc.title}")

        print("\n" + "="*50)
        print("💰 투자 페이지 구매가 수집 (Sheet6)")
        print("="*50)

        invest_data = get_today_buy_price()

        if not invest_data or not invest_data.get('success'):
            print("❌ 구매가 수집 실패")
            sys.exit(1)

        worksheet  = doc.worksheet(INVEST_SHEET_NAME)
        col_values = worksheet.col_values(START_COL)
        next_row   = max(START_ROW, len(col_values) + 1)

        kst             = ZoneInfo("Asia/Seoul")
        collection_time = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
        row_data        = [collection_time, invest_data['date'], int(invest_data['price'])]
        cell_range      = f"B{next_row}:D{next_row}"

        if update_sheet_with_retry(worksheet, cell_range, [row_data]):
            print(f"✅ Sheet6 저장 성공: {row_data}")
            sys.exit(0)
        else:
            print("❌ Sheet6 저장 실패")
            sys.exit(1)

    except Exception as e:
        print(f"❌ 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run()
