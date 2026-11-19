# Licencias de FirmaManPla

🇪🇸 Español · 🇬🇧 [English](#firmamanpla-licences)

## Licencia de la aplicación

El código y la documentación del autor (`firmar.py`, `firma_gui.py`, `almacenes.py`, `construir.py`, `empaquetado/windows`, el flujo de construcción y los textos del repositorio) se distribuyen con la licencia [Apache-2.0](LICENSE), con el aviso de [NOTICE](NOTICE). Permite usarlos, modificarlos y redistribuirlos, también con fin comercial. Quien los redistribuya, con cambios o sin ellos, entrega una copia de la licencia, conserva los avisos de derechos de autor, patentes, marcas y atribución, indica los ficheros que haya modificado e incluye los avisos de atribución del fichero NOTICE (sección 4). Es una prueba de concepto sin garantía ni soporte; para una versión comercial, el contacto es <https://manpla.net/contacto>. La aplicación muestra sus condiciones de uso en la pestaña «Condiciones de uso» y con `firmar.py --condiciones`.

## Componentes de terceros

La licencia de la aplicación cubre solo el código del autor. Los componentes de terceros conservan la suya, y sus versiones exactas están en `uv.lock`:

| Componente | Licencia |
|---|---|
| Qt 6.12.0 (los módulos que usa la aplicación), en las ruedas PySide6 6.12.0, PySide6-Essentials 6.12.0, PySide6-Addons 6.12.0 y PySide6-Pdf 6.12.0.140, y shiboken6 6.12.0 | LGPL-3.0-only, la opción que se usa de las tres que ofrecen (LGPL-3.0-only, GPL-2.0-only o GPL-3.0-only). PySide6-WebEngine 6.12.0.140 está en `uv.lock` como dependencia de PySide6, pero no se empaqueta |
| PDFium, dentro de Qt PDF (libQt6Pdf), con el que se busca el hueco de la firma añadida | BSD-3-Clause, con partes en Apache-2.0 ([PDFium.txt](recursos/licencias/PDFium.txt)) |
| Python 3.11, el intérprete que va en el paquete (python-build-standalone), con las bibliotecas que lleva enlazadas (OpenSSL, SQLite, expat, libffi, libmpdec, zlib, bzip2, xz, ncurses, libedit, libuuid) | PSF-2.0, y las de cada biblioteca ([Python-incorporado.txt](recursos/licencias/Python-incorporado.txt)) |
| pyHanko 0.38.1 (con los certificados de los firmantes de la lista de listas de la UE) y pyhanko-certvalidator 0.33.0 | MIT |
| xsdata 26.10 | MIT |
| signxml 5.3.0 | Apache-2.0 |
| asn1crypto 1.5.1, oscrypto 1.3.0, uritools 7.0.0, tzlocal 5.4.5, attrs 26.1.0, charset-normalizer 3.5.2 y urllib3 2.8.0 | MIT |
| cryptography 50.0.2 | Apache-2.0 o BSD-3-Clause |
| cffi 2.1.1 y pycparser 3.12 | MIT-0 y BSD-3-Clause |
| setuptools 84.2.1, con los módulos que incluye en `_vendor`, que PyInstaller añade al paquete | MIT |
| tzdata 2026.6, solo en Windows | Apache-2.0 |
| pypdf 7.1.0, lxml 6.1.3 e idna 3.20 | BSD-3-Clause |
| reportlab 5.1.0 | BSD |
| pillow 13.0.0 | MIT-CMU |
| requests 2.34.2, aiosignal 1.4.0, frozenlist 1.8.0, multidict 7.2.1, propcache 0.5.4 y yarl 1.25.1 | Apache-2.0 |
| aiohttp 3.14.5 | Apache-2.0 y MIT |
| packaging 26.3 | Apache-2.0 o BSD-2-Clause |
| aiohappyeyeballs 2.7.1 y typing_extensions 4.16.0 | PSF-2.0 |
| certifi 2026.10.23 | MPL-2.0 |
| PyInstaller 6.22.3, cargador del ejecutable | GPL-2.0-or-later con la excepción del cargador («Bootloader Exception») |
| DejaVu Sans, en `recursos/fuentes` | la de Bitstream Vera, con los cambios de DejaVu en dominio público ([LICENCIA-DejaVu.txt](recursos/fuentes/LICENCIA-DejaVu.txt)) |
| Runtime de AppImage, en `empaquetado/linux` (type2-runtime, confirmación fedfad5) | MIT el runtime y musl libc, LGPL-2.1 libfuse 3 ([LGPL-2.1.txt](recursos/licencias/LGPL-2.1.txt)), BSD-2-Clause squashfuse, BSD-3-Clause libzstd y Zlib zlib ([AppImage-runtime.txt](recursos/licencias/AppImage-runtime.txt)); su código, en <https://github.com/AppImage/type2-runtime> |
| Certificados de `confianza/` | certificados públicos de FNMT-RCM, Izenpe, Sectigo, BalTstamp, el Sistema de Certificação Electrónica do Estado (SCEE) portugués y el Instituto dos Registos e do Notariado (Cartão de Cidadão, emitido por el SCEE) |

Qt y PySide6 se usan sin modificar y bajo la LGPL-3.0. En los paquetes van como bibliotecas compartidas, separadas del código de la aplicación, y quien recibe un paquete puede sustituirlas por otra versión. Qt Virtual Keyboard, que solo se ofrece bajo GPL-3.0 o licencia comercial, se retira de los paquetes al construirlos. La licencia de la aplicación no restringe la modificación de esas bibliotecas ni la ingeniería inversa necesaria para depurar esas modificaciones. Su código fuente está en <https://download.qt.io/official_releases/qt/6.12/6.12.0/single/> (Qt) y en <https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/> (PySide6), y los textos de la LGPL-3.0, de la GPL-3.0 y de Apache-2.0 acompañan a la aplicación en `recursos/licencias`: [LGPL-3.0.txt](recursos/licencias/LGPL-3.0.txt), [GPL-3.0.txt](recursos/licencias/GPL-3.0.txt) y [Apache-2.0.txt](recursos/licencias/Apache-2.0.txt).

Cada paquete lleva `TERCEROS.txt`, que `construir.py` genera al construirlo con el texto de licencia y los avisos (NOTICE) de cada distribución de Python incluida y la licencia del intérprete. El paquete de Linux lleva además `TERCEROS-SISTEMA.txt`: las bibliotecas que PyInstaller copia del sistema de construcción (GTK, GLib, Pango, cairo, systemd y otras, muchas con licencia LGPL-2.1), con el paquete de Ubuntu del que sale cada una, su fichero copyright y el paquete fuente con su versión, de donde se obtiene su código. Los textos de la LGPL-2.1 y de la MPL-2.0 (certifi, cuyo código está en <https://github.com/certifi/python-certifi>) acompañan a la aplicación en `recursos/licencias`. Qt incluye a su vez componentes de terceros, con las licencias que enumera <https://doc.qt.io/qt-6/licenses-used-in-qt.html>; la de ICU, que va en las ruedas de PySide6, está en [Qt-terceros.txt](recursos/licencias/Qt-terceros.txt).

---

# FirmaManPla licences

## Licence of the application

The author's code and documentation (`firmar.py`, `firma_gui.py`, `almacenes.py`, `construir.py`, `empaquetado/windows`, the build workflow and the texts of the repository) are distributed under the [Apache-2.0](LICENSE) licence, with the notice in [NOTICE](NOTICE). It allows them to be used, modified and redistributed, also for a commercial purpose. Whoever redistributes them, with or without changes, passes on a copy of the licence, keeps the copyright, patent, trademark and attribution notices, states the files they have modified and includes the attribution notices of the NOTICE file (section 4). It is a proof of concept without warranty or support; for a commercial version, the contact is <https://manpla.net/en/contacto>. The application shows its terms of use in the "Condiciones de uso" tab and with `firmar.py --condiciones`.

## Third-party components

The licence of the application covers only the author's code. Third-party components keep their own, and their exact versions are in `uv.lock`:

| Component | Licence |
|---|---|
| Qt 6.12.0 (the modules the application uses), in the PySide6 6.12.0, PySide6-Essentials 6.12.0, PySide6-Addons 6.12.0 and PySide6-Pdf 6.12.0.140 wheels, and shiboken6 6.12.0 | LGPL-3.0-only, the option used of the three they offer (LGPL-3.0-only, GPL-2.0-only or GPL-3.0-only). PySide6-WebEngine 6.12.0.140 is in `uv.lock` as a dependency of PySide6 but is not packaged |
| PDFium, inside Qt PDF (libQt6Pdf), used to find the space for an added signature | BSD-3-Clause, with parts under Apache-2.0 ([PDFium.txt](recursos/licencias/PDFium.txt)) |
| Python 3.11, the interpreter in the package (python-build-standalone), with the libraries linked into it (OpenSSL, SQLite, expat, libffi, libmpdec, zlib, bzip2, xz, ncurses, libedit, libuuid) | PSF-2.0, and those of each library ([Python-incorporado.txt](recursos/licencias/Python-incorporado.txt)) |
| pyHanko 0.38.1 (with the certificates of the signers of the EU list of trusted lists) and pyhanko-certvalidator 0.33.0 | MIT |
| xsdata 26.10 | MIT |
| signxml 5.3.0 | Apache-2.0 |
| asn1crypto 1.5.1, oscrypto 1.3.0, uritools 7.0.0, tzlocal 5.4.5, attrs 26.1.0, charset-normalizer 3.5.2 and urllib3 2.8.0 | MIT |
| cryptography 50.0.2 | Apache-2.0 or BSD-3-Clause |
| cffi 2.1.1 and pycparser 3.12 | MIT-0 and BSD-3-Clause |
| setuptools 84.2.1, with the modules it includes in `_vendor`, which PyInstaller adds to the package | MIT |
| tzdata 2026.6, on Windows only | Apache-2.0 |
| pypdf 7.1.0, lxml 6.1.3 and idna 3.20 | BSD-3-Clause |
| reportlab 5.1.0 | BSD |
| pillow 13.0.0 | MIT-CMU |
| requests 2.34.2, aiosignal 1.4.0, frozenlist 1.8.0, multidict 7.2.1, propcache 0.5.4 and yarl 1.25.1 | Apache-2.0 |
| aiohttp 3.14.5 | Apache-2.0 and MIT |
| packaging 26.3 | Apache-2.0 or BSD-2-Clause |
| aiohappyeyeballs 2.7.1 and typing_extensions 4.16.0 | PSF-2.0 |
| certifi 2026.10.23 | MPL-2.0 |
| PyInstaller 6.22.3, bootloader of the executable | GPL-2.0-or-later with the Bootloader Exception |
| DejaVu Sans, in `recursos/fuentes` | the Bitstream Vera licence, with the DejaVu changes in the public domain ([LICENCIA-DejaVu.txt](recursos/fuentes/LICENCIA-DejaVu.txt)) |
| AppImage runtime, in `empaquetado/linux` (type2-runtime, commit fedfad5) | MIT for the runtime and musl libc, LGPL-2.1 for libfuse 3 ([LGPL-2.1.txt](recursos/licencias/LGPL-2.1.txt)), BSD-2-Clause for squashfuse, BSD-3-Clause for libzstd and Zlib for zlib ([AppImage-runtime.txt](recursos/licencias/AppImage-runtime.txt)); its source, at <https://github.com/AppImage/type2-runtime> |
| Certificates in `confianza/` | public certificates of FNMT-RCM, Izenpe, Sectigo, BalTstamp, the Sistema de Certificação Electrónica do Estado (SCEE) of the Portuguese State and the Instituto dos Registos e do Notariado (Cartão de Cidadão, issued by the SCEE) |

Qt and PySide6 are used unmodified and under the LGPL-3.0. In the packages they are shared libraries, separate from the code of the application, and whoever receives a package can replace them with another version. Qt Virtual Keyboard, which is offered only under GPL-3.0 or a commercial licence, is removed from the packages when they are built. The licence of the application does not restrict the modification of those libraries or the reverse engineering needed to debug such modifications. Their source code is at <https://download.qt.io/official_releases/qt/6.12/6.12.0/single/> (Qt) and at <https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/> (PySide6), and the texts of the LGPL-3.0, the GPL-3.0 and Apache-2.0 accompany the application in `recursos/licencias`: [LGPL-3.0.txt](recursos/licencias/LGPL-3.0.txt), [GPL-3.0.txt](recursos/licencias/GPL-3.0.txt) and [Apache-2.0.txt](recursos/licencias/Apache-2.0.txt).

Each package carries `TERCEROS.txt`, which `construir.py` generates when building it with the licence text and the notices (NOTICE) of each Python distribution included and the licence of the interpreter. The Linux package also carries `TERCEROS-SISTEMA.txt`: the libraries PyInstaller copies from the build system (GTK, GLib, Pango, cairo, systemd and others, many under the LGPL-2.1), with the Ubuntu package each one comes from, its copyright file and the source package with its version, from which its source code is obtained. The texts of the LGPL-2.1 and the MPL-2.0 (certifi, whose source is at <https://github.com/certifi/python-certifi>) accompany the application in `recursos/licencias`. Qt in turn includes third-party components, with the licences listed at <https://doc.qt.io/qt-6/licenses-used-in-qt.html>; that of ICU, which travels in the PySide6 wheels, is in [Qt-terceros.txt](recursos/licencias/Qt-terceros.txt).
