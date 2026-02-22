import os
import json
import time
import re
import sys
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


def create_driver():
    """
    ✅ 수정: driver 생성 함수 분리 - 매번 새 인스턴스 생성 보장
    """
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-background-networking")  # ✅ 추가: 불필요한 네트워크 차단
    chrome_options.add_argument("--memory-pressure-off")            # ✅ 추가: 메모리 압박 방지
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(40)  # ✅ 수정: 30→40초로 여유 확보
    return driver


def quit_driver(driver):
    """
    ✅ 수정: driver 종료 함수 분리 - 항상 안전하게 종료
    """
    if driver:
        try:
            driver.quit()
        except Exception as e:
            print(f"⚠️ 드라이버 종료 실패 (무시): {e}")


def clean_text(text):
    text = text.replace("'", "").replace("<<", "").replace(",", "")
    cleaned = re.sub(r'[^0-9]', '', text).strip()
    return cleaned if cleaned else "0"


def get_dnf_data(target_url, max_retries=MAX_RETRIES):
    """
    ✅ 수정: 매 시도마다 driver를 새로 생성/종료 + body 실제 로딩 검증 추가
    """
    for attempt in range(max_retries):
        driver = None
        try:
            print(f"🔄 [{attempt+1}/{max_retries}] 접속 시도: {target_url}")

            driver = create_driver()
            driver.get(target_url)

            wait = WebDriverWait(driver, 35)

            # ✅ 수정: body가 실제로 채워졌는지 먼저 검증 (빈 body 크래시 방지)
            wait.until(lambda d: d.execute_script(
                "return document.body && document.body.innerHTML.length > 300"
            ))
            print("✅ 페이지 body 로딩 확인")

            # ✅ 추가: JS 렌더링 완료 대기 (테이블이 동적 생성되는 경우 대비)
            wait.until(lambda d: d.execute_script(
                "return document.readyState"
            ) == "complete")

            row_24_xpath = "//td[contains(text(), '24시간내')]/parent::tr"
            row_24_elem = wait.until(EC.presence_of_element_located((By.XPATH, row_24_xpath)))
            print("✅ 24시간 행 발견")

            row_72_xpath = "//td[contains(text(), '72시간내')]/parent::tr"
            row_72_elem = wait.until(EC.presence_of_element_located((By.XPATH, row_72_xpath)))
            print("✅ 72시간 행 발견")

            time.sleep(2)  # ✅ 수정: 3초→2초 (body 검증으로 이미 충분)

            cols_24 = row_24_elem.find_elements(By.TAG_NAME, "td")
            cols_72 = row_72_elem.find_elements(By.TAG_NAME, "td")

            print(f"📊 24시간 컬럼 수: {len(cols_24)}, 72시간 컬럼 수: {len(cols_72)}")

            if len(cols_24) < 4 or len(cols_72) < 4:
                raise ValueError(f"컬럼 수 부족: 24h={len(cols_24)}, 72h={len(cols_72)}")

            raw_24 = [cols_24[i].text for i in range(1, 4)]
            raw_72 = [cols_72[i].text for i in range(1, 4)]
            print(f"📝 24시간 원본: {raw_24}")
            print(f"📝 72시간 원본: {raw_72}")

            data_24 = [clean_text(t) for t in raw_24]
            data_72 = [clean_text(t) for t in raw_72]
            result = data_24 + data_72

            if all(x == '0' for x in result):
                raise ValueError("⚠️ 모든 데이터가 0 또는 비어있음")

            print(f"✅ 데이터 수집 성공: {result}")
            return result

        except Exception as e:
            print(f"⚠️ [{attempt+1}/{max_retries}] 수집 실패: {e}")

            if driver:
                try:
                    page_source_preview = driver.page_source[:500]
                    print(f"📄 페이지 미리보기: {page_source_preview}...")
                except:
                    pass

            if attempt < max_retries - 1:
                wait_time = 10 * (attempt + 1)  # ✅ 수정: 5→10초 간격으로 늘림
                print(f"   {wait_time}초 후 재시도...")
                time.sleep(wait_time)
            else:
                print(f"❌ 최종 실패 ({target_url})")
                import traceback
                traceback.print_exc()
                return None

        finally:
            quit_driver(driver)  # ✅ 수정: 항상 driver 종료 (성공/실패 무관)


def get_today_buy_price_from_chart(max_retries=MAX_CHART_RETRIES):
    """
    ✅ 수정: driver 생성/종료 분리 적용
    """
    for attempt in range(max_retries):
        driver = None
        try:
            print(f"🔄 [{attempt+1}/{max_retries}] 투자 페이지 접속 시도")

            driver = create_driver()
            driver.get(INVEST_URL)

            wait = WebDriverWait(driver, 35)

            # ✅ 수정: body 실제 로딩 검증
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
            quit_driver(driver)  # ✅ 수정: 항상 driver 종료


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
        print("📦 아이템 데이터 수집 시작 (9개 아이템)")
        print("="*50)

        for i, item in enumerate(ITEMS):
            if "여기에" in item['url']:
                print(f"⏭️  [{i+1}/9] {item['sheet_name']} 스킵 (URL 미설정)")
                continue

            print()
            print(f"--- [{i+1}/9] {item['sheet_name']} 작업 중 ---")

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

            # ✅ 수정: 시트 간 대기를 5→8초로 늘려 서버 부하 분산
            time.sleep(8)

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
