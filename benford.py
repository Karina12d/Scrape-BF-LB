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
def _figura(titulo, conteo, prueba, cuenta, archivo_png):
    """UNA sola gráfica: curva de Benford + curva observada (chi-cuadrado) + área de distancia + veredicto."""
    n, chi, v = prueba["n"], prueba["chi"], prueba["veredicto"]
    color_v = COLORES[v]
    observado = [100 * conteo[d] / n if n else 0 for d in DIGITOS]
    esperado = [100 * benford(d) for d in DIGITOS]

    fig = plt.figure(figsize=(11.5, 7.6))
    gs = fig.add_gridspec(2, 1, height_ratios=[5, 1.15], hspace=0.42)
    ax = fig.add_subplot(gs[0])
    gauge = fig.add_subplot(gs[1])

    # --- dos curvas: Benford (roja) y observada/chi-cuadrado (verde); el área rayada entre ambas es la distancia
    xs = list(DIGITOS)
    ax.fill_between(xs, observado, esperado, interpolate=True, facecolor="#3B4FD8", alpha=0.22,
                    hatch="///", edgecolor="#3B4FD8", linewidth=0, label="Distancia (área entre curvas)")
    ax.plot(xs, esperado, color="#EF4444", marker="o", linewidth=2.8, markersize=7,
            label="Ley de Benford (esperado)", zorder=3)
    ax.plot(xs, observado, color="#84B30F", marker="o", linewidth=2.8, markersize=7,
            label="Observado – chi-cuadrado", zorder=4)
    for d in DIGITOS:
        ax.text(d, max(observado[d - 1], esperado[d - 1]) + 1.0, str(conteo[d]), ha="center", va="bottom",
                fontsize=10, color="#1F2340", fontweight="bold")

    ax.set_xticks(list(DIGITOS))
    ax.set_xticklabels([f"{d}\nχ²ᵢ = {prueba['contrib'][d]:.2f}" for d in DIGITOS], fontsize=9)
    ax.set_xlabel("Primer dígito   (χ²ᵢ = (O − E)² / E: aporte de cada dígito a la distancia)")
    ax.set_ylabel("Frecuencia (%)")
    ax.set_ylim(0, max(max(observado), max(esperado)) + 12)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper center", ncol=3, frameon=True, fontsize=9.5)
    ax.set_title(f"Ley de Benford y chi-cuadrado – {titulo} de los usuarios de @{cuenta} (n = {n})",
                 fontsize=13, fontweight="bold")

    resumen = (f"Distancia χ² = Σ(O−E)²/E = {chi:.2f}\n"
               f"gl = {GL}   p-valor = {prueba['p']:.4f}\n"
               f"RESULTADO: {v.upper()}")
    ax.text(0.985, 0.80, resumen, transform=ax.transAxes, ha="right", va="top", fontsize=11,
            fontweight="bold", color=color_v, bbox=dict(boxstyle="round,pad=0.5", fc="white", ec=color_v, lw=2))

    # --- escala de decisión: dónde cae la distancia χ²
    xmax = 35 if chi > 35 else max(30, chi * 1.25)
    fuera = chi > xmax
    x_marca = xmax * 0.97 if fuera else chi
    gauge.axvspan(0, CRITICO_5, color=COLORES["Humano"], alpha=0.35)
    gauge.axvspan(CRITICO_5, CRITICO_1, color=COLORES["Posible bot"], alpha=0.45)
    gauge.axvspan(CRITICO_1, xmax, color=COLORES["Bot"], alpha=0.35)
    gauge.text(CRITICO_5 / 2, 0.5, f"HUMANO\n(χ² ≤ {CRITICO_5})", ha="center", va="center", fontsize=9)
    gauge.text((CRITICO_5 + CRITICO_1) / 2, 0.5, "POSIBLE\nBOT", ha="center", va="center", fontsize=8)
    gauge.text((CRITICO_1 + xmax) / 2, 0.5, f"BOT (χ² > {CRITICO_1})", ha="center", va="center", fontsize=9)
    gauge.axvline(x_marca, color=color_v, linewidth=4)
    gauge.annotate(f"χ² = {chi:.2f}" + (" →" if fuera else ""), xy=(x_marca, 1.0), xytext=(0, 6),
                   textcoords="offset points", ha="center", va="bottom", fontsize=10,
                   fontweight="bold", color=color_v, annotation_clip=False)
    gauge.set_xlim(0, xmax)
    gauge.set_ylim(0, 1)
    gauge.set_yticks([])
    gauge.set_xlabel("Escala de decisión según la distancia χ² (8 grados de libertad)")

    fig.savefig(archivo_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def graficar(resultados, cuenta, archivo_png):
    for i, (titulo, conteo, prueba) in enumerate(resultados):
        destino = archivo_png if i == 0 else archivo_png.replace(".png", f"_{titulo.lower()}.png")
        _figura(titulo, conteo, prueba, cuenta, destino)


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