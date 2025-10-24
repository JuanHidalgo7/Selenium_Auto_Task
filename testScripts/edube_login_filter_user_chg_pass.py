# edube_login_filter_user.py  (fixed)

from time import sleep
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

LOGIN_URL = "https://edube.org/W1fXQ1lnXJUXl4TEnBBgCzquEwpauO2b/login"
USERS_LIST_URL = "https://edube.org/organization/test-candidate/list"

USERNAME = "jUaN.H1dA1g0#"
PASSWORD = "WhEy{[x8z$e(/)wgF!"
TARGET_EMAIL = "roobed@gmail.com"
NEW_PASSWORD = "python"

WAIT = 20  # seconds

def start_driver(headless=False):
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,900")
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

def login(driver):
    wait = WebDriverWait(driver, WAIT)
    driver.get(LOGIN_URL)

    # username/email field (try common selectors)
    user = None
    for by, sel in [
        (By.ID, "username"), (By.ID, "email"),
        (By.NAME, "username"), (By.NAME, "email"),
        (By.CSS_SELECTOR, "input[type='email']"), (By.CSS_SELECTOR, "input[type='text']"),
    ]:
        try:
            user = wait.until(EC.presence_of_element_located((by, sel)))
            break
        except TimeoutException:
            pass

    pwd = None
    try:
        pwd = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
    except TimeoutException:
        pass

    if not user or not pwd:
        raise RuntimeError("Couldn't find username or password inputs on login page.")

    user.clear(); user.send_keys(USERNAME)
    pwd.clear(); pwd.send_keys(PASSWORD)

    # submit
    try:
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    except Exception:
        pwd.send_keys("\n")

    # consider login successful if URL changes or a logout/profile menu appears
    try:
        wait.until(lambda d: d.current_url != LOGIN_URL)
    except TimeoutException:
        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'logout')]")
        ))

def filter_for_email(driver, email_value: str):
    """Open Users list and filter by an exact email value."""
    wait = WebDriverWait(driver, WAIT)
    driver.get(USERS_LIST_URL)

    # Email input (id is stable on this page)
    email_box = wait.until(EC.presence_of_element_located((By.ID, "filter_email_value")))
    email_box.clear()
    email_box.send_keys(email_value)

    # Click Filter
    filter_btn = driver.find_element(
        By.XPATH, "//form[contains(@class,'sonata-filter-form')]//button[contains(.,'Filter')]"
    )
    filter_btn.click()

    # Wait for any result row
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.sonata-ba-list tbody tr")))

def open_target_row_edit(driver, target_email: str):
    """Click the Id link in the row that contains target_email; return candidate id."""
    wait = WebDriverWait(driver, WAIT)

    # Find the row whose Email cell contains the target email
    row = wait.until(EC.presence_of_element_located(
        (By.XPATH, f"//table[contains(@class,'sonata-ba-list')]//tbody//tr[.//td[contains(normalize-space(.), '{target_email}')]]")
    ))

    # ⚠️ The Id link is in the **second** <td> (first is a checkbox). Use td[2].
    try:
        id_link = row.find_element(By.XPATH, ".//td[2]//a")
    except NoSuchElementException:
        # Robust fallback: any anchor in the row pointing to /organization/test-candidate/.../edit
        id_link = row.find_element(By.XPATH, ".//a[contains(@href,'/organization/test-candidate/') and contains(@href,'/edit')]")

    href = id_link.get_attribute("href")
    candidate_id = href.rstrip("/").split("/")[-2]
    id_link.click()
    logging.info(f"Opened edit page for candidate id {candidate_id}")
    return candidate_id

def set_password_and_update_close(driver, new_password: str):
    """On the edit page, fill Password and click 'Update and close'."""
    wait = WebDriverWait(driver, WAIT)

    # Password field (input[type=password]) — from your HTML it's there
    pwd_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
    pwd_input.clear()
    pwd_input.send_keys(new_password)

    # Click the exact green 'Update and close' button — in your HTML: name="btn_update_and_list"
    try:
        btn = driver.find_element(By.NAME, "btn_update_and_list")
    except NoSuchElementException:
        btn = driver.find_element(
            By.XPATH, "//button[contains(@class,'btn-success') and normalize-space()='Update and close']"
        )

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    try:
        btn.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", btn)

    # Wait for redirect away from the edit URL or list reload
    try:
        wait.until(lambda d: "/edit" not in d.current_url)
    except TimeoutException:
        sleep(2)

def main():
    driver = start_driver(headless=False)
    try:
        login(driver)
        filter_for_email(driver, TARGET_EMAIL)
        cand_id = open_target_row_edit(driver, TARGET_EMAIL)
        logging.info(f"Candidate found: {cand_id}")

        set_password_and_update_close(driver, NEW_PASSWORD)
        logging.info("Password updated and 'Update and close' clicked.")
        sleep(2)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
