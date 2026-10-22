from pdf_bigfive import guardar_pdf_bigfive

import json, random, re, time, os

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from google import genai
from google.genai import types

from google.genai import errors

MODELOS_GEMINI = ["gemini-3.5-flash", "gemini-3.1-flash-lite"]   # el primero es el preferido; el resto, respaldo
REINTENTOS_POR_MODELO = 4

try:
    with open("apiKey.txt", "r", encoding="utf-8") as f:
        api_key_leida = f.read().strip()
except FileNotFoundError:
    print("⚠️ Error: No se encontró el archivo 'apiKey.txt' en la carpeta del proyecto.")
    api_key_leida = ""

client = genai.Client(api_key=api_key_leida)

# ====== CONFIGURA ESTO ======
USERNAME = "sausage_player"   
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

MODELO_GEMINI = "gemini-3.5-flash"   # o "gemini-flash-latest" para que siempre apunte al vigente

def analizar_big_five(resultado_perfil):
    """Envía los datos de Instagram a la API de Gemini para calcular el modelo Big Five."""
    biografia = resultado_perfil["perfil"].get("biografia", "")
    posts_textos = [p["texto"] for p in resultado_perfil["publicaciones"] if p["texto"]]

    prompt = f"""
    Analiza el siguiente perfil de Instagram (biografía y fragmentos de publicaciones) basándote estrictamente en el modelo de personalidad de los Cinco Grandes (Big Five / OCEAN):
    - Apertura a la experiencia (Openness)
    - Responsabilidad (Conscientiousness)
    - Extroversión (Extraversion)
    - Amabilidad (Agreeableness)
    - Neuroticismo / Estabilidad emocional (Neuroticism)

    Biografía:
    {biografia}

    Textos de publicaciones recientes:
    {json.dumps(posts_textos[:15], ensure_ascii=False)}

    Devuelve la respuesta exclusivamente en formato JSON válido con esta estructura exacta:
    {{
      "apertura": {{"puntuacion": 0-100, "analisis": "breve explicación"}},
      "responsabilidad": {{"puntuacion": 0-100, "analisis": "breve explicación"}},
      "extroversion": {{"puntuacion": 0-100, "analisis": "breve explicación"}},
      "amabilidad": {{"puntuacion": 0-100, "analisis": "breve explicación"}},
      "neuroticismo": {{"puntuacion": 0-100, "analisis": "breve explicación"}},
      "resumen_psicologico": "Un párrafo describiendo el perfil general de la persona."
    }}
    """

    print("\n🧠 Conectando con Gemini para el análisis Big Five...")
    for modelo in MODELOS_GEMINI:
        for intento in range(1, REINTENTOS_POR_MODELO + 1):
            try:
                response = client.models.generate_content(
                    model=modelo,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    ),
                )
                texto = response.text.strip()
                texto = re.sub(r"^```(?:json)?|```$", "", texto, flags=re.M).strip()
                print(f"✅ Respuesta recibida de {modelo}.")
                return json.loads(texto)

            except errors.APIError as e:
                # 429 = límite de uso, 500/502/503/504 = problemas temporales del servidor
                if e.code in (429, 500, 502, 503, 504) and intento < REINTENTOS_POR_MODELO:
                    espera = (2 ** intento) + random.uniform(0, 1)   # ~2s, 4s, 8s...
                    print(f"⏳ {modelo} no disponible (error {e.code}). "
                          f"Reintento {intento}/{REINTENTOS_POR_MODELO - 1} en {espera:.0f}s...")
                    time.sleep(espera)
                    continue
                print(f"⚠️ {modelo} falló ({e.code}). Probando el siguiente modelo...")
                break   # pasa al siguiente modelo de la lista

            except json.JSONDecodeError as e:
                print(f"⚠️ {modelo} devolvió un JSON inválido: {e}")
                break

    print("❌ No se pudo obtener el análisis. Intenta de nuevo en unos minutos.")
    return None

# ====== EJECUCIÓN PRINCIPAL ======
with sync_playwright() as p:
    navegador = p.chromium.launch(headless=False)
    context = navegador.new_context(
        viewport={"width": 1280, "height": 900}, locale="es-ES",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    context.add_cookies(convertir_cookies(COOKIES_JSON))
    page = context.new_page()

    print(f"Navegando al perfil de @{USERNAME}...")
    page.goto(f"https://www.instagram.com/{USERNAME}/", wait_until="domcontentloaded")
    pausa(3, 5)

    if "accounts/login" in page.url:
        print("Cookies inválidas o expiradas. Vuelve a exportarlas.")
        navegador.close()
        raise SystemExit

    perfil = obtener_perfil(page)
    print("Perfil extraído correctamente.")

    enlaces = recolectar_enlaces(page)
    print(f"{len(enlaces)} enlaces encontrados. Extrayendo detalles de las publicaciones...")

    publicaciones_detalladas = []
    for idx, enlace in enumerate(enlaces, 1):
        print(f"Procesando publicación {idx}/{len(enlaces)}: {enlace}")
        detalles = obtener_datos_publicacion(page, enlace)
        publicaciones_detalladas.append(detalles)
        pausa(1.5, 3)

    resultado = {
        "perfil": perfil, 
        "publicaciones": publicaciones_detalladas
    }
    
    # 1. Guardar el archivo JSON de Instagram
    nombre_archivo_json = f"{USERNAME}_instagram.json"
    with open(nombre_archivo_json, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"✅ Scraping completado. Datos guardados en '{nombre_archivo_json}'.")

    # 2. Enviar los datos a la API de Gemini para el análisis Big Five
    resultado_big_five = analizar_big_five(resultado)

    if resultado_big_five:
       nombre_archivo_pdf = f"{USERNAME}_bigfive.pdf"
       guardar_pdf_bigfive(resultado, resultado_big_five, nombre_archivo_pdf)
       print(f"✅ Informe PDF guardado en '{nombre_archivo_pdf}'.")
    
    navegador.close()