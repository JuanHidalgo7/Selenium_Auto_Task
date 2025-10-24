from time import sleep
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGIN_URL = "https://edube.org/W1fXQ1lnXJUXl4TEnBBgCzquEwpauO2b/login"
USERS_LIST_URL = "https://edube.org/organization/test-candidate/list"
USERNAME = "jUaN.H1dA1g0#"
PASSWORD = "WhEy{[x8z$e(/)wgF!"
EMAIL_DOMAIN = "@eagle.fgcu.edu"
WAIT = 15

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
        (By.CSS_SELECTOR, "input[type='email']"), (By.CSS_SELECTOR, "input[type='text']")
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
        # fallback: look for logout link
        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'logout')]")
        ))

def go_to_users_and_filter(driver, email_domain: str):
    wait = WebDriverWait(driver, WAIT)
    driver.get(USERS_LIST_URL)

    # Email input has a stable id; fill it and click Filter
    email_box = wait.until(EC.presence_of_element_located((By.ID, "filter_email_value")))
    email_box.clear()
    email_box.send_keys(email_domain)

    # Click the Filter button inside the filters form
    # (button has class btn-primary and text 'Filter')
    filter_btn = driver.find_element(By.XPATH, "//form[contains(@class,'sonata-filter-form')]//button[contains(.,'Filter')]")
    filter_btn.click()

    # Wait for results table to refresh (page may reload; wait for any row)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.sonata-ba-list tbody tr")))

def main():
    driver = start_driver(headless=False)
    try:
        login(driver)
        go_to_users_and_filter(driver, EMAIL_DOMAIN)
        logging.info("Filtered by email domain; leaving the page open for 10s so you can see it.")
        sleep(10)  # adjust or remove as you like
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
