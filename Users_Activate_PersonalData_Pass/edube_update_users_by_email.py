import csv
import getpass
import logging
import os
from pathlib import Path
from time import sleep

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
)

LOGIN_URL = "https://edube.org/W1fXQ1lnXJUXl4TEnBBgCzquEwpauO2b/login"
LIST_URL = "https://edube.org/organization/test-candidate/list"
NEW_PASSWORD = "Python26!"
HEADLESS = False
WAIT = 15

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


def start_driver():
    opts = webdriver.ChromeOptions()
    if HEADLESS:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1440,1000")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def prompt_credentials():
    print("\n=== Conexión a plataforma de administración ===")
    username = input("Usuario administrador: ").strip()
    password = getpass.getpass("Contraseña administrador: ").strip()

    if not username or not password:
        raise ValueError("El usuario y la contraseña son obligatorios.")

    return username, password


def ask_csv_path():
    print("\n=== Archivo de datos ===")
    csv_path = input("Ruta completa del archivo CSV: ").strip().strip('"')
    path = Path(csv_path).expanduser()

    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {path}")
    if path.suffix.lower() != ".csv":
        raise ValueError("El archivo debe tener extensión .csv")

    return path


def load_csv_rows(csv_path: Path):
    rows = []
    required = {"email", "first_name", "last_name"}

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("El CSV no contiene encabezados.")

        normalized = {name.strip().lower(): name for name in reader.fieldnames}
        missing = [col for col in required if col not in normalized]
        if missing:
            raise ValueError(
                "Faltan columnas obligatorias en el CSV: " + ", ".join(missing)
            )

        for idx, raw in enumerate(reader, start=2):
            email = (raw.get(normalized["email"], "") or "").strip()
            first_name = (raw.get(normalized["first_name"], "") or "").strip()
            last_name = (raw.get(normalized["last_name"], "") or "").strip()

            if not email:
                logging.warning(f"Fila {idx}: se omitió porque no tiene email.")
                continue

            rows.append(
                {
                    "row_number": idx,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                }
            )

    if not rows:
        raise ValueError("El CSV no contiene registros válidos para procesar.")

    return rows


def login(driver, username: str, password: str):
    wait = WebDriverWait(driver, WAIT)
    logging.info("Abriendo página de login...")
    driver.get(LOGIN_URL)

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

    if not user:
        raise RuntimeError("No se encontró el campo de usuario/email en el login.")

    pwd = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))

    user.clear()
    user.send_keys(username)
    pwd.clear()
    pwd.send_keys(password)

    try:
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    except Exception:
        pwd.send_keys(Keys.ENTER)

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

    logging.info("Inicio de sesión exitoso.")


def clear_and_type(element, value: str):
    element.clear()
    try:
        element.send_keys(Keys.CONTROL, "a")
        element.send_keys(Keys.DELETE)
    except Exception:
        pass
    element.send_keys(value)


def open_list_page(driver):
    logging.info("Abriendo listado de usuarios...")
    driver.get(LIST_URL)
    WebDriverWait(driver, WAIT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "form.sonata-filter-form"))
    )


def search_user_by_email(driver, email: str):
    wait = WebDriverWait(driver, WAIT)
    logging.info(f"Buscando usuario por correo: {email}")

    open_list_page(driver)

    email_input = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='filter[email][value]']"))
    )
    clear_and_type(email_input, email)

    try:
        filter_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", filter_button)
        filter_button.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", filter_button)

    wait.until(lambda d: f"filter%5Bemail%5D%5Bvalue%5D={email.replace('@', '%40')}" in d.current_url or "filter[email][value]" in d.page_source)

    edit_link = find_edit_link_for_email(driver, email)
    if not edit_link:
        raise RuntimeError(f"No se encontró un enlace de edición para el correo {email}")

    href = edit_link.get_attribute("href")
    logging.info(f"Usuario localizado. Abriendo edición: {href}")
    driver.get(href)


def find_edit_link_for_email(driver, email: str):
    wait = WebDriverWait(driver, WAIT)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.sonata-ba-list, div.box-body")))

    exact_email_xpath = (
        "//table[contains(@class,'sonata-ba-list')]//tr["
        f".//*[normalize-space(text())='{email}']"
        "]//a[contains(@href,'/organization/test-candidate/') and contains(@href,'/edit')]"
    )
    try:
        return driver.find_element(By.XPATH, exact_email_xpath)
    except NoSuchElementException:
        pass

    fallback_xpath = "//a[contains(@href,'/organization/test-candidate/') and contains(@href,'/edit')]"
    links = driver.find_elements(By.XPATH, fallback_xpath)
    if len(links) == 1:
        return links[0]

    return None


def set_password_name_lastname_and_activate(driver, first_name: str, last_name: str, new_password: str):
    wait = WebDriverWait(driver, WAIT)
    logging.info("Llenando campos de edición del usuario...")

    first_name_input = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[name$='[firstName]']"))
    )
    last_name_input = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[name$='[lastName]']"))
    )

    clear_and_type(first_name_input, first_name)
    clear_and_type(last_name_input, last_name)

    pwd_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
    if not pwd_inputs:
        raise RuntimeError("No se encontró el campo de contraseña en la página de edición.")

    if len(pwd_inputs) >= 2:
        clear_and_type(pwd_inputs[0], new_password)
        clear_and_type(pwd_inputs[1], new_password)
    else:
        clear_and_type(pwd_inputs[0], new_password)

    is_active_input = None
    selectors = [
        "input[type='checkbox'][name$='[isActive]']",
        "input[type='checkbox'][name*='isActive']",
        "input[type='checkbox'][id*='isActive']",
    ]
    for sel in selectors:
        try:
            is_active_input = driver.find_element(By.CSS_SELECTOR, sel)
            break
        except NoSuchElementException:
            pass

    if not is_active_input:
        raise RuntimeError("No se encontró el checkbox 'Is Active'.")

    if not is_active_input.is_selected():
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", is_active_input)
        try:
            is_active_input.click()
        except Exception:
            driver.execute_script(
                "arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                is_active_input,
            )

    logging.info("Campos completados y checkbox 'Is Active' confirmado.")

    update_and_close = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button[name='btn_update_and_list']"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", update_and_close)
    try:
        update_and_close.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", update_and_close)

    try:
        wait.until(lambda d: "/edit" not in d.current_url)
    except TimeoutException:
        sleep(2)

    logging.info("Información actualizada con 'Update and Close'.")


def process_csv(driver, rows):
    total = len(rows)
    ok = 0
    fail = 0
    errors = []

    for index, row in enumerate(rows, start=1):
        email = row["email"]
        first_name = row["first_name"]
        last_name = row["last_name"]
        logging.info(f"[{index}/{total}] Procesando: {email}")
        try:
            search_user_by_email(driver, email)
            set_password_name_lastname_and_activate(
                driver,
                first_name=first_name,
                last_name=last_name,
                new_password=NEW_PASSWORD,
            )
            ok += 1
            logging.info(f"[{index}/{total}] OK -> {email}")
        except Exception as exc:
            fail += 1
            msg = f"[{index}/{total}] ERROR -> {email}: {exc}"
            errors.append(msg)
            logging.exception(msg)

    print("\n=== Resumen del archivo procesado ===")
    print(f"Registros correctos: {ok}")
    print(f"Registros con error: {fail}")
    if errors:
        print("Errores detectados:")
        for err in errors:
            print(f"- {err}")


def ask_repeat():
    while True:
        answer = input("\n¿Deseas procesar otro archivo CSV? (s/n): ").strip().lower()
        if answer in {"s", "si", "sí", "y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Respuesta no válida. Escribe 's' para sí o 'n' para no.")


def main():
    print("=== Automatización de actualización de usuarios por correo ===")
    username, password = prompt_credentials()
    driver = start_driver()

    try:
        login(driver, username, password)

        while True:
            try:
                csv_path = ask_csv_path()
                rows = load_csv_rows(csv_path)
                print(f"\nSe cargarán {len(rows)} registros desde: {csv_path}")
                process_csv(driver, rows)
            except Exception as exc:
                logging.exception(f"No fue posible procesar el archivo: {exc}")

            if not ask_repeat():
                break

    finally:
        print("\nCerrando navegador y finalizando programa...")
        driver.quit()


if __name__ == "__main__":
    main()
