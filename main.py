import os
import json
import time
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
from pyvirtualdisplay import Display

# ==========================================
# 📋 [사용자 설정 영역]
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1lKwU5aY6WGywhPRN1uIbCNjX8wQ7hcUNcGstgvoBeFI/edit"

ITEMS = [
    {"url": "http://dnfnow.xyz/item?item_idx=bfc7bb0aefe4d0c432ebf77836e68e3c", "sheet_name": "Sheet1"},
    {"url": "http://dnfnow.xyz/item?item_idx=4a737b2ae337a57260ca4663ce6a9bb0s3", "sheet_name": "Sheet2"},
    {"url": "http://dnfnow.xyz/item?item_idx=fac4ce61d490d3a006025c797abb5950", "sheet_name": "Sheet3"},
    {"url": "http://dnfnow.xyz/item?item_idx=bb5a6aeb6b44bbdce835679bef4335b5", "sheet_name": "Sheet4"},
    {"url": "http://dnfnow.xyz/item?item_idx=55be75a1c024aac3ef84ed3bed5b8db9", "sheet_name": "Sheet5"},
    {"url": "http://dnfnow.xyz/item?item_idx=4e5c23c6083931685b79d8b542eeb268", "sheet_name": "Sheet7"},
    {"url": "http://dnfnow.xyz/item?item_idx=028f60ed1253313f5bbd99f228461f33", "sheet_name": "Sheet8"},
    {"url": "http://dnfnow.xyz/item?item_idx=51f381d45d16ef4273ae25f01f7ea4c2", "sheet_name": "Sheet9"},
]

INVEST_URL = "http://dnfnow.xyz/invest"
INVEST_SHEET_NAME = "Sheet6"
START_ROW = 5
START_COL = 2
MAX_RETRIES = 3
MAX_CHART_RETRIES = 3
# ==========================================


def clean_text(text):
    text = text.replace("'", "").replace("<<", "").replace(",", "")
    cleaned = re.sub(r'[^0-9]', '', text).strip()
    return cleaned if cleaned else "0"


def get_dnf_data(target_url, max_retries=MAX_RETRIES):
    """
    requests + BeautifulSoup으로 데이터 수집
    실패 시 API 엔드포인트 시도
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    for attempt in range(max_retries):
        try:
            print(f"🔄 [{attempt+1}/{max_retries}] 접속 시도: {target_url}")

            response = requests.get(target_url, headers=headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')

            row_24 = None
            row_72 = None

            for td in soup.find_all('td'):
                if '24시간내' in td.get_text():
                    row_24 = td.find_parent('tr')
                if '72시간내' in td.get_text():
                    row_72 = td.find_parent('tr')

            if not row_24 or not row_72:
                print(f"⚠️ [{attempt+1}/{max_retries}] HTML 테이블 없음 → API 시도")

                item_idx = target_url.split("item_idx=")[-1]
                api_url = f"http://dnfnow.xyz/api/item?item_idx={item_idx}"
                api_resp = requests.get(api_url, headers=headers, timeout=30)

                if api_resp.status_code == 200:
                    try:
                        data = api_resp.json()
                        print(f"📦 API 전체 응답: {json.dumps(data, ensure_ascii=False)[:500]}")
                    except Exception as je:
                        print(f"⚠️ API JSON 파싱 실패: {je}")
                        print(f"📄 API 응답 텍스트: {api_resp.text[:300]}")
                else:
                    print(f"⚠️ API 응답 코드: {api_resp.status_code}")

                raise ValueError("테이블 행을 찾을 수 없음 (JS 렌더링 필요 가능성)")

            cols_24 = row_24.find_all('td')
            cols_72 = row_72.find_all('td')

            print(f"📊 24시간 컬럼 수: {len(cols_24)}, 72시간 컬럼 수: {len(cols_72)}")

            if len(cols_24) < 4 or len(cols_72) < 4:
                raise ValueError(f"컬럼 수 부족: 24h={len(cols_24)}, 72h={len(cols_72)}")

            raw_24 = [cols_24[i].get_text(strip=True) for i in range(1, 4)]
            raw_72 = [cols_72[i].get_text(strip=True) for i in range(1, 4)]
            print(f"📝 24시간 원본: {raw_24}")
            print(f"📝 72시간 원본: {raw_72}")

            data_24 = [clean_text(t) for t in raw_24]
            data_72 = [clean_text(t) for t in raw_72]
            result = data_24 + data_72

            if all(x == '0' for x in result):
                raise ValueError("모든 데이터가 0 또는 비어있음")

            print(f"✅ 데이터 수집 성공: {result}")
            return result

        except Exception as e:
            print(f"⚠️ [{attempt+1}/{max_retries}] 수집 실패: {e}")
            if attempt < max_retries - 1:
                wait_time = 10 * (attempt + 1)
                print(f"   {wait_time}초 후 재시도...")
                time.sleep(wait_time)
            else:
                print(f"❌ 최종 실패 ({target_url})")
                import traceback
                traceback.print_exc()
                return None


def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--memory-pressure-off")
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(40)
    return driver


def quit_driver(driver):
    if driver:
        try:
            driver.quit()
        except Exception as e:
            print(f"⚠️ 드라이버 종료 실패 (무시): {e}")


def get_today_buy_price_from_chart(max_retries=MAX_CHART_RETRIES):
    for attempt in range(max_retries):
        driver = None
        try:
            print(f"🔄 [{attempt+1}/{max_retries}] 투자 페이지 접속 시도")

            driver = create_driver()
            driver.get(INVEST_URL)

            wait = WebDriverWait(driver, 35)
            wait.until(lambda d: d.execute_script(
                "return document.body && document.body.innerHTML.length > 300"
            ))
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "canvas")))
            time.sleep(10)

            kst = ZoneInfo("Asia/Seoul")
            today = datetime.now(kst)
            today_yyyymmdd = today.strftime("%Y%m%d")

            print(f"📅 오늘 날짜: {today_yyyymmdd}")
            print(f"📊 차트 데이터 추출 시도...")

            extract_script = """
            try {
                var canvas = document.querySelector('canvas');
                if (!canvas) return {success: false, error: 'Canvas 없음'};

                var chart = canvas.chart || canvas.__chart__ || null;

                if (!chart && typeof Chart !== 'undefined' && Chart.instances) {
                    var instances = Chart.instances;
                    for (var key in instances) {
                        if (instances.hasOwnProperty(key)) {
                            chart = instances[key];
                            break;
                        }
                    }
                }

                if (!chart) {
                    var allCanvas = document.querySelectorAll('canvas');
                    for (var i = 0; i < allCanvas.length; i++) {
                        if (allCanvas[i].chart || allCanvas[i].__chart__) {
                            chart = allCanvas[i].chart || allCanvas[i].__chart__;
                            break;
                        }
                    }
                }

                if (!chart || !chart.data || !chart.data.datasets) {
                    return {success: false, error: 'Chart 인스턴스 없음'};
                }

                var datasets = chart.data.datasets;
                var labels = chart.data.labels;

                for (var i = 0; i < datasets.length; i++) {
                    var label = (datasets[i].label || '').toLowerCase();
                    if (label.includes('구매') || label === '구매' || label.includes('buy')) {
                        var data = datasets[i].data;
                        if (data && data.length > 0) {
                            var lastPrice = data[data.length - 1];
                            var lastLabel = labels[labels.length - 1];
                            return {
                                success: true,
                                price: Math.floor(lastPrice),
                                raw_price: lastPrice,
                                label: String(lastLabel),
                                total: data.length,
                                method: 'canvas.chart'
                            };
                        }
                    }
                }

                return {success: false, error: '구매 데이터셋 없음'};

            } catch(e) {
                return {success: false, error: e.toString()};
            }
            """

            result = driver.execute_script(extract_script)

            if result and result.get('success'):
                print(f"✅ 구매가격 추출 성공! (방법: {result.get('method')})")
                print(f"   그래프 레이블: {result.get('label')}")
                print(f"   원본 가격: {result.get('raw_price')}")
                print(f"   버림 처리: {result.get('price')}원")
                return {'success': True, 'date': today_yyyymmdd, 'price': result.get('price')}

            print(f"⚠️ [{attempt+1}/{max_retries}] Chart 접근 실패: {result.get('error') if result else 'Unknown'}")

            if attempt < max_retries - 1:
                print(f"   10초 후 재시도...")
                time.sleep(10)
            else:
                print(f"❌ 최종 실패: 모든 방법 실패")
                return None

        except Exception as e:
            print(f"⚠️ [{attempt+1}/{max_retries}] 투자 페이지 접속 실패: {e}")
            if attempt < max_retries - 1:
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
            if 'RATE_LIMIT_EXCEEDED' in error_msg or '429' in error_msg or '500' in error_msg or '503' in error_msg:
                wait_time = 2 ** attempt
                print(f"⚠️ API 에러 [{attempt+1}/{max_retries}]: {error_msg[:100]}")
                if attempt < max_retries - 1:
                    print(f"   {wait_time}초 후 재시도...")
                    time.sleep(wait_time)
            else:
                print(f"❌ 에러 (재시도 불가): {e}")
                raise
    return False


def save_invest_price_to_sheet(doc, price_data):
    if not price_data or not price_data.get('success'):
        print("❌ Sheet6: 저장할 데이터가 없습니다")
        return False
    try:
        worksheet = doc.worksheet(INVEST_SHEET_NAME)
        print(f"✅ '{INVEST_SHEET_NAME}' 시트 연결 완료")

        col_values = worksheet.col_values(START_COL)
        next_row = max(START_ROW, len(col_values) + 1)

        kst = ZoneInfo("Asia/Seoul")
        collection_time = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
        date_str = price_data.get('date')
        price = int(price_data.get('price', 0))
        row_data = [collection_time, date_str, price]
        cell_range = f"B{next_row}:D{next_row}"

        if update_sheet_with_retry(worksheet, cell_range, [row_data]):
            print(f"✅ Sheet6 저장 성공: {row_data}")
            return True
        else:
            print(f"❌ Sheet6 저장 실패 (재시도 초과)")
            return False

    except Exception as e:
        print(f"❌ Sheet6 저장 에러: {e}")
        import traceback
        traceback.print_exc()
        return False


def run():
    display = None
    failed_items = []

    try:
        display = Display(visible=0, size=(1920, 1080))
        display.start()
        print("✅ 가상 디스플레이 시작")
    except Exception as e:
        print(f"⚠️ 가상 디스플레이 시작 실패: {e}")

    try:
        if 'GDRIVE_API_KEY' not in os.environ:
            print("❌ 에러: GDRIVE_API_KEY가 없습니다.")
            sys.exit(1)

        json_key = json.loads(os.environ['GDRIVE_API_KEY'])
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(json_key, scopes=scope)
        client = gspread.authorize(creds)

        doc = client.open_by_url(SHEET_URL)
        print(f"✅ 구글 시트 연결 성공: {doc.title}")

        print()
        print("="*50)
        print("📦 아이템 데이터 수집 시작")
        print("="*50)

        for i, item in enumerate(ITEMS):
            if "여기에" in item['url']:
                print(f"⏭️  [{i+1}/{len(ITEMS)}] {item['sheet_name']} 스킵 (URL 미설정)")
                continue

            print()
            print(f"--- [{i+1}/{len(ITEMS)}] {item['sheet_name']} 작업 중 ---")

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

                    if update_sheet_with_retry(worksheet, cell_range, [final_row]):
                        print(f"💾 저장 완료: {final_row}")
                    else:
                        print(f"❌ {item['sheet_name']} 저장 최종 실패")
                        failed_items.append(item['sheet_name'])

                except Exception as e:
                    print(f"❌ {item['sheet_name']} 저장 에러: {e}")
                    import traceback
                    traceback.print_exc()
                    failed_items.append(item['sheet_name'])
            else:
                print(f"❌ {item['sheet_name']} 데이터 수집 실패")
                failed_items.append(item['sheet_name'])

            time.sleep(3)

        print()
        print("="*50)
        print("💰 투자 페이지 구매가격 수집 (Sheet6)")
        print("="*50)

        chart_success = False
        today_price_data = get_today_buy_price_from_chart()

        if today_price_data and today_price_data.get('success'):
            if save_invest_price_to_sheet(doc, today_price_data):
                chart_success = True

        if not chart_success:
            print("❌ Sheet6: 구매가격 수집/저장 실패")
            failed_items.append('Sheet6')

        print()
        print("="*50)
        print("📊 최종 결과")
        print("="*50)

        total_sheets = len([item for item in ITEMS if "여기에" not in item['url']]) + 1

        if failed_items:
            print(f"❌ 실패한 시트 ({len(failed_items)}개): {', '.join(failed_items)}")
            print(f"✅ 성공한 시트: {total_sheets - len(failed_items)}개")
            print("="*50)
            print("⚠️ 일부 데이터 수집 실패 - 워크플로우 실패로 종료")
            sys.exit(1)
        else:
            print(f"✅ 모든 시트 ({total_sheets}개) 데이터 수집 성공!")
            print("="*50)
            sys.exit(0)

    except Exception as e:
        print()
        print(f"❌ 프로그램 실행 중 치명적 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        if display:
            try:
                display.stop()
                print("✅ 가상 디스플레이 종료")
            except Exception as e:
                print(f"⚠️ 가상 디스플레이 종료 실패: {e}")


if __name__ == "__main__":
    run()
