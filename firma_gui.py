"""Aplicación de escritorio para firmar PDF con el certificado de la FNMT.

Usa las funciones de firmar.py: elegir el certificado (uno de los instalados
en Firefox o Chrome, o un fichero .p12 o .pfx) y el documento, firmar con el
pie en todas las páginas, comprobar la firma y validarla en local contra
las listas de confianza de la UE. La contraseña
no se guarda nunca; se recuerdan el último certificado, la última carpeta y
las opciones.

Las condiciones de uso (firmar.CONDICIONES) tienen su pestaña, y la primera
vez que se abre la ventana con cada versión del texto se pide aceptarlas.

Uso:
    firma_gui.py [documento.pdf]
    firma_gui.py --comprobar documento_firmado.pdf
    firma_gui.py --ue documento_firmado.pdf
    firma_gui.py --condiciones
"""
import contextlib
import html
import io
import re
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices, QFontDatabase, QIcon,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox,
    QRadioButton, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import almacenes  # noqa: E402
import firmar as f  # noqa: E402

TITULO = "Firma de documentos - ManPla.net"
ICONO = f.RECURSOS / "recursos" / "icono.png"
# carpeta donde se buscan ficheros .p12 o .pfx
CARPETAS_CERTS = [f.CARPETA_CERTS]
# clave de los ajustes con la versión de las condiciones ya aceptada
CLAVE_CONDICIONES = "condiciones_aceptadas"
# márgenes de los títulos y párrafos de las condiciones de uso
MARGENES_CONDICIONES = "margin-top:6px; margin-bottom:6px"


def _formulario(caja: QWidget) -> QFormLayout:
    """Formulario cuyos campos se estiran al ancho de la ventana.

    En macOS, Qt deja por defecto los campos a su tamaño mínimo y las rutas
    y la contraseña salen cortadas.
    """
    fl = QFormLayout(caja)
    fl.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return fl


def _sin_permiso(e: PermissionError, salida: Path) -> str:
    """Explica un error de permisos al escribir el firmado."""
    carpeta = salida.parent
    if sys.platform == "darwin":
        return (f"error al firmar: macOS no deja escribir en {carpeta}. Elige "
                "dónde guardar el firmado con «Cambiar…», o da acceso a "
                "FirmaManPla en Ajustes del Sistema › Privacidad y seguridad "
                "› Archivos y carpetas.")
    return (f"error al firmar: no hay permiso para escribir en {carpeta} "
            f"({e.strerror}). Elige otra carpeta con «Cambiar…».")


def _html_condiciones() -> str:
    """Las condiciones de uso en HTML, con sus direcciones como enlaces.

    Los márgenes de títulos y párrafos se dejan en 6 px (Qt pone 12 por
    defecto en los párrafos), para que el texto quepa en la pestaña a
    720 × 700 con el menor desplazamiento.

    Returns:
        Un título por apartado de firmar.CONDICIONES y sus párrafos.
    """
    partes = []
    for n, (titulo, parrafos) in enumerate(f.CONDICIONES, start=1):
        partes.append(f'<h3 style="{MARGENES_CONDICIONES}">{n}. '
                      f"{html.escape(titulo)}</h3>")
        for parrafo in parrafos:
            # la dirección acaba antes del paréntesis o del punto final
            texto = re.sub(r"https://[^\s)]+[^\s).,]",
                           lambda m: f'<a href="{m[0]}">{m[0]}</a>',
                           html.escape(parrafo))
            partes.append(f'<p style="{MARGENES_CONDICIONES}">{texto}</p>')
    return "".join(partes)


def _visor_condiciones() -> QTextBrowser:
    """Visor de las condiciones; sus enlaces se abren en el navegador."""
    visor = QTextBrowser()
    visor.setOpenExternalLinks(True)
    visor.setHtml(_html_condiciones())
    return visor


def _pie_condiciones() -> QLabel:
    """Versión de la aplicación y de las condiciones, licencia y contacto.

    Junto al aviso de derechos del autor va el de Qt y PySide6, con un
    enlace a la carpeta de los textos de la LGPL-3.0 y la GPL-3.0 que
    acompañan a la aplicación (LGPL-3.0, sección 4, letra c).
    """
    textos = QUrl.fromLocalFile(str(f.LICENCIAS_TERCEROS)).toString()
    pie = QLabel(
        f"FirmaManPla {f.VERSION} · condiciones de uso del "
        f"{f.VERSION_CONDICIONES} · © Manuel Muñoz Plá · "
        f'<a href="{f.LICENCIA_URL}">licencia {f.LICENCIA}</a> · '
        f'<a href="{f.CONTACTO}">contacto para una versión comercial</a> · '
        "Qt y PySide6 © The Qt Company Ltd. y otros, con licencia LGPL-3.0 "
        f'(<a href="{textos}">textos de la LGPL-3.0 y la GPL-3.0</a>)')
    pie.setWordWrap(True)
    pie.setOpenExternalLinks(True)
    return pie


class Avisador(QObject):
    """Lleva al hilo de la interfaz el resultado de una tarea."""

    hecho = Signal(str, bool, object)
    linea = Signal(str)


class Ventana(QWidget):
    """Ventana principal."""

    def __init__(self, documento: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle(TITULO)
        self.setWindowIcon(QIcon(str(ICONO)))
        self.setAcceptDrops(True)
        self.ajustes = QSettings("ManPla", "firma-pdf")
        # se retira el ajuste del sello de tiempo, sin uso
        self.ajustes.remove("con_tsa")
        self.avisador = Avisador()
        self.avisador.hecho.connect(self._fin_tarea)
        self.avisador.linea.connect(self._escribir)
        # con varios documentos elegidos, sus rutas; vacío con uno solo
        self.docs: list[str] = []
        self._poniendo = False
        self.datos_cert = None
        self._construir()
        # sin las condiciones de uso aceptadas, la ventana abre en su
        # pestaña y la de firma queda desactivada; los certificados no se
        # leen hasta aceptarlas
        self._documento_inicial = documento
        if (hasattr(self, "barra_condiciones")
                and self.ajustes.value(CLAVE_CONDICIONES, "")
                != f.VERSION_CONDICIONES):
            self._pedir_condiciones()
        else:
            self._preparar_firma()

    def _preparar_firma(self) -> None:
        """Carga los certificados y el documento con que se abrió."""
        self._cargar_certificados()
        if self._documento_inicial:
            self._poner_documento(self._documento_inicial)

    def condiciones_pendientes(self) -> bool:
        """Si la ventana espera todavía la aceptación de las condiciones."""
        barra = getattr(self, "barra_condiciones", None)
        return barra is not None and not barra.isHidden()

    def _pedir_condiciones(self) -> None:
        """Abre la ventana en las condiciones de uso, con la pestaña de
        firma desactivada hasta aceptarlas."""
        self.barra_condiciones.show()
        self.pestanas.setTabEnabled(0, False)
        self.pestanas.setCurrentIndex(1)
        self.b_aceptar.setFocus()

    def _aceptar_condiciones(self) -> None:
        """Anota la versión aceptada y abre la pestaña de firma."""
        self.ajustes.setValue(CLAVE_CONDICIONES, f.VERSION_CONDICIONES)
        self.barra_condiciones.hide()
        self.pestanas.setTabEnabled(0, True)
        self.pestanas.setCurrentIndex(0)
        self._preparar_firma()
        self.combo_cert.setFocus()

    # construcción ---------------------------------------------------------

    def _construir(self) -> None:
        """Monta las dos pestañas: la de firma, con sus tres bloques, los
        botones y el registro, y la de las condiciones de uso."""
        exterior = QVBoxLayout(self)
        self.pestanas = QTabWidget()
        exterior.addWidget(self.pestanas)
        pagina = self.pagina_firma = QWidget()
        self.pestanas.addTab(pagina, "Firmar")
        self.pestanas.addTab(self._pestana_condiciones(),
                             "Condiciones de uso")
        raiz = QVBoxLayout(pagina)

        raiz.addWidget(self._bloque_certificado())

        # documento
        caja_d = QGroupBox("2. Documentos (uno o varios PDF, también "
                           "arrastrándolos a la ventana)")
        fd = _formulario(caja_d)
        fila = QHBoxLayout()
        self.doc = QLineEdit()
        self.doc.textChanged.connect(self._doc_cambiado)
        b_doc = QPushButton("Elegir…")
        b_doc.setToolTip("Elige un PDF, o varios con Ctrl o Mayús: varios se "
                         "firman por separado o unidos en un solo PDF")
        b_doc.clicked.connect(self._elegir_doc)
        fila.addWidget(self.doc, 1)
        fila.addWidget(b_doc)
        fd.addRow("PDF (uno o varios)", fila)
        # con varios documentos: unirlos en uno o firmarlos por separado
        self.fila_modo = QWidget()
        fm = QHBoxLayout(self.fila_modo)
        fm.setContentsMargins(0, 0, 0, 0)
        self.separado = QRadioButton("Firmar cada uno por separado")
        self.unir = QRadioButton("Unir en un solo PDF y firmarlo una vez")
        self.separado.setChecked(True)
        grupo = QButtonGroup(self.fila_modo)
        for b in (self.separado, self.unir):
            grupo.addButton(b)
            fm.addWidget(b)
            b.toggled.connect(self._modo_cambiado)
        fm.addStretch(1)
        fd.addRow("Varios", self.fila_modo)
        self.fila_modo.setVisible(False)
        fd.labelForField(self.fila_modo).setVisible(False)
        fila = QHBoxLayout()
        self.salida = QLineEdit()
        b_sal = QPushButton("Cambiar…")
        b_sal.clicked.connect(self._elegir_salida)
        fila.addWidget(self.salida, 1)
        fila.addWidget(b_sal)
        fd.addRow("Firmado", fila)
        raiz.addWidget(caja_d)

        # opciones
        caja_o = QGroupBox("3. Opciones")
        fo = _formulario(caja_o)
        # opcionales: vacíos, enseñan una sugerencia en gris que no se usa
        # como valor; sin dato, la celda del pie va vacía
        self.motivo = QLineEdit(self.ajustes.value("motivo", ""))
        self.motivo.setPlaceholderText(
            "opcional: conformidad con la propuesta, aprobación del informe")
        self.lugar = QLineEdit(self.ajustes.value("lugar", ""))
        self.lugar.setPlaceholderText("opcional: ciudad y país")
        fo.addRow("Motivo", self.motivo)
        fo.addRow("Lugar", self.lugar)
        # la referencia es de cada documento: no se recuerda
        self.referencia = QLineEdit()
        self.referencia.setPlaceholderText(
            "opcional: propuesta, expediente, contrato")
        fo.addRow("Referencia", self.referencia)
        self.reducir = QCheckBox(
            "Reducir el contenido para dejar sitio al pie")
        self.reducir.setChecked(
            self.ajustes.value("reducir", "true") == "true")
        fo.addRow("", self.reducir)
        raiz.addWidget(caja_o)

        # botones
        fila = QHBoxLayout()
        self.b_firmar = QPushButton("Firmar")
        self.b_firmar.setDefault(True)
        self.b_firmar.clicked.connect(self._firmar)
        self.b_comprobar = QPushButton("Comprobar firma")
        self.b_comprobar.clicked.connect(self._comprobar)
        self.b_ue = QPushButton("Validar con las listas de la UE")
        self.b_ue.setToolTip(
            "Valida el firmado en este equipo, con pyHanko y en la hora "
            "actual, contra las listas de confianza de la UE que usa DSS, "
            "el validador de la Comisión Europea: nivel de la firma y "
            "cualificación del certificado y de los sellos. Se descargan "
            "las listas y la revocación; el documento no sale del equipo")
        self.b_ue.clicked.connect(self._ue)
        b_ver = QPushButton("Abrir firmado")
        b_ver.clicked.connect(self._abrir_firmados)
        for b in (self.b_firmar, self.b_comprobar, self.b_ue, b_ver):
            fila.addWidget(b)
        raiz.addLayout(fila)

        # registro de lo hecho
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        # con las pestañas, la ventana conserva su alto de antes
        self.log.setMinimumHeight(140)
        raiz.addWidget(self.log, 1)
        self.resize(720, 700)
        # el foco inicial sigue en el certificado, no en las pestañas
        self.combo_cert.setFocus()

    def _pestana_condiciones(self) -> QWidget:
        """Las condiciones de uso, con la versión, la licencia y el
        contacto, y debajo los botones para aceptarlas, que solo se ven
        mientras no se han aceptado."""
        pagina = QWidget()
        v = QVBoxLayout(pagina)
        v.addWidget(_visor_condiciones(), 1)
        v.addWidget(_pie_condiciones())
        barra = self.barra_condiciones = QWidget()
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(0, 6, 0, 0)
        aviso = QLabel("FirmaManPla se usa con estas condiciones. Al "
                       "aceptarlas se activa la pestaña «Firmar».")
        aviso.setWordWrap(True)
        fila.addWidget(aviso, 1)
        b_salir = QPushButton("Salir")
        b_salir.clicked.connect(QApplication.quit)
        self.b_aceptar = QPushButton("Acepto las condiciones")
        self.b_aceptar.setDefault(True)
        self.b_aceptar.clicked.connect(self._aceptar_condiciones)
        fila.addWidget(b_salir)
        fila.addWidget(self.b_aceptar)
        barra.hide()
        v.addWidget(barra)
        return pagina

    def _bloque_certificado(self) -> QGroupBox:
        """Elección del certificado: instalados, ficheros y contraseña.

        Lo reutiliza la ventana de firma múltiple.
        """
        caja_c = QGroupBox("1. Certificado")
        fc = _formulario(caja_c)
        fila = QHBoxLayout()
        self.combo_cert = QComboBox()
        self.combo_cert.setMinimumWidth(380)
        self.combo_cert.currentIndexChanged.connect(self._cert_cambiado)
        b_recargar = QPushButton("Recargar")
        b_recargar.setToolTip("Vuelve a leer los certificados instalados")
        b_recargar.clicked.connect(self._cargar_certificados)
        b_cert = QPushButton("Fichero…")
        b_cert.setToolTip("Añade un certificado .p12 o .pfx")
        b_cert.clicked.connect(self._elegir_cert)
        fila.addWidget(self.combo_cert, 1)
        fila.addWidget(b_recargar)
        fila.addWidget(b_cert)
        fc.addRow("Certificado", fila)
        fila = QHBoxLayout()
        self.clave = QLineEdit()
        self.clave.setEchoMode(QLineEdit.Password)
        self.clave.returnPressed.connect(self._abrir_cert)
        self.b_abrir = QPushButton("Abrir")
        self.b_abrir.clicked.connect(self._abrir_cert)
        fila.addWidget(self.clave, 1)
        fila.addWidget(self.b_abrir)
        self.rot_clave = QLabel("Contraseña")
        fc.addRow(self.rot_clave, fila)
        self.info_cert = QLabel("Certificado sin abrir")
        self.info_cert.setWordWrap(True)
        fc.addRow("", self.info_cert)
        return caja_c

    # certificado ----------------------------------------------------------

    def _cargar_certificados(self) -> None:
        """Llena la lista: primero los instalados, después los ficheros."""
        elementos = []
        try:
            for c in almacenes.listar():
                c["caduca"] = c["caduca"].astimezone(f.ZONA)
                etiqueta = (f"{c['nombre']} · caduca {c['caduca']:%d/%m/%Y}"
                            f" · {c['almacen']}")
                elementos.append((etiqueta,
                                  dict(c, clave_id="inst:" + c["huella"])))
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            # sin la herramienta del sistema solo quedan los ficheros
            self._escribir(f"no se pudieron leer los certificados "
                           f"instalados ({e}); quedan los ficheros")
        rutas = [str(p) for carpeta in CARPETAS_CERTS if carpeta.is_dir()
                 for p in sorted(carpeta.glob("*"))
                 if p.suffix.lower() in (".p12", ".pfx")]
        for r in self.ajustes.value("certs", []) or []:
            if r not in rutas and Path(r).exists():
                rutas.append(r)
        for r in rutas:
            elementos.append((f"Fichero: {Path(r).name}",
                              {"tipo": "p12", "ruta": r, "clave_id": r}))
        self.combo_cert.blockSignals(True)
        self.combo_cert.clear()
        for etiqueta, dato in elementos:
            self.combo_cert.addItem(etiqueta, dato)
        ultimo = self.ajustes.value("ultimo_cert", "")
        i = next((k for k, (_, d) in enumerate(elementos)
                  if d["clave_id"] == ultimo), 0)
        self.combo_cert.setCurrentIndex(i)
        self.combo_cert.blockSignals(False)
        self._cert_cambiado()

    def _elegir_cert(self) -> None:
        """Añade un certificado desde el diálogo de ficheros."""
        r, _ = QFileDialog.getOpenFileName(
            self, "Certificado", str(Path.home()),
            "Certificados (*.p12 *.pfx)")
        if r:
            self._recordar_cert(r)

    def _recordar_cert(self, ruta: str) -> None:
        """Guarda la ruta entre los certificados recordados y la elige."""
        certs = list(self.ajustes.value("certs", []) or [])
        if ruta not in certs:
            certs.append(ruta)
        self.ajustes.setValue("certs", certs)
        self.ajustes.setValue("ultimo_cert", ruta)
        self._cargar_certificados()

    def _cert_cambiado(self) -> None:
        """Ajusta la contraseña y los datos al certificado elegido.

        De un certificado instalado ya se conoce la parte pública, así que
        sus datos se muestran sin contraseña; la clave se lee al firmar. Un
        fichero, en cambio, va cifrado y hay que abrirlo antes.
        """
        self.datos_cert = None
        self.clave.clear()
        dato = self.combo_cert.currentData()
        if not dato:
            self.info_cert.setText("Sin certificados: añade un fichero")
            return
        self.ajustes.setValue("ultimo_cert", dato["clave_id"])
        if dato["tipo"] != "p12":
            # instalado en el sistema: Windows y macOS piden permiso por su
            # cuenta; en Linux hace falta la contraseña principal
            self.rot_clave.setText(dato["rotulo_clave"])
            self.clave.setPlaceholderText(dato["ayuda_clave"]
                                          + " (no se guarda)")
            self.clave.setEnabled(dato["pide_clave"])
            self.b_abrir.setVisible(False)
            self._mostrar_cert(dato)
        else:
            self.rot_clave.setText("Contraseña")
            self.clave.setPlaceholderText("la del fichero (no se guarda)")
            self.clave.setEnabled(True)
            self.b_abrir.setVisible(True)
            self.info_cert.setText("Fichero sin abrir: escribe su contraseña")

    def _abrir_cert(self) -> None:
        """Abre un fichero de certificado con su contraseña."""
        dato = self.combo_cert.currentData()
        if not dato or dato["tipo"] != "p12":
            return
        try:
            d = f.datos_certificado(Path(dato["ruta"]),
                                    self.clave.text().encode())
        except Exception:
            self.datos_cert = None
            self.info_cert.setText("<b style='color:#b00'>No se pudo abrir: "
                                   "¿contraseña?</b>")
            return
        self._mostrar_cert(d)

    def _mostrar_cert(self, d: dict) -> None:
        """Muestra titular, emisor y caducidad con su color."""
        self.datos_cert = d
        dias = (d["caduca"] - f.dt.datetime.now(f.ZONA)).days
        color = "#b00" if dias < 0 else ("#b60" if dias < 30 else "#070")
        estado = ("caducado" if dias < 0 else f"quedan {dias} días")
        self.info_cert.setText(
            f"<b>{d['nombre']}</b> · emitido por {d['emisor']} · "
            f"<span style='color:{color}'>caduca el "
            f"{d['caduca']:%d/%m/%Y} ({estado})</span>")

    # documento ------------------------------------------------------------

    def _elegir_doc(self) -> None:
        """Elige el PDF que se va a firmar, o varios."""
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Documentos", self.ajustes.value("carpeta",
                                                   str(Path.home())),
            "PDF (*.pdf)")
        if len(rutas) == 1:
            self._poner_documento(rutas[0])
        elif rutas:
            self._poner_documentos(rutas)

    def _poner_documento(self, ruta: str) -> None:
        """Pone el documento y recuerda su carpeta."""
        self.doc.setText(ruta)
        self.ajustes.setValue("carpeta", str(Path(ruta).parent))

    def _poner_documentos(self, rutas: list[str]) -> None:
        """Pone varios documentos, en el orden en que se eligieron."""
        self.docs = list(rutas)
        self._poniendo = True
        nombres = ", ".join(Path(r).name for r in rutas)
        self.doc.setText(f"{len(rutas)} documentos: {nombres}")
        self._poniendo = False
        self.ajustes.setValue("carpeta", str(Path(rutas[0]).parent))
        self._mostrar_modo(True)
        self._modo_cambiado()

    def _mostrar_modo(self, si: bool) -> None:
        self.fila_modo.setVisible(si)
        lay = self.fila_modo.parentWidget().layout()
        etiqueta = lay.labelForField(self.fila_modo) if lay else None
        if etiqueta:
            etiqueta.setVisible(si)

    def _modo_cambiado(self, *_) -> None:
        """Con varios documentos: un solo firmado, o uno junto a cada uno."""
        if not self.docs:
            return
        if self.unir.isChecked():
            p = Path(self.docs[0])
            self.salida.setEnabled(True)
            self.salida.setText(str(p.with_name(p.stem
                                                + "_unido_firmado.pdf")))
        else:
            self.salida.setEnabled(False)
            self.salida.setText("junto a cada original, como "
                                "«<nombre>_firmado.pdf»")

    def _doc_cambiado(self, texto: str) -> None:
        """Propone el nombre del firmado junto al original."""
        if self._poniendo:
            return
        if self.docs:
            # se ha escrito a mano: vuelve a un solo documento
            self.docs = []
            self._mostrar_modo(False)
            self.salida.setEnabled(True)
        p = Path(texto)
        if p.suffix.lower() == ".pdf":
            self.salida.setText(str(p.with_name(p.stem + "_firmado.pdf")))

    def _elegir_salida(self) -> None:
        """Cambia dónde se guarda el firmado."""
        r, _ = QFileDialog.getSaveFileName(
            self, "Guardar firmado como", self.salida.text(), "PDF (*.pdf)")
        if r:
            self.salida.setText(r)

    def dragEnterEvent(self, ev) -> None:  # noqa: N802
        """Acepta PDF y certificados arrastrados."""
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:  # noqa: N802
        """Uno o varios PDF van a los documentos; un .p12 o .pfx, a los
        certificados."""
        # sin las condiciones aceptadas no se carga nada
        if self.condiciones_pendientes():
            return
        pdfs = []
        for url in ev.mimeData().urls():
            r = url.toLocalFile()
            if r.lower().endswith(".pdf"):
                pdfs.append(r)
            elif r.lower().endswith((".p12", ".pfx")):
                self._recordar_cert(r)
        if len(pdfs) == 1:
            self._poner_documento(pdfs[0])
        elif pdfs:
            self._poner_documentos(pdfs)
        # soltados sobre las condiciones de uso, se vuelve a la pestaña de
        # firma (la ventana de firma múltiple no la tiene)
        pagina = getattr(self, "pagina_firma", None)
        if pdfs and pagina is not None:
            self.pestanas.setCurrentWidget(pagina)

    # acciones -------------------------------------------------------------

    def _firmar(self) -> None:
        """Comprueba lo necesario y firma en segundo plano."""
        if not self.datos_cert:
            self._abrir_cert()
            if not self.datos_cert:
                return
        if self.docs:
            return self._firmar_varios()
        entrada, salida = Path(self.doc.text()), Path(self.salida.text())
        if not entrada.is_file():
            return self._aviso("Elige el documento que vas a firmar.")
        if entrada.resolve() == salida.resolve():
            return self._aviso("El firmado no puede sobrescribir el original.")
        if salida.exists() and QMessageBox.question(
                self, "Firma", f"{salida.name} ya existe. ¿Sustituirlo?"
        ) != QMessageBox.Yes:
            return
        # un documento que llega firmado: se añade la firma sin tocar el
        # contenido, con su recuadro en un hueco en blanco
        cofirma = f.ya_firmado(entrada)
        if cofirma:
            try:
                previas = f.firmas_previas(entrada.read_bytes())
            except Exception as e:
                return self._aviso(f"No se pueden leer las firmas de "
                                   f"{entrada.name}: {e}")
            # solo cuentan las firmas, no los sellos de documento
            quien = ", ".join(
                f"{x['nombre']} ({x['fecha']})" if x["fecha"] else x["nombre"]
                for x in previas if x["tipo"] == "firma") or (
                "una firma que no se puede leer")
            if QMessageBox.question(
                    self, "Añadir firma",
                    f"{entrada.name} ya está firmado por: {quien}.\n\n"
                    "Se añadirá tu firma sin modificar el contenido, con su "
                    "recuadro en el campo de firma vacío que traiga el "
                    "documento o, si no trae ninguno, en el hueco en blanco "
                    "más bajo de la última página. El recuadro indicará las "
                    "firmas previas. El pie y la reducción de páginas no se "
                    "aplican.\n\n¿Continuar?"
            ) != QMessageBox.Yes:
                return
        self._guardar_opciones()
        dato = self.combo_cert.currentData()
        clave = self.clave.text()
        opciones = (self.motivo.text(), self.lugar.text(),
                    self.reducir.isChecked(), self.referencia.text().strip())
        self._escribir(f"firmando {entrada.name} como "
                       f"{self.datos_cert['nombre']}…")
        self._en_marcha(True)

        def trabajo():
            try:
                if dato["tipo"] != "p12":
                    # la clave sale del almacén a memoria, nunca a disco
                    p12, cl = almacenes.exportar(dato, clave)
                else:
                    p12, cl = Path(dato["ruta"]), clave.encode()
                if cofirma:
                    r = f.cofirmar(entrada, salida, p12, cl, opciones[0],
                                   opciones[1])
                    msg = (f"firma añadida: {r['salida']}\n  recuadro en la "
                           f"página {r['pagina']}"
                           + (" (en el campo de firma reservado)"
                              if r["campo_reservado"] else "")
                           + ({"compacto": " (recuadro compacto, por falta "
                                           "de sitio)",
                               "minimo": " (recuadro mínimo, por falta de "
                                         "sitio)"}.get(r["recuadro"], ""))
                           + "; firmas previas: "
                           + (", ".join(x["nombre"] for x in r["previas"]
                                        if x["tipo"] == "firma")
                              or "ninguna legible"))
                    self.avisador.hecho.emit(msg, True, r["salida"])
                    return
                r = f.firmar_documento(entrada, salida, p12, cl, *opciones)
                msg = (f"firmado: {r['salida']}\n  id {r['id']}, "
                       f"{r['paginas']} páginas")
                self.avisador.hecho.emit(msg, True, r["salida"])
            except PermissionError as e:
                self.avisador.hecho.emit(_sin_permiso(e, salida), False, None)
            except Exception as e:  # se muestra al usuario
                self.avisador.hecho.emit(f"error al firmar: {e}", False, None)

        threading.Thread(target=trabajo, daemon=True).start()

    def _firmar_varios(self) -> None:
        """Firma varios documentos, unidos o por separado, en segundo
        plano."""
        entradas = [Path(r) for r in self.docs]
        faltan = [e.name for e in entradas if not e.is_file()]
        if faltan:
            return self._aviso("No se encuentran: " + ", ".join(faltan))
        firmados = [e.name for e in entradas if f.ya_firmado(e)]
        unir = self.unir.isChecked()
        salida = Path(self.salida.text()) if unir else None
        if unir:
            if firmados:
                return self._aviso(
                    "No se pueden unir documentos ya firmados, porque su "
                    "firma no pasaría al PDF unido: " + ", ".join(firmados)
                    + ". Fírmalos por separado.")
            if salida.resolve() in [e.resolve() for e in entradas]:
                return self._aviso("El firmado no puede sobrescribir uno de "
                                   "los originales.")
            if salida.exists() and QMessageBox.question(
                    self, "Firma", f"{salida.name} ya existe. ¿Sustituirlo?"
            ) != QMessageBox.Yes:
                return
        else:
            existentes = [e.stem + "_firmado.pdf" for e in entradas
                          if e.with_name(e.stem + "_firmado.pdf").exists()]
            aviso = []
            if firmados:
                aviso.append(f"Ya traen firma, y se les añadirá la tuya con "
                             f"su recuadro: {', '.join(firmados)}.")
            if existentes:
                aviso.append("Se sustituirán: " + ", ".join(existentes)
                             + ".")
            if aviso and QMessageBox.question(
                    self, "Firma", "\n\n".join(aviso) + "\n\n¿Continuar?"
            ) != QMessageBox.Yes:
                return
        self._guardar_opciones()
        dato = self.combo_cert.currentData()
        clave = self.clave.text()
        opciones = dict(motivo=self.motivo.text(), lugar=self.lugar.text(),
                        reducir=self.reducir.isChecked(),
                        referencia=self.referencia.text().strip(),
                        unir=unir, salida_unida=salida)
        self._escribir(f"firmando {len(entradas)} documentos"
                       + (" unidos en uno" if unir else " por separado")
                       + f" como {self.datos_cert['nombre']}…")
        self._en_marcha(True)

        def trabajo():
            try:
                if dato["tipo"] != "p12":
                    # la clave sale del almacén a memoria, nunca a disco
                    p12, cl = almacenes.exportar(dato, clave)
                else:
                    p12, cl = Path(dato["ruta"]), clave.encode()
                filas = f.firmar_varios(entradas, p12, cl,
                                        avisar=self.avisador.linea.emit,
                                        **opciones)
                bien = sum(1 for x in filas if x["resultado"] == "firmado")
                # se recuerdan todos los firmados para «Abrir firmado»
                self._tanda = [str(x["salida"]) for x in filas
                               if x["salida"]]
                ultima = self._tanda[-1] if self._tanda else None
                self.avisador.hecho.emit(
                    f"terminado: {bien} de {len(filas)} "
                    + ("firmado" if unir else "documentos firmados"),
                    bien == len(filas), ultima)
            except PermissionError as e:
                self.avisador.hecho.emit(_sin_permiso(e, salida or
                                                      entradas[0]),
                                         False, None)
            except Exception as e:  # se muestra al usuario
                self.avisador.hecho.emit(f"error al firmar: {e}", False, None)

        threading.Thread(target=trabajo, daemon=True).start()

    def _comprobar(self) -> None:
        """Valida en segundo plano el firmado o, con varios documentos,
        todos los firmados de la última tanda (o los elegidos que ya
        llevan firma)."""
        tanda = [Path(r) for r in getattr(self, "_tanda", [])
                 if Path(r).is_file()]
        if self.docs:
            destinos = tanda or [Path(r) for r in self.docs
                                 if Path(r).is_file() and f.ya_firmado(
                                     Path(r))]
            if not destinos:
                return self._aviso("Ninguno de los documentos elegidos está "
                                   "firmado todavía.")
        else:
            destino = self._destino()
            if not destino.is_file():
                destino = Path(self.doc.text())
            if not destino.is_file():
                r, _ = QFileDialog.getOpenFileName(
                    self, "PDF firmado", self.ajustes.value("carpeta", ""),
                    "PDF (*.pdf)")
                if not r:
                    return
                destino = Path(r)
            destinos = [destino]
        self._escribir(f"comprobando {len(destinos)} documento"
                       f"{'s' if len(destinos) > 1 else ''} "
                       "(consulta OCSP)…")
        self._en_marcha(True)

        def trabajo():
            validos = 0
            for destino in destinos:
                buf = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf):
                        ok = f.comprobar(destino, "hard-fail")
                except Exception as e:
                    ok = False
                    buf.write(f"error al comprobar: {e}")
                validos += ok
                texto = buf.getvalue().rstrip()
                if len(destinos) == 1:
                    return self.avisador.hecho.emit(texto, ok, None)
                self.avisador.linea.emit(f"· {destino.name}\n{texto}")
            self.avisador.hecho.emit(
                f"comprobados {len(destinos)} documentos: {validos} "
                f"válido{'s' if validos != 1 else ''}"
                + ("" if validos == len(destinos) else
                   f", {len(destinos) - validos} NO VÁLIDO"
                   f"{'S' if len(destinos) - validos != 1 else ''}"),
                validos == len(destinos), None)

        threading.Thread(target=trabajo, daemon=True).start()

    def _ue(self) -> None:
        """Valida el firmado contra las listas de confianza de la UE, en
        local y en segundo plano."""
        destino = self._destino()
        if not destino.is_file():
            destino = Path(self.doc.text())
        if not destino.is_file():
            return self._aviso("No hay documento firmado que validar.")
        self._escribir(f"validando {destino.name} con las listas de "
                       "confianza de la UE (se descargan si la copia "
                       "guardada tiene más de un día; el documento no sale "
                       "del equipo)…")
        self._en_marcha(True)

        def trabajo():
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    ok = f.validar_ue(destino, "hard-fail")
            except Exception as e:
                ok = False
                buf.write(f"error al validar con las listas de la UE: {e}")
            self.avisador.hecho.emit(buf.getvalue().rstrip(), ok, None)

        threading.Thread(target=trabajo, daemon=True).start()

    def _abrir_firmados(self) -> None:
        """Abre el firmado o, con varios documentos, todos los de la última
        tanda."""
        tanda = [r for r in getattr(self, "_tanda", []) if Path(r).is_file()]
        if self.docs and tanda:
            for r in tanda:
                self._abrir(r)
        else:
            self._abrir(str(self._destino()))

    def _destino(self) -> Path:
        """El firmado sobre el que actúan «Abrir», «Comprobar» y «Validar
        con las listas de la UE»: con varios documentos, el último
        firmado."""
        if self.docs and getattr(self, "_ultimo", None):
            return Path(self._ultimo)
        return Path(self.salida.text())

    def _fin_tarea(self, mensaje: str, ok: bool, _r: object) -> None:
        """Recibe el resultado del hilo de trabajo."""
        if _r:
            self._ultimo = str(_r)
        self._en_marcha(False)
        self._escribir(mensaje)
        if not ok and mensaje.startswith("error"):
            self._aviso(mensaje)

    # utilidades -----------------------------------------------------------

    def _guardar_opciones(self) -> None:
        """Recuerda las opciones, nunca la contraseña."""
        self.ajustes.setValue("motivo", self.motivo.text())
        self.ajustes.setValue("lugar", self.lugar.text())
        self.ajustes.setValue("reducir",
                              str(self.reducir.isChecked()).lower())

    def _en_marcha(self, si: bool) -> None:
        """Bloquea los botones mientras corre una tarea."""
        for b in (self.b_firmar, self.b_comprobar, self.b_ue):
            b.setEnabled(not si)
        QApplication.setOverrideCursor(Qt.WaitCursor) if si else \
            QApplication.restoreOverrideCursor()

    def _escribir(self, texto: str) -> None:
        """Añade una entrada al registro de la ventana."""
        self.log.appendPlainText(texto + "\n")

    def _aviso(self, texto: str) -> None:
        """Muestra un aviso modal."""
        QMessageBox.warning(self, "Firma", texto)

    @staticmethod
    def _abrir(ruta: str) -> None:
        """Abre un fichero con la aplicación por defecto del sistema."""
        if ruta and Path(ruta).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(ruta))


def main() -> None:
    """Arranca la aplicación (o comprueba un PDF, lo valida con las listas
    de la UE o muestra las condiciones de uso, sin ventana)."""
    if len(sys.argv) == 2 and sys.argv[1] == "--autoprueba":
        sys.exit(f.autoprueba())
    if len(sys.argv) == 3 and sys.argv[1] == "--comprobar":
        sys.exit(0 if f.comprobar(Path(sys.argv[2]), "hard-fail") else 1)
    if len(sys.argv) == 3 and sys.argv[1] == "--ue":
        try:
            sys.exit(0 if f.validar_ue(Path(sys.argv[2]), "hard-fail")
                     else 1)
        except f.ErrorListasUE as e:
            sys.exit(f"error: {e}")
    if len(sys.argv) == 2 and sys.argv[1] == "--condiciones":
        print(f.texto_condiciones())
        sys.exit(0)
    app = QApplication(sys.argv)
    app.setApplicationName(TITULO)
    app.setDesktopFileName("firma-pdf")
    app.setWindowIcon(QIcon(str(ICONO)))
    # la ventana se abre siempre; sin las condiciones aceptadas, abre en
    # su pestaña y no deja firmar hasta aceptarlas
    v = Ventana(sys.argv[1] if len(sys.argv) > 1 else None)
    v.show()
    v.raise_()
    v.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
