# edube_update_by_ids_active.py
# - Login en edube
# - Para cada ID: abre /organization/test-candidate/<ID>/edit
#   - Cambia contraseña a "python" (dos campos si existen)
#   - Activa checkbox "Is active" (iCheck)
#   - Clic en "Update and close" (name="btn_update_and_list")

import logging
from time import sleep

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
)

# ------------------- CONFIG -------------------
LOGIN_URL = "https://edube.org/W1fXQ1lnXJUXl4TEnBBgCzquEwpauO2b/login"
EDIT_URL_FMT = "https://edube.org/organization/test-candidate/{}/edit"

USERNAME = "jUaN.H1dA1g0#"
PASSWORD = "WhEy{[x8z$e(/)wgF!"
NEW_PASSWORD = "1234567"  # contraseña que se aplicará a todos

IDS = [
    "17296", "255709"
    # agrega más IDs aquí...
]

HEADLESS = False
WAIT = 10  # segundos de espera explícita
# ----------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def start_driver():
    opts = webdriver.ChromeOptions()
    if HEADLESS:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def login(driver):
    wait = WebDriverWait(driver, WAIT)
    driver.get(LOGIN_URL)

    # Campo usuario/email (varios selectores por robustez)
    user = None
    for by, sel in [
        (By.ID, "username"),
        (By.ID, "email"),
        (By.NAME, "username"),
        (By.NAME, "email"),
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[type='text']"),
    ]:
        try:
            user = wait.until(EC.presence_of_element_located((by, sel)))
            break
        except TimeoutException:
            pass

    pwd = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
    if not user:
        raise RuntimeError("Login: no se encontró el campo de usuario/email.")

    user.clear()
    user.send_keys(USERNAME)
    pwd.clear()
    pwd.send_keys(PASSWORD)

    # Enviar formulario
    try:
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    except Exception:
        pwd.send_keys("\n")

    # Validar éxito (cambio de URL o link de logout)
    try:
        wait.until(lambda d: d.current_url != LOGIN_URL)
    except TimeoutException:
        wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'logout')]",
                )
            )
        )


def set_password_and_activate(driver, new_password: str):
    """
    En la página de edición:
      - Escribe password (soporta 1 o 2 campos: [first] y [second]).
      - Asegura checkbox 'Is active' marcado (usa iCheck: clic en <ins.iCheck-helper> o JS fallback).
      - Clic en 'Update and close'.
    """
    wait = WebDriverWait(driver, WAIT)

    # ---- Contraseña: soporta 2 campos (first/second) o 1 solo campo tipo password ----
    pwd1 = None
    pwd2 = None

    # Intento con nombres específicos (Sonata/ Symfony Form)
    try:
        pwd1 = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[type='password'][name$='[plainPassword][first]']")
            )
        )
        pwd2 = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[type='password'][name$='[plainPassword][second]']")
            )
        )
    except TimeoutException:
        # Fallback a cualquier input password visible
        pass

    if pwd1 and pwd2:
        pwd1.clear()
        pwd1.send_keys(new_password)
        pwd2.clear()
        pwd2.send_keys(new_password)
    else:
        # Si no hay 2 campos, usa el primero que exista
        pwd_generic = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
        pwd_generic.clear()
        pwd_generic.send_keys(new_password)

    # ---- "Is active": checkbox con iCheck ----
    # 1) Buscar input checkbox cuyo name o id contenga 'isActive'
    is_active_input = None
    try:
        is_active_input = driver.find_element(
            By.CSS_SELECTOR, "input[type='checkbox'][name$='[isActive]']"
        )
    except NoSuchElementException:
        # Alternativas por contains
        try:
            is_active_input = driver.find_element(
                By.CSS_SELECTOR, "input[type='checkbox'][name*='isActive' i]"
            )
        except NoSuchElementException:
            try:
                is_active_input = driver.find_element(
                    By.CSS_SELECTOR, "input[type='checkbox'][id*='isActive' i]"
                )
            except NoSuchElementException:
                is_active_input = None

    if not is_active_input:
        # Último intento via label "Is active"
        try:
            label = driver.find_element(
                By.XPATH,
                "//label[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'is active')]",
            )
            is_active_input = label.find_element(
                By.XPATH, ".//following::input[@type='checkbox'][1]"
            )
        except Exception:
            raise RuntimeError("No se encontró el checkbox 'Is active' en la página de edición.")

    def _is_checked(el):
        try:
            return el.is_selected()
        except Exception:
            return False

    if not _is_checked(is_active_input):
        # 2) Intentar clic sobre el helper de iCheck (hermano <ins class='iCheck-helper'>)
        clicked = False
        try:
            helper = is_active_input.find_element(
                By.XPATH, "./following-sibling::ins[contains(@class,'iCheck-helper')]"
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", helper)
            helper.click()
            clicked = True
        except Exception:
            clicked = False

        # 3) Si no funcionó, forzar por JS + eventos
        if not _is_checked(is_active_input):
            if not clicked:
                try:
                    driver.execute_script(
                        """
                        const cb = arguments[0];
                        cb.checked = true;
                        cb.dispatchEvent(new Event('change', {bubbles:true}));
                        cb.dispatchEvent(new Event('input', {bubbles:true}));
                        """,
                        is_active_input,
                    )
                except Exception:
                    pass

        # 4) Último intento: clic directo al input
        if not _is_checked(is_active_input):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", is_active_input)
                is_active_input.click()
            except Exception:
                pass

    logging.info("'Is active' marcado." if _is_checked(is_active_input) else "Advertencia: 'Is active' no se marcó.")

    # ---- Guardar con "Update and close" ----
    try:
        update_and_close = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[name='btn_update_and_list']"))
        )
    except TimeoutException:
        # Fallback por texto visible
        update_and_close = wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[contains(@class,'btn-success') and normalize-space()='Update and close']",
                )
            )
        )

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", update_and_close)
    try:
        update_and_close.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", update_and_close)

    # Esperar que salga de /edit (regreso a lista u otra vista)
    try:
        wait.until(lambda d: "/edit" not in d.current_url)
    except TimeoutException:
        sleep(2)


def process_by_ids(driver, ids):
    ok, fail = 0, 0
    for cid in ids:
        edit_url = EDIT_URL_FMT.format(cid)
        logging.info(f"[ID] {cid} -> {edit_url}")
        try:
            driver.get(edit_url)
            set_password_and_activate(driver, NEW_PASSWORD)
            ok += 1
        except Exception as e:
            logging.exception(f"Fallo con id {cid}: {e}")
            fail += 1
    logging.info(f"Terminado. OK={ok}, FAIL={fail}")


def main():
    driver = start_driver()
    try:
        login(driver)
        process_by_ids(driver, IDS)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
