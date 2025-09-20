import imaplib
import email
import time
import re
import os
from email.header import decode_header, make_header
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- 사용자 설정 ---
YOUR_NAVER_ID = "ENTER YOUR NAVER ID"  # 네이버 아이디
YOUR_NAVER_APP_PASSWORD = "ENTER YOUR NAVER APP PASSWORD"  # 네이버 앱 비밀번호


# 환경 변수에서 네이버 ID와 앱 비밀번호를 읽어옵니다. (환경 변수 설정이 안된 경우 기본값 사용)
# os.getenv(환경변수 있을시, 기본값)
NAVER_ID = os.getenv("NAVER_ID", YOUR_NAVER_ID)
NAVER_APP_PASSWORD = os.getenv("NAVER_APP_PASSWORD", YOUR_NAVER_APP_PASSWORD)

# --- 네이버 IMAP 서버 정보 ---
IMAP_SERVER = "imap.naver.com"
IMAP_PORT = 993

# --- 상수 설정 ---
READTIMEOUT_SEC = 1

def decode_mime_header(header):
    """MIME 인코딩된 메일 헤더를 디코딩합니다."""
    decoded_parts = decode_header(header)
    return str(make_header(decoded_parts))

def get_email_body(email_message):
    """email 메시지 객체에서 본문(text/plain)을 추출하여 반환합니다."""
    if email_message.is_multipart():
        for part in email_message.walk():
            if part.get_content_type() == "text/plain":
                try:
                    charset = part.get_content_charset()
                    return part.get_payload(decode=True).decode(charset or 'utf-8', errors='ignore')
                except Exception:
                    return "[본문 디코딩 오류]"
    else:
        try:
            charset = email_message.get_content_charset()
            return email_message.get_payload(decode=True).decode(charset or 'utf-8', errors='ignore')
        except Exception:
            return "[본문 디코딩 오류]"
    return ""

def extract_url(text):
    """주어진 텍스트에서 http 또는 https로 시작하는 URL을 찾아 반환합니다."""
    url_pattern = re.compile(r'https?://[^\s<>\"]+|www\.[^\s<>" ]+')
    match = url_pattern.search(text)
    if match:
        return match.group(0)
    return None

def automate_auth_page(url):
    """셀레니움을 사용하여 인증 페이지 자동화를 수행합니다."""
    driver = None
    try:
        print(f"\n감지된 URL >> {url}")
        print("새 헤드리스 브라우저 창을 열어 해당 URL로 이동합니다...")
        
        # --- 헤드리스 옵션 설정 ---
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)

        # --- 인증 페이지 자동화 로직 ---
        print("\n--- 인증 페이지 자동화 시작 ---")
        wait = WebDriverWait(driver, 15)

        # 1. 체크박스 대기 및 클릭
        print("체크박스가 클릭 가능해질 때까지 기다립니다...")
        checkbox = wait.until(EC.element_to_be_clickable((By.ID, "checkbox-not-robot")))
        print("체크박스를 찾았습니다. 클릭을 시도합니다.")
        checkbox.click()

        # 2. '인증 진행' 버튼 영역 대기
        print("'인증 진행' 버튼 영역이 나타날 때까지 기다립니다...")
        wait.until(
            lambda d: d.find_element(By.ID, "box-btn-tryAuth").value_of_css_property('display') == 'block'
        )
        print("성공: 체크박스 클릭 후 '인증 진행' 버튼 영역이 나타났습니다.")

        # 3. '인증 진행' 버튼 클릭
        print("'인증 진행' 버튼을 클릭합니다.")
        auth_button = wait.until(EC.element_to_be_clickable((By.ID, "btn-tryAuth")))
        auth_button.click()
        print("'인증 진행' 버튼 클릭 완료.")
        
        # 성공 메시지가 나타날 때까지 잠시 대기 (선택 사항)
        wait.until(EC.presence_of_element_located((By.ID, "message-count")))
        success_message = driver.find_element(By.ID, "message-count").text
        print(f"인증 완료 메시지: {success_message}")
        print("--- 인증 페이지 자동화 성공 ---\n")

    except Exception as e:
        print(f"[Selenium 오류] 자동화 중 문제가 발생했습니다: {e}")
    finally:
        if driver:
            print("5초 후에 브라우저를 닫습니다.")
            time.sleep(5)
            driver.quit()

def monitor_emails_and_open_link(target_subject, check_interval_sec):
    """특정 제목의 새 메일을 감시하고, 도착하면 링크를 추출하여 Selenium으로 엽니다."""
    print(f"'{target_subject}' 제목의 새 메일을 실시간으로 감시합니다.")
    print(f"확인 주기: {check_interval_sec}초 (종료하려면 Ctrl+C를 누르세요)")
    
    mail = None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(NAVER_ID, NAVER_APP_PASSWORD)

        while True:
            try:
                mail.select("INBOX")
                status, mail_ids = mail.search(None, '(UNSEEN)')
                
                if status == 'OK':
                    id_list = mail_ids[0].split()
                    if id_list:
                        # 최신 메일 1개만 처리하도록 변경 (중복 방지)
                        latest_mail_id = id_list[-1]
                        
                        status, data = mail.fetch(latest_mail_id, '(RFC822)')
                        
                        if status == 'OK':
                            raw_email = data[0][1]
                            email_message = email.message_from_bytes(raw_email)
                            subject = decode_mime_header(email_message['Subject'])
                            
                            if target_subject in subject:
                                print("\n" + "="*50)
                                print("지정된 제목의 새 메일이 도착했습니다!")
                                print(f"  - 제  목: {subject}")
                                print("-"*50)
                                
                                body = get_email_body(email_message)
                                url_to_open = extract_url(body)
                                
                                if url_to_open:
                                    # 별도 함수로 셀레니움 자동화 실행
                                    automate_auth_page(url_to_open)
                                else:
                                    print("[알림] 본문에서 URL을 찾지 못했습니다.")
                                print("="*50 + "\n")
                                
                                # 처리한 메일은 '읽음'으로 표시
                                mail.store(latest_mail_id, '+FLAGS', '\\Seen')

                time.sleep(check_interval_sec)
            except Exception as e:
                print(f"루프 중 오류 발생: {e}")
                print("5초 후 재시도합니다...")
                time.sleep(5)

    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    except Exception as e:
        print(f"오류가 발생했습니다: {e}")
    finally:
        if mail and mail.state != 'LOGOUT':
            mail.logout()
            print("IMAP 연결을 종료했습니다.")

# --- 메인 함수 실행 ---
if __name__ == "__main__":
    subject_to_watch = "[인증 알림이] Email 인증을 진행하여 주십시오."
    monitor_emails_and_open_link(subject_to_watch, check_interval_sec=READTIMEOUT_SEC)