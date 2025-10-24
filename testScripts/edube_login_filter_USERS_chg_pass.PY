import csv
import logging
from time import sleep

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException

# ===================== CONFIG =====================
LOGIN_URL = "https://edube.org/W1fXQ1lnXJUXl4TEnBBgCzquEwpauO2b/login"
USERS_LIST_URL = "https://edube.org/organization/test-candidate/list"

USERNAME = "jUaN.H1dA1g0#"
PASSWORD = "WhEy{[x8z$e(/)wgF!"

NEW_PASSWORD = "123456"          # password destino para TODOS

# ---- Elige el modo de trabajo ----
MODE = "BY_IDS"                  # opciones: "BY_IDS", "BY_EMAILS", "BY_FILTER_ALL"

# MODO BY_IDS: lista de IDs (ejemplo)
IDS = ["17296", "255709"]

# MODO BY_EMAILS: ruta a CSV con columna 'email' (una por línea)
EMAILS_CSV = "emails.csv"

# MODO BY_FILTER_ALL: procesa todas las filas de un filtro (p. ej. un dominio)
FILTER_EMAIL_VALUE = "@eagle.fgcu.edu"

HEADLESS = False
WAIT = 25
# ==================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def start_driver(headless=False):
    opts = webdriver.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1400,900")
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def login(driver):
    wait = WebDriverWait(driver, WAIT)
    driver.get(LOGIN_URL)

    # user field
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

    # password field
    try:
        pwd = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
    except TimeoutException:
        raise RuntimeError("No pude localizar el campo de contraseña en Login.")

    if not user:
        raise RuntimeError("No pude localizar el campo de usuario/email en Login.")

    user.clear(); user.send_keys(USERNAME)
    pwd.clear(); pwd.send_keys(PASSWORD)

    # enviar
    try:
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    except Exception:
        pwd.send_keys("\n")

    # éxito: URL cambia o aparece logout
    try:
        wait.until(lambda d: d.current_url != LOGIN_URL)
    except TimeoutException:
        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'logout')]")
        ))


def open_users_list(driver):
    driver.get(USERS_LIST_URL)
    WebDriverWait(driver, WAIT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table.sonata-ba-list"))
    )


def apply_email_filter(driver, email_value: str):
    """Escribe en el filtro Email y pulsa Filter."""
    wait = WebDriverWait(driver, WAIT)
    email_box = wait.until(EC.presence_of_element_located((By.ID, "filter_email_value")))
    email_box.clear()
    email_box.send_keys(email_value)

    filter_btn = driver.find_element(
        By.XPATH, "//form[contains(@class,'sonata-filter-form')]//button[contains(.,'Filter')]"
    )
    filter_btn.click()
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.sonata-ba-list tbody tr")))


def open_edit_from_first_row(driver):
    """En la tabla actual, abre el link de edición (ID) de la primera fila. Devuelve (id, href)."""
    wait = WebDriverWait(driver, WAIT)
    row = wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "table.sonata-ba-list tbody tr")
    ))
    # Ojo: el ID está en la 2ª celda (td[2]) con un <a> al edit
    try:
        id_link = row.find_element(By.XPATH, ".//td[2]//a")
    except NoSuchElementException:
        id_link = row.find_element(By.XPATH, ".//a[contains(@href,'/organization/test-candidate/') and contains(@href,'/edit')]")

    href = id_link.get_attribute("href")
    candidate_id = href.rstrip("/").split("/")[-2]
    id_link.click()
    return candidate_id, href


def open_edit_from_row(driver, row_webelement):
    """Abre el link de edición de una fila dada. Devuelve (id, href)."""
    try:
        id_link = row_webelement.find_element(By.XPATH, ".//td[2]//a")
    except NoSuchElementException:
        id_link = row_webelement.find_element(By.XPATH, ".//a[contains(@href,'/organization/test-candidate/') and contains(@href,'/edit')]")
    href = id_link.get_attribute("href")
    candidate_id = href.rstrip('/').split('/')[-2]
    id_link.click()
    return candidate_id, href


def set_password_and_update_close(driver, new_password: str):
    """En la página de edición: escribir password y pulsar 'Update and close'."""
    wait = WebDriverWait(driver, WAIT)
    pwd_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
    pwd_input.clear()
    pwd_input.send_keys(new_password)

    # Botón: name="btn_update_and_list"
    try:
        btn = driver.find_element(By.NAME, "btn_update_and_list")
    except NoSuchElementException:
        btn = driver.find_element(By.XPATH, "//button[contains(@class,'btn-success') and normalize-space()='Update and close']")

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    try:
        btn.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", btn)

    # Esperar que salga de /edit (vuelve a la lista)
    try:
        wait.until(lambda d: "/edit" not in d.current_url)
    except TimeoutException:
        sleep(2)


# ----------------- MODOS -----------------

def process_by_ids(driver, ids):
    """Más rápido: entra directo por URL /<id>/edit y actualiza."""
    ok, fail = 0, 0
    for cid in ids:
        edit_url = f"https://edube.org/organization/test-candidate/{cid}/edit"
        logging.info(f"[ID] {cid} -> {edit_url}")
        driver.get(edit_url)
        try:
            set_password_and_update_close(driver, NEW_PASSWORD)
            ok += 1
        except Exception as e:
            logging.exception(f"Fallo con id {cid}: {e}")
            fail += 1
    logging.info(f"BY_IDS terminado. OK={ok}, FAIL={fail}")


def process_by_emails(driver, emails):
    """Filtra cada email, abre su fila y actualiza."""
    ok, fail = 0, 0
    for email in emails:
        try:
            open_users_list(driver)
            apply_email_filter(driver, email)
            cid, href = open_edit_from_first_row(driver)
            logging.info(f"[EMAIL] {email} -> id {cid}")
            set_password_and_update_close(driver, NEW_PASSWORD)
            ok += 1
        except Exception as e:
            logging.exception(f"Fallo con email {email}: {e}")
            fail += 1
    logging.info(f"BY_EMAILS terminado. OK={ok}, FAIL={fail}")


def process_by_filter_all(driver, filter_email_value):
    """
    Aplica el filtro (por dominio o patrón) y recorre TODAS las filas de TODAS las páginas,
    abriendo cada 'Edit', actualizando y volviendo a la lista.
    """
    open_users_list(driver)
    apply_email_filter(driver, filter_email_value)

    total_ok, total_fail = 0, 0
    wait = WebDriverWait(driver, WAIT)

    while True:
        # Obtener todas las filas visibles en la página actual
        rows = wait.until(EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "table.sonata-ba-list tbody tr")
        ))
        logging.info(f"Filas en esta página: {len(rows)}")

        # Procesar cada fila: abrir edición, actualizar, volver a la lista (la app regresa sola tras 'Update and close')
        for idx in range(len(rows)):
            # Nota: las referencias a 'rows' se invalidan tras navegación; re-captura fila por índice cada vez
            rows_now = driver.find_elements(By.CSS_SELECTOR, "table.sonata-ba-list tbody tr")
            row = rows_now[idx]
            try:
                cid, href = open_edit_from_row(driver, row)
                logging.info(f"[FILTER_ALL] id {cid}")
                set_password_and_update_close(driver, NEW_PASSWORD)
                total_ok += 1
            except Exception as e:
                logging.exception(f"Fallo en fila {idx+1}: {e}")
                total_fail += 1

        # ¿Hay siguiente página? busca un botón/enlace de '›' o un li con activo y siguiente
        next_link = None
        try:
            # Botón '›' habilitado
            next_link = driver.find_element(By.XPATH, "//a[normalize-space()='›' or normalize-space()='>']")
        except NoSuchElementException:
            # Si no hay, intenta por rel=next
            try:
                next_link = driver.find_element(By.XPATH, "//a[@rel='next']")
            except NoSuchElementException:
                next_link = None

        if not next_link or "disabled" in (next_link.get_attribute("class") or "").lower():
            break  # no hay más páginas

        # Ir a la siguiente página y esperar la tabla
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_link)
            next_link.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", next_link)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.sonata-ba-list tbody tr")))

    logging.info(f"BY_FILTER_ALL terminado. OK={total_ok}, FAIL={total_fail}")


# ----------------- MAIN -----------------

def main():
    driver = start_driver(headless=HEADLESS)
    try:
        login(driver)

        if MODE == "BY_IDS":
            process_by_ids(driver, IDS)

        elif MODE == "BY_EMAILS":
            emails = []
            with open(EMAILS_CSV, newline='', encoding="utf-8") as f:
                reader = csv.DictReader(f)
                # Acepta archivos con cabecera 'email' o archivos de una sola columna sin cabecera
                if "email" in reader.fieldnames:
                    for row in reader:
                        if row.get("email"):
                            emails.append(row["email"].strip())
                else:
                    f.seek(0)
                    for line in f:
                        e = line.strip()
                        if e:
                            emails.append(e)
            process_by_emails(driver, emails)

        elif MODE == "BY_FILTER_ALL":
            process_by_filter_all(driver, FILTER_EMAIL_VALUE)

        else:
            logging.error("MODE inválido. Usa 'BY_IDS', 'BY_EMAILS' o 'BY_FILTER_ALL'.")

        sleep(2)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
