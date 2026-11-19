"""Construye la aplicación de escritorio para el sistema en que se ejecuta.

PyInstaller no compila para otros sistemas: el ejecutable de Windows se
construye en Windows y el de macOS en macOS (a mano o con el flujo de
.github/workflows/construir.yml). PyInstaller deja la aplicación en
dist/FirmaManPla, y después se empaqueta según el sistema:

- Linux: un AppImage, un solo fichero ejecutable (appimagetool 1.9.1 y el
  runtime de empaquetado/linux, los dos fijados por huella).
- Windows: un instalador .msi por usuario, sin permisos de administrador
  (WiX, con empaquetado/windows/Package.wxs).
- macOS: un .dmg con el .app y un enlace a Aplicaciones (hdiutil).

Con la aplicación viajan TERCEROS.txt, con los textos de licencia y los
avisos (NOTICE) de cada distribución de Python que se empaqueta y la
licencia del intérprete, y en Linux TERCEROS-SISTEMA.txt, con el fichero
copyright de cada paquete del sistema del que PyInstaller copia
bibliotecas y el paquete fuente de donde se obtiene su código.

Uso:
    uv run --group construir python construir.py
"""
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import PyInstaller.__main__

AQUI = Path(__file__).resolve().parent
NOMBRE = "FirmaManPla"
EMPAQUETADO = AQUI / "empaquetado"

# appimagetool fijado por versión y huella; el runtime va en el repositorio
# porque la publicación «continuous» de type2-runtime se sobrescribe
APPIMAGETOOL = (
    "https://github.com/AppImage/appimagetool/releases/download/1.9.1/"
    "appimagetool-x86_64.AppImage",
    "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0")
RUNTIME = (EMPAQUETADO / "linux" / "runtime-x86_64",
           "617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46")


# para qué pide la aplicación cada carpeta protegida de macOS: sin estas
# claves, macOS niega el acceso sin preguntar (errno 1 al escribir el
# firmado en Documentos)
USOS_MACOS = {
    "NSDocumentsFolderUsageDescription":
        "Para leer los PDF que eliges y guardar los firmados en Documentos.",
    "NSDesktopFolderUsageDescription":
        "Para leer los PDF que eliges y guardar los firmados en el Escritorio.",
    "NSDownloadsFolderUsageDescription":
        "Para leer los PDF que eliges y guardar los firmados en Descargas.",
    "NSRemovableVolumesUsageDescription":
        "Para firmar PDF guardados en discos externos.",
    "NSNetworkVolumesUsageDescription":
        "Para firmar PDF guardados en carpetas de red.",
}


def _permisos_macos(app: Path) -> None:
    """Añade al Info.plist las descripciones de uso y vuelve a sellar el .app.

    Cambiar el Info.plist invalida la firma ad hoc que pone PyInstaller, así
    que el paquete se vuelve a firmar ad hoc.
    """
    import plistlib

    info = app / "Contents" / "Info.plist"
    datos = plistlib.loads(info.read_bytes())
    datos.update(USOS_MACOS)
    info.write_bytes(plistlib.dumps(datos))
    subprocess.run(["codesign", "--force", "--sign", "-", str(app)],
                   check=True)
    subprocess.run(["codesign", "--verify", "--strict", str(app)],
                   check=True)


def _restos_teclado(raiz: Path) -> list[Path]:
    """Rutas de la aplicación empaquetada que son de Qt Virtual Keyboard.

    Args:
        raiz: la carpeta que deja PyInstaller, o el .app en macOS.

    Returns:
        Los ficheros, carpetas y enlaces con «virtualkeyboard» en el nombre,
        sin distinguir mayúsculas y sin seguir los enlaces.
    """
    return [Path(carpeta) / nombre
            for carpeta, carpetas, ficheros in os.walk(raiz)
            for nombre in carpetas + ficheros
            if "virtualkeyboard" in nombre.lower()]


def _sin_teclado_virtual(raiz: Path) -> None:
    """Retira Qt Virtual Keyboard de la aplicación empaquetada.

    PyInstaller lo recoge como complemento de entrada de texto de Qt, y ese
    módulo solo se ofrece bajo GPL-3.0 o licencia comercial, sin la opción
    LGPL del resto de Qt que lleva el paquete. La aplicación no lo usa. Se
    borran sus bibliotecas, su complemento y sus enlaces, y la construcción
    se detiene si después queda alguno.

    Args:
        raiz: la carpeta que deja PyInstaller, o el .app en macOS (antes de
            volver a sellarlo).
    """
    restos = _restos_teclado(raiz)
    # primero lo más hondo, para borrar el contenido antes que su carpeta
    for ruta in sorted(restos, key=lambda r: len(r.parts), reverse=True):
        if ruta.is_symlink() or ruta.is_file():
            ruta.unlink()
        elif ruta.is_dir():
            shutil.rmtree(ruta)
    quedan = _restos_teclado(raiz)
    if quedan:
        raise SystemExit("Qt Virtual Keyboard sigue en el paquete: "
                         + ", ".join(str(r) for r in quedan))
    print(f"Qt Virtual Keyboard retirado: {len(restos)} rutas")


# herramientas de construcción que no viajan en el paquete
SOLO_CONSTRUCCION = {"pyinstaller", "pyinstaller-hooks-contrib", "altgraph",
                     "macholib", "pefile", "pywin32-ctypes",
                     "pyside6-webengine"}
# ficheros de los metadatos de una distribución que llevan su licencia
MARCAS_LICENCIA = ("LICEN", "COPYING", "NOTICE", "AUTHORS")


def _licencias_python(destino: Path) -> None:
    """Escribe TERCEROS.txt: licencia del intérprete y, de cada
    distribución del entorno salvo las de construcción, sus ficheros de
    licencia y de avisos (NOTICE) tal como los trae.

    Args:
        destino: fichero que se escribe.

    Raises:
        SystemExit: si alguna distribución no trae texto ni expresión de
            licencia.
    """
    from importlib.metadata import distributions

    partes = [f"{'=' * 78}\nPython {platform.python_version()} (PSF-2.0)"
              f"\n{'=' * 78}"]
    interprete = [Path(sys.base_prefix) / "lib" /
                  f"python{sys.version_info.major}.{sys.version_info.minor}"
                  / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE.txt"]
    texto = next((x for x in interprete if x.is_file()), None)
    if texto is None:
        sys.exit("no se encuentra la licencia del intérprete de Python")
    partes.append(texto.read_text(encoding="utf-8", errors="replace"))
    sin_licencia = []
    for d in sorted(distributions(), key=lambda d: d.metadata["Name"].lower()):
        nombre = d.metadata["Name"]
        if re.sub(r"[-_.]+", "-", nombre).lower() in SOLO_CONSTRUCCION:
            continue
        expresion = (d.metadata.get("License-Expression")
                     or d.metadata.get("License") or "").strip()
        textos = []
        for f in sorted((f for f in d.files or []
                         if ".dist-info/" in str(f)
                         and any(m in f.name.upper()
                                 for m in MARCAS_LICENCIA)), key=str):
            ruta = Path(d.locate_file(f))
            if ruta.is_file():
                textos.append(f"--- {f} ---\n" + ruta.read_text(
                    encoding="utf-8", errors="replace"))
        if not textos:
            if not expresion:
                sin_licencia.append(nombre)
                continue
            # pyside6 y shiboken6 no traen el texto: es el de la lgpl-3.0
            # de recursos/licencias
            textos.append(f"Su distribución no trae el texto de la licencia "
                          f"({expresion}); el de la LGPL-3.0 está en "
                          "recursos/licencias/LGPL-3.0.txt.")
        partes.append(f"{'=' * 78}\n{nombre} {d.version}"
                      + (f" ({expresion.splitlines()[0][:70]})"
                         if expresion else "") + f"\n{'=' * 78}")
        partes += textos
    if sin_licencia:
        sys.exit("sin texto ni expresión de licencia: "
                 + ", ".join(sin_licencia))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        "Componentes de terceros de FirmaManPla: licencia y avisos de cada "
        "uno, tal como los traen sus distribuciones.\n\n"
        + "\n\n".join(partes) + "\n", encoding="utf-8")


def _licencias_sistema(interna: Path) -> None:
    """Escribe, en Linux, TERCEROS-SISTEMA.txt junto a las bibliotecas:
    de cada biblioteca que PyInstaller copió del sistema, el paquete de
    Debian o Ubuntu del que sale, su paquete fuente con la versión (de
    donde se obtiene el código, como piden la LGPL y otras licencias) y el
    fichero copyright del paquete. Las bibliotecas que no son de ningún
    paquete del sistema vienen de las distribuciones de Python, con su
    licencia en TERCEROS.txt.

    Args:
        interna: carpeta _internal de la aplicación construida.

    Raises:
        SystemExit: sin dpkg, o si un paquete no tiene fichero copyright.
    """
    if not shutil.which("dpkg"):
        sys.exit("hace falta dpkg para inventariar las bibliotecas del "
                 "sistema")
    paquetes: dict[str, list[str]] = {}
    for so in sorted(interna.glob("*.so*")):
        if so.is_symlink() or not so.is_file():
            continue
        r = subprocess.run(["dpkg", "-S", f"*/{so.name}"], text=True,
                           capture_output=True)
        duenos = {linea.split(": ", 1)[0] for linea in r.stdout.splitlines()
                  if ": " in linea and "i386" not in linea.split(": ")[0]}
        for dueno in sorted(duenos)[:1]:
            paquetes.setdefault(dueno, []).append(so.name)
    sistema = "Linux"
    os_release = Path("/etc/os-release")
    if os_release.is_file():
        for linea in os_release.read_text().splitlines():
            if linea.startswith("PRETTY_NAME="):
                sistema = linea.split("=", 1)[1].strip('"')
    partes = []
    for paquete, bibliotecas in sorted(paquetes.items()):
        fuente, version = subprocess.run(
            ["dpkg-query", "-W", "-f", "${source:Package}\t"
             "${source:Version}", paquete], text=True, capture_output=True,
            check=True).stdout.split("\t")
        copyright_ = Path("/usr/share/doc") / paquete.split(":")[0] / \
            "copyright"
        if not copyright_.is_file():
            sys.exit(f"{paquete}: sin /usr/share/doc/.../copyright")
        partes.append(
            f"{'=' * 78}\n{paquete} (paquete fuente {fuente} {version}): "
            f"{', '.join(bibliotecas)}\nfuente: "
            f"https://launchpad.net/ubuntu/+source/{fuente}/{version} o "
            f"«apt-get source {fuente}={version}»\n{'=' * 78}\n"
            + copyright_.read_text(encoding="utf-8", errors="replace"))
    (interna / "TERCEROS-SISTEMA.txt").write_text(
        f"Bibliotecas que PyInstaller copió del sistema de construcción "
        f"({sistema}) en FirmaManPla, con el paquete del que sale cada una, "
        "su paquete fuente y el fichero copyright del paquete, que da su "
        "licencia (las de la LGPL-2.1 y la LGPL-3.0 están en "
        "recursos/licencias). El código fuente de cada paquete se obtiene "
        "en la dirección que se indica o con apt-get source.\n\n"
        + "\n\n".join(partes) + "\n", encoding="utf-8")
    print(f"TERCEROS-SISTEMA.txt: {len(paquetes)} paquetes del sistema")


def _version() -> str:
    """La versión de pyproject.toml, la misma que firmar.VERSION."""
    import tomllib

    datos = tomllib.loads((AQUI / "pyproject.toml").read_text())
    return datos["project"]["version"]


def _huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _herramienta(url: str, huella: str) -> Path:
    """Descarga una herramienta a build/herramientas y comprueba su huella."""
    destino = AQUI / "build" / "herramientas" / url.rsplit("/", 1)[1]
    if not destino.exists() or _huella(destino) != huella:
        destino.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, destino)
    if _huella(destino) != huella:
        raise SystemExit(f"huella inesperada en {destino.name}")
    destino.chmod(0o755)
    return destino


def appimage(origen: Path, salida: Path) -> None:
    """Empaqueta la carpeta de PyInstaller en un AppImage.

    El AppDir lleva un AppRun que arranca el ejecutable, el .desktop y el
    icono en su raíz. appimagetool se ejecuta extraído, sin FUSE, para que
    funcione también en las máquinas de construcción.
    """
    runtime, huella = RUNTIME
    if _huella(runtime) != huella:
        raise SystemExit("huella inesperada en el runtime de AppImage")
    herramienta = _herramienta(*APPIMAGETOOL)
    appdir = AQUI / "build" / f"{NOMBRE}.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(origen, appdir / "usr" / "lib" / NOMBRE, symlinks=True)
    apprun = appdir / "AppRun"
    apprun.write_text(
        "#!/bin/sh\n"
        "# arranca la aplicación empaquetada por PyInstaller\n"
        'AQUI="$(dirname "$(readlink -f "$0")")"\n'
        f'exec "$AQUI/usr/lib/{NOMBRE}/{NOMBRE}" "$@"\n')
    apprun.chmod(0o755)
    (appdir / "firmamanpla.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={NOMBRE}\n"
        "GenericName=Firma electrónica de PDF\n"
        "Comment=Firma PDF en PAdES con pie visible y código QR\n"
        "Exec=AppRun %f\n"
        "Icon=firmamanpla\n"
        "Terminal=false\n"
        "Categories=Office;\n"
        "MimeType=application/pdf;\n"
        f"X-AppImage-Version={_version()}\n")
    shutil.copy(AQUI / "recursos" / "icono.png", appdir / "firmamanpla.png")
    if shutil.which("desktop-file-validate"):
        subprocess.run(["desktop-file-validate",
                        str(appdir / "firmamanpla.desktop")], check=True)
    entorno = dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
    subprocess.run([str(herramienta), "--no-appstream", "--runtime-file",
                    str(runtime), str(appdir), str(salida)], check=True,
                   env=entorno)


def msi(origen: Path, salida: Path) -> None:
    """Construye el instalador .msi con WiX (la orden «wix» en el PATH)."""
    subprocess.run(["wix", "build", "-arch", "x64",
                    *os.environ.get("WIX_OPCIONES", "").split(),
                    "-d", f"Version={_version()}",
                    "-bindpath", f"app={origen}",
                    str(EMPAQUETADO / "windows" / "Package.wxs"),
                    "-o", str(salida)], check=True)


def dmg(app: Path, salida: Path) -> None:
    """Imagen de disco con el .app y un enlace a /Applications.

    La firma ad hoc que pone PyInstaller (rehecha en _permisos_macos) se
    comprueba antes; cp -Rp conserva enlaces y atributos del paquete.
    hdiutil falla a veces con «Resource busy» en las máquinas de GitHub,
    así que se reintenta.
    """
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)],
                   check=True)
    carpeta = AQUI / "build" / "dmg"
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir(parents=True)
    subprocess.run(["cp", "-Rp", str(app), str(carpeta)], check=True)
    (carpeta / "Applications").symlink_to("/Applications")
    subprocess.run(["sync"], check=True)
    for intento in range(3):
        r = subprocess.run(["hdiutil", "create", "-volname", NOMBRE,
                            "-srcfolder", str(carpeta), "-ov",
                            "-format", "UDZO", str(salida)])
        if r.returncode == 0:
            return
        time.sleep(10)
    raise SystemExit("hdiutil no pudo crear la imagen de disco")


def main() -> None:
    """Llama a PyInstaller y empaqueta el resultado según el sistema."""
    sep = os.pathsep
    if sys.platform.startswith("win"):
        sistema, icono = "windows", AQUI / "recursos" / "icono.ico"
    elif sys.platform == "darwin":
        # PyInstaller convierte el png a icns con pillow
        sistema, icono = "macos", AQUI / "recursos" / "icono.png"
    else:
        sistema, icono = "linux", AQUI / "recursos" / "icono.png"
    terceros = AQUI / "build" / "licencias" / "TERCEROS.txt"
    _licencias_python(terceros)
    PyInstaller.__main__.run([
        str(AQUI / "firma_gui.py"),
        "--name", NOMBRE,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--icon", str(icono),
        "--add-data", f"{AQUI / 'confianza'}{sep}confianza",
        "--add-data", f"{AQUI / 'recursos'}{sep}recursos",
        # la licencia, con su aviso, y las licencias de terceros viajan
        # con la aplicación
        "--add-data", f"{AQUI / 'LICENSE'}{sep}.",
        "--add-data", f"{AQUI / 'NOTICE'}{sep}.",
        "--add-data", f"{AQUI / 'LICENCIAS.md'}{sep}.",
        "--add-data", f"{terceros}{sep}.",
        "--collect-submodules", "pyhanko",
        "--collect-submodules", "pyhanko_certvalidator",
        # los firmantes de la lista de listas de la UE viajan como datos
        "--collect-data", "pyhanko",
        "--collect-submodules", "xsdata.formats",
        # signxml lee sus esquemas (xmldsig y xades) como recursos, los de
        # xades de un paquete sin __init__.py que pyinstaller no encuentra
        # si no se le pide
        "--collect-data", "signxml",
        "--hidden-import", "signxml.xades.schemas",
        # reportlab carga sus códigos de barras de forma dinámica
        "--collect-submodules", "reportlab.graphics.barcode",
        "--osx-bundle-identifier", "net.manpla.firma-pdf",
        "--distpath", str(AQUI / "dist"),
        "--workpath", str(AQUI / "build"),
        "--specpath", str(AQUI / "build"),
    ])
    # el teclado virtual de qt (gpl-3.0 o comercial) no viaja en el paquete
    _sin_teclado_virtual(
        AQUI / "dist" / (f"{NOMBRE}.app" if sistema == "macos" else NOMBRE))
    if sistema == "linux":
        _licencias_sistema(AQUI / "dist" / NOMBRE / "_internal")
    # el nombre del paquete lleva sistema y arquitectura, sin versión: así
    # releases/latest/download/<nombre> lleva siempre a la última
    arquitectura = platform.machine().lower()
    base = AQUI / "dist" / f"{NOMBRE}-{sistema}-{arquitectura}"
    if sistema == "macos":
        app = AQUI / "dist" / f"{NOMBRE}.app"
        _permisos_macos(app)
        dmg(app, Path(f"{base}.dmg"))
        print(f"construido: {app}\npaquete: {base}.dmg")
    elif sistema == "windows":
        msi(AQUI / "dist" / NOMBRE, Path(f"{base}.msi"))
        print(f"paquete: {base}.msi")
    else:
        appimage(AQUI / "dist" / NOMBRE, Path(f"{base}.AppImage"))
        print(f"paquete: {base}.AppImage")


if __name__ == "__main__":
    main()
