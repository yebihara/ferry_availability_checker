#!/usr/bin/env python3
"""
AWS Lambda用フェリー空室確認プログラム
"""

import json
import os
import time
import boto3
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def setup_driver():
    """Chrome WebDriverのセットアップ（Lambda用）"""
    options = Options()
    
    # シンプルで確実な設定
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1280x1696')
    
    # Lambda環境用の設定
    options.binary_location = '/opt/chrome/chrome'
    
    from selenium.webdriver.chrome.service import Service
    service = Service(
        executable_path='/usr/local/bin/chromedriver',
        log_path='/tmp/chromedriver.log'
    )
    
    try:
        print("ChromeDriverサービスを開始中...")
        driver = webdriver.Chrome(
            service=service,
            options=options
        )
        
        print("WebDriverが正常に初期化されました")
        print(f"Chrome version: {driver.capabilities['browserVersion']}")
        print(f"ChromeDriver version: {driver.capabilities['chrome']['chromedriverVersion']}")
        
        # タイムアウトを短めに設定
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(10)
        
        return driver
    except Exception as e:
        print(f"WebDriver初期化エラー: {e}")
        print(f"エラー型: {type(e).__name__}")
        raise


def send_notification_email(availability_status, departure_date, has_availability=False):
    """SESを使ってメール通知を送信"""
    ses_client = boto3.client('ses', region_name='us-east-1')  # SESのリージョンを指定
    
    # 空きの有無によってメール件名と内容を調整
    if has_availability:
        subject = f"🚢 【空きあり】フェリー空室情報 - {departure_date}"
        status_message = "空きが見つかりました！"
        notification_note = "この通知は1時間おきの定期チェックで送信されています。"
    else:
        subject = f"📋 フェリー空室情報 - {departure_date}"
        status_message = "現在空きはありません。"
        notification_note = "この通知は1時間おきの定期チェックで送信されています。"
    
    # メール本文を作成
    body_text = f"""フェリーの空室状況をお知らせします。

出発日: {departure_date}
航路: 東京 → 徳島

{status_message}

空室状況:
2名個室: {availability_status['2名個室']}
二等洋室: {availability_status['二等洋室']}

{notification_note}
"""
    
    body_html = f"""
    <html>
    <body>
        <h2>フェリー空室情報</h2>
        <p><strong>出発日:</strong> {departure_date}<br>
        <strong>航路:</strong> 東京 → 徳島</p>
        
        <div style="padding: 10px; margin: 10px 0; border-radius: 5px; {'background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb;' if has_availability else 'background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;'}">
            <strong>{status_message}</strong>
        </div>
        
        <h3>空室状況</h3>
        <ul>
            <li><strong>2名個室:</strong> {availability_status['2名個室']}</li>
            <li><strong>二等洋室:</strong> {availability_status['二等洋室']}</li>
        </ul>
        
        <p><em>{notification_note}</em></p>
    </body>
    </html>
    """
    
    try:
        response = ses_client.send_email(
            Source='yuichiro.ebihara@gmail.com',  # 送信者アドレス（SESで認証済み）
            Destination={
                'ToAddresses': ['yuichiro.ebihara@gmail.com']
            },
            Message={
                'Subject': {
                    'Data': subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': body_text,
                        'Charset': 'UTF-8'
                    },
                    'Html': {
                        'Data': body_html,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        print(f"メール送信成功: {response['MessageId']}")
        return True
    except Exception as e:
        print(f"メール送信エラー: {e}")
        return False


def parse_date(date_str):
    """YYYYMMDD形式の日付文字列をYYYY/MM/DD形式に変換"""
    try:
        date_obj = datetime.strptime(date_str, "%Y%m%d")
        return date_obj.strftime("%Y/%m/%d")
    except ValueError:
        raise ValueError(f"日付形式が正しくありません: {date_str}")


def check_ferry_availability(departure_date):
    """フェリーの空室状況をチェック"""
    driver = None
    try:
        driver = setup_driver()
        
        # ページの読み込み待機
        wait = WebDriverWait(driver, 15)
        
        # 初期ページにアクセス
        driver.get("https://yoyaku-otf.jp/ryokyaku")
        
        # 利用規約に同意
        try:
            agree_checkbox = driver.find_element(By.ID, "agree_with")
            driver.execute_script("arguments[0].click();", agree_checkbox)
            time.sleep(1)
        except Exception as e:
            print(f"同意チェックボックスでエラー: {e}")
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}")
        
        # 「新規予約へ進む」ボタンをクリック
        try:
            new_reservation_button = driver.find_element(By.CSS_SELECTOR, "input[value='新規予約へ進む']")
            driver.execute_script("arguments[0].click();", new_reservation_button)
            time.sleep(3)
        except Exception as e:
            print(f"新規予約ボタンでエラー: {e}")
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}")
        
        # 往復選択で「片道」を選択（値が2）
        try:
            one_way_element = driver.find_element(By.ID, "w_ryokyaku_yoyaku_ohuku_yoyaku_kb_2")
            driver.execute_script("arguments[0].click();", one_way_element)
            time.sleep(1)
        except Exception as e:
            print(f"片道選択でエラー: {e}")
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}")
        
        # 航路選択で「東京 >>> 徳島」を選択
        try:
            route_element = driver.find_element(By.ID, "w_ryokyaku_yoyaku_koro_cd")
            select = Select(route_element)
            select.select_by_value("12")
            time.sleep(1)
        except Exception as e:
            print(f"航路選択でエラー: {e}")
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}")
        
        # 出発日を設定
        try:
            date_element = driver.find_element(By.ID, "w_ryokyaku_yoyaku_yuki_jyosen_on")
            date_element.clear()
            date_element.send_keys(departure_date)
            time.sleep(1)
        except Exception as e:
            print(f"日付入力でエラー: {e}")
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}")
        
        # 「次へ進む」ボタンをクリック
        try:
            next_button = driver.find_element(By.CSS_SELECTOR, "input[value='次へ進む']")
            driver.execute_script("arguments[0].click();", next_button)
            time.sleep(5)
        except Exception as e:
            print(f"次へボタンクリックでエラー: {e}")
            print(f"エラーの詳細: {type(e).__name__}: {str(e)}")
        
        # 空室状況をチェック
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # 「2名個室」「二等洋室」の空き状況を確認
        room_availability = {
            "2名個室": "取得できませんでした",
            "二等洋室": "取得できませんでした"
        }
        
        tables = driver.find_elements(By.TAG_NAME, "table")
        
        for table in tables:
            table_text = table.text
            if '二等洋室' in table_text or '2名個室' in table_text:
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
                        print(f"行の処理でエラー: {e}")
                        continue
        
        return room_availability
        
    except TimeoutException as e:
        print("ページの読み込みがタイムアウトしました")
        print(f"エラーの詳細: {type(e).__name__}: {str(e)}")
        return {
            "2名個室": "取得できませんでした",
            "二等洋室": "取得できませんでした"
        }
    except Exception as e:
        print(f"予期しないエラーが発生しました: {e}")
        print(f"エラーの詳細: {type(e).__name__}: {str(e)}")
        return {
            "2名個室": "取得できませんでした",
            "二等洋室": "取得できませんでした"
        }
    finally:
        if driver:
            driver.quit()


def lambda_handler(event, context):
    """Lambda関数のエントリーポイント"""
    try:
        # 環境変数から日付を取得（デフォルトは20250809）
        departure_date_raw = os.environ.get('DEPARTURE_DATE', '20250809')
        departure_date = parse_date(departure_date_raw)
        
        print(f"フェリー空室チェック開始: {departure_date}")
        
        # 空室状況をチェック
        availability = check_ferry_availability(departure_date)
        
        print(f"空室状況: {availability}")
        
        # 空きがあるかチェック（×でなければ空きあり）
        has_availability = False
        for room_type, status in availability.items():
            if status != '×' and status != '取得できませんでした':
                has_availability = True
                break
        
        result = {
            'departure_date': departure_date,
            'availability': availability,
            'has_availability': has_availability,
            'notification_sent': False
        }
        
        # 空きの有無に関わらず毎回メール通知を送信
        if has_availability:
            print("空きが見つかりました。メール通知を送信します。")
        else:
            print("空きがありませんでした。定期通知メールを送信します。")
        
        notification_success = send_notification_email(availability, departure_date, has_availability)
        result['notification_sent'] = notification_success
        
        return {
            'statusCode': 200,
            'body': json.dumps(result, ensure_ascii=False)
        }
        
    except Exception as e:
        print(f"Lambda実行エラー: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            }, ensure_ascii=False)
        }