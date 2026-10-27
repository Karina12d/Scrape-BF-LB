"""
Recolector de datos para la Ley de Benford.

Macro con Playwright que:
  1. Abre la lista de seguidores de la cuenta scrapeada (la misma USERNAME de scraper.py).
  2. Va pasando el mouse sobre el nombre de cada usuario de la lista; Instagram muestra una
     tarjeta flotante (hover card) con publicaciones / seguidores / seguidos, así que NO se
     entra al perfil de cada usuario.
  3. Guarda usuario, seguidores y seguidos de 200 usuarios en JSON (para benford.py) y Excel.

No importa ni modifica scraper.py ni pdf_bigfive.py.

Uso:
    python recolector_seguidores.py                 # usa USERNAME de scraper.py
    python recolector_seguidores.py otra_cuenta     # o indica otra cuenta
"""
import csv, json, random, re, sys, time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ====== CONFIGURA ESTO ======
USERNAME_POR_DEFECTO = "sausage_player"   # solo se usa si no se logra leer scraper.py
TOTAL_USUARIOS = 200
ESPERA_TARJETA = 4.0          # segundos máx. esperando que aparezca la tarjeta al hacer hover
PERMITIR_FALLBACK_PERFIL = False   # True = si la tarjeta no aparece, abre el perfil (más lento y más riesgo)

SAMESITE = {"no_restriction": "None", "lax": "Lax", "strict": "Strict", "unspecified": "Lax"}


# ---------------------------------------------------------------- utilidades
def leer_username_de_scraper():
    """Lee USERNAME de scraper.py con una regex (importarlo ejecutaría todo el scraping)."""
    try:
        with open("scraper.py", "r", encoding="utf-8") as f:
            m = re.search(r'^USERNAME\s*=\s*["\']([\w.]+)["\']', f.read(), re.M)
        if m:
            return m.group(1)
    except FileNotFoundError:
        pass
    return USERNAME_POR_DEFECTO


def convertir_cookies(texto):
    resultado = []
    for c in json.loads(texto):
        ck = {
            "name": c["name"], "value": c["value"], "domain": c["domain"],
            "path": c.get("path", "/"), "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": SAMESITE.get(str(c.get("sameSite", "")).lower(), "Lax"),
        }
        if not c.get("session") and "expirationDate" in c:
            ck["expires"] = int(c["expirationDate"])
        resultado.append(ck)
    return resultado


def pausa(a=1.0, b=2.5):
    time.sleep(random.uniform(a, b))


# Número (con posible sufijo mil/M/K) seguido de su etiqueta, tolerando salto de línea entre ambos
_NUM = r"([\d.,]+(?:\s*(?:mil|M|K))?)"
RE_SEGUIDORES = re.compile(_NUM + r"\s*(?:seguidores|followers)\b", re.I)
RE_SEGUIDOS = re.compile(_NUM + r"\s*(?:seguidos|following)\b", re.I)


def extraer_conteos(texto):
    """Devuelve (seguidores, seguidos) como texto, o (None, None) si no están en el texto."""
    ms, mf = RE_SEGUIDORES.search(texto), RE_SEGUIDOS.search(texto)
    return (ms.group(1).strip() if ms else None,
            mf.group(1).strip() if mf else None)


# ---------------------------------------------------------------- hover card
# Busca en toda la página el elemento más pequeño que parezca la tarjeta del usuario:
# contiene su nombre y las tres etiquetas (publicaciones, seguidores, seguidos).
JS_TARJETA = """
(usuario) => {
  const u = usuario.toLowerCase();
  let mejor = null;
  for (const el of document.querySelectorAll('div')) {
    const t = el.innerText;
    if (!t || t.length > 500) continue;
    const l = t.toLowerCase();
    if (l.includes(u) && /(publicaciones|posts)/.test(l)
        && /(seguidores|followers)/.test(l) && /(seguidos|following)/.test(l)) {
      if (!mejor || t.length < mejor.length) mejor = t;
    }
  }
  return mejor;
}
"""


def leer_tarjeta(page, usuario):
    """Espera a que aparezca la hover card y devuelve (seguidores, seguidos)."""
    limite = time.time() + ESPERA_TARJETA
    while time.time() < limite:
        texto = page.evaluate(JS_TARJETA, usuario)
        if texto:
            seg, sgd = extraer_conteos(texto)
            if seg is not None and sgd is not None:
                return seg, sgd
        time.sleep(0.4)
    return None, None


def leer_perfil_fallback(contexto, usuario):
    """Solo si PERMITIR_FALLBACK_PERFIL=True: abre el perfil en una pestaña aparte."""
    pag = contexto.new_page()
    try:
        pag.goto(f"https://www.instagram.com/{usuario}/", wait_until="domcontentloaded", timeout=15000)
        pag.wait_for_selector("header", timeout=10000)
        return extraer_conteos(pag.locator("header").first.inner_text())
    except PWTimeout:
        return None, None
    finally:
        pag.close()


# ---------------------------------------------------------------- lista de seguidores
def abrir_lista_seguidores(page, cuenta):
    page.goto(f"https://www.instagram.com/{cuenta}/", wait_until="domcontentloaded")
    pausa(3, 5)
    if "accounts/login" in page.url:
        print("Cookies inválidas o expiradas. Vuelve a exportarlas.")
        raise SystemExit
    page.wait_for_selector("header", timeout=15000)

    # Varios selectores de respaldo: Instagram cambia el href (con o sin "/" final) y el texto
    candidatos = [
        page.locator('header a[href*="/followers"]'),
        page.locator('a[href*="/followers"]'),
        page.get_by_role("link", name=re.compile(r"seguidores|followers", re.I)),
        page.locator("header").get_by_text(re.compile(r"seguidores|followers", re.I)),
    ]
    for candidato in candidatos:
        if candidato.count() > 0:
            candidato.first.click()
            break
    else:
        print("⚠️ No se encontró el enlace de seguidores. Posibles causas: la cuenta es privada "
              "y no la sigues, las cookies no son válidas o Instagram cambió la página.")
        raise SystemExit

    page.wait_for_selector('div[role="dialog"]', timeout=15000)
    pausa(2, 3)


def usuarios_visibles(page, cuenta):
    """Nombres de usuario que se ven ahora mismo en la lista (en orden de aparición)."""
    anclas = page.eval_on_selector_all(
        'div[role="dialog"] a[href^="/"]',
        "els => els.map(e => ({href: e.getAttribute('href'), texto: e.innerText.trim()}))",
    )
    vistos, orden = set(), []
    for a in anclas:
        m = re.fullmatch(r"/([\w.]+)/", a["href"] or "")
        # el enlace con texto == usuario es el nombre (el otro enlace es la foto)
        if m and a["texto"] == m.group(1) and m.group(1) != cuenta and m.group(1) not in vistos:
            vistos.add(m.group(1))
            orden.append(m.group(1))
    return orden


def desplazar_lista(page):
    caja = page.locator('div[role="dialog"]').first.bounding_box()
    if caja:
        page.mouse.move(caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2)
    page.mouse.wheel(0, random.randint(500, 800))
    pausa(1.2, 2.2)


# ---------------------------------------------------------------- guardado
def _a_numero(valor):
    """'2593' -> 2593 | '1.234' -> 1234 | '1,2 mil' se deja como texto."""
    v = str(valor).strip()
    if re.fullmatch(r"\d+", v):
        return int(v)
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", v):
        return int(v.replace(".", ""))
    return v


def guardar(datos, base):
    with open(f"{base}.json", "w", encoding="utf-8") as f:   # lo lee benford.py
        json.dump(datos, f, ensure_ascii=False, indent=2)

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        # respaldo sin openpyxl: CSV con ';' y BOM para que Excel en español separe las columnas
        with open(f"{base}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["usuario", "seguidores", "seguidos"])
            w.writerows([d["usuario"], d["seguidores"], d["seguidos"]] for d in datos)
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Usuarios"
    ws.append(["Usuario", "Seguidores", "Seguidos"])
    for celda in ws[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="1F2340")
        celda.alignment = Alignment(horizontal="center")
    for d in datos:
        ws.append([d["usuario"], _a_numero(d["seguidores"]), _a_numero(d["seguidos"])])
    for fila in ws.iter_rows(min_row=2, min_col=2, max_col=3):
        for celda in fila:
            celda.alignment = Alignment(horizontal="right")
            if isinstance(celda.value, int):
                celda.number_format = "#,##0"
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.freeze_panes = "A2"
    wb.save(f"{base}.xlsx")


def cargar_previo(base):
    """Permite reanudar si la ejecución se interrumpió."""
    try:
        with open(f"{base}.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


# ---------------------------------------------------------------- principal
def recolectar_usuarios(page, contexto, cuenta):
    """Recolecta TOTAL_USUARIOS usando una página/contexto de Playwright YA abiertos y con sesión.
    scraper.py puede llamarla con su propio navegador; así no se abre un segundo."""
    base = f"{cuenta}_usuarios_{TOTAL_USUARIOS}"
    datos = cargar_previo(base)
    procesados = {d["usuario"] for d in datos}
    if datos:
        print(f"Reanudando: ya hay {len(datos)} usuarios guardados en '{base}.json'.")

    if len(datos) < TOTAL_USUARIOS:
        print(f"Abriendo la lista de seguidores de @{cuenta}...")
        abrir_lista_seguidores(page, cuenta)

    sin_nuevos = 0
    while len(datos) < TOTAL_USUARIOS and sin_nuevos < 8:
        pendientes = [u for u in usuarios_visibles(page, cuenta) if u not in procesados]
        if not pendientes:
            sin_nuevos += 1
            desplazar_lista(page)
            continue
        sin_nuevos = 0

        for usuario in pendientes:
            if len(datos) >= TOTAL_USUARIOS:
                break
            procesados.add(usuario)
            enlace = page.locator(f'div[role="dialog"] a[href="/{usuario}/"]') \
                         .filter(has_text=usuario).first
            try:
                enlace.scroll_into_view_if_needed(timeout=5000)
                enlace.hover(timeout=5000)
            except PWTimeout:
                print(f"  · @{usuario}: no se pudo pasar el mouse, se omite.")
                continue

            seguidores, seguidos = leer_tarjeta(page, usuario)
            if (seguidores is None or seguidos is None) and PERMITIR_FALLBACK_PERFIL:
                seguidores, seguidos = leer_perfil_fallback(contexto, usuario)

            if seguidores is None or seguidos is None:
                print(f"  · @{usuario}: la tarjeta no apareció, se omite.")
            else:
                datos.append({"usuario": usuario, "seguidores": seguidores, "seguidos": seguidos})
                guardar(datos, base)   # guarda en cada paso por si se interrumpe
                print(f"[{len(datos)}/{TOTAL_USUARIOS}] @{usuario}  seguidores={seguidores}  seguidos={seguidos}")

            # saca el mouse de la tarjeta para que se cierre antes del siguiente hover
            page.mouse.move(5, 5)
            pausa(0.8, 1.8)

        desplazar_lista(page)

    guardar(datos, base)
    if len(datos) < TOTAL_USUARIOS:
        print(f"⚠️ Solo se pudieron recolectar {len(datos)} de {TOTAL_USUARIOS} usuarios.")
    print(f"✅ Datos guardados en '{base}.json' y '{base}.xlsx'.")
    return datos


def main():
    """Uso independiente: abre su propio navegador (python recolector_seguidores.py)."""
    cuenta = sys.argv[1] if len(sys.argv) > 1 else leer_username_de_scraper()
    base = f"{cuenta}_usuarios_{TOTAL_USUARIOS}"

    try:
        with open("cookies.json", "r", encoding="utf-8") as f:
            cookies = f.read()
    except FileNotFoundError:
        print("⚠️ Error: No se encontró el archivo 'cookies.json' en la carpeta del proyecto.")
        raise SystemExit

    previo = cargar_previo(base)
    if len(previo) >= TOTAL_USUARIOS:   # ya está todo: solo regenera los archivos, sin navegador
        guardar(previo, base)
        print(f"✅ Ya había {len(previo)} usuarios. Archivos regenerados: '{base}.json' y '{base}.xlsx'.")
        return

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=False)   # visible: así ves la macro trabajando
        contexto = navegador.new_context(
            viewport={"width": 1280, "height": 900}, locale="es-ES",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        contexto.add_cookies(convertir_cookies(cookies))
        page = contexto.new_page()
        recolectar_usuarios(page, contexto, cuenta)
        navegador.close()


if __name__ == "__main__":
    main()