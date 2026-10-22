from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (Flowable, KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

# ---------- Paleta ----------
OSCURO = colors.HexColor("#1F2340")
GRIS = colors.HexColor("#6B7280")
GRIS_CLARO = colors.HexColor("#E5E7EB")
FONDO_SUAVE = colors.HexColor("#F5F6FA")
BLANCO = colors.white

RASGOS = [
    ("apertura", "Apertura a la experiencia", "Openness", colors.HexColor("#7C3AED")),
    ("responsabilidad", "Responsabilidad", "Conscientiousness", colors.HexColor("#0EA5A4")),
    ("extroversion", "Extroversión", "Extraversion", colors.HexColor("#F59E0B")),
    ("amabilidad", "Amabilidad", "Agreeableness", colors.HexColor("#10B981")),
    ("neuroticismo", "Neuroticismo", "Neuroticism", colors.HexColor("#EF4444")),
]

# ---------- Estilos ----------
E_NOMBRE = ParagraphStyle("nombre", fontName="Helvetica-Bold", fontSize=22, textColor=BLANCO, leading=26)
E_USER = ParagraphStyle("user", fontName="Helvetica", fontSize=11, textColor=colors.HexColor("#C7CAF0"), leading=14)
E_SECCION = ParagraphStyle("seccion", fontName="Helvetica-Bold", fontSize=14, textColor=OSCURO,
                           spaceBefore=14, spaceAfter=8)
E_TEXTO = ParagraphStyle("texto", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#374151"),
                         leading=14.5, alignment=TA_JUSTIFY)
E_BIO = ParagraphStyle("bio", parent=E_TEXTO, fontName="Helvetica-Oblique", textColor=GRIS)
E_RASGO = ParagraphStyle("rasgo", fontName="Helvetica-Bold", fontSize=11.5, textColor=OSCURO, leading=14)
E_RASGO_EN = ParagraphStyle("rasgo_en", fontName="Helvetica", fontSize=8.5, textColor=GRIS, leading=11)
E_STAT_N = ParagraphStyle("stat_n", fontName="Helvetica-Bold", fontSize=16, textColor=OSCURO,
                          alignment=TA_CENTER, leading=19)
E_STAT_L = ParagraphStyle("stat_l", fontName="Helvetica", fontSize=8.5, textColor=GRIS,
                          alignment=TA_CENTER, leading=11)
E_NOTA = ParagraphStyle("nota", fontName="Helvetica-Oblique", fontSize=8, textColor=GRIS, leading=11)


def limpiar(texto):
    """Escapa XML y elimina caracteres que Helvetica no puede dibujar (emojis, etc.)."""
    if texto is None:
        return ""
    texto = str(texto)
    texto = texto.encode("cp1252", errors="ignore").decode("cp1252")
    return escape(texto).replace("\n", "<br/>")


class BarraPuntuacion(Flowable):
    """Barra horizontal con porcentaje."""

    def __init__(self, valor, color, ancho, alto=11):
        super().__init__()
        self.valor, self.color, self.ancho, self.alto = valor, color, ancho, alto

    def wrap(self, *_):
        return self.ancho, self.alto

    def draw(self):
        c = self.canv
        c.setFillColor(GRIS_CLARO)
        c.roundRect(0, 0, self.ancho, self.alto, self.alto / 2, stroke=0, fill=1)
        ancho_val = max(self.alto, self.ancho * self.valor / 100)
        c.setFillColor(self.color)
        c.roundRect(0, 0, ancho_val, self.alto, self.alto / 2, stroke=0, fill=1)


def _puntuacion(dato):
    try:
        return max(0, min(100, int(float(dato.get("puntuacion", 0)))))
    except (TypeError, ValueError, AttributeError):
        return 0


def _cabecera(perfil, ancho):
    nombre = limpiar(perfil.get("nombre") or perfil.get("usuario"))
    usuario = limpiar(perfil.get("usuario"))
    celda = [Paragraph(nombre, E_NOMBRE), Paragraph(f"@{usuario} · Perfil de personalidad Big Five", E_USER)]
    t = Table([[celda]], colWidths=[ancho])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), OSCURO),
        ("LEFTPADDING", (0, 0), (-1, -1), 22),
        ("RIGHTPADDING", (0, 0), (-1, -1), 22),
        ("TOPPADDING", (0, 0), (-1, -1), 22),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", [10, 10, 10, 10]),
    ]))
    return t


def _estadisticas(perfil, publicaciones, ancho):
    datos = [
        (perfil.get("seguidores") or "—", "Seguidores"),
        (perfil.get("seguidos") or "—", "Seguidos"),
        (str(len(publicaciones)), "Publicaciones analizadas"),
    ]
    fila = [[Paragraph(limpiar(n), E_STAT_N), ] for n, _ in datos]
    celdas = [[[Paragraph(limpiar(n), E_STAT_N), Paragraph(l, E_STAT_L)] for n, l in datos]]
    t = Table(celdas, colWidths=[ancho / 3] * 3)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), FONDO_SUAVE),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, GRIS_CLARO),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
    ]))
    return t


def _bloque_rasgo(clave, titulo, ingles, color, dato, ancho):
    puntos = _puntuacion(dato)
    analisis = limpiar(dato.get("analisis", "")) if isinstance(dato, dict) else ""

    encabezado = Table(
        [[[Paragraph(titulo, E_RASGO), Paragraph(ingles, E_RASGO_EN)],
          Paragraph(f'<font color="{color.hexval().replace("0x", "#")}" size="20"><b>{puntos}</b></font>'
                    f'<font color="#6B7280" size="9"> / 100</font>',
                    ParagraphStyle("p", alignment=2, leading=22))]],
        colWidths=[ancho * 0.7, ancho * 0.3],
    )
    encabezado.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    return KeepTogether([
        encabezado,
        Spacer(1, 5),
        BarraPuntuacion(puntos, color, ancho),
        Spacer(1, 7),
        Paragraph(analisis, E_TEXTO),
        Spacer(1, 16),
    ])


def _pie(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(GRIS_CLARO)
    canvas.line(2 * cm, 1.6 * cm, A4[0] - 2 * cm, 1.6 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRIS)
    canvas.drawString(2 * cm, 1.1 * cm, f"Generado el {datetime.now():%d/%m/%Y} · Estimación automática con IA, solo orientativa")
    canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Página {doc.page}")
    canvas.restoreState()


def guardar_pdf_bigfive(resultado_instagram, analisis, nombre_archivo):
    """Genera un PDF estilizado con el perfil de Instagram y el análisis Big Five."""
    perfil = resultado_instagram["perfil"]
    publicaciones = resultado_instagram["publicaciones"]

    doc = SimpleDocTemplate(
        nombre_archivo, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2.2 * cm,
        title=f"Big Five - @{perfil.get('usuario')}", author="Análisis Big Five",
    )
    ancho = A4[0] - 4 * cm - 12  # descuenta el padding interno del frame

    historia = [_cabecera(perfil, ancho), Spacer(1, 12), _estadisticas(perfil, publicaciones, ancho)]

    bio = perfil.get("biografia")
    if bio:
        historia += [Spacer(1, 12), Paragraph(limpiar(bio), E_BIO)]

    historia.append(Paragraph("Resultados del modelo OCEAN", E_SECCION))
    for clave, titulo, ingles, color in RASGOS:
        dato = analisis.get(clave, {})
        historia.append(_bloque_rasgo(clave, titulo, ingles, color, dato, ancho))

    resumen = analisis.get("resumen_psicologico")
    if resumen:
        caja = Table([[Paragraph(limpiar(resumen), E_TEXTO)]], colWidths=[ancho])
        caja.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), FONDO_SUAVE),
            ("LINEBEFORE", (0, 0), (0, -1), 4, OSCURO),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))
        historia.append(KeepTogether([Paragraph("Resumen psicológico", E_SECCION), caja]))

    historia += [Spacer(1, 14),
                 Paragraph("Este informe se basa únicamente en la biografía y textos públicos de las "
                           "publicaciones y no constituye una evaluación psicológica profesional.", E_NOTA)]

    doc.build(historia, onFirstPage=_pie, onLaterPages=_pie)
    return nombre_archivo
