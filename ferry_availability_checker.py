#!/usr/bin/env python3
"""
フェリー空室確認プログラム
大阪南港 → 東京間のフェリー予約サイトで空室状況を確認する
"""

import time
import sys
import argparse
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def setup_driver():
    """Chrome WebDriverのセットアップ"""
    options = Options()
    options.add_argument('--headless')  # ヘッドレスモードで実行
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
    
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        print(f"WebDriverの初期化に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)


def check_ferry_availability(departure_date):
    """フェリーの空室状況をチェック"""
    driver = setup_driver()
    
    try:
        # 初期ページにアクセス
        driver.get("https://yoyaku-otf.jp/ryokyaku")
        
        # ページの読み込み待機
        wait = WebDriverWait(driver, 10)
        
        # 利用規約に同意
        try:
            agree_checkbox = driver.find_element(By.ID, "agree_with")
            driver.execute_script("arguments[0].click();", agree_checkbox)
            time.sleep(1)
        except Exception as e:
            print(f"同意チェックボックスでエラー: {e}", file=sys.stderr)
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}", file=sys.stderr)
        
        # 「新規予約へ進む」ボタンをクリック
        try:
            new_reservation_button = driver.find_element(By.CSS_SELECTOR, "input[value='新規予約へ進む']")
            driver.execute_script("arguments[0].click();", new_reservation_button)
            time.sleep(3)
        except Exception as e:
            print(f"新規予約ボタンでエラー: {e}", file=sys.stderr)
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}", file=sys.stderr)
        
        # 往復選択で「片道」を選択（値が2）
        try:
            # 片道は値が2のラジオボタン
            one_way_element = driver.find_element(By.ID, "w_ryokyaku_yoyaku_ohuku_yoyaku_kb_2")
            driver.execute_script("arguments[0].click();", one_way_element)
            time.sleep(1)
        except Exception as e:
            print(f"片道選択でエラー: {e}", file=sys.stderr)
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}", file=sys.stderr)
        
        # 航路選択で「東京 >>> 徳島」を選択
        try:
            # 東京 <=> 徳島の航路（値が12）を選択
            route_element = driver.find_element(By.ID, "w_ryokyaku_yoyaku_koro_cd")
            select = Select(route_element)
            select.select_by_value("12")
            time.sleep(1)
        except Exception as e:
            print(f"航路選択でエラー: {e}", file=sys.stderr)
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}", file=sys.stderr)
        
        # 出発日を設定
        try:
            # 実際の日付入力フィールドIDに基づいて設定
            date_element = driver.find_element(By.ID, "w_ryokyaku_yoyaku_yuki_jyosen_on")
            date_element.clear()
            date_element.send_keys(departure_date)
            time.sleep(1)
        except Exception as e:
            print(f"日付入力でエラー: {e}", file=sys.stderr)
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}", file=sys.stderr)
        
        # 「次へ進む」ボタンをクリック
        try:
            # 実際の送信ボタンに基づいてクリック
            next_button = driver.find_element(By.CSS_SELECTOR, "input[value='次へ進む']")
            driver.execute_script("arguments[0].click();", next_button)
            time.sleep(5)  # ページ遷移を十分に待つ
        except Exception as e:
            print(f"次へボタンクリックでエラー: {e}", file=sys.stderr)
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}", file=sys.stderr)
        
        # 空室状況をチェック
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # 「2名個室」「二等洋室」の空き状況を確認
        try:
            # 各部屋タイプの空き状況を記録
            room_availability = {
                "2名個室": "取得できませんでした",
                "二等洋室": "取得できませんでした"
            }
            
            # spare_ct クラスを持つセルを探す
            spare_cells = driver.find_elements(By.CLASS_NAME, "spare_ct")
            
            # 各部屋タイプの行を探す
            tables = driver.find_elements(By.TAG_NAME, "table")
            
            for table in tables:
                table_text = table.text
                if '二等洋室' in table_text or '2名個室' in table_text:
                    # このテーブル内で空き状況を検索
                    rows = table.find_elements(By.TAG_NAME, "tr")
                    for row in rows:
                        try:
                            # 2名個室の空き状況をチェック
                            if '2名個室' in row.text:
                                # spare_ct クラスを持つセルを探す
                                spare_cell = row.find_element(By.CLASS_NAME, "spare_ct")
                                availability_text = spare_cell.text.strip()
                                if availability_text:
                                    room_availability["2名個室"] = availability_text
                            
                            # 二等洋室の空き状況をチェック（女性部屋は除く）
                            if '二等洋室' in row.text and '女性部屋' not in row.text:
                                # spare_ct クラスを持つセルを探す
                                spare_cell = row.find_element(By.CLASS_NAME, "spare_ct")
                                availability_text = spare_cell.text.strip()
                                if availability_text:
                                    room_availability["二等洋室"] = availability_text
                        except Exception as e:
                            # 個別の行でエラーが起きても続行
                            print(f"行の処理でエラー: {e}", file=sys.stderr)
                            continue
            
            # 結果を表示
            print(f"2名個室: {room_availability['2名個室']}")
            print(f"二等洋室: {room_availability['二等洋室']}")
                    
        except Exception as e:
            print(f"空室確認でエラー: {e}", file=sys.stderr)
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}", file=sys.stderr)
            print("2名個室: 取得できませんでした")
            print("二等洋室: 取得できませんでした")
        
    except TimeoutException as e:
        print("ページの読み込みがタイムアウトしました", file=sys.stderr)
        print(f"エラーの詳細: {type(e).__name__}: {str(e)}", file=sys.stderr)
        print("2名個室: 取得できませんでした")
        print("二等洋室: 取得できませんでした")
    except Exception as e:
        print(f"予期しないエラーが発生しました: {e}", file=sys.stderr)
        print(f"エラーの詳細: {type(e).__name__}: {str(e)}", file=sys.stderr)
        print("2名個室: 取得できませんでした")
        print("二等洋室: 取得できませんでした")
    finally:
        driver.quit()


def parse_date(date_str):
    """YYYYMMDD形式の日付文字列をYYYY/MM/DD形式に変換"""
    try:
        # YYYYMMDD形式の文字列をパース
        date_obj = datetime.strptime(date_str, "%Y%m%d")
        # YYYY/MM/DD形式に変換
        return date_obj.strftime("%Y/%m/%d")
    except ValueError:
        print(f"エラー: 日付形式が正しくありません。YYYYMMDD形式で入力してください: {date_str}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="フェリー空室確認プログラム",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python ferry_availability_checker.py 20250809
  python ferry_availability_checker.py 20251225
        """
    )
    parser.add_argument(
        "date",
        help="出発日をYYYYMMDD形式で指定（例: 20250809）"
    )
    
    args = parser.parse_args()
    
    # 日付を変換
    formatted_date = parse_date(args.date)
    
    # 空室確認を実行
    check_ferry_availability(formatted_date)