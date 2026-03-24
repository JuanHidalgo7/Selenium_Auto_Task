import logging
import threading
from time import sleep
import tkinter as tk
from tkinter import font as tkfont

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ------------------- CONFIG -------------------
LOGIN_URL = "https://edube.org/W1fXQ1lnXJUXl4TEnBBgCzquEwpauO2b/login"
DASHBOARD_URL = "https://edube.org/organization/dashboard"
WAIT = 20
REFRESH_INTERVAL = 300  # 5 minutes

LABEL_SUSPICIOUS = "Suspicious Exam Sessions"
LABEL_UNVERIFIED = "Unverified Exam Sessions"
LABEL_ORG_APPS = "Organization Applications"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ------------------- SELENIUM -------------------
def start_driver(headless=False):
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def login(driver, username, password):
    wait = WebDriverWait(driver, WAIT)
    driver.get(LOGIN_URL)

    user = None
    for by, sel in [
        (By.ID, "username"), (By.ID, "email"),
        (By.NAME, "username"), (By.NAME, "email"),
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[type='text']")
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


def get_counter_from_small_box(scope_el, label_text: str) -> str | None:
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

    return suspicious, unverified, org_apps


# ------------------- TKINTER APP -------------------
class OpenEDGApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EDUBE Dashboard Counters")
        self.root.geometry("720x560")
        self.root.resizable(False, False)

        self.driver = None
        self.connected = False

        self.title_font = tkfont.Font(family="Arial", size=16, weight="bold")
        self.label_font = tkfont.Font(family="Arial", size=11)
        self.mid_font = tkfont.Font(family="Arial", size=18)
        self.big_font = tkfont.Font(family="Arial", size=40, weight="bold")

        self.login_frame = None
        self.dashboard_frame = None

        self.username_entry = None
        self.password_entry = None
        self.login_status = None

        self.lbl_suspicious = None
        self.lbl_unverified = None
        self.lbl_orgapps = None
        self.dashboard_status = None

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.build_login_frame()

    # ---------- UI builders ----------
    def clear_frames(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def build_login_frame(self):
        self.clear_frames()
        self.login_frame = tk.Frame(self.root)
        self.login_frame.pack(expand=True)

        tk.Label(
            self.login_frame,
            text="OpenEDG Login",
            font=self.title_font
        ).pack(pady=(20, 12))

        form = tk.Frame(self.login_frame)
        form.pack(pady=10)

        tk.Label(form, text="Username:", font=self.label_font, width=12, anchor="e").grid(row=0, column=0, padx=8, pady=8)
        self.username_entry = tk.Entry(form, width=30, font=self.label_font)
        self.username_entry.grid(row=0, column=1, padx=8, pady=8)

        tk.Label(form, text="Password:", font=self.label_font, width=12, anchor="e").grid(row=1, column=0, padx=8, pady=8)
        self.password_entry = tk.Entry(form, width=30, show="*", font=self.label_font)
        self.password_entry.grid(row=1, column=1, padx=8, pady=8)

        self.login_status = tk.Label(self.login_frame, text="", fg="red", font=("Arial", 10))
        self.login_status.pack(pady=(8, 8))

        btns = tk.Frame(self.login_frame)
        btns.pack(pady=10)

        tk.Button(btns, text="Connect", width=14, command=self.start_connection).grid(row=0, column=0, padx=8)
        tk.Button(btns, text="Exit", width=14, command=self.on_close).grid(row=0, column=1, padx=8)

        self.username_entry.focus_set()

    def build_dashboard_frame(self):
        self.clear_frames()
        self.dashboard_frame = tk.Frame(self.root)
        self.dashboard_frame.pack(expand=True, fill="both")

        tk.Label(self.dashboard_frame, text="Suspicious Exam Sessions", font=self.mid_font).pack(pady=(22, 0))
        self.lbl_suspicious = tk.Label(self.dashboard_frame, text="N/A", font=self.big_font)
        self.lbl_suspicious.pack()

        tk.Label(self.dashboard_frame, text="Unverified Exam Sessions", font=self.mid_font).pack(pady=(18, 0))
        self.lbl_unverified = tk.Label(self.dashboard_frame, text="N/A", font=self.big_font)
        self.lbl_unverified.pack()

        tk.Label(self.dashboard_frame, text="Organization Applications", font=self.mid_font).pack(pady=(18, 0))
        self.lbl_orgapps = tk.Label(self.dashboard_frame, text="N/A", font=self.big_font)
        self.lbl_orgapps.pack()

        self.dashboard_status = tk.Label(self.dashboard_frame, text="Connecting...", font=("Arial", 12))
        self.dashboard_status.pack(pady=(16, 0))

    # ---------- UI updates ----------
    def set_login_status(self, msg, color="red"):
        if self.login_status:
            self.login_status.config(text=msg, fg=color)

    def set_dashboard_status(self, msg):
        if self.dashboard_status:
            self.dashboard_status.config(text=msg)

    def update_dashboard_values(self, suspicious, unverified, org):
        if self.lbl_suspicious:
            self.lbl_suspicious.config(text=suspicious if suspicious else "N/A")
        if self.lbl_unverified:
            self.lbl_unverified.config(text=unverified if unverified else "N/A")
        if self.lbl_orgapps:
            self.lbl_orgapps.config(text=org if org else "N/A")
        self.set_dashboard_status("Last updated.")

    # ---------- Workflow ----------
    def start_connection(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        if not username or not password:
            self.set_login_status("Please enter username and password.")
            return

        self.set_login_status("Connecting...", color="black")

        # Disable entries during login
        self.username_entry.config(state="disabled")
        self.password_entry.config(state="disabled")

        threading.Thread(
            target=self.connect_and_load_dashboard,
            args=(username, password),
            daemon=True
        ).start()

    def connect_and_load_dashboard(self, username, password):
        try:
            driver = start_driver(headless=False)
            login(driver, username, password)

            self.driver = driver
            self.connected = True

            self.root.after(0, self.build_dashboard_frame)
            self.root.after(100, self.refresh_dashboard_data)

        except Exception as e:
            logging.exception("Connection failed")

            try:
                if self.driver:
                    self.driver.quit()
            except Exception:
                pass

            self.driver = None
            self.connected = False

            def restore_login():
                self.username_entry.config(state="normal")
                self.password_entry.config(state="normal")
                self.set_login_status(f"Connection failed: {e}")

            self.root.after(0, restore_login)

    def refresh_dashboard_data(self):
        if not self.driver:
            return

        self.set_dashboard_status("Updating data from dashboard...")

        def worker():
            try:
                suspicious, unverified, org = get_dashboard_counters(self.driver)
                self.root.after(0, lambda: self.update_dashboard_values(suspicious, unverified, org))
            except Exception as e:
                logging.exception("Error refreshing data")
                self.root.after(0, lambda: self.set_dashboard_status(f"Error: {e}"))
            finally:
                self.root.after(REFRESH_INTERVAL * 1000, self.refresh_dashboard_data)

        threading.Thread(target=worker, daemon=True).start()

    def on_close(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ------------------- MAIN -------------------
def main():
    app = OpenEDGApp()
    app.run()


if __name__ == "__main__":
    main()