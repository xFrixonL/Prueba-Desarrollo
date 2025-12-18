import re
import time
import json
import os
import random

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException


class Scraper(object):
    """Able to start up a browser, to authenticate to Instagram and get
    followers and people following a specific user."""

    @staticmethod
    def create_driver(chromedriver_path):
        chrome_options = Options()
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        service = Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            },
        )
        return driver

    @staticmethod
    def load_simple_cookies_and_auth(driver, cookies_simple_json_path="cookies.json"):
        """
        Lee un JSON con una lista de cookies completas o un formato simple (dict).
        Intenta añadirlas y verifica si la sesión se activa.
        """
        if not os.path.exists(cookies_simple_json_path):
            return False

        driver.get("https://www.instagram.com/")
        time.sleep(2)

        with open(cookies_simple_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            cookies = []
            for name, value in data.items():
                cookies.append(
                    {
                        "name": name,
                        "value": value,
                        "domain": ".instagram.com",
                        "path": "/",
                    }
                )
        elif isinstance(data, list):
            cookies = data
        else:
            return False

        for c in cookies:
            try:
                driver.add_cookie(c)
            except Exception as e:
                print(f"No se pudo añadir cookie {c.get('name')}: {e}")

        driver.refresh()
        time.sleep(3)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//nav"))
            )
            return True
        except Exception:
            return False

    def __init__(self, target, chromedriver_path=None, cookies_path=None):
        self.target = target
        self.driver = self.create_driver(chromedriver_path)
        self._cookies_loaded = False

    def close(self):
        """Close the browser."""

        self.driver.close()

    def authenticate(self, username, password):
        print("\nLogging in…")
        self.driver.get("https://www.instagram.com/accounts/login/")

        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )

        self.driver.find_element(By.NAME, "username").send_keys(username)
        pwd = self.driver.find_element(By.NAME, "password")
        pwd.send_keys(password)
        pwd.send_keys(Keys.RETURN)

        print("Esperando a que Instagram complete el login...")

        # esperar hasta que NO esté en /accounts/login
        WebDriverWait(self.driver, 90).until(
            lambda d: "/accounts/login" not in d.current_url
        )

        # espera extra para popups internos
        time.sleep(5)


    def get_users(self, group, verbose=False, max_scrolls=100, max_inactivity=10):
        """
        Obtiene únicamente los seguidos (following) haciendo scroll automático.
        """

        if group.lower() != "following":
            raise ValueError("Este scraper está configurado solo para obtener 'following'")

        link = self._get_link(group)
        self._open_dialog(link)

        print(f"Scrolleando {group} ...")

        users = set()
        last_height = 0
        same_height_count = 0
        scroll_count = 0
        last_capture_time = time.time()
        retries = 0

        while True:
            scroll_count += 1

            # Scroll gradual en vez de saltar al final
            self.driver.execute_script(
                """
                const dialog = document.querySelector('div[role="dialog"]');
                if (!dialog) return;
                const divs = dialog.querySelectorAll('div');
                for (let div of divs) {
                    if (div.scrollHeight > div.clientHeight * 1.2) {
                        div.scrollTop = div.scrollTop + div.clientHeight;
                        break;
                    }
                }
                """
            )

            # Espera aleatoria más humana
            time.sleep(random.uniform(2.5, 4.0))

            # Reobtener el contenedor cada vez
            scroll_box = self.users_list_container
            links = scroll_box.find_elements(By.XPATH, ".//a[contains(@href, '/')]")

            new_users = 0
            for link in links:
                username = link.text.strip()
                if username and username not in users:
                    users.add(username)
                    new_users += 1
                    if verbose:
                        print(f" {username}")

            if new_users > 0:
                last_capture_time = time.time()
                retries = 0
            else:
                retries += 1

            inactivity_time = time.time() - last_capture_time
            if inactivity_time > max_inactivity:
                if retries < 3:
                    print(f"No hay nuevos usuarios, reintentando scroll ({retries}/3)...")
                    time.sleep(3)
                    continue
                else:
                    print("No se detectan nuevas peticiones, scroll detenido definitivamente.")
                    break

            current_height = self.driver.execute_script(
                """
                const dialog = document.querySelector('div[role="dialog"]');
                if (!dialog) return 0;
                const divs = dialog.querySelectorAll('div');
                for (let div of divs) {
                    if (div.scrollHeight > div.clientHeight * 1.2) return div.scrollHeight;
                }
                return 0;
                """
            )

            if current_height == last_height:
                same_height_count += 1
            else:
                same_height_count = 0
                last_height = current_height

            if same_height_count >= 5:
                print("Scroll parece detenido visualmente, intentando reactivar...")
                time.sleep(3)
                same_height_count = 0

            if scroll_count > max_scrolls:
                print("Límite máximo de scroll alcanzado.")
                break

        return list(users)

    def _get_link(self, group):
        """Return the element linking to the users list dialog (layout 2025)."""

        group = "following"

        print(f"\nNavigating to {self.target} profile…")
        self.driver.get(f"https://www.instagram.com/{self.target}/")

        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//header"))
            )

            possible_links = self.driver.find_elements(
                By.XPATH,
                "//header//a[contains(@href,'/followers') or contains(@href,'/following') or contains(@href,'/seguidos') or contains(@href,'/seguidores')]",
            )

            if not possible_links:
                possible_links = self.driver.find_elements(
                    By.XPATH,
                    "//header//div[@role='link' or @role='button'] | //header//span",
                )

            if not possible_links:
                raise Exception(
                    "No se encontraron elementos clicables para seguidores/seguidos."
                )

            group = group.lower()
            target_el = None

            for el in possible_links:
                text = el.text.strip().lower()
                if (
                    ("followers" in text and group == "followers")
                    or ("following" in text and group == "following")
                    or ("seguidores" in text and group == "followers")
                    or ("seguidos" in text and group == "following")
                ):
                    target_el = el
                    break

            if not target_el:
                for el in possible_links:
                    href = el.get_attribute("href") or ""
                    if ("/followers" in href and group == "followers") or (
                        "/following" in href and group == "following"
                    ):
                        target_el = el
                        break

            if not target_el:
                raise Exception(
                    f"No se encontró enlace de '{group}' en el perfil actual."
                )

            return target_el

        except Exception as e:
            print(f"Error buscando el enlace de '{group}': {e}")
            return None

    def _open_dialog(self, link):
        if link is None:
            raise Exception("No se pudo abrir el diálogo: enlace no encontrado.")

        link.click()

        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
            )
        except:
            raise Exception(
                "No se detectó ningún diálogo emergente después de hacer clic."
            )

        try:
            self.users_list_container = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[@role='dialog']//div[contains(@class,'_aano')]")
                )
            )
        except:
            try:
                self.users_list_container = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//div[@role='dialog']//div[@class]")
                    )
                )
            except:
                raise Exception(
                    "No se encontró el contenedor de la lista de usuarios en el diálogo."
                )

    def get_followers_count(self, usernames, delay_range=(2, 4)):
        results = {}
        number_re = re.compile(r"([\d,.]+)")

        for i, username in enumerate(usernames, 1):
            url = f"https://www.instagram.com/{username}/"
            try:
                self.driver.get(url)
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//header"))
                )
            except Exception as e:
                print(f"{username}: header no cargó: {e}")
                results[username] = "N/A"
                time.sleep(random.uniform(*delay_range))
                continue

            followers_count = None

            try:
                follower_link = self.driver.find_element(
                    By.XPATH, "//a[contains(@href,'/followers')]"
                )
                raw = (
                    follower_link.get_attribute("title")
                    or follower_link.get_attribute("aria-label")
                    or follower_link.text
                )
                if raw:
                    m = number_re.search(raw)
                    if m:
                        followers_count = m.group(1).replace(",", "").replace(".", "")
            except NoSuchElementException:
                pass
            except Exception:
                pass

            if not followers_count:
                try:
                    meta = self.driver.find_element(
                        By.XPATH, "//meta[@name='description']"
                    )
                    content = meta.get_attribute("content") or ""
                    m = number_re.search(content)
                    if m:
                        followers_count = m.group(1).replace(",", "").replace(".", "")
                except Exception:
                    pass

            if not followers_count:
                try:
                    raw_json = self.driver.execute_script(
                        "return (window._sharedData || window.__initialData || null);"
                    )
                    if raw_json:
                        js_str = str(raw_json)
                        idx = js_str.lower().find("followers")
                        if idx != -1:
                            snippet = js_str[max(0, idx - 120) : idx + 120]
                            m = number_re.search(snippet)
                            if m:
                                followers_count = (
                                    m.group(1).replace(",", "").replace(".", "")
                                )
                    if not followers_count:
                        try:
                            ld = self.driver.find_element(
                                By.XPATH, "//script[@type='application/ld+json']"
                            )
                            ld_text = ld.get_attribute("innerText") or ""
                            m = number_re.search(ld_text)
                            if m:
                                followers_count = (
                                    m.group(1).replace(",", "").replace(".", "")
                                )
                        except Exception:
                            pass
                except Exception:
                    pass

            if not followers_count:
                try:
                    time.sleep(1)
                    follower_link = self.driver.find_element(
                        By.XPATH, "//a[contains(@href,'/followers')]"
                    )
                    raw = (
                        follower_link.get_attribute("title")
                        or follower_link.get_attribute("aria-label")
                        or follower_link.text
                    )
                    if raw:
                        m = number_re.search(raw)
                        if m:
                            followers_count = (
                                m.group(1).replace(",", "").replace(".", "")
                            )
                except Exception:
                    pass

            results[username] = followers_count or "N/A"

            time.sleep(random.uniform(1.5, 2.5))

        return results

    def get_profile_data(self, username, delay_range=(2, 4)):
        data = {
            "usuario": username,
            "seguidores": None,
            "seguidos": None,
            "biografia": None,
            "tipo_cuenta": None,
            "verificada": False,
        }

        url = f"https://www.instagram.com/{username}/"
        self.driver.get(url)

        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//header"))
            )
        except:
            return data

        # BIOGRAFÍA
        try:
            bio = self.driver.find_element(By.XPATH, "//header//section//span")
            data["biografia"] = bio.text.strip()
        except:
            pass

        # SEGUIDORES Y SEGUIDOS
        try:
            links = self.driver.find_elements(By.XPATH, "//header//a")
            for l in links:
                href = l.get_attribute("href") or ""
                text = l.text.replace(",", "").replace(".", "")
                if text.isdigit():
                    if "/followers" in href:
                        data["seguidores"] = int(text)
                    elif "/following" in href:
                        data["seguidos"] = int(text)
        except:
            pass

        # CUENTA PRIVADA / PÚBLICA
        try:
            self.driver.find_element(
                By.XPATH, "//h2[contains(text(),'Private')]"
            )
            data["tipo_cuenta"] = "Privada"
        except:
            data["tipo_cuenta"] = "Pública"

        # CUENTA VERIFICADA
        try:
            self.driver.find_element(
                By.XPATH, "//svg[@aria-label='Verified']"
            )
            data["verificada"] = True
        except:
            pass

        time.sleep(random.uniform(*delay_range))
        return data
