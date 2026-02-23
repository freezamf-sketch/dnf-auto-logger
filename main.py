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

INVEST_URL        = "http://dnfnow.xyz/invest"
INVEST_SHEET_NAME = "Sheet6"
START_ROW         = 5
START_COL         = 2
MAX_RETRIES       = 3
# ==========================================


def clean_number(text: str) -> int:
    """숫자 이외 모든 문자(↑, 쉼표 등) 제거 후 int 반환"""
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
            html = response.text

            # ✅ 인코딩 디버그 출력 (첫 시도에만)
            if attempt == 0:
                snippet = html[html.find('시간'):html.find('시간')+50] if '시간' in html else html[:200]
                print(f"📄 HTML 스니펫: {snippet}")

            soup = BeautifulSoup(html, 'html.parser')

            # ✅ 핵심 수정: tr 전체를 순회하며 첫 번째 td 텍스트로 매칭
            row_24 = None
            row_72 = None

            for tr in soup.find_all('tr'):
                tds = tr.find_all('td')
                if not tds:
                    continue
                first_td_text = tds[0].get_text(strip=True)
                if '24' in first_td_text and '시간' in first_td_text:
                    row_24 = tr
                elif '72' in first_td_text and '시간' in first_td_text:
                    row_72 = tr

            if not row_24 or not row_72:
                # 못 찾으면 HTML 전체 테이블 구조를 로그로 출력
                print(f"⚠️ 테이블 탐지 실패. 전체 tr 목록:")
                for i, tr in enumerate(soup.find_all('tr')[:10]):
                    tds = [td.get_text(strip=True)[:20] for td in tr.find_all('td')]
                    print(f"   tr[{i}]: {tds}")
                raise ValueError("테이블 행을 찾을 수 없음")

            cols_24 = row_24.find_all('td')
            cols_72 = row_72.find_all('td')

            print(f"📊 24h 컬럼수: {len(cols_24)}, 72h 컬럼수: {len(cols_72)}")
            print(f"📝 24h 원본: {[td.get_text(strip=True) for td in cols_24]}")
            print(f"📝 72h 원본: {[td.get_text(strip=True) for td in cols_72]}")

            # 현재 구조: [라벨(0), 물량(1), 총거래액(2), 평균가격(3)]
            if len(cols_24) < 4 or len(cols_72) < 4:
                raise ValueError(f"컬럼 수 부족: 24h={len(cols_24)}, 72h={len(cols_72)}")

            vol_24  = clean_number(cols_24[1].get_text(strip=True))
            tot_24  = clean_number(cols_24[2].get_text(strip=True))
            avg_24  = clean_number(cols_24[3].get_text(strip=True))
            vol_72  = clean_number(cols_72[1].get_text(strip=True))
            tot_72  = clean_number(cols_72[2].get_text(strip=True))
            avg_72  = clean_number(cols_72[3].get_text(strip=True))

            result = [vol_24, tot_24, avg_24, vol_72, tot_72, avg_72]

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


def get_invest_data(max_retries: int = MAX_RETRIES):
    """
    /invest 페이지의 '세라템 투자처' 테이블에서
    현재 골드 거래 시세(100만 골드당 현금)를 수집.

    테이블 구조 (확인됨):
    | 아이템명 | 세라템 가격 | 현재 가격 | 현재 물량 | 100만당 환산 현금 |
    → '현재 가격' 컬럼(인덱스 2)의 첫 번째 유효한 행 값을 저장
    """
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    kst       = ZoneInfo("Asia/Seoul")
    today_str = datetime.now(kst).strftime("%Y%m%d")

    for attempt in range(max_retries):
        try:
            print(f"🔄 [{attempt+1}/{max_retries}] 투자 페이지 접속: {INVEST_URL}")
            resp = requests.get(INVEST_URL, headers=req_headers, timeout=30)
            resp.raise_for_status()
            resp.encoding = 'utf-8'

            soup = BeautifulSoup(resp.text, 'html.parser')

            # ✅ '100만당 환산 현금' 헤더가 있는 테이블 탐지
            target_table = None
            for table in soup.find_all('table'):
                if '100만당' in table.get_text() or '환산' in table.get_text():
                    target_table = table
                    break

            if not target_table:
                raise ValueError("투자 테이블을 찾을 수 없음")

            rows = target_table.find_all('tr')
            print(f"📊 투자 테이블 행 수: {len(rows)}")

            # 헤더 파싱으로 컬럼 인덱스 확인
            header_row = rows[0]
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            print(f"📋 헤더: {headers}")

            # '현재 가격' 컬럼 인덱스 동적 탐색
            price_col_idx = None
            for idx, h in enumerate(headers):
                if '현재' in h and '가격' in h:
                    price_col_idx = idx
                    break
            if price_col_idx is None:
                price_col_idx = 2  # fallback: 인덱스 2
            print(f"💡 현재 가격 컬럼 인덱스: {price_col_idx}")

            # 데이터 행 전체 수집 (물량없음 제외)
            invest_rows = []
            for row in rows[1:]:
                cols = row.find_all('td')
                if len(cols) <= price_col_idx:
                    continue
                price_text = cols[price_col_idx].get_text(strip=True)
                if '물량없음' in price_text or not price_text:
                    continue
                price_val = clean_number(price_text)
                if price_val > 0:
                    item_name = cols[0].get_text(strip=True)
                    invest_rows.append((item_name, price_val))

            if not invest_rows:
                raise ValueError("유효한 투자 데이터 없음")

            # 첫 번째 유효 행의 현재 가격을 대표값으로 사용
            first_item, first_price = invest_rows[0]
            print(f"✅ 투자 데이터 수집 성공: {len(invest_rows)}건, 대표값={first_item}/{first_price}")
            return {
                'success': True,
                'date': today_str,
                'price': first_price,
                'rows': invest_rows,
            }

        except Exception as e:
            print(f"⚠️ [{attempt+1}/{max_retries}] 투자 페이지 실패: {e}")
            if attempt < max_retries - 1:
                print(f"   10초 후 재시도...")
                time.sleep(10)
            else:
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
                print(f"⚠️ API 에러 [{attempt+1}/{max_retries}]: {error_msg[:100]}")
                if attempt < max_retries - 1:
                    print(f"   {wait_time}초 후 재시도...")
                    time.sleep(wait_time)
            else:
                print(f"❌ 재시도 불가 에러: {e}")
                raise
    return False


def save_invest_to_sheet(doc, invest_data):
    if not invest_data or not invest_data.get('success'):
        print("❌ Sheet6: 저장할 데이터 없음")
        return False
    try:
        worksheet  = doc.worksheet(INVEST_SHEET_NAME)
        col_values = worksheet.col_values(START_COL)
        next_row   = max(START_ROW, len(col_values) + 1)

        kst             = ZoneInfo("Asia/Seoul")
        collection_time = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
        date_str        = invest_data['date']
        price           = int(invest_data['price'])  # int로 강제 변환 (double 초과 방지)

        row_data   = [collection_time, date_str, price]
        cell_range = f"B{next_row}:D{next_row}"

        if update_sheet_with_retry(worksheet, cell_range, [row_data]):
            print(f"✅ Sheet6 저장 성공: {row_data}")
            return True
        else:
            print("❌ Sheet6 저장 실패")
            return False

    except Exception as e:
        print(f"❌ Sheet6 저장 에러: {e}")
        import traceback
        traceback.print_exc()
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
        print("📦 아이템 데이터 수집 시작")
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
                    # result_data는 이미 int 리스트 → 스프레드시트에 숫자로 저장
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
        print("💰 투자 페이지 수집 (Sheet6)")
        print("="*50)

        invest_data = get_invest_data()
        if not save_invest_to_sheet(doc, invest_data):
            failed_items.append('Sheet6')

        print("\n" + "="*50)
        print("📊 최종 결과")
        print("="*50)
        total = len(ITEMS) + 1

        if failed_items:
            print(f"❌ 실패 ({len(failed_items)}개): {', '.join(failed_items)}")
            print(f"✅ 성공: {total - len(failed_items)}개")
            sys.exit(1)
        else:
            print(f"✅ 전체 성공 ({total}개)")
            sys.exit(0)

    except Exception as e:
        print(f"❌ 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run()
