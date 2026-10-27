"""
Ley de Benford sobre los datos recolectados por recolector_seguidores.py.

Solo usa el PRIMER DÍGITO de la cantidad de seguidos de cada usuario:
  1. extrae el primer dígito,
  2. cuenta cuántas veces aparece cada dígito (1-9) y lo escribe también en el Excel (misma hoja),
  3. grafica lo observado contra lo esperado por Benford: P(d) = log10(1 + 1/d),
  4. aplica la prueba de chi-cuadrado (8 grados de libertad) y clasifica: Humano / Posible bot / Bot.

Uso:
    python benford.py                              # usa USERNAME de scraper.py
    python benford.py ruta/al/archivo.json         # o un JSON concreto
"""
import json, math, re, sys
from collections import Counter

import matplotlib
matplotlib.use("Agg")   # genera el PNG sin necesitar ventana
import matplotlib.pyplot as plt

TOTAL_USUARIOS = 200
METRICAS = [("seguidos", "Seguidos")]   # solo se grafica "seguidos"
DIGITOS = range(1, 10)

# Chi-cuadrado con 9 categorías -> 8 grados de libertad
GL = 8
CRITICO_5 = 15.507   # p = 0.05
CRITICO_1 = 20.090   # p = 0.01
# chi2 <= CRITICO_5            -> se ajusta a Benford      -> HUMANO
# CRITICO_5 < chi2 <= CRITICO_1 -> desviación moderada     -> POSIBLE BOT
# chi2 > CRITICO_1             -> desviación fuerte        -> BOT
MIN_MUESTRA = 50     # por debajo de esto el resultado no es confiable
COLORES = {"Humano": "#10B981", "Posible bot": "#F59E0B", "Bot": "#EF4444"}


def leer_username_de_scraper():
    try:
        with open("scraper.py", "r", encoding="utf-8") as f:
            m = re.search(r'^USERNAME\s*=\s*["\']([\w.]+)["\']', f.read(), re.M)
        if m:
            return m.group(1)
    except FileNotFoundError:
        pass
    return "sausage_player"


def parsear_cantidad(texto):
    """'2593' -> 2593 | '2.593' -> 2593 | '1,2 mil' -> 1200 | '3.4M' -> 3400000 | inválido -> None"""
    if texto is None:
        return None
    t = str(texto).strip().lower().replace("\u00a0", " ")
    m = re.fullmatch(r"([\d.,]+)\s*(mil|k|m)?", t)
    if not m:
        return None
    numero, sufijo = m.groups()
    if sufijo:                                    # con sufijo, el separador es decimal
        valor = float(numero.replace(",", "."))
        return int(round(valor * {"mil": 1e3, "k": 1e3, "m": 1e6}[sufijo]))
    return int(re.sub(r"[.,]", "", numero))       # sin sufijo, los separadores son de miles


def primer_digito(valor):
    """Primer dígito significativo (1-9); None si el valor es 0 o no existe."""
    if not valor:
        return None
    return int(str(abs(valor))[0])


def contar_primeros_digitos(valores):
    conteo = Counter(d for d in map(primer_digito, valores) if d)
    return {d: conteo.get(d, 0) for d in DIGITOS}


def benford(d):
    return math.log10(1 + 1 / d)


# ---------------------------------------------------------------- chi-cuadrado
def p_valor(chi, gl=GL):
    """P(X >= chi) para chi-cuadrado con gl PAR (forma cerrada, sin scipy)."""
    x = chi / 2
    return math.exp(-x) * sum(x ** k / math.factorial(k) for k in range(gl // 2))


def densidad_chi(x, gl=GL):
    """Densidad de chi-cuadrado con gl par: x^(k-1) e^(-x/2) / (2^k (k-1)!), k = gl/2."""
    k = gl // 2
    return x ** (k - 1) * math.exp(-x / 2) / (2 ** k * math.factorial(k - 1))


def veredicto(chi):
    if chi <= CRITICO_5:
        return "Humano"
    if chi <= CRITICO_1:
        return "Posible bot"
    return "Bot"


def prueba_chi_cuadrado(conteo):
    n = sum(conteo.values())
    esperado = {d: n * benford(d) for d in DIGITOS}
    contrib = {d: (conteo[d] - esperado[d]) ** 2 / esperado[d] for d in DIGITOS} if n else {d: 0 for d in DIGITOS}
    chi = sum(contrib.values())
    return {"n": n, "esperado": esperado, "contrib": contrib, "chi": chi,
            "p": p_valor(chi) if n else 1.0, "veredicto": veredicto(chi)}


# ---------------------------------------------------------------- gráfica
def _panel_benford(ax, titulo, conteo, prueba):
    n = prueba["n"]
    observado = [100 * conteo[d] / n if n else 0 for d in DIGITOS]
    esperado = [100 * benford(d) for d in DIGITOS]

    barras = ax.bar(DIGITOS, observado, color="#7C3AED", alpha=0.85, label="Observado")
    ax.plot(DIGITOS, esperado, color="#EF4444", marker="o", linewidth=2, label="Ley de Benford")
    for barra, d in zip(barras, DIGITOS):
        ax.text(barra.get_x() + barra.get_width() / 2, barra.get_height() + 0.6,
                str(conteo[d]), ha="center", va="bottom", fontsize=9, color="#1F2340")

    ax.set_title(f"{titulo}: primer dígito (n = {n})", fontsize=13, fontweight="bold")
    ax.set_xlabel("Primer dígito")
    ax.set_ylabel("Frecuencia (%)")
    ax.set_xticks(list(DIGITOS))
    ax.set_ylim(0, max(max(observado), max(esperado)) + 8)
    ax.grid(axis="y", alpha=0.3)
    ax.legend()


def _panel_chi(ax, prueba):
    chi, v = prueba["chi"], prueba["veredicto"]
    xmax = 35 if chi > 35 else max(30, chi * 1.25)   # si χ² es enorme, se limita la escala
    fuera = chi > xmax
    x_marca = xmax * 0.97 if fuera else chi
    xs = [i * xmax / 400 for i in range(1, 401)]
    ys = [densidad_chi(x) for x in xs]

    ax.plot(xs, ys, color="#1F2340", linewidth=2)
    ax.fill_between(xs, ys, where=[x <= CRITICO_5 for x in xs], color=COLORES["Humano"], alpha=0.30,
                    label=f"Humano (χ² ≤ {CRITICO_5})")
    ax.fill_between(xs, ys, where=[CRITICO_5 < x <= CRITICO_1 for x in xs], color=COLORES["Posible bot"],
                    alpha=0.35, label=f"Posible bot ({CRITICO_5} < χ² ≤ {CRITICO_1})")
    ax.fill_between(xs, ys, where=[x > CRITICO_1 for x in xs], color=COLORES["Bot"], alpha=0.35,
                    label=f"Bot (χ² > {CRITICO_1})")
    ax.axvline(x_marca, color=COLORES[v], linewidth=3)
    ax.annotate(f"χ² = {chi:.2f}{' (fuera de escala →)' if fuera else ''}\np = {prueba['p']:.4f}\n{v.upper()}",
                xy=(x_marca, max(ys) * 0.55), xytext=(-8 if x_marca > xmax * 0.6 else 8, 0),
                textcoords="offset points",
                ha="right" if x_marca > xmax * 0.6 else "left", fontsize=11, fontweight="bold",
                color=COLORES[v], bbox=dict(boxstyle="round", fc="white", ec=COLORES[v]))

    ax.set_title(f"Curva chi-cuadrado ({GL} grados de libertad)", fontsize=13, fontweight="bold")
    ax.set_xlabel("χ²")
    ax.set_ylabel("Densidad")
    ax.set_xlim(0, xmax)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9)


def graficar(resultados, cuenta, archivo_png):
    filas = len(resultados)
    fig, ejes = plt.subplots(filas, 2, figsize=(14, 5.4 * filas), squeeze=False)
    for fila, (titulo, conteo, prueba) in zip(ejes, resultados):
        _panel_benford(fila[0], titulo, conteo, prueba)
        _panel_chi(fila[1], prueba)

    fig.suptitle(f"Ley de Benford y chi-cuadrado – usuarios de @{cuenta}", fontsize=15, fontweight="bold")
    fig.tight_layout()
    fig.savefig(archivo_png, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- Excel (misma hoja)
def guardar_en_excel(archivo_json, resultados):
    """Agrega conteo, chi-cuadrado y veredicto en la misma hoja del Excel (a la derecha de los datos)."""
    ruta = re.sub(r"\.json$", ".xlsx", archivo_json)
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        wb = load_workbook(ruta)
    except ImportError:
        print("⚠️ Falta openpyxl: pip install openpyxl. No se escribió la tabla en el Excel.")
        return
    except FileNotFoundError:
        print(f"⚠️ No existe '{ruta}'. Ejecuta primero recolector_seguidores.py.")
        return

    ws = wb["Usuarios"] if "Usuarios" in wb.sheetnames else wb.active
    col = 5   # columna E (la D queda en blanco como separador)
    for titulo, conteo, prueba in resultados:
        n = prueba["n"]
        encabezados = ["Primer dígito", f"Conteo {titulo.lower()}", "Observado %", "Benford %",
                       "Conteo esperado", "(O-E)²/E"]
        for j, texto in enumerate(encabezados):
            c = ws.cell(row=1, column=col + j, value=texto)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="7C3AED")
            c.alignment = Alignment(horizontal="center", wrap_text=True)
            ws.column_dimensions[c.column_letter].width = 18
        for i, d in enumerate(DIGITOS, start=2):
            ws.cell(row=i, column=col, value=d).alignment = Alignment(horizontal="center")
            ws.cell(row=i, column=col + 1, value=conteo[d])
            ws.cell(row=i, column=col + 2, value=conteo[d] / n if n else 0).number_format = "0.0%"
            ws.cell(row=i, column=col + 3, value=benford(d)).number_format = "0.0%"
            ws.cell(row=i, column=col + 4, value=prueba["esperado"][d]).number_format = "0.00"
            ws.cell(row=i, column=col + 5, value=prueba["contrib"][d]).number_format = "0.000"
        fila_total = 2 + len(DIGITOS)
        ws.cell(row=fila_total, column=col, value="Total").font = Font(bold=True)
        ws.cell(row=fila_total, column=col + 1, value=n).font = Font(bold=True)
        ws.cell(row=fila_total, column=col + 4, value=n).font = Font(bold=True)
        c = ws.cell(row=fila_total, column=col + 5, value=prueba["chi"])
        c.font, c.number_format = Font(bold=True), "0.000"

        resumen = [("Chi-cuadrado (χ²)", round(prueba["chi"], 3)),
                   ("Grados de libertad", GL),
                   ("Valor crítico 5%", CRITICO_5),
                   ("Valor crítico 1%", CRITICO_1),
                   ("p-valor", round(prueba["p"], 4)),
                   ("Resultado", prueba["veredicto"].upper())]
        for k, (etiqueta, valor) in enumerate(resumen, start=fila_total + 2):
            ws.cell(row=k, column=col, value=etiqueta).font = Font(bold=True)
            ws.cell(row=k, column=col + 1, value=valor).alignment = Alignment(horizontal="center")
        res = ws.cell(row=fila_total + 2 + len(resumen) - 1, column=col + 1)
        res.font = Font(bold=True, color="FFFFFF")
        res.fill = PatternFill("solid", fgColor=COLORES[prueba["veredicto"]].lstrip("#"))
        col += len(encabezados) + 1

    try:
        wb.save(ruta)
        print(f"✅ Tabla de Benford y chi-cuadrado agregada en '{ruta}' (hoja '{ws.title}', desde la columna E).")
    except PermissionError:
        print(f"⚠️ No se pudo guardar '{ruta}': ciérralo en Excel y vuelve a ejecutar benford.py.")


# ---------------------------------------------------------------- principal
def main():
    if len(sys.argv) > 1:
        archivo = sys.argv[1]
        cuenta = re.sub(r"_usuarios_\d+\.json$", "", archivo.replace("\\", "/").split("/")[-1])
    else:
        cuenta = leer_username_de_scraper()
        archivo = f"{cuenta}_usuarios_{TOTAL_USUARIOS}.json"

    try:
        with open(archivo, "r", encoding="utf-8") as f:
            usuarios = json.load(f)
    except FileNotFoundError:
        print(f"⚠️ No se encontró '{archivo}'. Ejecuta primero recolector_seguidores.py.")
        raise SystemExit

    print(f"Usuarios leídos: {len(usuarios)}\n")
    resultados = []
    for clave, titulo in METRICAS:
        valores = [parsear_cantidad(u.get(clave)) for u in usuarios]
        conteo = contar_primeros_digitos(valores)
        prueba = prueba_chi_cuadrado(conteo)
        resultados.append((titulo, conteo, prueba))

        n = prueba["n"]
        print(f"== {titulo}: {n} valores con primer dígito válido ==")
        print("dígito | conteo | observado % | Benford % | esperado | (O-E)²/E")
        for d in DIGITOS:
            obs = 100 * conteo[d] / n if n else 0
            print(f"   {d}   | {conteo[d]:>6} | {obs:>10.1f}  | {100 * benford(d):>8.1f}  | "
                  f"{prueba['esperado'][d]:>8.1f} | {prueba['contrib'][d]:>8.3f}")
        print(f"\nχ² = {prueba['chi']:.3f}  (gl = {GL}, crítico 5% = {CRITICO_5}, crítico 1% = {CRITICO_1})")
        print(f"p-valor = {prueba['p']:.4f}")
        print(f"RESULTADO: {prueba['veredicto'].upper()}")
        if n < MIN_MUESTRA:
            print(f"⚠️ Solo {n} valores válidos (< {MIN_MUESTRA}): el resultado no es confiable.")
        print()

    archivo_png = f"benford_{cuenta}.png"
    graficar(resultados, cuenta, archivo_png)
    print(f"✅ Gráfica guardada en '{archivo_png}'.")

    guardar_en_excel(archivo, resultados)


if __name__ == "__main__":
    main()