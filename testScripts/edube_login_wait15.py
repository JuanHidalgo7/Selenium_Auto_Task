from time import sleep
import sys
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# -------- CONFIG --------
LOGIN_URL = "https://edube.org/W1fXQ1lnXJUXl4TEnBBgCzquEwpauO2b/login"

# You provided these credentials. For production use, put them in env vars instead.
USERNAME = "jUaN.H1dA1g0#"
PASSWORD = "WhEy{[x8z$e(/)wgF!"

USE_ENV_VARS = False  # set True to load from EDUBE_USER / EDUBE_PASS env vars
HEADLESS = False      # True to run without opening a visible browser
WAIT_TIMEOUT = 12     # seconds to wait for elements and login success detection
# ------------------------

def get_credentials():
    if USE_ENV_VARS:
        import os
        u = os.getenv("EDUBE_USER")
        p = os.getenv("EDUBE_PASS")
        if not u or not p:
            logger.error("Env vars EDUBE_USER / EDUBE_PASS not found.")
            sys.exit(1)
        return u, p
    return USERNAME, PASSWORD

def start_chrome(headless: bool = False):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1400,900")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def find_input(driver, wait, candidates):
    """
    Tries a list of (By, selector) until an element is found (presence).
    Returns the WebElement or None.
    """
    for by, sel in candidates:
        try:
            elem = wait.until(EC.presence_of_element_located((by, sel)))
            return elem
        except TimeoutException:
            continue
    return None

def login_flow(driver, username, password):
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    driver.get(LOGIN_URL)
    logger.info("Opened login page: %s", LOGIN_URL)

    # candidate locators for username/email
    username_candidates = [
        (By.ID, "username"),
        (By.ID, "email"),
        (By.NAME, "username"),
        (By.NAME, "email"),
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[type='text']"),
        (By.XPATH, "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')]"),
        (By.XPATH, "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'user')]"),
    ]

    # candidate locators for password
    password_candidates = [
        (By.ID, "password"),
        (By.NAME, "password"),
        (By.CSS_SELECTOR, "input[type='password']"),
        (By.XPATH, "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'password')]"),
    ]

    user_elem = find_input(driver, wait, username_candidates)
    pw_elem = find_input(driver, wait, password_candidates)

    # fallback: scan inputs heuristically
    if not user_elem or not pw_elem:
        inputs = driver.find_elements(By.TAG_NAME, "input")
        for inp in inputs:
            t = (inp.get_attribute("type") or "").lower()
            name = (inp.get_attribute("name") or "").lower()
            pid = (inp.get_attribute("id") or "").lower()
            placeholder = (inp.get_attribute("placeholder") or "").lower()
            if ("password" in t) or ("password" in name) or ("password" in pid) or ("password" in placeholder):
                if not pw_elem:
                    pw_elem = inp
            if any(k in name or k in pid or k in placeholder for k in ("user","email","login","usuario")):
                if not user_elem and inp != pw_elem:
                    user_elem = inp

    if not user_elem or not pw_elem:
        logger.error("Could not find username or password inputs. Inspect login page and adapt selectors.")
        return False

    # fill credentials
    user_elem.clear()
    user_elem.send_keys(username)
    pw_elem.clear()
    pw_elem.send_keys(password)
    logger.info("Credentials filled")

    # try clicking submit button first
    try:
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_btn.click()
        logger.info("Clicked submit button")
    except Exception:
        # fallback to pressing Enter in password field
        pw_elem.send_keys("\n")
        logger.info("Submitted by pressing Enter in password field")

    # Wait for success: 1) URL change OR 2) presence of logout link/menu
    try:
        wait.until(lambda d: d.current_url != LOGIN_URL)
        logger.info("Detected URL change after login: %s", driver.current_url)
        return True
    except TimeoutException:
        logger.info("URL didn't change; checking for logout/dashboard indicators")
        try:
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'logout') or contains(., 'Logout')]")
            ))
            logger.info("Found logout link — login likely successful")
            return True
        except TimeoutException:
            # also accept presence of nav or dashboard element
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "nav")))
                logger.info("Found a nav element — login may be successful")
                return True
            except TimeoutException:
                logger.warning("No clear success signal after login.")
                return False

def main():
    username, password = get_credentials()
    driver = start_chrome(headless=HEADLESS)
    try:
        ok = login_flow(driver, username, password)
        if not ok:
            logger.error("Login not detected as successful. Exiting (closing browser).")
            return

        logger.info("Login successful — waiting 15 seconds before closing (as requested).")
        sleep(15)
    finally:
        logger.info("Closing browser.")
        driver.quit()

if __name__ == "__main__":
    main()
