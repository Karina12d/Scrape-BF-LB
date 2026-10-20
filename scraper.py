import json, random, re, time
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ====== CONFIGURA ESTO ======
USERNAME = "alondra_cgp"   
MAX_POSTS = 25

try:
    with open("cookies.json", "r", encoding="utf-8") as f:
        COOKIES_JSON = f.read()
except FileNotFoundError:
    print("⚠️ Error: No se encontró el archivo 'cookies.json' en la carpeta del proyecto.")
    COOKIES_JSON = "[]"

SAMESITE = {"no_restriction": "None", "lax": "Lax", "strict": "Strict", "unspecified": "Lax"}
FIN_BIO = {"seguir", "siguiendo", "seguir también", "mensaje", "follow", "following", "message"}

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


def pausa(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))


def obtener_perfil(page):
    page.wait_for_selector("header", timeout=15000)
    texto = page.locator("header").first.inner_text()
    lineas = [l.strip() for l in texto.split("\n") if l.strip()]

    patron = re.compile(
        r"^([\d.,]+(?:\s*(?:mil|M|K))?)\s+(publicaciones|seguidores|seguidos|posts|followers|following)$",
        re.I,
    )
    perfil = {"usuario": USERNAME, "nombre": None, "seguidores": None,
              "seguidos": None, "biografia": ""}

    ultimo_contador = -1
    for i, linea in enumerate(lineas):
        m = patron.match(linea)
        if not m:
            continue
        ultimo_contador = i
        tipo = m.group(2).lower()
        if tipo in ("seguidores", "followers"):
            perfil["seguidores"] = m.group(1)
        elif tipo in ("seguidos", "following"):
            perfil["seguidos"] = m.group(1)

    # Nombre
    if len(lineas) > 1 and not patron.match(lineas[1]):
        perfil["nombre"] = lineas[1]

    # Biografía
    bio = []
    for linea in lineas[ultimo_contador + 1:]:
        if linea.lower() in FIN_BIO or linea.lower() == USERNAME.lower():
            break
        bio.append(linea)
    perfil["biografia"] = "\n".join(bio)
    return perfil


def recolectar_enlaces(page):
    enlaces = {}   # clave: código de la publicación, evita duplicados
    sin_nuevos = 0
    while len(enlaces) < MAX_POSTS and sin_nuevos < 10:
        hrefs = page.eval_on_selector_all(
            'a[href*="/p/"], a[href*="/reel/"]', "els => els.map(e => e.href)"
        )
        antes = len(enlaces)
        for h in hrefs:
            m = re.search(r"/(p|reel)/([\w-]+)", h.split("?")[0])
            if m and m.group(2) not in enlaces:
                enlaces[m.group(2)] = f"https://www.instagram.com/{m.group(1)}/{m.group(2)}/"

        sin_nuevos = sin_nuevos + 1 if len(enlaces) == antes else 0
        if sin_nuevos >= 3:
            page.mouse.wheel(0, -600)   # sube un poco para forzar que cargue más
            pausa(1, 2)
        page.mouse.wheel(0, random.randint(900, 1400))   # scroll más corto
        pausa(1.5, 3)
    return list(enlaces.values())[:MAX_POSTS]


def obtener_datos_publicacion(page, url):
    """Navega a una publicación individual y separa correctamente texto, likes, comentarios y fecha."""
    datos = {
        "url": url,
        "tipo": "reel" if "/reel/" in url else "post",
        "texto": "",
        "likes": None,
        "comentarios": None,
        "fecha": None
    }
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        pausa(2, 4)

        # 1. Obtener la metaetiqueta og:description
        contenido_meta = ""
        try:
            meta_desc = page.locator('meta[property="og:description"]')
            if meta_desc.count() > 0:
                contenido_meta = meta_desc.get_attribute("content") or ""
        except Exception:
            pass

        if contenido_meta:
            # Extraer Likes
            m_likes = re.search(r"([\d.,]+\s*(?:mil|M|K)?)\s*(?:likes|Me gusta)", contenido_meta, re.I)
            if m_likes:
                datos["likes"] = m_likes.group(1).strip()

            # Extraer Comentarios
            m_comments = re.search(r"([\d.,]+\s*(?:mil|M|K)?)\s*(?:comments|comentarios)", contenido_meta, re.I)
            if m_comments:
                datos["comentarios"] = m_comments.group(1).strip()

            # Extraer el texto real (caption)
            m_texto = re.search(r':\s*["“](.*)["”]$', contenido_meta, re.S)
            if m_texto:
                datos["texto"] = m_texto.group(1).strip()
            else:
                partes = re.split(r'-\s*[\w_.-]+\s+(?:el|on)\s+[^:]+:\s*', contenido_meta)
                if len(partes) > 1:
                    datos["texto"] = partes[-1].strip()

        # 2. Respaldo para el texto si no se pudo extraer del meta
        if not datos["texto"]:
            try:
                h1_elem = page.locator("article h1").first
                if h1_elem.count() > 0:
                    datos["texto"] = h1_elem.inner_text().strip()
            except Exception:
                pass

        # 3. Extraer Fecha exacta (etiqueta <time>)
        try:
            time_elem = page.locator("article time, time").first
            if time_elem.count() > 0:
                datos["fecha"] = time_elem.get_attribute("datetime")
        except Exception:
            pass

        if not datos["fecha"] and contenido_meta:
            m_fecha = re.search(r'(?:el|on)\s+([A-Za-z0-9\s,]+):', contenido_meta)
            if m_fecha:
                datos["fecha"] = m_fecha.group(1).strip()

    except PWTimeout:
        print(f"Timeout al cargar la publicación: {url}")
    except Exception as e:
        print(f"Error procesando {url}: {e}")

    return datos


with sync_playwright() as p:
    navegador = p.chromium.launch(headless=False)
    context = navegador.new_context(
        viewport={"width": 1280, "height": 900}, locale="es-ES",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    context.add_cookies(convertir_cookies(COOKIES_JSON))
    page = context.new_page()

    page.goto(f"https://www.instagram.com/{USERNAME}/", wait_until="domcontentloaded")
    pausa(3, 5)

    if "accounts/login" in page.url:
        print("Cookies inválidas o expiradas. Vuelve a exportarlas.")
        navegador.close()
        raise SystemExit

    perfil = obtener_perfil(page)
    print("Perfil:", json.dumps(perfil, ensure_ascii=False, indent=2))

    enlaces = recolectar_enlaces(page)
    print(f"{len(enlaces)} enlaces encontrados. Extrayendo detalles...")

    # Scrapeo detallado de cada publicación encontrada
    publicaciones_detalladas = []
    for idx, enlace in enumerate(enlaces, 1):
        print(f"Procesando publicación {idx}/{len(enlaces)}: {enlace}")
        detalles = obtener_datos_publicacion(page, enlace)
        publicaciones_detalladas.append(detalles)
        pausa(1.5, 3) # Pausa preventiva entre peticiones para evitar bloqueos

    resultado = {
        "perfil": perfil, 
        "publicaciones": publicaciones_detalladas
    }
    
    with open(f"{USERNAME}_instagram.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print("Listo. Resultados detallados guardados en", f"{USERNAME}_instagram.json")
    navegador.close()