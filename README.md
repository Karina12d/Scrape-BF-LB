# Instagram Profile & Post Scraper con Playwright

## Descripción

Script desarrollado en Python que utiliza **Playwright** para extraer información visible de un perfil de Instagram, recopilar enlaces de publicaciones y reels, realizar un scraping detallado de cada post (texto, likes, comentarios y fecha), y guardar todos los resultados estructurados en un archivo JSON.

Después, la biografía y los textos de las publicaciones se envían a la **API de Gemini**, que estima la personalidad de la cuenta según el modelo de los **Cinco Grandes (Big Five / OCEAN)**. Con ese resultado se genera un **informe en PDF**.

> El informe es una estimación automática y orientativa. No constituye una evaluación psicológica profesional.

---

## Características

* **Datos de Perfil:** Extrae nombre, biografía, seguidores y seguidos.
* **Scraping de Publicaciones:** Visita cada post/reel para extraer su texto (caption), cantidad de likes, comentarios y fecha.
* **Prevención de Duplicados:** Evita procesar enlaces repetidos durante el desplazamiento (*scroll*).
* **Autenticación Segura:** Utiliza cookies externas independientes del código principal.
* **Análisis Big Five con Gemini:** puntuación de 0 a 100 y explicación para apertura, responsabilidad, extroversión, amabilidad y neuroticismo, más un resumen psicológico.
* **Tolerancia a fallos de la API:** reintentos con espera creciente ante errores 429/500/502/503/504 y cambio automático a un modelo de respaldo.
* **Informe PDF:** cabecera del perfil, barras de puntuación por rasgo y resumen.
* **Exportación JSON:** Guarda toda la información de manera ordenada en un archivo único.

---

## Requisitos

* Python 3.8 o superior
* Playwright
* google-genai (SDK de Gemini)
* ReportLab
* Una cuenta de Instagram con sesión iniciada y una clave de API de Gemini

---

## Instalación

1. Clona el repositorio o descarga los archivos del proyecto.
2. Instala las dependencias necesarias mediante el archivo `requirements.txt`:
    ```bash
    pip install -r requirements.txt

3. Instala el navegador Chromium necesario para Playwright:
    ```bash
    playwright install chromium

---

## Configuración

### 1. Configurar las Cookies (Importante)
> **Nota:** Este programa permite el uso de cookies configuradas manualmente o mediante una extensión del navegador.
Para evitar bloqueos de inicio de sesión, el script requiere cookies válidas:
1. Crea un archivo llamado `cookies.json` en la raíz del proyecto (puedes guiarte de la estructura de `cookiesEjemplo.json`).
2. Exporta tus cookies de sesión de Instagram desde el navegador y pégalas en el archivo `cookies.json`.

> **Advertencia de Seguridad:** Nunca subas tu archivo `cookies.json` a GitHub ni lo compartas públicamente, ya que contiene acceso directo a tu cuenta. El proyecto cuenta con un archivo `.gitignore` para protegerlo automáticamente.

### 2. Clave de API de Gemini
1. Ingresa a [Google AI Studio](https://aistudio.google.com/apikey) con tu cuenta de Google y crea una clave (*Create API key*).
2. Crea un archivo `apiKey.txt` en la raíz del proyecto y pega la clave sola, sin comillas ni espacios.

### 3. Parámetros del Script
Abre el archivo `scraper.py` y ajusta el usuario que deseas analizar y el límite de publicaciones:
```python
USERNAME = "nombre_de_usuario" 
MAX_POSTS = 10
```
Opcionalmente, puedes cambiar los modelos de Gemini (el primero es el preferido y el resto, respaldo) y los reintentos por modelo:

```python
MODELOS_GEMINI = ["gemini-3.5-flash", "gemini-3.1-flash-lite"]
REINTENTOS_POR_MODELO = 4
```

---

## Ejecución

Ejecuta el script en tu terminal con el siguiente comando:
```bash
python scraper.py
```

--- 

## Tecnologías Utilizadas
1. Python
2. Playwright
3. JSON
4. API de Gemini (`google-genai`)
5. ReportLab

