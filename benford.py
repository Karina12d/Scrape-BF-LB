import json, math, re, sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # genera el PNG sin necesitar ventana
import matplotlib.pyplot as plt

from recolector_seguidores import TOTAL_USUARIOS, leer_username_de_scraper

CAMPO, GL, MIN_MUESTRA = "seguidos", 8, 50
CRITICO_5, CRITICO_1 = 15.507, 20.090   # chi-cuadrado con 8 gl: p = 0.05 y p = 0.01
COLORES = {"Humano": "#10B981", "Posible bot": "#F59E0B", "Bot": "#EF4444"}
D = range(1, 10)


def benford(d):
    return math.log10(1 + 1 / d)


def parsear_cantidad(texto):
    """'2593' -> 2593 | '2.593' -> 2593 | '1,2 mil' -> 1200 | '3,4 M' -> 3400000 | inválido -> None"""
    m = re.fullmatch(r"([\d.,]+)\s*(mil|k|m)?", str(texto).strip().lower())
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
    esp = {d: n * benford(d) for d in D}
    contrib = {d: (conteo[d] - esp[d]) ** 2 / esp[d] for d in D}
    chi = sum(contrib.values())
    x = chi / 2   # p-valor exacto para gl par: e^(-x) * sum(x^k / k!), k < gl/2
    p = math.exp(-x) * sum(x ** k / math.factorial(k) for k in range(GL // 2))
    v = "Humano" if chi <= CRITICO_5 else "Posible bot" if chi <= CRITICO_1 else "Bot"
    return {"conteo": conteo, "n": n, "esp": esp, "contrib": contrib, "chi": chi, "p": p, "veredicto": v}


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
        wb = load_workbook(ruta)
    except FileNotFoundError:
        return print(f"⚠️ No existe '{ruta}'. Ejecuta primero recolector_seguidores.py.")
    ws = wb["Usuarios"] if "Usuarios" in wb.sheetnames else wb.active
    n = r["n"]
    filas = [["Primer dígito", f"Conteo {CAMPO}", "Observado %", "Benford %", "Conteo esperado", "(O-E)²/E"]]
    filas += [[d, r["conteo"][d], r["conteo"][d] / n, benford(d), r["esp"][d], r["contrib"][d]] for d in D]
    filas += [["Total", n], [], ["Chi-cuadrado (χ²)", round(r["chi"], 3)], ["Grados de libertad", GL],
              ["Valor crítico 5%", CRITICO_5], ["Valor crítico 1%", CRITICO_1],
              ["p-valor", round(r["p"], 4)], ["Resultado", r["veredicto"].upper()]]
    for i, fila in enumerate(filas, 1):
        for j, valor in enumerate(fila, 5):
            ws.cell(i, j, valor)
    for i in range(2, 11):
        ws.cell(i, 7).number_format = ws.cell(i, 8).number_format = "0.0%"
    for c in ws[1][4:10]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="7C3AED")
    for col in "EFGHIJ":
        ws.column_dimensions[col].width = 18
    res = ws.cell(len(filas), 6)
    res.font, res.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=COLORES[r["veredicto"]][1:])
    try:
        wb.save(ruta)
        print(f"✅ Tabla de Benford y chi-cuadrado agregada en '{ruta}' (hoja '{ws.title}', desde la columna E).")
    except PermissionError:
        print(f"⚠️ No se pudo guardar '{ruta}': ciérralo en Excel y vuelve a ejecutar benford.py.")


def main():
    if len(sys.argv) > 1:
        archivo = sys.argv[1]
        cuenta = re.sub(r"_usuarios_\d+\.json$", "", re.split(r"[\\/]", archivo)[-1])
    else:
        cuenta = leer_username_de_scraper()
        archivo = f"{cuenta}_usuarios_{TOTAL_USUARIOS}.json"
    try:
        usuarios = json.loads(Path(archivo).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"⚠️ No se encontró '{archivo}'. Ejecuta primero recolector_seguidores.py.")
    valores = [parsear_cantidad(u.get(CAMPO)) for u in usuarios]
    if not any(valores):
        raise SystemExit("⚠️ No hay valores válidos para analizar.")

    r = analizar(valores)
    print(f"Usuarios leídos: {len(usuarios)} | valores con primer dígito válido: {r['n']}\n")
    print("dígito | conteo | observado % | Benford %")
    for d in D:
        print(f"   {d}   | {r['conteo'][d]:>6} | {100 * r['conteo'][d] / r['n']:>10.1f}  | {100 * benford(d):>8.1f}")
    print(f"\nχ² = {r['chi']:.3f} (gl = {GL}, crítico 5% = {CRITICO_5}, 1% = {CRITICO_1})  p = {r['p']:.4f}")
    print(f"RESULTADO: {r['veredicto'].upper()}")
    if r["n"] < MIN_MUESTRA:
        print(f"⚠️ Solo {r['n']} valores válidos (< {MIN_MUESTRA}): el resultado no es confiable.")

    png = f"benford_{cuenta}.png"
    graficar(r, cuenta, png)
    print(f"\n✅ Gráfica guardada en '{png}'.")
    guardar_en_excel(archivo, r)


if __name__ == "__main__":
    main()