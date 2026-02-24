import os
import json
import time
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1lKwU5aY6WGywhPRN1uIbCNjX8wQ7hcUNcGstgvoBeFI/edit"

ITEMS = [
    {"url": "http://dnfnow.xyz/item?item_idx=bfc7bb0aefe4d0c432ebf77836e68e3c",  "sheet_name": "Sheet1"},
    {"url": "http://dnfnow.xyz/item?item_idx=4a737b2ae337a57260ca4663ce6a9bb0",  "sheet_name": "Sheet2"},
    {"url": "http://dnfnow.xyz/item?item_idx=fac4ce61d490d3a006025c797abb5950",  "sheet_name": "Sheet3"},
    {"url": "http://dnfnow.xyz/item?item_idx=bb5a6aeb6b44bbdce835679bef4335b5",  "sheet_name": "Sheet4"},
    {"url": "http://dnfnow.xyz/item?item_idx=55be75a1c024aac3ef84ed3bed5b8db9",  "sheet_name": "Sheet5"},
    {"url": "http://dnfnow.xyz/item?item_idx=4e5c23c6083931685b79d8b542eeb268",  "sheet_name": "Sheet7"},
    {"url": "http://dnfnow.xyz/item?item_idx=028f60ed1253313f5bbd99f228461f33",  "sheet_name": "Sheet8"},
    {"url": "http://dnfnow.xyz/item?item_idx=51f381d45d16ef4273ae25f01f7ea4c2",  "sheet_name": "Sheet9"},
]

START_ROW  = 5
START_COL  = 2
MAX_RETRIES = 3
# ==========================================


def clean_number(text: str) -> int:
    cleaned = re.sub(r'[^\d]', '', text).strip()
    return int(cleaned) if cleaned else 0


def get_dnf_data(target_url: str, max_retries: int = MAX_RETRIES):
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }

    for attempt in range(max_retries):
        try:
            print(f"🔄 [{attempt+1}/{max_retries}] 접속 시도: {target_url}")
            response = requests.get(target_url, headers=req_headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')

            row_24 = None
            row_72 = None

            for tr in soup.find_all('tr'):
                tds = tr.find_all('td')
                if not tds:
                    continue
                first = tds[0].get_text(strip=True)
                if first == '24시간내':
                    row_24 = tr
                elif first == '72시간내':
                    row_72 = tr

            if not row_24 or not row_72:
                print("⚠️ 테이블 탐지 실패. tr 첫 td 목록:")
                for i, tr in enumerate(soup.find_all('tr')[:15]):
                    tds = tr.find_all('td')
                    if tds:
                        print(f"   tr[{i}]: '{tds[0].get_text(strip=True)}'")
                raise ValueError("테이블 행을 찾을 수 없음")

            cols_24 = row_24.find_all('td')
            cols_72 = row_72.find_all('td')

            print(f"📝 24h 원본: {[td.get_text(strip=True) for td in cols_24]}")
            print(f"📝 72h 원본: {[td.get_text(strip=True) for td in cols_72]}")

            if len(cols_24) < 4 or len(cols_72) < 4:
                raise ValueError(f"컬럼 수 부족: 24h={len(cols_24)}, 72h={len(cols_72)}")

            result = [
                clean_number(cols_24[1].get_text(strip=True)),
                clean_number(cols_24[2].get_text(strip=True)),
                clean_number(cols_24[3].get_text(strip=True)),
                clean_number(cols_72[1].get_text(strip=True)),
                clean_number(cols_72[2].get_text(strip=True)),
                clean_number(cols_72[3].get_text(strip=True)),
            ]

            if all(x == 0 for x in result):
                raise ValueError("모든 데이터가 0")

            print(f"✅ 수집 성공: {result}")
            return result

        except Exception as e:
            print(f"⚠️ [{attempt+1}/{max_retries}] 실패: {e}")
            if attempt < max_retries - 1:
                wait = 10 * (attempt + 1)
                print(f"   {wait}초 후 재시도...")
                time.sleep(wait)
            else:
                print(f"❌ 최종 실패: {target_url}")
                import traceback
                traceback.print_exc()
                return None


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
    failed_items = []

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
        print("📦 아이템 데이터 수집 시작 (Sheet1~9)")
        print("="*50)

        for i, item in enumerate(ITEMS):
            print(f"\n--- [{i+1}/{len(ITEMS)}] {item['sheet_name']} ---")
            result_data = get_dnf_data(item['url'])

            if result_data:
                try:
                    worksheet  = doc.worksheet(item['sheet_name'])
                    col_values = worksheet.col_values(START_COL)
                    next_row   = max(START_ROW, len(col_values) + 1)

                    kst        = ZoneInfo("Asia/Seoul")
                    now_time   = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
                    final_row  = [now_time] + result_data
                    cell_range = f"B{next_row}:H{next_row}"

                    if update_sheet_with_retry(worksheet, cell_range, [final_row]):
                        print(f"💾 저장 완료: {final_row}")
                    else:
                        failed_items.append(item['sheet_name'])

                except Exception as e:
                    print(f"❌ {item['sheet_name']} 저장 에러: {e}")
                    import traceback
                    traceback.print_exc()
                    failed_items.append(item['sheet_name'])
            else:
                failed_items.append(item['sheet_name'])

            time.sleep(3)

        print("\n" + "="*50)
        print("📊 최종 결과")
        print("="*50)

        if failed_items:
            print(f"❌ 실패 ({len(failed_items)}개): {', '.join(failed_items)}")
            print(f"✅ 성공: {len(ITEMS) - len(failed_items)}개")
            sys.exit(1)
        else:
            print(f"✅ 전체 성공 ({len(ITEMS)}개)")
            sys.exit(0)

    except Exception as e:
        print(f"❌ 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run()
