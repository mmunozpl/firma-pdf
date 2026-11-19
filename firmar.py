"""Firma un PDF con el certificado de la FNMT y le pone un pie de firma.

Cada página recibe un recuadro al pie, al modo de las referencias
electrónicas de la Seguridad Social: firmante, fecha, identificador del
documento y página, con una línea sobre cómo comprobar la firma. Después se
firma en PAdES con el certificado (.p12 o .pfx exportado del navegador), y el
campo de firma se coloca sobre el recuadro de la última página, de modo que
pulsarlo en el lector abre la validación.

El contenido original se reduce lo justo para dejar libre la banda del pie,
así que ningún texto del documento queda tapado.

Uso:
    firmar.py entrada.pdf [-o salida.pdf] --p12 certificado.p12
        [--motivo "..."] [--lugar "Sevilla"] [--sin-reducir]
    firmar.py entrada.pdf --solo-pie --nombre "Manuel Muñoz Plá"

Con --solo-pie no se firma: se pone el pie y se deja el PDF listo para
firmarlo en Okular o en AutoFirma, dibujando la firma sobre el recuadro.
La contraseña se pide por teclado, o se toma de FIRMA_P12_CLAVE si existe.

    firmar.py --listar
    firmar.py entrada.pdf --instalado N

Con --listar se enumeran los certificados con clave privada instalados en el
sistema (Firefox y Chrome en Linux, el almacén personal en Windows, el
llavero en macOS; ver almacenes.py); --instalado N firma con el número N de
esa lista, sin exportar nada a disco. En Linux la contraseña es la principal
del navegador, vacía si no tiene.

    firmar.py documento_firmado.pdf --comprobar [--valide | --valide-web]
    firmar.py documento_firmado.pdf --ue

Con --comprobar se valida en local lo mismo que valida VALIDe: integridad,
cadena hasta la raíz de la FNMT y revocación por OCSP o CRL, y se busca la
huella del fichero en el registro. Con --valide se envía el fichero a VALIDe
y se muestra su respuesta: el código de seguridad del formulario se enseña
en una imagen y lo escribe la persona, nunca el programa. Con --valide-web
solo se abre el formulario en el navegador. Con --ue se valida en local
contra las listas de confianza de la UE, con la cualificación del
certificado y de los sellos; se descargan las listas, no el documento.

Cada firma se anota en registro.csv, en la carpeta de datos del usuario
(~/.local/share/ManPla/firma-pdf, %APPDATA%\\ManPla\\firma-pdf o
~/Library/Application Support/ManPla/firma-pdf).

La firma es PAdES-B-B.

    firmar.py --condiciones

Con --condiciones se muestran las condiciones de uso: la licencia y la
ausencia de garantía y de soporte.
"""
import argparse
import csv
import datetime as dt
import getpass
import hashlib
import html
import io
import logging
import os
import re
import secrets
import subprocess
import tempfile
import textwrap
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.serialization import pkcs12
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers
from pyhanko.stamp import TextStampStyle
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import ArrayObject, FloatObject, NameObject
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.barcode.qrencoder import QR8bitByte, QRECI
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import Color, black
from reportlab.pdfgen import canvas

import almacenes

# versión de la aplicación (la misma que pyproject.toml)
VERSION = "0.3.0"

# condiciones de uso: un solo texto para la ventana, para «--condiciones» y
# para la portada del repositorio. Su versión es la fecha del texto, con su
# revisión si cambia más de una vez el mismo día: si el texto cambia, cambia
# la versión y la ventana vuelve a pedir que se acepten
VERSION_CONDICIONES = "19-11-2026 (revisión 4)"
LICENCIA = "Apache-2.0"
LICENCIA_URL = "https://www.apache.org/licenses/LICENSE-2.0"
CONTACTO = "https://manpla.net/contacto"
CONDICIONES = (
    ("Licencia", (
        f"FirmaManPla se distribuye con la licencia {LICENCIA} "
        f"({LICENCIA_URL}). Permite usarla, modificarla y redistribuirla, "
        "también con fin comercial. Quien la redistribuya, con cambios o "
        "sin ellos, entrega una copia de la licencia, conserva los avisos "
        "de derechos de autor, patentes, marcas y atribución, indica los "
        "ficheros que haya modificado e incluye los avisos de atribución "
        "del fichero NOTICE (sección 4). La licencia cubre el código del "
        "autor: Qt y PySide6 (LGPL-3.0) y los demás componentes de "
        "terceros conservan la suya.",
        "Para una versión comercial de la aplicación, contacte con el autor "
        f"en {CONTACTO}. La ampliación de la aplicación con sellos de tiempo "
        "puede requerir la contratación de servicios de terceros.",
    )),
    ("Sin garantía ni soporte", (
        "Esta aplicación es una prueba de concepto (POC) que se publica tal "
        "cual, sin garantía de ningún tipo, sin mantenimiento y sin "
        "soporte: no se atienden incidencias ni peticiones. Su uso corre "
        "por cuenta y bajo la responsabilidad exclusiva de quien la use, "
        "que debe comprobar cada firma antes de confiar en ella.",
        "La licencia excluye la garantía y la responsabilidad del autor "
        "hasta donde la ley lo permite (secciones 7 y 8 de Apache-2.0).",
    )),
)

# recursos de la herramienta: junto al guion, o dentro del ejecutable
RECURSOS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
# textos de las licencias de terceros que acompañan a la aplicación
LICENCIAS_TERCEROS = RECURSOS / "recursos" / "licencias"


def _carpeta_datos() -> Path:
    """Carpeta de datos del usuario, la que reserva cada sistema."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME",
                                   Path.home() / ".local" / "share"))
    carpeta = base / "ManPla" / "firma-pdf"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


DATOS = _carpeta_datos()
REGISTRO = DATOS / "registro.csv"
CARPETA_CERTS = DATOS / "certificados"
ZONA = ZoneInfo("Europe/Madrid")
VALIDE_BASE = "https://valide.redsara.es/valide/"
VALIDE = VALIDE_BASE + "validarFirma/ejecutar.html"
VALIDE_ENVIO = VALIDE_BASE + "ejecutarValidarFirma/ejecutar.html"
VALIDE_MAX = 8 * 1024 * 1024  # límite del formulario
# listas de confianza de la UE: la lista de listas (LOTL) de la Comisión y
# las listas nacionales a las que apunta, con su firma XAdES comprobada por
# pyHanko; se guardan un día en la carpeta de datos. Solo se descargan las
# listas y la revocación: el documento no sale del equipo
LISTAS_UE = DATOS / "listas-ue"
CADUCIDAD_LISTAS = dt.timedelta(days=1)
# justificante de la última validación de la sesión (la «versión imprimible»)
VALIDE_JUSTIFICANTE = VALIDE_BASE + "descargarJustificanteFirma/ejecutar.html"
# raíz de la FNMT, incluida en la herramienta para no depender del sistema
# (sha256 ebc5570c29018c4d67b1aa127baf12f703b4611ebc17b7dab5573894179b93fa)
RAIZ_FNMT = RECURSOS / "confianza" / "fnmt-raiz.pem"
# anclas de los sellos en confianza/tsa, con la huella SHA-256 de su DER: la
# raíz autofirmada de la cadena de cada unidad de sellado. La aplicación no
# pide sellos (firma en PAdES-B-B); las anclas sirven para que «Comprobar
# firma» valide, con la revocación de su unidad, los sellos de tiempo que
# lleven los documentos de estos servicios. pyHanko 0.38.1
# necesita como ancla la autoridad situada por encima de la que firma la CRL
# de la unidad: con un ancla que no es autofirmada y firma ella misma esa
# CRL, no construye la ruta del emisor de la CRL, y la revocación de la
# unidad queda solo en manos del OCSP (Sectigo y el Cartão de Cidadão) o no
# se comprueba (Izenpe, sin OCSP): el sello sale entonces como no fiable.
# Cada raíz se tomó por la AIA o
# del repositorio de su autoridad y verifica la firma de la intermedia que
# figura en la lista de confianza, o la de la unidad:
# - Sectigo Qualified Time Stamping Root R45, por la AIA de la CA R35, que es
#   la identidad del servicio en la TSL española
# - ROOT CA QC IZENPE, por la AIA de SUBCA QC IZENPE - TSA, emisora de la
#   unidad de Izenpe. Abarca todas las subCA cualificadas de Izenpe, y
#   pyHanko sigue exigiendo a la unidad el uso extendido de sellado de
#   tiempo
# - BaltStamp Root CA 2026, por la AIA de la emisora de la unidad (BaltStamp
#   Issuing CA 2026), y coincide con la del paquete de certificados de
#   BalTstamp (baltstamp-certs-202603.zip). Con la emisora como ancla,
#   pyHanko 0.38.1 no valida las respuestas OCSP de su respondedor delegado
#   ni puede construir la ruta del emisor de su CRL, que es el propio ancla
#   sin ser autofirmado, y el sello no sale de confianza ni en soft-fail. La
#   unidad, BalTstamp QTSA TSU1 (53c9935a…ddaf), es la identidad del
#   «Qualified Time Stamp Service 10» de la TSL lituana
# - ECRaizEstado 002, raíz del Estado portugués (SCEE), por la AIA de
#   Cartão de Cidadão 006, que se tomó del repositorio del Cartão de Cidadão
#   y emite la EC de Assinatura Digital Qualificada do Cartão de Cidadão
#   0018. La EC 0018 figura en la TSL portuguesa como CA/QC concedida y
#   emite la unidad (Serviço de Validação Cronológica do Cartão de Cidadão
#   000015, identidad de un servicio QTST concedido de esa lista); emite
#   también los certificados de firma de los ciudadanos, y la raíz, toda la
#   PKI del Estado portugués. pyHanko solo acepta como unidad de sellado un
#   certificado con el uso extendido de sellado de tiempo
HUELLAS_TSA = {
    "sectigo-qualified-tsa-root-r45.pem":
        "f871f8976b4068d700d5f281084b4a29eaf4b8f35743330ba062fab46f58c2ed",
    "izenpe-root-ca-qc.pem":
        "8e5b8baedc4d58be0e301cccb6ed173c08d7c77ce4350973389ff1afa11d7a65",
    "baltstamp-root-ca-2026.pem":
        "4cdadb86797a66f5ac4166d22d052b1cd7c223e800dd9553b7bdf3619d4a7a80",
    "ecraizestado-002.pem":
        "3932e8a2a6f9e422594291c14dd87667bfd0a72e607dfdd2872beab0e4d21a10",
}
CONFIANZA_TSA = sorted((RECURSOS / "confianza" / "tsa").glob("*.pem"))
# intermedias de cada cadena, en confianza/tsa/intermedios: entre la raíz y
# la unidad, para construir la ruta sin descargarlas (la unidad del Cartão
# de Cidadão no trae la de su emisora ni el sello la incluye). Nunca son
# ancla
HUELLAS_INTERMEDIOS_TSA = {
    "sectigo-qualified-tsa-r35.pem":
        "cd0a3e00a1bdae3a159fa9e3d70f8e664f560fdce16357cbe440ed0b0d88244f",
    "izenpe-subca-qc-tsa.pem":
        "cf2058aac27925521fc7f2abacd2ee5429dd8d938debd3395ba4a6c042465da7",
    "baltstamp-issuing-ca-2026.pem":
        "d288c20f167825472f95fe1b32a2609f3b557b82502b80375ec41c24b9829aaf",
    "cartao-cidadao-006.pem":
        "ebefabdc96639a5feb3af145afe538d5f146a0cad2c8ec0684dd96b2b3f369e5",
    "cartao-cidadao-ec-0018.pem":
        "947ec40bc41abcb8765b29bc612eafd219f5de5fef2a569bcf73badb2661e094",
}
INTERMEDIOS_TSA = sorted(
    (RECURSOS / "confianza" / "tsa" / "intermedios").glob("*.pem"))
# geometría del pie, en puntos
MARGEN = 24
ALTO_FILA = 9
ALTO_TABLA = 4 * ALTO_FILA  # dos bloques de rótulo y valor
ALTO_NOTA = 14
HUECO_QR = 5
ALTO_TITULO = 10
# la nota va bajo la tabla, con su mismo ancho; el qr ocupa a su derecha
# del título al final de la nota: 60 pt, unos 2,1 cm (módulos de 0,47 mm
# con un nombre corto y una serie de 32 cifras hexadecimales; de 0,40 con
# un nombre de 40 caracteres y una serie de 40). Más pequeño de 54 pt,
# zbar deja de leerlo a 150 ppp de escáner
LADO_QR = ALTO_TITULO + ALTO_TABLA + ALTO_NOTA
BANDA = MARGEN + LADO_QR
# cuerpos de letra del pie, en puntos
TAM_TITULO = 7
TAM_ROTULO = 4.5
TAM_VALOR = 5
TAM_NOTA = 5.5
INTERLINEA_NOTA = 6.5
# base del texto dentro de su fila
BASE_FILA = 2.7
# turquesa de manpla.net (#14b8c9) aclarado al 40 % sobre blanco: #a1e3e9
FONDO = Color(0xA1 / 255, 0xE3 / 255, 0xE9 / 255)
NOTA = (
    "Documento firmado electrónicamente (PAdES) con {certificado}. La firma "
    "puede comprobarse en valide.redsara.es o en el validador DSS de la "
    "Comisión Europea.\nCualquier modificación posterior del documento la "
    "invalida."
)
# textos de la nota que van como enlace, con su destino: VALIDe y la página
# de validación de la demostración de DSS de la Comisión
ENLACES_NOTA = [
    ("valide.redsara.es",
     "https://valide.redsara.es/valide/validarFirma/ejecutar.html"),
    ("el validador DSS de la Comisión Europea",
     "https://ec.europa.eu/digital-building-blocks/DSS/webapp-demo/"
     "validation"),
]
# turquesa oscuro para el enlace, legible impreso en gris
COLOR_ENLACE = Color(0x0B / 255, 0x6F / 255, 0x7A / 255)


def _certificado_nota(emisor: str) -> str:
    """Cómo nombra la nota al certificado: «cualificado» solo si lo es.

    Los certificados de persona física de la FNMT son cualificados; de
    cualquier otro emisor la nota no lo afirma.
    """
    if "FNMT" in emisor.upper():
        return ("certificado cualificado de persona física emitido por la "
                "FNMT-RCM")
    return f"certificado emitido por {emisor}"


def _bytes(p12: Path | bytes) -> bytes:
    """Devuelve el PKCS#12 en bytes, venga de fichero o de memoria."""
    return p12 if isinstance(p12, bytes) else Path(p12).read_bytes()


def datos_certificado(p12: Path | bytes, clave: bytes) -> dict:
    """Lee del certificado el nombre del firmante, el emisor y la caducidad.

    Args:
        p12: ruta del fichero PKCS#12 o sus bytes.
        clave: contraseña del fichero.

    Returns:
        Diccionario con «nombre», «emisor», «caduca» y «huella».
    """
    _, cert, _ = pkcs12.load_key_and_certificates(_bytes(p12), clave)
    d = almacenes.datos_de_cert(cert)
    d["caduca"] = d["caduca"].astimezone(ZONA)
    return d


def _ajustar(c: canvas.Canvas, texto: str, fuente: str, tam: float,
             ancho: float) -> str:
    """Recorta el texto con puntos suspensivos para que quepa en la celda."""
    if c.stringWidth(texto, fuente, tam) <= ancho:
        return texto
    while texto and c.stringWidth(texto + "…", fuente, tam) > ancho:
        texto = texto[:-1]
    return texto.rstrip() + "…"


def _bloque(c: canvas.Canvas, x0: float, x1: float, y: float,
            columnas: list[tuple[str, float, str]],
            fuente: str = "Helvetica",
            negrita: str = "Helvetica-Bold") -> None:
    """Dibuja un bloque de dos filas: rótulos con fondo y valores debajo.

    Args:
        c: lienzo.
        x0: borde izquierdo.
        x1: borde derecho.
        y: base del bloque.
        columnas: (rótulo, fracción del ancho, valor) por columna.
    """
    c.setFillColor(FONDO)
    c.rect(x0, y + ALTO_FILA, x1 - x0, ALTO_FILA, stroke=0, fill=1)
    c.setFillColor(black)
    c.rect(x0, y, x1 - x0, 2 * ALTO_FILA)
    c.line(x0, y + ALTO_FILA, x1, y + ALTO_FILA)
    xa = x0
    for k, (rotulo, frac, valor) in enumerate(columnas):
        xb = x1 if k == len(columnas) - 1 else xa + (x1 - x0) * frac
        if k:
            c.line(xa, y, xa, y + 2 * ALTO_FILA)
        cx = (xa + xb) / 2
        c.setFont(negrita, TAM_ROTULO)
        c.drawCentredString(cx, y + ALTO_FILA + BASE_FILA, rotulo)
        valor = _ajustar(c, valor, fuente, TAM_VALOR, xb - xa - 5)
        c.setFont(fuente, TAM_VALOR)
        c.drawCentredString(cx, y + BASE_FILA, valor)
        xa = xb


# designador ECI de UTF-8 (ISO/IEC 18004): sin él, cada lector interpreta
# los bytes a su manera y algunos leen mal las tildes y la «º»
ECI_UTF8 = 26


def texto_qr(datos: dict, fecha: str, ident: str) -> str:
    """Contenido del qr: los datos mínimos para cotejar el papel con la
    firma, en texto y sin enlace.

    Firmante y número de serie se cotejan con el panel del validador; la
    huella abreviada liga el papel al documento original. Fecha, emisor,
    motivo y el resto ya van impresos en el recuadro. Solo lleva las líneas
    que tienen dato.
    """
    lineas = [
        ("", "Firma digital"),
        ("Firmante:", datos.get("nombre")),
        ("Nº serie cert.:", datos.get("serie")),
        ("Huella original:", datos.get("huella_original")),
    ]
    return "\n".join(f"{r} {v}".strip() for r, v in lineas if v)


def _simbolo_qr(texto: str) -> QrCodeWidget:
    """El símbolo QR del texto, en UTF-8 declarado con su ECI.

    reportlab 5.1.0 elige la versión del símbolo sin contar los bits del
    designador ECI: con ciertas longitudes de texto la versión elegida se
    queda corta («code length overflow»). Se fija entonces la siguiente.
    """
    def widget(version):
        return QrCodeWidget([QRECI(ECI_UTF8), QR8bitByte(texto)],
                            barLevel="L", barBorder=2, qrVersion=version)

    w = widget(None)
    try:
        w.qr.make()
    except Exception as e:
        if "overflow" not in str(e):
            raise
        w = widget(w.qr.version + 1)
        w.qr.make()
    return w


def _qr(c: canvas.Canvas, texto: str, x: float, y: float,
        lado: float) -> None:
    """Dibuja un qr en el cuadrado indicado.

    Corrección L y margen de dos módulos (el pie ya deja blanco alrededor):
    módulos más grandes en el mismo sitio, legibles a 150 ppp.
    """
    w = _simbolo_qr(texto)
    x0, y0, x1, y1 = w.getBounds()
    d = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0,
                                       lado / (y1 - y0), 0, 0])
    d.add(w)
    renderPDF.draw(d, c, x, y)


def pie(ancho: float, datos: dict, fecha: str, ident: str, pagina: int,
        total: int) -> PdfReader:
    """Dibuja el recuadro de pie para una página.

    Args:
        ancho: ancho de la página en puntos.
        datos: «nombre» y «emisor» (de la nota), y los opcionales
            «lugar», «motivo», «referencia», «formato»,
            «emisor_cn», «serie» y «huella_original»; sin dato, la celda
            va vacía.
        fecha: fecha y hora de firma, ya formateadas.
        ident: identificador del documento.
        pagina: número de página.
        total: número total de páginas.

    Returns:
        Lector con una sola página que contiene el pie.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(ancho, BANDA))
    x_izq, x_der = MARGEN, ancho - MARGEN
    y_tabla = MARGEN + ALTO_NOTA
    # el qr a la derecha, del título al final de la nota; título, tablas y
    # nota a su izquierda
    _qr(c, texto_qr(datos, fecha, ident), x_der - LADO_QR, MARGEN, LADO_QR)
    x0, x1 = x_izq, x_der - LADO_QR - HUECO_QR
    c.setFont("Helvetica-Bold", TAM_TITULO)
    c.drawString(x0 + 2, y_tabla + ALTO_TABLA + 3, "FIRMA ELECTRÓNICA")
    c.setLineWidth(0.6)
    def d(clave):
        return datos.get(clave) or ""

    # bloque superior: quién, cuándo, dónde, para qué y con qué referencia
    _bloque(c, x0, x1, y_tabla + 2 * ALTO_FILA, [
        ("Firmante", 0.28, datos["nombre"]),
        ("Fecha de firma", 0.19, fecha),
        ("Lugar", 0.12, d("lugar")),
        ("Motivo", 0.28, d("motivo")),
        ("Referencia", 0.13, d("referencia")),
    ])
    # bloque inferior: con qué certificado y formato, sobre qué documento
    # y en qué página
    _bloque(c, x0, x1, y_tabla, [
        ("Emisor del certificado", 0.21, d("emisor_cn")),
        ("Nº de serie del certificado", 0.32, d("serie")),
        ("Formato", 0.11, d("formato")),
        ("Huella original (SHA-256)", 0.15, d("huella_original")),
        ("Id. documento", 0.13, ident),
        ("Página", 0.08, f"{pagina} de {total}"),
    ])
    # nota de comprobación, en dos líneas
    c.setFont("Helvetica", TAM_NOTA)
    texto = NOTA.format(certificado=_certificado_nota(datos["emisor"]))
    nota_con_enlaces(c, texto, x0, x1,
                     MARGEN + ALTO_NOTA - TAM_NOTA - 1, TAM_NOTA,
                     INTERLINEA_NOTA, centrar=True)
    c.save()
    buf.seek(0)
    return PdfReader(buf)


def nota_con_enlaces(c: canvas.Canvas, texto: str, x0: float, x1: float,
                     y: float, tam: float, interlinea: float,
                     con_enlaces: bool = True,
                     fuente: str = "Helvetica",
                     centrar: bool = False) -> None:
    """Escribe una nota en dos líneas como mucho, con sus enlaces.

    Cada frase separada por «\\n» va en su línea si caben en dos; si no,
    el texto se parte seguido. Los textos de ENLACES_NOTA van en color,
    subrayados y con su destino, y no se parten entre líneas.

    Args:
        c: lienzo.
        texto: la nota.
        x0: margen izquierdo.
        x1: margen derecho.
        y: línea base de la primera línea.
        tam: cuerpo de letra.
        interlinea: distancia entre líneas.
        con_enlaces: si los enlaces van en color y con destino; sin ellos,
            en texto normal (en la apariencia de una firma no puede haber
            anotaciones de enlace).
        centrar: si cada línea va centrada entre x0 y x1.
    """
    c.setFont(fuente, tam)
    # cada enlace con espacios duros, para que no se parta entre líneas
    enlaces = [(e.replace(" ", "\u00a0"), url) for e, url in ENLACES_NOTA]
    for (e, _), (duro, _) in zip(ENLACES_NOTA, enlaces):
        texto = texto.replace(e, duro)

    def partir(t: str) -> list[str]:
        lineas, actual = [], ""
        for p in t.split(" "):
            prueba = f"{actual} {p}".strip(" ")
            if c.stringWidth(prueba, fuente, tam) > x1 - x0:
                lineas.append(actual)
                actual = p
            else:
                actual = prueba
        return lineas + [actual]

    def colocar() -> list[str]:
        lineas = [x for parte in texto.split("\n") for x in partir(parte)]
        if len(lineas) > 2:
            lineas = partir(texto.replace("\n", " "))
        return lineas

    # si no cabe en dos líneas, se reduce el cuerpo hasta 4 pt
    lineas = colocar()
    while len(lineas) > 2 and tam > 4:
        tam = round(tam - 0.25, 2)
        lineas = colocar()
    c.setFont(fuente, tam)
    for k, linea in enumerate(lineas[:2]):
        yk = y - k * interlinea
        x, resto = x0, linea
        if centrar:
            x += (x1 - x0 - c.stringWidth(linea, fuente, tam)) / 2
        while resto:
            # el enlace que aparece antes en lo que queda de línea
            hallados = [(resto.find(e), e, url) for e, url in enlaces
                        if e in resto] if con_enlaces else []
            if not hallados:
                c.drawString(x, yk, resto)
                break
            pos, e, url = min(hallados)
            antes = resto[:pos]
            c.drawString(x, yk, antes)
            x += c.stringWidth(antes, fuente, tam)
            ancho_e = c.stringWidth(e, fuente, tam)
            c.setFillColor(COLOR_ENLACE)
            c.drawString(x, yk, e)
            c.setStrokeColor(COLOR_ENLACE)
            c.setLineWidth(0.3)
            c.line(x, yk - 0.8, x + ancho_e, yk - 0.8)
            c.linkURL(url, (x, yk - 1.5, x + ancho_e, yk + tam),
                      relative=0, thickness=0)
            c.setFillColor(black)
            c.setStrokeColor(black)
            x += ancho_e
            resto = resto[pos + len(e):]


def _trasladar_anotaciones(pag, t: Transformation) -> None:
    """Aplica a las anotaciones la transformación aplicada al contenido.

    pypdf transforma solo lo que se dibuja: enlaces, campos de formulario y
    notas conservan sus coordenadas y quedarían desplazados respecto del
    texto reducido. Se transforman su rectángulo y, si lo tienen, sus
    cuadriláteros (los de los enlaces y los resaltados).
    """
    def punto(x, y):
        return t.apply_on((float(x), float(y)))

    for ref in pag.get("/Annots") or []:
        a = ref.get_object()
        r = a.get("/Rect")
        if r is not None and len(r) == 4:
            (xa, ya), (xb, yb) = punto(r[0], r[1]), punto(r[2], r[3])
            a[NameObject("/Rect")] = ArrayObject(
                [FloatObject(v) for v in (min(xa, xb), min(ya, yb),
                                          max(xa, xb), max(ya, yb))])
        q = a.get("/QuadPoints")
        if q is not None:
            nuevos = []
            for k in range(0, len(q) - 1, 2):
                nuevos.extend(punto(q[k], q[k + 1]))
            a[NameObject("/QuadPoints")] = ArrayObject(
                [FloatObject(v) for v in nuevos])


def preparar(entrada: Path, datos: dict, fecha: str, ident: str,
             reducir: bool) -> tuple[bytes, list]:
    """Añade el pie a cada página, reduciendo el contenido si procede.

    Args:
        entrada: PDF original.
        datos: nombre del firmante y emisor.
        fecha: fecha de firma formateada.
        ident: identificador del documento.
        reducir: si se reduce el contenido para liberar la banda del pie.

    Returns:
        Los bytes del PDF con pie y el rectángulo del recuadro en la última
        página, para colocar sobre él el campo de firma.
    """
    # se clona sobre el escritor: pypdf 7 solo transforma páginas suyas
    escritor = PdfWriter(clone_from=str(entrada))
    total = len(escritor.pages)
    caja = None
    for i, pag in enumerate(escritor.pages, start=1):
        if pag.rotation:
            pag.transfer_rotation_to_content()
        mb = pag.mediabox
        ancho, alto = float(mb.width), float(mb.height)
        x_org, y_org = float(mb.left), float(mb.bottom)
        if reducir:
            # se escala el contenido y se sube por encima de la banda
            s = (alto - BANDA) / alto
            dx = x_org + ancho * (1 - s) / 2
            t = (Transformation().translate(-x_org, -y_org).scale(s, s)
                 .translate(dx, y_org + BANDA))
            pag.add_transformation(t)
            _trasladar_anotaciones(pag, t)
        sello = pie(ancho, datos, fecha, ident, i, total).pages[0]
        pag.merge_transformed_page(
            sello, Transformation().translate(x_org, y_org)
        )
        # la fusión deja el contenido sin comprimir: el qr solo, unos 47 KB
        # por página; se vuelve a comprimir
        pag.compress_content_streams(level=9)
        y_tabla = y_org + MARGEN + ALTO_NOTA
        caja = (x_org + MARGEN, y_tabla, x_org + ancho - MARGEN,
                y_tabla + ALTO_TABLA)
    escritor.add_metadata({"/Author": datos["nombre"]})
    buf = io.BytesIO()
    escritor.write(buf)
    return buf.getvalue(), [int(v) for v in caja]


def firmar(datos_pdf: bytes, caja: list, total: int, p12: Path | bytes,
           clave: bytes, motivo: str, lugar: str) -> bytes:
    """Firma en PAdES-B-B, sin sello de tiempo, con el campo visible sobre
    el recuadro de la última página.

    Args:
        datos_pdf: PDF ya con el pie.
        caja: rectángulo del recuadro en la última página.
        total: número de páginas.
        p12: fichero PKCS#12 o sus bytes.
        clave: contraseña.
        motivo: motivo de la firma.
        lugar: lugar de la firma.

    Returns:
        Los bytes del PDF firmado.
    """
    firmante = signers.SimpleSigner.load_pkcs12_data(
        _bytes(p12), other_certs=[], passphrase=clave)
    if firmante is None:
        sys.exit("no se pudo abrir el certificado (¿contraseña?)")
    meta = signers.PdfSignatureMetadata(
        field_name="FirmaManPla", md_algorithm="sha256",
        subfilter=fields.SigSeedSubFilter.PADES,
        reason=motivo or None, location=lugar or None,
    )
    campo = fields.SigFieldSpec(
        "FirmaManPla", on_page=total - 1, box=tuple(caja)
    )
    # el recuadro ya está dibujado: la apariencia del campo va vacía
    estilo = TextStampStyle(stamp_text=" ", border_width=0)
    pdf_signer = signers.PdfSigner(
        meta, signer=firmante, stamp_style=estilo, new_field_spec=campo,
    )
    w = IncrementalPdfFileWriter(io.BytesIO(datos_pdf))
    return pdf_signer.sign_pdf(w).getvalue()


def _cambios(est) -> str:
    """Qué se ha añadido al PDF después de esta firma, según pyHanko.

    Las revisiones añadidas detrás de la firma no rompen su integridad
    criptográfica; el nivel de modificación dice si eran de las permitidas.
    """
    nivel = getattr(est, "modification_level", None)
    if nivel is None or nivel.name == "NONE":
        return "ninguno"
    return {"LTA_UPDATES": "solo datos de validación",
            "FORM_FILLING": "firmas o campos de formulario",
            "ANNOTATIONS": "anotaciones",
            "OTHER": "otros cambios: revisar"}.get(nivel.name, nivel.name)


def comprobar(pdf: Path, revocacion: str) -> bool:
    """Valida las firmas de un PDF contra la raíz de la FNMT.

    Comprueba que el documento no ha cambiado desde la firma, que el
    certificado encadena hasta la raíz y que no está revocado (OCSP o CRL,
    descargados en el momento). Busca también la huella en el registro.

    Args:
        pdf: documento firmado.
        revocacion: «hard-fail» exige consultar la revocación;
            «soft-fail» la consulta si puede.

    Returns:
        True si todas las firmas son válidas.
    """
    from pyhanko.keys import load_cert_from_pemder
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import (validate_pdf_signature,
                                         validate_pdf_timestamp)
    from pyhanko_certvalidator import ValidationContext

    # se silencian los avisos internos: el resultado va en la tabla
    for nombre in ("pyhanko", "pyhanko_certvalidator", "asyncio"):
        logging.getLogger(nombre).setLevel(logging.CRITICAL)
    contexto = ValidationContext(
        trust_roots=[load_cert_from_pemder(str(RAIZ_FNMT))],
        allow_fetching=True, revocation_mode=revocacion,
    )
    # el sello se valida contra las raíces de sellado, con sus intermedias
    contexto_ts = ValidationContext(
        trust_roots=[load_cert_from_pemder(str(p)) for p in CONFIANZA_TSA],
        other_certs=[load_cert_from_pemder(str(p)) for p in INTERMEDIOS_TSA],
        allow_fetching=True, revocation_mode="soft-fail",
    )
    with pdf.open("rb") as fh:
        firmas = PdfFileReader(fh).embedded_signatures
        if not firmas:
            if b"/adbe.pkcs7.sha1" in pdf.read_bytes():
                print("lleva una firma en formato antiguo (adbe.pkcs7.sha1, "
                      "con SHA-1), que esta comprobación no valida: se "
                      "puede validar en VALIDe (valide.redsara.es)")
            else:
                print("el documento no lleva ninguna firma")
            return False
        todo_bien = True
        for n, firma in enumerate(firmas, start=1):
            if firma.sig_object_type == "/DocTimeStamp":
                # el sello de documento de B-LTA: se valida como sello
                est = validate_pdf_timestamp(firma,
                                             validation_context=contexto_ts)
                filas = [
                    ("hora", est.timestamp.astimezone(ZONA).strftime(
                        "%d/%m/%Y %H:%M:%S")),
                    ("emitido por", est.signing_cert.subject.native.get(
                        "common_name", "?")),
                    ("intacto", "sí" if est.intact else "NO"),
                    ("válido", "sí" if est.valid else "NO"),
                    ("de confianza", "sí" if est.trusted else "NO"),
                    ("cubre", "el fichero entero" if est.coverage.name ==
                     "ENTIRE_FILE" else "su revisión; hay revisiones detrás"),
                ]
                print(f"sello de documento {n} ({firma.field_name})")
                for k, v in filas:
                    print(f"  {k:<22}{v}")
                todo_bien &= bool(est.intact and est.valid and est.trusted)
                continue
            est = validate_pdf_signature(firma, contexto,
                                         ts_validation_context=contexto_ts)
            sujeto = est.signing_cert.subject.native
            nombre = " ".join(
                x for x in (sujeto.get("given_name"), sujeto.get("surname"))
                if x
            ) or sujeto.get("common_name", "?").split(" - ")[0]
            momento = est.signer_reported_dt
            sello = est.timestamp_validity
            filas = [
                ("firmante", nombre.title()),
                ("emisor", est.signing_cert.issuer.native.get(
                    "common_name", "?")),
                ("fecha declarada", momento.astimezone(ZONA).strftime(
                    "%d/%m/%Y %H:%M") if momento else "sin fecha"),
                ("sello de tiempo", "sí, válido" if sello and sello.valid
                 else ("sí, no válido" if sello else "no")),
                ("documento intacto", "sí" if est.intact else "NO"),
                ("firma criptográfica", "válida" if est.valid else "NO"),
                ("cadena hasta la FNMT", "sí" if est.trusted else "NO"),
                ("revocado", "sí" if est.revoked else "no"),
                ("cubre", "el fichero entero" if est.coverage.name ==
                 "ENTIRE_FILE" else "su revisión; hay revisiones detrás"),
                ("cambios posteriores", _cambios(est)),
            ]
            print(f"firma {n} ({firma.field_name})")
            for k, v in filas:
                print(f"  {k:<22}{v}")
            todo_bien &= est.bottom_line
    huella = hashlib.sha256(pdf.read_bytes()).hexdigest()
    anotado = None
    if REGISTRO.exists():
        with REGISTRO.open(encoding="utf-8") as fh:
            anotado = next((r for r in csv.DictReader(fh)
                            if r["sha256_firmado"] == huella), None)
    if anotado:
        print(f"registro: id {anotado['id']}, firmado el {anotado['fecha']}")
    else:
        print("registro: esta huella no figura en el registro")
    print("resultado:", "VÁLIDO" if todo_bien else "NO VÁLIDO")
    return todo_bien


def fecha_firma(momento: dt.datetime) -> str:
    """Fecha y hora con su desfase respecto de UTC: 16/11/2026 21:15
    UTC+01:00."""
    z = momento.strftime("%z")
    return f"{momento:%d/%m/%Y %H:%M} UTC{z[:3]}:{z[3:]}"


def huella_corta(datos: bytes) -> str:
    """Los 16 primeros caracteres del SHA-256, en grupos de cuatro."""
    h = hashlib.sha256(datos).hexdigest()[:16].upper()
    return " ".join(h[i:i + 4] for i in range(0, 16, 4))


def _anotar(fila: dict) -> None:
    """Añade una fila al registro; si la cabecera del fichero no coincide
    con las columnas actuales, la reescribe conservando las filas que ya
    tenía."""
    campos = ["id", "fecha", "original", "sha256_original", "firmado",
              "sha256_firmado", "sello_tiempo", "formato", "referencia",
              "certificado"]
    filas = []
    if REGISTRO.exists():
        with REGISTRO.open(encoding="utf-8", newline="") as fh:
            lector = csv.DictReader(fh)
            if lector.fieldnames != campos:
                filas = list(lector)
    if filas or not REGISTRO.exists():
        with REGISTRO.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=campos, restval="")
            w.writeheader()
            w.writerows(filas)
    with REGISTRO.open("a", encoding="utf-8", newline="") as fh:
        csv.DictWriter(fh, fieldnames=campos, restval="").writerow(fila)


def _ident() -> str:
    """Identificador corto del documento, de tres grupos hexadecimales."""
    return "-".join(secrets.token_hex(2).upper() for _ in range(3))


def ya_firmado(pdf: Path) -> bool:
    """Si el PDF lleva alguna firma, de cualquier formato o aplicación.

    Toda firma de PDF declara los bytes que cubre en un «/ByteRange».
    """
    return b"/ByteRange" in pdf.read_bytes()


def texto_condiciones() -> str:
    """Las condiciones de uso en texto plano, para la línea de órdenes.

    Returns:
        La cabecera con la versión de la aplicación y la fecha de las
        condiciones, y cada apartado numerado con sus párrafos, a 78
        columnas y sin partir las direcciones.
    """
    lineas = [f"FirmaManPla {VERSION}. Condiciones de uso del "
              f"{VERSION_CONDICIONES}"]
    for n, (titulo, parrafos) in enumerate(CONDICIONES, start=1):
        lineas += ["", f"{n}. {titulo}"]
        for parrafo in parrafos:
            lineas += ["", textwrap.fill(parrafo, 78, break_long_words=False,
                                         break_on_hyphens=False)]
    return "\n".join(lineas)


def _autoprueba_firma() -> str:
    """Firma en memoria con un certificado de usar y tirar, sin red, y
    comprueba que la firma es PAdES-B-B: íntegra, válida y sin sello de
    tiempo.

    Returns:
        El resumen de lo comprobado.
    """
    from asn1crypto import x509 as a_x509
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                           "AUTOPRUEBA")])
    ahora = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(nombre).issuer_name(nombre)
            .public_key(clave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(ahora - dt.timedelta(minutes=5))
            .not_valid_after(ahora + dt.timedelta(days=1))
            .sign(clave, hashes.SHA256()))
    p12 = pkcs12.serialize_key_and_certificates(
        b"autoprueba", clave, cert, None,
        serialization.BestAvailableEncryption(b"autoprueba"))
    buf = io.BytesIO()
    lienzo = canvas.Canvas(buf, pagesize=(595.28, 841.89))
    lienzo.drawString(72, 770, "autoprueba")
    lienzo.save()
    firmado = firmar(buf.getvalue(), [72, 72, 300, 126], 1, p12,
                     b"autoprueba", "", "")
    firmas = PdfFileReader(io.BytesIO(firmado)).embedded_signatures
    assert len(firmas) == 1 and firmas[0].sig_object_type == "/Sig"
    assert firmas[0].sig_object["/SubFilter"] == "/ETSI.CAdES.detached"
    contexto = ValidationContext(
        trust_roots=[a_x509.Certificate.load(
            cert.public_bytes(serialization.Encoding.DER))],
        allow_fetching=False, revocation_mode="soft-fail")
    est = validate_pdf_signature(firmas[0], contexto)
    assert est.intact and est.valid and est.timestamp_validity is None
    return "firma PAdES-B-B en memoria"


def _autoprueba_anclas() -> None:
    """Comprueba que las anclas de los sellos son las cuatro raíces
    autofirmadas de HUELLAS_TSA y las intermedias las de
    HUELLAS_INTERMEDIOS_TSA, con su huella, y que cada intermedia
    encadena con una raíz."""
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding

    def cargar(rutas: list[Path]) -> dict:
        certs = {}
        for p in rutas:
            cert = x509.load_pem_x509_certificate(p.read_bytes())
            assert cert.extensions.get_extension_for_class(
                x509.BasicConstraints).value.ca, p.name
            certs[p.name] = cert
        return certs

    def huellas(certs: dict) -> dict:
        return {n: hashlib.sha256(c.public_bytes(Encoding.DER)).hexdigest()
                for n, c in certs.items()}

    raices, intermedias = cargar(CONFIANZA_TSA), cargar(INTERMEDIOS_TSA)
    assert huellas(raices) == HUELLAS_TSA, huellas(raices)
    assert huellas(intermedias) == HUELLAS_INTERMEDIOS_TSA, huellas(
        intermedias)
    # cada raíz es autofirmada, y cada intermedia la firma una raíz u otra
    # intermedia que acaba en una raíz
    for n, c in raices.items():
        assert c.issuer == c.subject, n
        c.verify_directly_issued_by(c)
    emisores = {c.subject: c for c in [*raices.values(),
                                       *intermedias.values()]}
    for n, c in intermedias.items():
        for _ in range(len(emisores)):
            emisor = emisores[c.issuer]
            c.verify_directly_issued_by(emisor)
            if emisor.issuer == emisor.subject:
                break
            c = emisor
        else:
            raise AssertionError(f"{n} no encadena con una raíz")


def _autoprueba_listas_ue() -> int:
    """Comprueba, sin red, las piezas de la validación con las listas de la
    UE: los certificados de los firmantes de la LOTL que trae pyHanko, el
    analizador de listas (xsdata), los esquemas de signxml y una firma XML
    de ida y vuelta (esquema, canonicalización C14N de lxml y comprobación
    criptográfica), que debe aceptarse intacta y rechazarse alterada. Una
    LOTL sin firma debe rechazarse.

    Returns:
        El número de certificados de firmantes de la LOTL.
    """
    from cryptography import x509 as cx509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from lxml import etree
    from pyhanko.sign.validation.errors import SignatureValidationError
    from pyhanko.sign.validation.qualified import eutl_parse
    from signxml import XMLSigner, XMLVerifier
    from signxml.exceptions import InvalidSignature
    from signxml.xades import XAdESVerifier

    # los esquemas de xmldsig y de xades viajan como datos de signxml
    assert XMLVerifier.schemas() and XAdESVerifier.schemas()
    firmantes = eutl_parse.latest_known_lotl_tlso_certs()
    anclaje = eutl_parse.ojeu_bootstrap_lotl_tlso_certs()
    assert firmantes and anclaje
    # firma xml con una clave de usar y tirar
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = cx509.Name([cx509.NameAttribute(NameOID.COMMON_NAME,
                                             "autoprueba")])
    ahora = dt.datetime.now(dt.timezone.utc)
    cert = (cx509.CertificateBuilder().subject_name(nombre)
            .issuer_name(nombre).public_key(clave.public_key())
            .serial_number(1).not_valid_before(ahora)
            .not_valid_after(ahora + dt.timedelta(days=1))
            .sign(clave, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM)
    firmado = XMLSigner().sign(etree.fromstring("<a><b>autoprueba</b></a>"),
                               key=clave, cert=pem)
    XMLVerifier().verify(firmado, x509_cert=pem)
    firmado.find("b").text = "alterado"
    try:
        XMLVerifier().verify(firmado, x509_cert=pem)
    except InvalidSignature:
        pass
    else:
        raise AssertionError("se aceptó una firma xml alterada")
    lista = (
        '<TrustServiceStatusList xmlns="http://uri.etsi.org/02231/v2#" '
        'TSLTag="http://uri.etsi.org/19612/TSLTag"><SchemeInformation>'
        "<TSLVersionIdentifier>6</TSLVersionIdentifier>"
        "</SchemeInformation></TrustServiceStatusList>")
    assert eutl_parse._raw_tl_parse(lista).scheme_information
    try:
        eutl_parse.validate_and_parse_lotl(lista)
    except SignatureValidationError:
        pass
    else:
        raise AssertionError("se aceptó una LOTL sin firma")
    return len(firmantes)


def autoprueba() -> int:
    """Comprueba que la aplicación empaquetada tiene lo que necesita.

    Dibuja un pie con su QR en memoria y carga pyHanko, sin ventana ni red.
    Firma en memoria en PAdES-B-B, y comprueba las anclas con que «Comprobar
    firma» valida los sellos de tiempo que traiga un documento, los
    módulos y datos con que se leen las listas de confianza de la UE y el
    texto de las condiciones de uso. Sirve para probar el ejecutable de
    cada sistema tras construirlo.

    Returns:
        0 si todo carga; el error se propaga si algo falta.
    """
    from pyhanko.version import __version__ as version_pyhanko

    datos = {"nombre": "Firmante De Prueba", "emisor": "pruebas",
             "emisor_cn": "AC DE PRUEBAS", "formato": "PAdES-B-B",
             "serie": "00", "huella_original": "0000 0000 0000 0000"}
    r = pie(595.28, datos, fecha_firma(dt.datetime.now(ZONA)), "0000-0000",
            1, 1)
    assert len(r.pages) == 1
    # el qr lleva sus cuatro líneas, y cabe con nombres de cualquier largo
    qr = texto_qr(datos, fecha_firma(dt.datetime.now(ZONA)), "0000-0000")
    assert qr.splitlines()[0] == "Firma digital" and len(qr.splitlines()) == 4
    for n in range(1, 121):
        _simbolo_qr(texto_qr(dict(datos, nombre="Ñ" * n), "", ""))
    assert RAIZ_FNMT.exists()
    _autoprueba_anclas()
    # la cofirma rasteriza la página con QtPdf para buscar el hueco
    buf = io.BytesIO()
    lienzo = canvas.Canvas(buf, pagesize=(595.28, 841.89))
    lienzo.drawString(72, 770, "autoprueba")
    lienzo.save()
    assert _hueco(buf.getvalue(), RECUADROS)["tipo"] == "completo"
    # las condiciones de uso llevan sus dos apartados y nombran la licencia
    # y el contacto, sin servicios de sellado; la licencia viaja con la
    # aplicación, con su aviso. se comparan sin los saltos de línea del
    # texto plano
    condiciones = " ".join(texto_condiciones().split())
    assert len(CONDICIONES) == 2 and VERSION_CONDICIONES in condiciones
    assert LICENCIA in condiciones and LICENCIA_URL in condiciones
    assert CONTACTO in condiciones and "sellado" not in condiciones
    licencia = (RECURSOS / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in licencia and "Version 2.0" in licencia
    assert "Manuel Muñoz Plá" in (RECURSOS / "NOTICE").read_text(
        encoding="utf-8")
    # los textos de las licencias de terceros acompañan a la aplicación
    for nombre in ("LGPL-3.0.txt", "LGPL-2.1.txt", "GPL-3.0.txt",
                   "Apache-2.0.txt", "MPL-2.0.txt", "PDFium.txt",
                   "AppImage-runtime.txt", "Python-incorporado.txt",
                   "Qt-terceros.txt"):
        assert (LICENCIAS_TERCEROS / nombre).stat().st_size > 2000, nombre
    if getattr(sys, "frozen", False):
        # el paquete lleva la licencia y los avisos de cada componente
        terceros = (RECURSOS / "TERCEROS.txt").read_text(encoding="utf-8")
        for nombre in ("Python 3.11", "signxml", "lxml", "xsdata", "pyHanko",
                       "certifi", "requests", "NOTICE"):
            assert nombre in terceros, nombre
        if sys.platform.startswith("linux"):
            assert (RECURSOS / "TERCEROS-SISTEMA.txt").stat().st_size > 1000
    firma = _autoprueba_firma()
    firmantes_lotl = _autoprueba_listas_ue()
    print(f"FirmaManPla {VERSION}: pie, QR y hueco de cofirma dibujados, "
          f"{firma}, raíz de la FNMT y {len(CONFIANZA_TSA)} raíces y "
          f"{len(INTERMEDIOS_TSA)} intermedias de comprobación con su "
          f"huella, lectura de las listas de la UE ({firmantes_lotl} "
          f"firmantes de la LOTL), condiciones de uso del "
          f"{VERSION_CONDICIONES} y licencia {LICENCIA}, pyHanko "
          f"{version_pyhanko}")
    return 0


def poner_pie(entrada: Path, salida: Path, nombre: str,
              emisor: str = "la FNMT-RCM", reducir: bool = True,
              motivo: str = "", lugar: str = "",
              referencia: str = "") -> dict:
    """Pone el pie en todas las páginas sin firmar.

    El sello de tiempo lo decide después el programa que firme, así que el
    pie remite a la firma.

    Args:
        entrada: PDF original.
        salida: PDF de destino.
        nombre: firmante que se muestra.
        emisor: emisor del certificado.
        reducir: si se reduce el contenido para liberar la banda.
        motivo: motivo de la firma.
        lugar: lugar de la firma.
        referencia: referencia libre (propuesta, expediente, contrato).

    Returns:
        Diccionario con «salida», «id» y «caja».
    """
    if ya_firmado(entrada):
        raise ValueError(f"{entrada.name} ya lleva una firma: el pie la "
                         "invalidaría")
    fecha = fecha_firma(dt.datetime.now(ZONA))
    ident = _ident()
    # sello, formato y certificado los decide el programa que firme
    datos = {"nombre": nombre, "emisor": emisor, "motivo": motivo,
             "lugar": lugar, "referencia": referencia,
             "huella_original": huella_corta(entrada.read_bytes())}
    con_pie, caja = preparar(entrada, datos, fecha, ident, reducir)
    salida.write_bytes(con_pie)
    return {"salida": salida, "id": ident, "caja": caja}


def firmar_documento(entrada: Path, salida: Path, p12: Path | bytes,
                     clave: bytes, motivo: str = "", lugar: str = "",
                     reducir: bool = True, referencia: str = "") -> dict:
    """Pone el pie, firma en PAdES-B-B y anota en el registro.

    Args:
        entrada: PDF original.
        salida: PDF firmado de destino.
        p12: fichero PKCS#12 o sus bytes.
        clave: contraseña del fichero.
        motivo: motivo de la firma.
        lugar: lugar de la firma.
        reducir: si se reduce el contenido para liberar la banda.
        referencia: referencia libre (propuesta, expediente, contrato).

    Returns:
        Diccionario con «salida», «id» y «paginas».
    """
    if ya_firmado(entrada):
        raise ValueError(
            f"{entrada.name} ya lleva una firma (para añadir otra, cofirmar): "
            "poner el pie redibuja las "
            "páginas y la invalidaría. Firma el original sin firmar.")
    datos = datos_certificado(p12, clave)
    ahora = dt.datetime.now(ZONA)
    if datos["caduca"] < ahora:
        raise ValueError("el certificado caducó el "
                         f"{datos['caduca']:%d/%m/%Y}")
    original = entrada.read_bytes()
    datos.update(
        motivo=motivo, lugar=lugar, referencia=referencia,
        formato="PAdES-B-B",
        certificado=f"{datos['emisor_cn']} · nº {datos['serie']}",
        huella_original=huella_corta(original),
    )
    ident = _ident()
    con_pie, caja = preparar(entrada, datos, fecha_firma(ahora), ident,
                             reducir)
    total = len(PdfReader(io.BytesIO(con_pie)).pages)
    firmado = firmar(con_pie, caja, total, p12, clave, motivo, lugar)
    salida.write_bytes(firmado)

    # se anota en el registro local, como el código de autenticidad; la
    # columna del sello queda vacía, porque la firma es PAdES-B-B
    _anotar({
        "id": ident, "fecha": ahora.isoformat(timespec="seconds"),
        "original": entrada.name,
        "sha256_original": hashlib.sha256(original).hexdigest(),
        "firmado": salida.name,
        "sha256_firmado": hashlib.sha256(firmado).hexdigest(),
        "sello_tiempo": "", "formato": datos["formato"],
        "referencia": referencia, "certificado": datos["certificado"],
    })
    return {"salida": salida, "id": ident, "paginas": total}


# cofirma: añadir la firma propia a un documento que llega ya firmado ------

# recuadros de la cofirma, de mayor a menor: completo (tres bloques, nota y
# QR), compacto (dos bloques y una línea) y mínimo (cuatro líneas, de ancho
# ajustable); alto y ancho mínimo en puntos
ALTO_TABLA_COFIRMA = 6 * ALTO_FILA  # tres bloques, con las firmas previas
LADO_QR_COFIRMA = ALTO_TABLA_COFIRMA
ALTO_COFIRMA = ALTO_TITULO + ALTO_TABLA_COFIRMA + ALTO_NOTA + 2
ALTO_COFIRMA_COMPACTO = ALTO_TITULO + 4 * ALTO_FILA + 10
ALTO_COFIRMA_MINIMO = 38
ANCHO_COFIRMA_MINIMO = 300
RECUADROS = [("completo", ALTO_COFIRMA, 500),
             ("compacto", ALTO_COFIRMA_COMPACTO, 400),
             ("minimo", ALTO_COFIRMA_MINIMO, ANCHO_COFIRMA_MINIMO)]
# el mínimo no se estira más allá de este ancho
ANCHO_MAX_MINIMO = 460
# distancia mínima del recuadro al borde inferior del papel, en puntos
MARGEN_PAPEL = 14
NOTA_COFIRMA = (
    "Firma electrónica (PAdES) con {certificado}, añadida a un documento que "
    "ya estaba firmado sin modificar su contenido. Las firmas pueden "
    "comprobarse en valide.redsara.es o en el validador DSS de la Comisión "
    "Europea.\nCualquier modificación posterior del documento las invalida."
)


def _fuentes_unicode() -> tuple[str, str]:
    """DejaVu Sans (normal y negrita), incrustada: los nombres de otros
    países llevan letras que Helvetica no tiene."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "DejaVuSans" not in pdfmetrics.getRegisteredFontNames():
        carpeta = RECURSOS / "recursos" / "fuentes"
        pdfmetrics.registerFont(TTFont("DejaVuSans",
                                       str(carpeta / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold",
                                       str(carpeta / "DejaVuSans-Bold.ttf")))
    return "DejaVuSans", "DejaVuSans-Bold"


def _lector(datos_pdf: bytes):
    """Lector de pyHanko del documento recibido."""
    from pyhanko.pdf_utils.reader import PdfFileReader

    return PdfFileReader(io.BytesIO(datos_pdf), strict=False)


def firmas_previas(datos_pdf: bytes) -> list[dict]:
    """Firmas y sellos de tiempo de documento que ya lleva el documento,
    en orden: titular (o emisor del sello), hora que declaran y tipo."""
    from cryptography import x509

    lista = []
    firmas = _lector(datos_pdf).embedded_signatures
    for s in sorted(firmas, key=lambda s: s.signed_revision):
        nombre = almacenes.datos_de_cert(x509.load_der_x509_certificate(
            s.signer_cert.dump()))["nombre"]
        if s.sig_object_type == "/DocTimeStamp":
            info = s.signed_data["encap_content_info"]["content"].parsed
            hora, tipo = info["gen_time"].native, "sello"
        else:
            hora, tipo = s.self_reported_timestamp, "firma"
        lista.append({"nombre": nombre, "tipo": tipo, "campo": s.field_name,
                      "fecha": hora.astimezone(ZONA).strftime(
                          "%d/%m/%Y %H:%M") if hora else ""})
    return lista


def _texto_previas(previas: list[dict], c: canvas.Canvas, ancho: float,
                   tam: float, fuente: str = "Helvetica") -> str:
    """Las firmas previas en una línea que quepa: «A (fecha), B y N más».

    Solo cuentan las firmas: los sellos de documento de una firma anterior
    en B-LTA los muestra el validador.
    """
    nombres = [f"{p['nombre']} ({p['fecha']})" if p["fecha"] else p["nombre"]
               for p in previas if p["tipo"] == "firma"]
    if not nombres:
        return "ninguna legible"
    for n in range(len(nombres), 0, -1):
        resto = len(nombres) - n
        t = ", ".join(nombres[:n]) + (f" y {resto} más" if resto else "")
        if c.stringWidth(t, fuente, tam) <= ancho:
            return t
    return f"{len(nombres)} firmas previas"


def _caja_visible(pag) -> tuple[float, float, float, float]:
    """La caja que muestran los visores: la CropBox recortada a la
    MediaBox."""
    mb, cb = pag.mediabox, pag.cropbox
    return (max(float(mb.left), float(cb.left)),
            max(float(mb.bottom), float(cb.bottom)),
            min(float(mb.right), float(cb.right)),
            min(float(mb.top), float(cb.top)))


def _hueco(datos_pdf: bytes, recuadros: list[tuple]) -> dict:
    """El sitio del recuadro: el hueco en blanco más bajo de la última
    página que admita el mayor de los recuadros posibles; si no lo hay, la
    página anterior, y así hasta la primera.

    La página se rasteriza con Qt a 1 píxel por punto, en su caja visible;
    las anotaciones visibles (recuadros de otras firmas, campos de
    formulario, notas) cuentan como ocupadas aunque el rasterizado no las
    dibuje. Se busca, de abajo arriba, un rectángulo en blanco del alto de
    cada recuadro y de al menos su ancho mínimo, dentro de los márgenes.

    Args:
        datos_pdf: el documento.
        recuadros: (tipo, alto, ancho mínimo), de mayor a menor.

    Returns:
        «pagina», «tipo», «x0», «y0», «ancho» en puntos PDF si hay sitio;
        si no, «pagina» None y «giradas», las páginas que no se miran por
        llevar /Rotate.
    """
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtPdf import QPdfDocument

    if QGuiApplication.instance() is None:
        global _app_qt
        _app_qt = QGuiApplication(["firmar", "-platform", "offscreen"])
    lector = PdfReader(io.BytesIO(datos_pdf))
    datos_qt = QByteArray(datos_pdf)
    buf = QBuffer(datos_qt)
    buf.open(QIODevice.ReadOnly)
    doc = QPdfDocument()
    doc.load(buf)
    giradas = 0
    try:
        if doc.status() != QPdfDocument.Status.Ready:
            raise ValueError("no se pudo rasterizar el documento para "
                             "buscar el hueco del recuadro")
        for i in range(len(lector.pages) - 1, -1, -1):
            pag = lector.pages[i]
            if pag.rotation % 360:
                giradas += 1
                continue
            cx0, cy0, cx1, cy1 = _caja_visible(pag)
            w, h = int(cx1 - cx0), int(cy1 - cy0)
            if w <= 2 * MARGEN or h <= MARGEN_PAPEL:
                continue
            render = doc.render(i, QSize(w, h))
            if render.isNull():
                continue
            img = QImage(w, h, QImage.Format_Grayscale8)
            img.fill(255)
            pintor = QPainter(img)
            pintor.drawImage(0, 0, render)
            # las anotaciones visibles, como ocupadas
            pintor.setPen(0)
            for ref in pag.get("/Annots") or []:
                a = ref.get_object()
                if int(a.get("/F", 0)) & 2 or "/Rect" not in a:
                    continue
                r = [float(v) for v in a["/Rect"]]
                ax0, ax1 = sorted((r[0], r[2]))
                ay0, ay1 = sorted((r[1], r[3]))
                pintor.fillRect(int(ax0 - cx0) - 2, int(cy1 - ay1) - 2,
                                int(ax1 - ax0) + 4, int(ay1 - ay0) + 4, 0)
            pintor.end()
            bpl = img.bytesPerLine()
            bits = img.constBits().tobytes()
            # suma acumulada, por columna, de píxeles no blancos
            xa, xb = MARGEN, w - MARGEN
            acum = [[0] * (xb - xa)]
            for y in range(h):
                fila = bits[y * bpl + xa:y * bpl + xb]
                prev = acum[-1]
                acum.append([prev[k] + (fila[k] <= 240)
                             for k in range(xb - xa)])
            for tipo, alto, ancho_min in recuadros:
                alto_px = int(alto) + 4
                ancho_max = w - 2 * MARGEN if tipo != "minimo" \
                    else ANCHO_MAX_MINIMO
                if ancho_min > w - 2 * MARGEN:
                    continue
                # de abajo arriba: filas [arriba, abajo] del rectángulo
                for abajo in range(h - MARGEN_PAPEL, alto_px - 1, -1):
                    a, b = acum[abajo - alto_px + 1], acum[abajo + 1]
                    mejor, ini = (0, 0), None
                    for k in range(xb - xa + 1):
                        libre = k < xb - xa and b[k] == a[k]
                        if libre and ini is None:
                            ini = k
                        elif not libre and ini is not None:
                            if k - ini > mejor[0]:
                                mejor = (k - ini, ini)
                            ini = None
                    if mejor[0] >= ancho_min + 4:
                        ancho = min(mejor[0] - 4, ancho_max)
                        x0 = xa + mejor[1] + (mejor[0] - ancho) / 2
                        return {"pagina": i, "tipo": tipo,
                                "x0": cx0 + x0, "y0": cy0 + h - abajo + 1,
                                "ancho": ancho, "giradas": giradas}
        return {"pagina": None, "giradas": giradas}
    finally:
        doc.close()
        buf.close()


def _apariencia_cofirma(ancho: float, tipo: str, datos: dict,
                        fecha: str, previas: list[dict]) -> bytes:
    """El recuadro de la cofirma como página PDF, para la apariencia.

    Tipos: «completo» (tres bloques, nota y QR), «compacto» (dos bloques y
    una línea) y «minimo» (cuatro líneas de texto, para huecos estrechos).
    Lleva fondo blanco propio y una fuente Unicode incrustada.
    """
    fuente, negrita = _fuentes_unicode()
    alto = {"completo": ALTO_COFIRMA, "compacto": ALTO_COFIRMA_COMPACTO,
            "minimo": ALTO_COFIRMA_MINIMO}[tipo]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(ancho, alto))
    c.setFillColor(Color(1, 1, 1))
    c.rect(0, 0, ancho, alto, stroke=0, fill=1)
    c.setFillColor(black)
    c.setLineWidth(0.6)

    def d(clave):
        return datos.get(clave) or ""

    if tipo == "minimo":
        x0, tam = 4, TAM_NOTA
        c.rect(0.5, 0.5, ancho - 1, alto - 1)
        c.setFillColor(FONDO)
        c.rect(0.8, alto - 10.5, ancho - 1.6, 9.7, stroke=0, fill=1)
        c.setFillColor(black)
        c.setFont(negrita, TAM_ROTULO)
        c.drawString(x0, alto - 8, _ajustar(
            c, f"FIRMA ELECTRÓNICA · {datos['nombre']} · {fecha}", negrita,
            TAM_ROTULO, ancho - 2 * x0))
        c.setFont(fuente, tam)
        lineas = [
            f"Certificado: {d('emisor_cn')} nº {d('serie')} · "
            f"{d('formato')}",
            "Firmas previas: " + _texto_previas(
                previas, c, ancho - 2 * x0 - 45, tam, fuente),
            "Comprobable en valide.redsara.es o en el validador DSS de la "
            "Comisión Europea.",
        ]
        for k, linea in enumerate(lineas):
            c.drawString(x0, alto - 17.5 - k * 7.5,
                         _ajustar(c, linea, fuente, tam, ancho - 2 * x0))
    elif tipo == "compacto":
        x0, x1 = 1, ancho - 1
        y = 1 + 10
        c.setFont(negrita, TAM_TITULO)
        c.drawString(x0 + 2, y + 4 * ALTO_FILA + 3, "FIRMA ELECTRÓNICA")
        _bloque(c, x0, x1, y + 2 * ALTO_FILA, [
            ("Firmante", 0.36, datos["nombre"]),
            ("Fecha de firma", 0.32, fecha),
            ("Formato", 0.32, d("formato")),
        ], fuente, negrita)
        _bloque(c, x0, x1, y, [
            ("Firmas previas en el documento", 1.0,
             _texto_previas(previas, c, x1 - x0 - 8, TAM_VALOR, fuente)),
        ], fuente, negrita)
        c.setFont(fuente, TAM_NOTA)
        c.drawString(x0, 2, _ajustar(
            c, "Las firmas pueden comprobarse en valide.redsara.es o en el "
            "validador DSS de la Comisión Europea.", fuente, TAM_NOTA,
            ancho - 2))
    else:
        x_izq, x_der = 1, ancho - 1
        y_tabla = ALTO_NOTA + 1
        _qr(c, texto_qr(datos, fecha, ""), x_der - LADO_QR_COFIRMA, y_tabla,
            LADO_QR_COFIRMA)
        x0, x1 = x_izq, x_der - LADO_QR_COFIRMA - HUECO_QR
        c.setFont(negrita, TAM_TITULO)
        c.drawString(x0 + 2, y_tabla + ALTO_TABLA_COFIRMA + 3,
                     "FIRMA ELECTRÓNICA")
        _bloque(c, x0, x1, y_tabla + 4 * ALTO_FILA, [
            ("Firmante", 0.28, datos["nombre"]),
            ("Fecha de firma", 0.27, fecha),
            ("Lugar", 0.20, d("lugar")),
            ("Motivo", 0.25, d("motivo")),
        ], fuente, negrita)
        _bloque(c, x0, x1, y_tabla + 2 * ALTO_FILA, [
            ("Firmas previas en el documento", 1.0,
             _texto_previas(previas, c, x1 - x0 - 8, TAM_VALOR, fuente)),
        ], fuente, negrita)
        _bloque(c, x0, x1, y_tabla, [
            ("Emisor del certificado", 0.28, d("emisor_cn")),
            ("Nº de serie del certificado", 0.52, d("serie")),
            ("Formato", 0.20, d("formato")),
        ], fuente, negrita)
        nota_con_enlaces(
            c, NOTA_COFIRMA.format(
                certificado=_certificado_nota(datos["emisor"])),
            x_izq, x_der, ALTO_NOTA - TAM_NOTA, TAM_NOTA, INTERLINEA_NOTA,
            con_enlaces=False, fuente=fuente)
    c.save()
    return buf.getvalue()


def _estado_previas(datos_pdf: bytes) -> dict:
    """Integridad de cada firma previa y lo añadido después de ella.

    Returns:
        Campo → «íntegra» (bool) y «cambios» (nivel de modificación de
        pyHanko, o «sospechoso»).
    """
    from pyhanko.sign.diff_analysis import (DEFAULT_DIFF_POLICY,
                                            SuspiciousModification)
    from pyhanko.sign.validation.errors import SignatureValidationError
    from pyhanko.sign.validation import validate_pdf_timestamp
    from pyhanko.sign.validation.generic_cms import validate_sig_integrity
    from pyhanko_certvalidator import ValidationContext

    # solo integridad: sin anclas ni red; la confianza la juzga el validador
    sin_red = ValidationContext(trust_roots=[], allow_fetching=False,
                                revocation_mode="soft-fail")
    estado = {}
    for s in _lector(datos_pdf).embedded_signatures:
        try:
            s.compute_integrity_info(diff_policy=DEFAULT_DIFF_POLICY)
            r = s.diff_result
            cambios = ("sospechoso" if isinstance(r, SuspiciousModification)
                       else r.modification_level.name)
            if s.sig_object_type == "/DocTimeStamp":
                # el sello de documento: su huella y su firma, sin red
                st = validate_pdf_timestamp(s, validation_context=sin_red)
                integra = bool(st.intact and st.valid)
            else:
                intacta, valida = validate_sig_integrity(
                    s.signer_info, s.signer_cert, "data",
                    s.compute_digest())
                integra = bool(intacta and valida)
        except (SignatureValidationError, ValueError, KeyError) as e:
            cambios, integra = f"error: {e}", False
        estado[s.field_name] = {"íntegra": integra, "cambios": cambios}
    return estado


def _sin_danos(antes: dict, despues: dict) -> None:
    """Las firmas previas no pueden quedar peor de lo que estaban.

    Lo añadido después de cada firma previa tiene que seguir siendo, como
    mucho, relleno o firma de campos y datos de validación (pyHanko).
    """
    permitidos = ("NONE", "LTA_UPDATES", "FORM_FILLING")
    for campo, e in antes.items():
        d = despues.get(campo, {"íntegra": False, "cambios": "ausente"})
        if not d["íntegra"] or d["cambios"] not in permitidos:
            raise ValueError(
                f"la firma añadida dejaría la firma previa «{campo}» con "
                f"cambios no permitidos ({d['cambios']}); no se guarda")


def cofirmar(entrada: Path, salida: Path, p12: Path | bytes, clave: bytes,
             motivo: str = "", lugar: str = "") -> dict:
    """Añade la firma propia (PAdES-B-B), visible, a un documento que
    llega firmado.

    El contenido de las páginas no se toca: el recuadro es la apariencia
    del campo de firma, en una revisión incremental. Si el documento trae
    un campo de firma vacío, se firma en él; si no, se crea uno en el hueco
    en blanco más bajo de la última página (o de la anterior más cercana
    que lo tenga). El recuadro dice quién firmó antes, según las firmas del
    propio documento. Antes se comprueba que las firmas previas están
    íntegras, y después, que siguen sin cambios no permitidos.

    Args:
        entrada: PDF recibido, ya firmado.
        salida: PDF de destino.
        p12: fichero PKCS#12 o sus bytes.
        clave: contraseña del fichero.
        motivo: motivo de la firma.
        lugar: lugar de la firma.

    Returns:
        Diccionario con «salida», «previas», «pagina», «recuadro»,
        «compacto» y «campo_reservado».
    """
    from pyhanko.pdf_utils.layout import (AxisAlignment, Margins,
                                          SimpleBoxLayoutRule)
    from pyhanko.sign.validation.pdf_embedded import read_certification_data
    from pyhanko.stamp import StaticStampStyle

    recibido = entrada.read_bytes()
    lector = _lector(recibido)
    if lector.encrypted:
        raise ValueError(f"{entrada.name} está cifrado: no se puede añadir "
                         "una firma a un PDF cifrado")
    if read_certification_data(lector) is not None:
        raise ValueError(f"{entrada.name} lleva una firma de certificación: "
                         "no admite firmas nuevas en campos creados después, "
                         "y añadir la tuya la invalidaría")
    antes = _estado_previas(recibido)
    rotas = [c for c, e in antes.items() if not e["íntegra"]]
    tocadas = [c for c, e in antes.items()
               if e["cambios"] not in ("NONE", "LTA_UPDATES",
                                       "FORM_FILLING")]
    if rotas or tocadas:
        raise ValueError(
            f"{entrada.name} ya trae firmas que no se sostienen: "
            + "; ".join([f"«{c}» no está íntegra" for c in rotas]
                        + [f"«{c}» tiene cambios no permitidos después"
                           for c in tocadas if c not in rotas])
            + ". Compruébalo antes de añadir tu firma")
    previas = firmas_previas(recibido)
    datos = datos_certificado(p12, clave)
    ahora = dt.datetime.now(ZONA)
    if datos["caduca"] < ahora:
        raise ValueError("el certificado caducó el "
                         f"{datos['caduca']:%d/%m/%Y}")
    datos.update(motivo=motivo, lugar=lugar, formato="PAdES-B-B",
                 huella_original=huella_corta(recibido))

    # un campo de firma vacío, reservado por quien preparó el documento
    reservado = None
    nombres = set()
    for nombre, valor, ref in fields.enumerate_sig_fields(lector):
        nombres.add(nombre)
        if valor is None and reservado is None:
            w = ref.get_object()
            r = [float(v) for v in w.get("/Rect", [0, 0, 0, 0])]
            ancho_r, alto_r = abs(r[2] - r[0]), abs(r[3] - r[1])
            if ancho_r >= 60 and alto_r >= 20:
                reservado = (nombre, ancho_r, alto_r)
    if reservado:
        campo, ancho, alto_r = reservado
        tipo = next((t for t, a, m in RECUADROS
                     if alto_r >= a and ancho >= m), "minimo")
        pagina, caja = None, None
    else:
        sitio = _hueco(recibido, RECUADROS)
        if sitio["pagina"] is None:
            n_g = sitio["giradas"]
            motivo_falta = (
                "" if not n_g else
                "; la única página está girada y no se mira" if n_g == 1
                and len(lector.root["/Pages"]["/Kids"]) == 1 else
                f"; {n_g} página{'s' if n_g > 1 else ''} no se mira"
                f"{'n' if n_g > 1 else ''} por estar girada"
                f"{'s' if n_g > 1 else ''}")
            raise ValueError(
                f"{entrada.name} no tiene ningún hueco en blanco de "
                f"{ALTO_COFIRMA_MINIMO} × {ANCHO_COFIRMA_MINIMO} puntos "
                f"(1,3 × 10,6 cm) para el recuadro de la firma{motivo_falta}")
        pagina, tipo, ancho = sitio["pagina"], sitio["tipo"], sitio["ancho"]
        alto = dict((t, a) for t, a, _ in RECUADROS)[tipo]
        caja = (round(sitio["x0"]), round(sitio["y0"]),
                round(sitio["x0"] + ancho), round(sitio["y0"] + alto))
        campo, n = "FirmaManPla", 2
        while campo in nombres:
            campo, n = f"FirmaManPla{n}", n + 1

    firmante = signers.SimpleSigner.load_pkcs12_data(
        _bytes(p12), other_certs=[], passphrase=clave)
    meta = signers.PdfSignatureMetadata(
        field_name=campo, md_algorithm="sha256",
        subfilter=fields.SigSeedSubFilter.PADES,
        reason=motivo or None, location=lugar or None)
    with tempfile.TemporaryDirectory() as tmp:
        apariencia = Path(tmp) / "recuadro.pdf"
        apariencia.write_bytes(_apariencia_cofirma(
            ancho, tipo, datos, fecha_firma(ahora), previas))
        estilo = StaticStampStyle.from_pdf_file(
            str(apariencia), border_width=0,
            background_layout=SimpleBoxLayoutRule(
                x_align=AxisAlignment.ALIGN_MID,
                y_align=AxisAlignment.ALIGN_MID,
                margins=Margins(0, 0, 0, 0)))
        espec = None if reservado else fields.SigFieldSpec(
            campo, on_page=pagina, box=caja)
        firmado = signers.PdfSigner(
            meta, signer=firmante, stamp_style=estilo,
            new_field_spec=espec).sign_pdf(
            IncrementalPdfFileWriter(io.BytesIO(recibido)),
            existing_fields_only=bool(reservado)).getvalue()
    _sin_danos(antes, _estado_previas(firmado))
    if pagina is None:
        pagina = _pagina_del_campo(firmado, campo)
    salida.write_bytes(firmado)
    _anotar({
        "id": campo, "fecha": ahora.isoformat(timespec="seconds"),
        "original": entrada.name,
        "sha256_original": hashlib.sha256(recibido).hexdigest(),
        "firmado": salida.name,
        "sha256_firmado": hashlib.sha256(firmado).hexdigest(),
        "sello_tiempo": "", "formato": datos["formato"],
        "referencia": "", "certificado":
            f"{datos['emisor_cn']} · nº {datos['serie']}",
    })
    return {"salida": salida, "previas": previas,
            "pagina": (pagina + 1) if pagina is not None else None,
            "recuadro": tipo, "compacto": tipo != "completo",
            "campo_reservado": bool(reservado)}


def _pagina_del_campo(datos_pdf: bytes, campo: str) -> int | None:
    """Índice de la página con el recuadro de un campo de firma."""
    for i, pag in enumerate(PdfReader(io.BytesIO(datos_pdf)).pages):
        for ref in pag.get("/Annots") or []:
            if ref.get_object().get("/T") == campo:
                return i
    return None


# varios documentos a la vez ------------------------------------------------

def unir_pdfs(entradas: list[Path]) -> bytes:
    """Une varios PDF sin firmar en uno, en orden, con un marcador por
    documento original.

    Un PDF firmado no se une: su firma no pasaría al documento unido.
    """
    firmados = [e.name for e in entradas if ya_firmado(e)]
    if firmados:
        raise ValueError(
            "no se pueden unir documentos ya firmados, porque su firma no "
            "pasaría al PDF unido: " + ", ".join(firmados)
            + ". Fírmalos por separado")
    escritor = PdfWriter()
    for e in entradas:
        escritor.append(str(e), outline_item=e.stem)
    buf = io.BytesIO()
    escritor.write(buf)
    return buf.getvalue()


def firmar_varios(entradas: list[Path], p12: Path | bytes, clave: bytes,
                  motivo: str = "", lugar: str = "",
                  reducir: bool = True, referencia: str = "",
                  unir: bool = False, salida_unida: Path | None = None,
                  avisar=print) -> list[dict]:
    """Firma varios documentos: unidos en un solo PDF o por separado.

    Unidos, se firma una vez el PDF que resulta de juntarlos en orden
    (unir_pdfs). Por separado, cada uno se firma junto a su original como
    «<nombre>_firmado.pdf»; el que ya llegue firmado recibe la firma
    añadida con su recuadro (cofirmar). Un error en un documento no detiene
    los demás. El resultado de cada documento se avisa por «avisar».

    Returns:
        Una fila por documento firmado (o por el unido) con «documento»,
        «resultado» («firmado» o «error»), «salida» y «detalle».
    """
    if unir:
        destino = salida_unida or entradas[0].with_name(
            entradas[0].stem + "_unido_firmado.pdf")
        with tempfile.TemporaryDirectory() as tmp:
            unido = Path(tmp) / (destino.stem.removesuffix("_firmado")
                                 + ".pdf")
            unido.write_bytes(unir_pdfs(entradas))
            r = firmar_documento(unido, destino, p12, clave, motivo, lugar,
                                 reducir, referencia)
        fila = {"documento": ", ".join(e.name for e in entradas),
                "resultado": "firmado", "salida": destino,
                "detalle": f"{len(entradas)} documentos unidos en "
                f"{r['paginas']} páginas"}
        avisar(f"{destino.name}: {fila['detalle']}")
        return [fila]
    filas = []
    for e in entradas:
        destino = e.with_name(e.stem + "_firmado.pdf")
        try:
            if ya_firmado(e):
                r = cofirmar(e, destino, p12, clave, motivo, lugar)
                det = (f"firma añadida, recuadro en la página "
                       f"{r['pagina']}")
            else:
                r = firmar_documento(e, destino, p12, clave, motivo, lugar,
                                     reducir, referencia)
                n = r["paginas"]
                det = f"{n} página{'s' if n != 1 else ''}"
            filas.append({"documento": e.name, "resultado": "firmado",
                          "salida": destino, "detalle": det})
        except Exception as ex:  # cada documento sigue su suerte
            filas.append({"documento": e.name, "resultado": "error",
                          "salida": None, "detalle": str(ex)})
        avisar(f"{e.name}: {filas[-1]['resultado']} "
               f"({filas[-1]['detalle']})")
    return filas


class SesionValide:
    """Envía un PDF al formulario de VALIDe dentro de una misma sesión.

    El formulario exige un código de seguridad en imagen. Esta clase trae la
    imagen y envía el código que escribe la persona; no intenta leerlo.
    """

    def __init__(self) -> None:
        import requests

        self.http = requests.Session()
        self.http.headers["User-Agent"] = "Mozilla/5.0"
        # se abre el formulario para obtener la cookie de sesión
        self.http.get(VALIDE, timeout=30).raise_for_status()

    def captcha(self) -> bytes:
        """Devuelve la imagen del código de seguridad (JPEG)."""
        r = self.http.get(VALIDE_BASE + "kaptcha.jpg", timeout=30)
        r.raise_for_status()
        return r.content

    def enviar(self, pdf: Path, codigo: str) -> dict:
        """Envía el PDF con el código y resume la respuesta.

        Args:
            pdf: documento firmado.
            codigo: código de seguridad escrito por la persona.

        Returns:
            Diccionario con «estado» («respuesta», «codigo_incorrecto» o
            «error»), «texto» legible y «pagina» (HTML guardado en una
            carpeta privada, o None).
        """
        if pdf.stat().st_size > VALIDE_MAX:
            return {"estado": "error", "pagina": None,
                    "texto": "VALIDe solo admite ficheros de hasta 8 MB"}
        with pdf.open("rb") as fh:
            r = self.http.post(
                VALIDE_ENVIO, data={"codigoSeguridad": codigo.strip()},
                files={"fileData": (pdf.name, fh, "application/pdf")},
                timeout=120,
            )
        r.raise_for_status()
        # el formulario va en latin-1 y la respuesta en utf-8
        try:
            pagina = r.content.decode("utf-8")
        except UnicodeDecodeError:
            pagina = r.content.decode("latin-1")
        aviso = re.search(r'class="validacion"[^>]*>(.*?)</span>', pagina,
                          re.S)
        if aviso:
            texto = html.unescape(re.sub(r"<[^>]+>", " ", aviso.group(1)))
            texto = " ".join(texto.split())
            estado = ("codigo_incorrecto" if "seguridad" in texto.lower()
                      else "error")
            return {"estado": estado, "texto": texto, "pagina": None}
        return {"estado": "respuesta", "texto": _texto_de_pagina(pagina),
                "pagina": _guardar_pagina(pagina, pdf.stem)}

    def justificante(self, pdf: Path) -> Path:
        """Descarga el justificante de la validación que acaba de hacer
        VALIDe en esta sesión y lo guarda junto al documento.

        Es un PDF que genera VALIDe con el documento y una banda lateral con
        el firmante y el resultado. Lo emite VALIDe, no esta aplicación.

        Args:
            pdf: documento que se envió.

        Returns:
            Ruta del justificante («…_justificante_valide.pdf»).
        """
        r = self.http.post(VALIDE_JUSTIFICANTE, timeout=120)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF"):
            raise ValueError("VALIDe no devolvió un PDF: valida primero el "
                             "documento en esta misma sesión")
        destino = pdf.with_name(pdf.stem + "_justificante_valide.pdf")
        destino.write_bytes(r.content)
        return destino


def _texto_de_pagina(pagina: str) -> str:
    """Extrae el texto del cuerpo de una página de VALIDe, por líneas."""
    m = re.search(r'<div id="cuerpo">(.*?)<div id="contenidoBottom">',
                  pagina, re.S)
    t = m.group(1) if m else pagina
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"<(script|style)\b.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"</t[dh]>", " | ", t, flags=re.I)
    t = re.sub(r"<br\s*/?>|</(p|div|tr|li|h\d|table|fieldset)>", "\n", t,
               flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    lineas = (" ".join(x.split()).strip(" |") for x in t.splitlines())
    return "\n".join(x for x in lineas if x)


def _guardar_pagina(pagina: str, nombre: str) -> Path:
    """Guarda la respuesta de VALIDe para verla en el navegador.

    Va a la carpeta temporal del usuario (en memoria y privada cuando existe
    XDG_RUNTIME_DIR), con una base para que carguen sus estilos.
    """
    carpeta = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    destino = carpeta / f"valide-{nombre}.html"
    pagina = re.sub(r"<head>", '<head><base href="https://valide.redsara.es/">',
                    pagina, count=1, flags=re.I)
    destino.write_text(pagina, encoding="utf-8")
    destino.chmod(0o600)
    return destino


def abrir(destino: str | Path) -> None:
    """Abre un fichero o una dirección con la aplicación del sistema."""
    destino = str(destino)
    if sys.platform.startswith("win"):
        os.startfile(destino)  # noqa: S606
    else:
        orden = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([orden, destino], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)


def abrir_valide() -> None:
    """Abre el formulario de VALIDe en el navegador."""
    abrir(VALIDE)


_REGISTRO_UE: dict = {}
# con alguna lista nacional sin cargar, el registro se reutiliza poco tiempo
CADUCIDAD_INCOMPLETO = dt.timedelta(minutes=10)


class ErrorListasUE(RuntimeError):
    """Las listas de confianza de la UE no se pudieron cargar."""


def registro_ue() -> dict:
    """Carga las listas de confianza de la UE en un registro de pyHanko.

    Descarga la lista de listas (LOTL) y las nacionales, o las lee de
    LISTAS_UE si se descargaron hace menos de un día, y comprueba la firma
    de cada una: la de la LOTL con los certificados de la Comisión que trae
    pyHanko, y si la Comisión los ha cambiado, partiendo del anclaje
    publicado en el Diario Oficial. Dentro de un mismo proceso el registro
    se reutiliza un día, o diez minutos si falta alguna lista. Una copia
    guardada ilegible se borra y se descarga de nuevo.

    Returns:
        El registro («registro»), la fecha de emisión de la LOTL
        («emitida»), las listas nacionales a las que apunta
        («referenciadas»), las cargadas («cargadas»), los territorios
        cuya lista no se pudo descargar o comprobar («faltan») y el número
        de entradas de servicio que pyHanko no interpreta («omitidas»).

    Raises:
        ErrorListasUE: sin red y sin copia vigente, o si la LOTL no se
            puede comprobar.
    """
    import asyncio
    import json
    import shutil

    import aiohttp
    from pyhanko.sign.validation.qualified import eutl_fetch, eutl_parse

    ahora = dt.datetime.now(dt.timezone.utc)
    if _REGISTRO_UE and ahora < _REGISTRO_UE["caduca"]:
        return _REGISTRO_UE["datos"]

    async def cargar():
        cache = eutl_fetch.FileSystemTLCache(LISTAS_UE, CADUCIDAD_LISTAS)
        tiempo = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=tiempo) as cliente:
            lotl = await eutl_fetch.fetch_lotl(cliente, cache)
            try:
                eutl_parse.validate_and_parse_lotl(lotl)
                firmantes = None
            except Exception:
                # la Comisión ha cambiado los firmantes de la LOTL: se
                # recorren sus LOTL pivote desde el anclaje del Diario
                firmantes = await eutl_fetch.bootstrap_lotl_signers(
                    lotl, cliente, cache=cache)
            registro, errores = await eutl_fetch.lotl_to_registry(
                lotl, cliente, lotl_tlso_certs=firmantes, cache=cache)
        info = eutl_parse.parse_lotl_unsafe(lotl)
        referenciadas = sum(eutl_parse.LOTL_RULE not in r.scheme_rules
                            for r in info.references)
        # los fallos de una lista entera se separan de los de un servicio
        faltan = []
        for e in errores:
            m = re.match(r"Failed to (download|parse) trusted list for "
                         r"(\S+) ", str(e))
            if m:
                faltan.append(m.group(2))
        return {"registro": registro, "emitida": info.claimed_date_issued,
                "referenciadas": referenciadas,
                "cargadas": referenciadas - len(faltan),
                "faltan": sorted(faltan),
                "omitidas": len(errores) - len(faltan)}

    # pyHanko avisa de cada servicio que no interpreta: van en el recuento
    for nombre in ("pyhanko", "pyhanko_certvalidator", "asyncio"):
        logging.getLogger(nombre).setLevel(logging.CRITICAL)
    borrada = False
    try:
        try:
            datos = asyncio.run(cargar())
        except (json.JSONDecodeError, KeyError, TypeError):
            # índice de la copia guardada ilegible: se descarga de nuevo
            shutil.rmtree(LISTAS_UE, ignore_errors=True)
            borrada = True
            datos = asyncio.run(cargar())
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        raise ErrorListasUE(
            "no se pudieron descargar las listas de confianza de la UE "
            f"({type(e).__name__}: {e}). "
            + ("La copia guardada estaba dañada y se ha borrado: hace falta "
               "red para descargarla de nuevo" if borrada else
               "Sin red, la copia guardada solo sirve durante un día desde "
               "su descarga")) from e
    except Exception as e:
        raise ErrorListasUE(
            "no se pudo comprobar la lista de listas de la UE "
            f"({type(e).__name__}: {e})") from e
    _REGISTRO_UE.update(datos=datos, caduca=ahora + (
        CADUCIDAD_INCOMPLETO if datos["faltan"] else CADUCIDAD_LISTAS))
    return datos


# motivo, en palabras, de cada subindicación de AdES que da pyHanko cuando
# un certificado encadena pero no se puede dar por bueno
MOTIVOS_UE = {
    "REVOKED_NO_POE": "certificado revocado",
    "REVOKED_CA_NO_POE": "una autoridad de la cadena está revocada",
    "OUT_OF_BOUNDS_NO_POE": (
        "certificado caducado o fuera de su vigencia en la hora actual "
        "(pyHanko no lo valida en la hora del sello)"),
    "OUT_OF_BOUNDS_NOT_REVOKED": (
        "certificado caducado en la hora actual, sin revocar"),
    "EXPIRED": "certificado caducado",
    "NOT_YET_VALID": "certificado aún no vigente",
    "TRY_LATER": "no se pudo consultar la revocación",
    "REVOCATION_OUT_OF_BOUNDS_NO_POE": (
        "la información de revocación no cubre la hora de la validación"),
    "CERTIFICATE_CHAIN_GENERAL_FAILURE": (
        "fallo de la cadena o de la consulta de revocación"),
    "CHAIN_CONSTRAINTS_FAILURE": "la cadena no cumple sus restricciones",
    "SIG_CONSTRAINTS_FAILURE": (
        "el certificado no tiene el uso de clave que se pide"),
    "CRYPTO_CONSTRAINTS_FAILURE": "algoritmo no admitido",
    "CRYPTO_CONSTRAINTS_FAILURE_NO_POE": "algoritmo no admitido hoy",
}


def _confianza_ue(estado) -> str:
    """Si el certificado de una firma o de un sello es de confianza en las
    listas de la UE y, si no lo es, por qué: documento alterado, firma
    criptográfica no válida, sin cadena hasta un servicio de las listas, o
    una cadena que existe pero no se da por buena (revocación, caducidad,
    consulta de revocación fallida)."""
    if not estado.intact:
        return "no evaluado: el contenido cambió después de firmar"
    if not estado.valid:
        return "no evaluado: la firma criptográfica no es válida"
    if estado.trusted:
        return "de confianza"
    nombre = getattr(estado.trust_problem_indic, "name", "")
    motivo = MOTIVOS_UE.get(nombre, nombre or "motivo no indicado")
    if estado.validation_path is not None:
        return "encadena, pero no es de confianza: " + motivo
    if nombre in ("", "NO_CERTIFICATE_CHAIN_FOUND"):
        return "NO encadena con un servicio de las listas"
    # pyHanko se detiene antes de buscar la cadena (un algoritmo que no
    # admite, por ejemplo)
    return "cadena no evaluada: " + motivo


def _nivel_ue(cualificacion) -> str:
    """Nivel que corresponde al certificado de la firma según su
    cualificación, con los nombres del Reglamento eIDAS."""
    if cualificacion is None:
        return "no determinado (el certificado no encadena con la UE)"
    st = cualificacion.status
    if st.qualified and st.qc_type.name == "QC_WEB":
        return "certificado cualificado de sitio web: no es de firma"
    sello = st.qualified and st.qc_type.name == "QC_ESEAL"
    if not st.qualified:
        return "firma electrónica avanzada (certificado no cualificado)"
    if st.qc_key_security.is_qscd:
        return ("sello electrónico cualificado" if sello
                else "firma electrónica cualificada")
    return ("sello electrónico avanzado basado en certificado cualificado"
            if sello else
            "firma electrónica avanzada basada en certificado cualificado")


def _sello_ue(registro, estado) -> str:
    """Confianza y cualificación de un sello de tiempo.

    Es cualificado si alguna autoridad de su ruta es un servicio de sellado
    cualificado (QTST) concedido en la hora del sello. pyHanko solo guarda
    el estado vigente de cada servicio (la historia de las listas no lleva
    el certificado): si el servicio está concedido hoy pero el periodo
    vigente empezó después del sello, la cualificación en su hora no se
    puede determinar, y se dice así.
    """
    from pyhanko.sign.validation.qualified.tsp import QTST_URI

    if not estado.trusted:
        texto = _confianza_ue(estado)
        if texto.startswith("NO encadena"):
            texto += ("; pyHanko no tiene como ancla los servicios de "
                      "sellado retirados de las listas: el sello de uno de "
                      "ellos se valida en DSS o en VALIDe")
        return texto
    ruta = estado.validation_path
    for sd in registro.applicable_tsps_on_path(ruta, estado.timestamp):
        if sd.base_info.service_type == QTST_URI:
            return f"de confianza, cualificado ({sd.base_info.service_name})"
    for sd in registro.applicable_tsps_on_path(ruta, None):
        if sd.base_info.service_type == QTST_URI:
            desde = sd.base_info.valid_from.astimezone(ZONA)
            return ("de confianza; cualificación en la hora del sello no "
                    "determinable (la lista da el servicio concedido desde "
                    f"el {desde:%d/%m/%Y})")
    return "de confianza, no cualificado"


def validar_ue(pdf: Path, revocacion: str) -> bool:
    """Valida las firmas de un PDF en local contra las listas de confianza
    de la UE, las mismas que usa DSS, el validador de la Comisión Europea,
    sin enviar el documento.

    Con pyHanko: las anclas son los servicios cualificados de las listas de
    la UE (registro_ue), la revocación se consulta en el momento, y para
    cada firma se dice si su certificado es cualificado y si la clave está
    en un dispositivo cualificado (QSCD), y para cada sello si lo emite un
    servicio de sellado cualificado. La validación es en la hora actual:
    pyHanko no valida en el pasado sin datos de revocación incrustados.

    Args:
        pdf: documento firmado.
        revocacion: «hard-fail» exige consultar la revocación;
            «soft-fail» la consulta si puede.

    Returns:
        True si todas las firmas son válidas y de confianza.

    Raises:
        ErrorListasUE: si las listas no se pudieron cargar.
    """
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import (validate_pdf_signature,
                                         validate_pdf_timestamp)
    from pyhanko.sign.validation.qualified.assess import (
        QualificationAssessor)
    from pyhanko.sign.validation.qualified.tsp import TSPTrustManager
    from pyhanko_certvalidator import ValidationContext

    class GestorSellos(TSPTrustManager):
        """Acepta también como emisor de la unidad de sellado la identidad
        de un servicio QTST: varias listas, la española entre ellas, dan
        la autoridad que emite la unidad y no la unidad (ETSI TS 119 612,
        5.5.3)."""

        def find_potential_issuers(self, cert):
            yield from super().find_potential_issuers(cert)
            for autoridad in self.tsp_registry.known_timestamp_authorities:
                ancla = self.as_trust_anchor(autoridad)
                if ancla and autoridad.is_potential_issuer_of(cert):
                    yield ancla

    ue = registro_ue()
    registro = ue["registro"]
    faltan = (f" (sin cargar: {', '.join(ue['faltan'])})"
              if ue["faltan"] else "")
    print(f"listas de confianza de la UE: lista de listas del "
          f"{ue['emitida'].astimezone(ZONA):%d/%m/%Y}; {ue['cargadas']} de "
          f"{ue['referenciadas']} listas nacionales cargadas, con su firma "
          f"comprobada{faltan}; {ue['omitidas']} entradas de servicio que "
          "pyHanko no interpreta, omitidas")
    evaluador = QualificationAssessor(registro)
    contexto = ValidationContext(
        trust_manager=TSPTrustManager(registro), allow_fetching=True,
        revocation_mode=revocacion)
    contexto_ts = ValidationContext(
        trust_manager=GestorSellos(registro), allow_fetching=True,
        revocation_mode="soft-fail")
    with pdf.open("rb") as fh:
        firmas = PdfFileReader(fh).embedded_signatures
        if not firmas:
            if b"/adbe.pkcs7.sha1" in pdf.read_bytes():
                print("lleva una firma en formato antiguo (adbe.pkcs7.sha1, "
                      "con SHA-1), que esta validación no admite: se puede "
                      "validar en VALIDe (valide.redsara.es)")
            else:
                print("el documento no lleva ninguna firma")
            return False
        todo_bien = True
        for n, firma in enumerate(firmas, start=1):
            if firma.sig_object_type == "/DocTimeStamp":
                est = validate_pdf_timestamp(firma,
                                             validation_context=contexto_ts)
                filas = [
                    ("hora", est.timestamp.astimezone(ZONA).strftime(
                        "%d/%m/%Y %H:%M:%S")),
                    ("emitido por", est.signing_cert.subject.native.get(
                        "common_name", "?")),
                    ("intacto", "sí" if est.intact else "NO"),
                    ("válido", "sí" if est.valid else "NO"),
                    ("listas de la UE", _sello_ue(registro, est)),
                ]
                print(f"sello de documento {n} ({firma.field_name})")
                for k, v in filas:
                    print(f"  {k:<22}{v}")
                todo_bien &= bool(est.intact and est.valid and est.trusted)
                continue
            est = validate_pdf_signature(firma, contexto,
                                         ts_validation_context=contexto_ts)
            sujeto = est.signing_cert.subject.native
            nombre = " ".join(
                x for x in (sujeto.get("given_name"), sujeto.get("surname"))
                if x
            ) or sujeto.get("common_name", "?").split(" - ")[0]
            # la cualificación se evalúa con la cadena, aunque no se dé por
            # buena: la fila de las listas dice por qué
            ruta = est.validation_path
            sin_cadena = getattr(est.trust_problem_indic, "name", "") in (
                "", "NO_CERTIFICATE_CHAIN_FOUND")
            try:
                cualificacion = (evaluador.check_entity_cert_qualified(ruta)
                                 if ruta else None)
                nivel = (_nivel_ue(cualificacion)
                         if ruta or (est.intact and est.valid and sin_cadena)
                         else "no evaluado")
            except (NotImplementedError, ValueError) as e:
                cualificacion = None
                nivel = f"no determinado (pyHanko: {e})"
            sello = est.timestamp_validity
            filas = [
                ("firmante", nombre.title()),
                ("emisor", est.signing_cert.issuer.native.get(
                    "common_name", "?")),
                ("documento intacto", "sí" if est.intact else "NO"),
                ("firma criptográfica", "válida" if est.valid else "NO"),
                ("listas de la UE", _confianza_ue(est)),
                ("revocado", "sí" if est.revoked else
                 "no" if est.trusted else "no comprobado"),
                ("nivel", nivel),
            ]
            if cualificacion and cualificacion.service_definition:
                filas.append(("servicio", cualificacion.service_definition
                              .base_info.service_name))
            if sello:
                filas.append(("sello de tiempo", (
                    "válido, " if sello.valid and sello.intact
                    else "NO válido, ") + _sello_ue(registro, sello)))
            filas += [
                ("cubre", "el fichero entero" if est.coverage.name ==
                 "ENTIRE_FILE" else "su revisión; hay revisiones detrás"),
                ("cambios posteriores", _cambios(est)),
            ]
            print(f"firma {n} ({firma.field_name})")
            for k, v in filas:
                print(f"  {k:<22}{v}")
            todo_bien &= est.bottom_line
    print("resultado:", "VÁLIDO" if todo_bien else "NO VÁLIDO")
    return todo_bien


def valide_terminal(pdf: Path, justificante: bool = False) -> bool:
    """Envía a VALIDe desde la terminal, enseñando el código en un visor.

    Args:
        pdf: documento firmado.
        justificante: si se descarga después el justificante de VALIDe.

    Returns:
        True si VALIDe respondió (su veredicto va en el texto).
    """
    print("el documento se envía a la plataforma @firma (VALIDe)")
    sesion = SesionValide()
    for _ in range(3):
        img = Path(os.environ.get("XDG_RUNTIME_DIR")
                   or tempfile.gettempdir()) / "valide-codigo.jpg"
        img.write_bytes(sesion.captcha())
        abrir(img)
        codigo = input("código de seguridad que ves en la imagen: ")
        r = sesion.enviar(pdf, codigo)
        img.unlink(missing_ok=True)
        if r["estado"] != "codigo_incorrecto":
            break
        print("código incorrecto; otra imagen")
    print(r["texto"])
    if r["pagina"]:
        print(f"página completa: {r['pagina']}")
    if justificante and r["estado"] == "respuesta":
        try:
            print(f"justificante de VALIDe: {sesion.justificante(pdf)}")
        except Exception as e:  # el veredicto ya está impreso
            print(f"no se pudo descargar el justificante: {e}")
    return r["estado"] == "respuesta"


def main() -> None:
    """Punto de entrada de la línea de órdenes."""
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog=f"Licencia {LICENCIA}; prueba de concepto, sin garantía. "
               "Condiciones de uso: firmar.py --condiciones")
    ap.add_argument("entrada", type=Path, nargs="*",
                    help="uno o varios PDF; con varios, se firman por "
                         "separado o, con --unir, unidos en uno")
    ap.add_argument("--unir", action="store_true",
                    help="con varios PDF, los une en uno (con -o, su "
                         "nombre) y lo firma una vez")
    ap.add_argument("--listar", action="store_true",
                    help="enumera los certificados instalados")
    ap.add_argument("--condiciones", action="store_true",
                    help="muestra las condiciones de uso y la licencia")
    ap.add_argument("--instalado", type=int,
                    help="firma con el certificado N de --listar")
    ap.add_argument("-o", "--salida", type=Path)
    ap.add_argument("--p12", type=Path)
    ap.add_argument("--solo-pie", action="store_true",
                    help="pone el pie sin firmar")
    ap.add_argument("--nombre", help="firmante, con --solo-pie")
    ap.add_argument("--emisor", default="la FNMT-RCM",
                    help="emisor del certificado, con --solo-pie")
    ap.add_argument("--motivo", default="")
    ap.add_argument("--lugar", default="")
    ap.add_argument("--referencia", default="",
                    help="referencia libre: propuesta, expediente, contrato")
    ap.add_argument("--justificante", action="store_true",
                    help="con --valide, descarga el justificante de VALIDe")
    ap.add_argument("--sin-reducir", action="store_true")
    ap.add_argument("--comprobar", action="store_true",
                    help="valida un PDF ya firmado")
    ap.add_argument("--valide", action="store_true",
                    help="envía el PDF a VALIDe (el código lo escribes tú)")
    ap.add_argument("--ue", action="store_true",
                    help="valida en local contra las listas de confianza "
                         "de la UE, con la cualificación del certificado "
                         "(se descargan las listas, no el documento)")
    ap.add_argument("--valide-web", action="store_true",
                    help="abre el formulario de VALIDe en el navegador")
    ap.add_argument("--revocacion", default="hard-fail",
                    choices=["hard-fail", "soft-fail"])
    a = ap.parse_args()
    if a.condiciones:
        print(texto_condiciones())
        return
    if a.listar:
        for n, c in enumerate(almacenes.listar(), start=1):
            print(f"{n}. {c['nombre']} · {c['emisor']} · caduca "
                  f"{c['caduca']:%d/%m/%Y} · {c['almacen']}")
        return
    if not a.entrada:
        ap.error("falta el documento")
    entradas = a.entrada
    a.entrada = entradas[0]
    if len(entradas) > 1 and (a.comprobar or a.valide or a.valide_web
                              or a.ue or a.solo_pie):
        ap.error("con varios documentos solo se puede firmar")
    if len(entradas) > 1 and a.salida and not a.unir:
        ap.error("-o con varios documentos solo vale con --unir")
    if a.comprobar or a.valide or a.valide_web or a.ue:
        ok = comprobar(a.entrada, a.revocacion) if a.comprobar else True
        if a.ue:
            try:
                ok = validar_ue(a.entrada, a.revocacion) and ok
            except ErrorListasUE as e:
                print(f"error: {e}", file=sys.stderr)
                ok = False
        if a.valide:
            ok = valide_terminal(a.entrada, a.justificante) and ok
        if a.valide_web:
            print(f"VALIDe: sube {a.entrada.resolve()}")
            abrir_valide()
        sys.exit(0 if ok else 1)
    sufijo = "_pie.pdf" if a.solo_pie else "_firmado.pdf"
    salida = a.salida or a.entrada.with_name(a.entrada.stem + sufijo)

    if a.solo_pie:
        if not a.nombre:
            sys.exit("con --solo-pie hace falta --nombre")
        r = poner_pie(a.entrada, salida, a.nombre, a.emisor,
                      not a.sin_reducir, a.motivo, a.lugar, a.referencia)
        print(f"pie puesto: {salida}  (id {r['id']})")
        print(f"recuadro de la última página, en puntos: {r['caja']}")
        return
    clave = os.environ.get("FIRMA_P12_CLAVE")
    if a.instalado:
        c = almacenes.listar()[a.instalado - 1]
        if clave is None and c["pide_clave"]:
            clave = getpass.getpass("Contraseña principal del navegador "
                                    "(Intro si no tiene): ")
        p12, clave_b = almacenes.exportar(c, clave or "")
    elif a.p12:
        clave = clave or getpass.getpass("Contraseña del certificado: ")
        p12, clave_b = a.p12, clave.encode()
    else:
        sys.exit("falta --p12 o --instalado (o --solo-pie)")
    if len(entradas) > 1:
        filas = firmar_varios(
            entradas, p12, clave_b, a.motivo, a.lugar, not a.sin_reducir,
            a.referencia, a.unir, a.salida)
        sys.exit(0 if all(x["resultado"] == "firmado" for x in filas)
                 else 1)
    if ya_firmado(a.entrada):
        # llega firmado: se añade la firma con su recuadro, sin tocar nada
        r = cofirmar(a.entrada, salida, p12, clave_b, a.motivo, a.lugar)
        quien = (", ".join(x["nombre"] for x in r["previas"]
                           if x["tipo"] == "firma")
                 or "ninguna legible")
        print(f"firma añadida: {salida} (recuadro en la página "
              f"{r['pagina']}; firmas previas: {quien})")
        return
    r = firmar_documento(a.entrada, salida, p12, clave_b, a.motivo,
                         a.lugar, not a.sin_reducir, a.referencia)
    print(f"firmado: {salida}  (id {r['id']}, {r['paginas']} páginas)")


if __name__ == "__main__":
    main()
