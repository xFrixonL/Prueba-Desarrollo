from modules.scraper import Scraper
from modules.utils import ask_input, ask_multiple_option
import pandas as pd

groups = ['followers', 'following']

target = ask_input('Enter the target username: ')
group = ask_multiple_option(options=groups)

def scrape(group):
    chromedriver_path = r"C:\Users\fing.labcom\Desktop\Grupo1 - WEB SCRAPING Y LEY DE BENFORD\drivers\chromedriver.exe"
    cookies_path = r"C:\Users\fing.labcom\Desktop\Grupo1 - WEB SCRAPING Y LEY DE BENFORD\drivers\cookies.json"

    driver = Scraper.create_driver(chromedriver_path)

    print("Intentando cargar cookies desde cookies.json...")
    session_ok = Scraper.load_simple_cookies_and_auth(driver, cookies_path)

    scraper = Scraper(target)
    scraper.driver = driver

    if not session_ok:
        username = ask_input('Username: ')
        password = ask_input(is_password=True)
        scraper.authenticate(username, password)

    links = scraper.get_users(group, verbose=True)
    print(f"\nSe obtuvieron {len(links)} usuarios.")

    profiles_data = []

    for user in links:
        profile = scraper.get_profile_data(user)
        profiles_data.append(profile)

    scraper.close()

    if not profiles_data:
        print("\nNo se obtuvieron datos de perfiles.")
        return

    # =========================
    # CREACIÓN DEL DATAFRAME
    # =========================
    tabla = pd.DataFrame(profiles_data)

    # Limpieza básica
    if "seguidores" in tabla.columns:
        tabla = tabla[tabla["seguidores"].notna()]
        tabla["seguidores"] = tabla["seguidores"].astype(int)

    if "seguidos" in tabla.columns:
        tabla["seguidos"] = pd.to_numeric(tabla["seguidos"], errors="coerce")

    print("\n=== TABLA DE PERFILES ===")
    print(tabla.to_string(index=False))

    # (Opcional) guardar resultados
    tabla.to_csv("perfiles_instagram.csv", index=False, encoding="utf-8-sig")
    print("\nArchivo guardado como perfiles_instagram.csv")

if __name__ == "__main__":
    scrape(group)
