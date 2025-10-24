# Auto_User_Edube_Register.py
# -------------------------------------------------------
# Bulk auto-registration script for https://edube.org/registration
# Uses Selenium with Chrome and webdriver-manager.
# Reads a list of emails from emails.txt and registers each with a generic password.
# For each email the script opens a fresh browser window, attempts registration (with retries),
# then closes the browser before proceeding to the next email.
# -------------------------------------------------------

import time
import random
import sys
import logging
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException,
    ElementClickInterceptedException
)
from webdriver_manager.chrome import ChromeDriverManager

# ---------- Configuration ----------
REGISTRATION_URL = "https://edube.org/registration"
EMAILS_FILE = "C:\\Users\\juanh\\Documents\\OpenEDG\\Selenium_Scripts\\emails.txt"   # one email per line
PASSWORD = "Python123!"       # must meet site’s password policy
HEADLESS = False              # set True if you want headless
IMPLICIT_WAIT = 5             # seconds for find_element fallbacks
MAX_RETRIES = 3               # retries per email on transient errors
WAIT_BETWEEN_REGISTRATIONS = 20  # fixed delay between each registration (in seconds)
# -----------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

def read_emails(path):
    p = Path(path)
    if not p.exists():
        logging.error("Emails file not found: %s", path)
        sys.exit(1)
    emails = [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    logging.info("Loaded %d emails", len(emails))
    return emails

def make_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
    if HEADLESS:
        options.add_argument("--headless=new")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(IMPLICIT_WAIT)
    return driver

def detect_cloudflare_interstitial(driver):
    """Return True if page appears to be a Cloudflare challenge / checking page."""
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "checking your browser" in body_text or "cloudflare" in body_text or "please enable javascript" in body_text:
            return True
    except Exception:
        pass
    title = driver.title.lower() if driver.title else ""
    if "just a moment" in title or "checking your browser" in title:
        return True
    return False

def register_email(driver, email):
    """Perform a single registration attempt on the current driver session.
    Returns (success:bool, message:str)."""
    try:
        driver.get(REGISTRATION_URL)
    except WebDriverException as e:
        return False, f"Navigation error: {e}"

    # If Cloudflare interstitial present, wait a short while for it to clear
    if detect_cloudflare_interstitial(driver):
        logging.warning("Cloudflare interstitial detected, waiting up to 60s for it to clear...")
        try:
            WebDriverWait(driver, 60).until(lambda d: not detect_cloudflare_interstitial(d))
        except TimeoutException:
            return False, "Cloudflare interstitial did not clear in time"

    wait = WebDriverWait(driver, 20)
    try:
        email_input = wait.until(EC.presence_of_element_located((By.ID, "registration_email")))
        pwd_input = wait.until(EC.presence_of_element_located((By.ID, "registration_plainPassword")))
    except TimeoutException:
        return False, "Could not find email/password inputs (page structure changed?)"

    email_input.clear()
    email_input.send_keys(email)
    pwd_input.clear()
    pwd_input.send_keys(PASSWORD)

    # Clear any client-side token field if present (harmless)
    try:
        driver.execute_script("var e=document.getElementById('registration_captcha'); if(e){ e.value=''; }")
    except Exception:
        pass

    # Click submit
    try:
        submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit)
        submit.click()
    except (NoSuchElementException, ElementClickInterceptedException) as e:
        return False, f"Could not click Sign up button: {e}"
    except Exception as e:
        return False, f"Unexpected error clicking submit: {e}"

    # Small wait for result
    time.sleep(5)
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        body = ""

    # Heuristics for success/failure
    if any(k in body for k in ("verify", "confirmation", "welcome", "check your email", "registration success", "success")):
        return True, "Likely success - confirmation/verify text found"
    if any(k in body for k in ("already", "exists", "invalid", "error")):
        snippet = body[:400].replace("\n", " ")
        return False, f"Registration failed, server responded with: {snippet}"
    if driver.current_url != REGISTRATION_URL:
        return True, f"URL changed after submit to {driver.current_url}"
    return False, "No clear success or error message detected after submit"

def main():
    emails = read_emails(EMAILS_FILE)
    if not emails:
        logging.error("No emails to process.")
        return

    results = []
    for idx, email in enumerate(emails, start=1):
        logging.info("[%d/%d] Starting registration for %s (new browser session)", idx, len(emails), email)

        # Open a fresh browser for this email
        driver = None
        try:
            driver = make_driver()
            attempt = 0
            success = False
            reason = ""
            while attempt < MAX_RETRIES and not success:
                attempt += 1
                logging.info("  Attempt %d for %s", attempt, email)
                ok, msg = register_email(driver, email)
                if ok:
                    logging.info("  Registered %s -> %s", email, msg)
                    success = True
                    reason = msg
                else:
                    logging.warning("  Attempt %d failed for %s: %s", attempt, email, msg)
                    reason = msg
                    if attempt < MAX_RETRIES:
                        backoff = (2 ** attempt) + random.uniform(2, 6)
                        logging.info("  Backing off %.1f seconds before retry...", backoff)
                        time.sleep(backoff)
            results.append((email, success, reason))
        except Exception as e:
            logging.exception("Unexpected error while processing %s: %s", email, e)
            results.append((email, False, f"Exception: {e}"))
        finally:
            # Close browser session for this email (important)
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        # fixed delay between registrations
        logging.info("Waiting %d seconds before next registration to avoid rate limits...", WAIT_BETWEEN_REGISTRATIONS)
        time.sleep(WAIT_BETWEEN_REGISTRATIONS)

    success_count = sum(1 for r in results if r[1])
    logging.info("Done. %d/%d success", success_count, len(results))
    for email, ok, msg in results:
        status = "OK" if ok else "FAIL"
        print(f"{status}\t{email}\t{msg}")

if __name__ == "__main__":
    main()
