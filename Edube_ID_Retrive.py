from time import sleep
import logging
from pathlib import Path
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------- Config ----------
LOGIN_URL = "https://edube.org/W1fXQ1lnXJUXl4TEnBBgCzquEwpauO2b/login"
USERS_LIST_URL = "https://edube.org/organization/test-candidate/list"
USERNAME = "jUaN.H1dA1g0#"
PASSWORD = "WhEy{[x8z$e(/)wgF!"
WAIT = 15

EMAILS_FILE = r"C:\Users\juanh\Documents\OpenEDG\Selenium_Scripts\emails.txt"  # one email per line
OUTPUT_FILE = r"C:\Users\juanh\Documents\OpenEDG\Selenium_Scripts\email_id_results.txt"

# ---------- Driver ----------
def start_driver(headless=False):
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

# ---------- Auth ----------
def login(driver):
    wait = WebDriverWait(driver, WAIT)
    driver.get(LOGIN_URL)

    # Try common locators for username
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

    try:
        pwd = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
    except TimeoutException:
        pwd = None

    if not user or not pwd:
        raise RuntimeError("Couldn't find username or password inputs on login page.")

    user.clear(); user.send_keys(USERNAME)
    pwd.clear(); pwd.send_keys(PASSWORD)

    # Submit
    try:
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    except Exception:
        pwd.send_keys("\n")

    # Consider login successful if URL changes or a logout/profile menu appears
    try:
        wait.until(lambda d: d.current_url != LOGIN_URL)
    except TimeoutException:
        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'logout')]")
        ))

# ---------- Utilities ----------
def read_emails(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Emails file not found: {path}")
    emails = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and "@" in s:
            emails.append(s)
    return emails

def normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())

def get_id_from_element_attr(el) -> str | None:
    """
    Extract numeric ID from element attributes where the page encodes it:
    objectId="907165"  (primary per your HTML)
    Fallbacks: objectid, data-object-id, data-objectid, data-id, id
    """
    candidate_attrs = ["objectId", "objectid", "data-object-id", "data-objectid", "data-id", "id"]
    for attr in candidate_attrs:
        val = el.get_attribute(attr)
        if val:
            m = re.search(r"\d+", str(val))
            if m:
                return m.group(0)

    # Last resort: scrape from the element's outerHTML
    outer = el.get_attribute("outerHTML") or ""
    m = re.search(r'objectId\s*=\s*["\']?(\d+)', outer, flags=re.I)
    if m:
        return m.group(1)
    return None

def filter_by_email_and_get_id_via_objectId(driver, email: str) -> str | None:
    wait = WebDriverWait(driver, WAIT)

    # Ensure we are on the list page
    if USERS_LIST_URL not in driver.current_url:
        driver.get(USERS_LIST_URL)

    # Fill filter email input and click Filter
    email_box = wait.until(EC.presence_of_element_located((By.ID, "filter_email_value")))
    email_box.clear()
    email_box.send_keys(email)

    filter_btn = driver.find_element(
        By.XPATH,
        "//form[contains(@class,'sonata-filter-form')]//button[contains(normalize-space(.),'Filter')]"
    )
    filter_btn.click()

    # Wait for table to be present
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.sonata-ba-list")))
    # Wait for at least one row or 'no results'
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.sonata-ba-list tbody tr")))
    except TimeoutException:
        return None

    # Find the row containing the email and read its objectId
    # (We search in the row's text to match the email, then read attributes.)
    try:
        row = driver.find_element(
            By.XPATH,
            "//table[contains(@class,'sonata-ba-list')]//tbody//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
            f"'{normalize(email)}')]"
        )
    except NoSuchElementException:
        return None

    return get_id_from_element_attr(row)

# ---------- Orchestration ----------
def main():
    emails = read_emails(EMAILS_FILE)
    if not emails:
        logging.error("No valid emails found in the input file.")
        return

    driver = start_driver(headless=False)
    out_lines = []
    try:
        login(driver)
        driver.get(USERS_LIST_URL)

        for idx, email in enumerate(emails, 1):
            logging.info(f"[{idx}/{len(emails)}] Looking up objectId for {email} ...")
            try:
                user_id = filter_by_email_and_get_id_via_objectId(driver, email)
            except Exception as e:
                logging.exception(f"Error while processing {email}: {e}")
                user_id = None

            if user_id is None:
                logging.warning(f"No Id found for {email}")
                out_lines.append(f"{email}\tNOT_FOUND")
            else:
                logging.info(f"Found Id {user_id} for {email}")
                out_lines.append(f"{email}\t{user_id}")

            sleep(0.2)

        Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(OUTPUT_FILE).write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        logging.info(f"Done. Wrote {len(out_lines)} lines to: {OUTPUT_FILE}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
