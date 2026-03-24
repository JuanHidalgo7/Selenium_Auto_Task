import atexit
import logging
import secrets
import threading
from time import sleep

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# ------------------- Flask config -------------------
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# ------------------- OpenEDG config -------------------
LOGIN_URL = "https://edube.org/W1fXQ1lnXJUXl4TEnBBgCzquEwpauO2b/login"
DASHBOARD_URL = "https://edube.org/organization/dashboard"
WAIT = 20

LABEL_SUSPICIOUS = "Suspicious Exam Sessions"
LABEL_UNVERIFIED = "Unverified Exam Sessions"
LABEL_ORG_APPS = "Organization Applications"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ------------------- In-memory session store -------------------
# This is suitable for a first local/web version. For production, replace it with
# a real session/database solution.
USER_STATE = {}
STATE_LOCK = threading.Lock()


def start_driver(headless: bool = True):
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def login(driver, username: str, password: str):
    wait = WebDriverWait(driver, WAIT)
    driver.get(LOGIN_URL)

    user = None
    for by, sel in [
        (By.ID, "username"), (By.ID, "email"),
        (By.NAME, "username"), (By.NAME, "email"),
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[type='text']"),
    ]:
        try:
            user = wait.until(EC.presence_of_element_located((by, sel)))
            break
        except TimeoutException:
            pass

    pwd = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))

    if not user or not pwd:
        raise RuntimeError("Couldn't find username/password inputs on the login page.")

    user.clear()
    user.send_keys(username)
    pwd.clear()
    pwd.send_keys(password)

    try:
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    except Exception:
        pwd.send_keys("\n")

    try:
        wait.until(lambda d: d.current_url != LOGIN_URL)
    except TimeoutException:
        try:
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'logout')]")
            ))
        except TimeoutException:
            raise RuntimeError("Login failed. Check username/password or page structure.")


def normalize(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def find_main_content(driver):
    for sel in [
        (By.CSS_SELECTOR, ".content-wrapper"),
        (By.CSS_SELECTOR, "section.content"),
        (By.CSS_SELECTOR, ".sonata-ba-content"),
        (By.TAG_NAME, "main"),
    ]:
        try:
            return driver.find_element(*sel)
        except NoSuchElementException:
            continue
    return driver.find_element(By.TAG_NAME, "body")


def get_counter_from_small_box(scope_el, label_text: str):
    label = normalize(label_text)
    xpath = (
        ".//div[contains(@class,'small-box')]"
        f"[.//p[contains(translate(normalize-space(.), "
        f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{label}')]]"
    )

    boxes = scope_el.find_elements(By.XPATH, xpath)
    for box in boxes:
        try:
            h3 = box.find_element(By.XPATH, ".//div[contains(@class,'inner')]/h3")
            value = (h3.text or "").strip()
            if value:
                return value
        except NoSuchElementException:
            continue
    return None


def get_dashboard_counters(driver):
    wait = WebDriverWait(driver, WAIT)
    driver.get(DASHBOARD_URL)

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "body.sonata-bc .wrapper")))
    except TimeoutException:
        pass

    sleep(1.2)
    scope = find_main_content(driver)

    suspicious = get_counter_from_small_box(scope, LABEL_SUSPICIOUS)
    unverified = get_counter_from_small_box(scope, LABEL_UNVERIFIED)
    org_apps = get_counter_from_small_box(scope, LABEL_ORG_APPS)

    return {
        "suspicious": suspicious,
        "unverified": unverified,
        "org_apps": org_apps,
    }


def create_server_session(username: str, password: str):
    sid = secrets.token_urlsafe(24)
    with STATE_LOCK:
        USER_STATE[sid] = {
            "username": username,
            "password": password,
            "driver": None,
            "lock": threading.Lock(),
        }
    session["sid"] = sid
    return sid


def get_current_state():
    sid = session.get("sid")
    if not sid:
        return None
    return USER_STATE.get(sid)


def ensure_logged_in_driver(state):
    with state["lock"]:
        if state.get("driver") is None:
            driver = start_driver(headless=True)
            login(driver, state["username"], state["password"])
            state["driver"] = driver
        return state["driver"]


def cleanup_state(sid: str):
    with STATE_LOCK:
        state = USER_STATE.pop(sid, None)
    if state and state.get("driver"):
        try:
            state["driver"].quit()
        except Exception:
            pass


@app.route("/", methods=["GET"])
def home():
    if get_current_state():
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_route():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not password:
        return render_template("login.html", error="Please enter username and password.", username=username), 400

    old_sid = session.get("sid")
    if old_sid:
        cleanup_state(old_sid)

    sid = create_server_session(username, password)
    state = USER_STATE[sid]

    try:
        ensure_logged_in_driver(state)
    except Exception as exc:
        cleanup_state(sid)
        session.pop("sid", None)
        return render_template("login.html", error=f"Connection failed: {exc}", username=username), 401

    return redirect(url_for("dashboard"))


@app.route("/dashboard", methods=["GET"])
def dashboard():
    if not get_current_state():
        return redirect(url_for("home"))
    return render_template("dashboard.html")


@app.route("/api/counters", methods=["GET"])
def api_counters():
    state = get_current_state()
    if not state:
        return jsonify({"error": "Not authenticated."}), 401

    try:
        driver = ensure_logged_in_driver(state)
        counters = get_dashboard_counters(driver)
        counters["ok"] = True
        return jsonify(counters)
    except Exception as exc:
        logger.exception("Failed to fetch counters")
        # reset driver once, so next refresh can recreate it
        try:
            if state.get("driver"):
                state["driver"].quit()
        except Exception:
            pass
        state["driver"] = None
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/logout", methods=["POST"])
def logout():
    sid = session.pop("sid", None)
    if sid:
        cleanup_state(sid)
    return redirect(url_for("home"))


@atexit.register
def shutdown_all_drivers():
    for sid in list(USER_STATE.keys()):
        cleanup_state(sid)


if __name__ == "__main__":
    app.run(debug=True)
