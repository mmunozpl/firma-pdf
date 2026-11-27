# [Software] FirmaManPla. Firma de PDF con pie visible y código QR

🇪🇸 Español · 🇬🇧 [English](README.md)

**Manuel Muñoz Plá**

[![Release](https://img.shields.io/badge/Release-v0.3.1-009e73)](https://github.com/mmunozpl/firma-pdf/releases/tag/v0.3.1)
[![Web](https://img.shields.io/badge/Web-manpla.net-009e73)](https://manpla.net/posts/firmar-pdf-certificado-fnmt/)
[![License](https://img.shields.io/badge/License-Apache--2.0-009e73)](LICENSE)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0000--5714--912X-a6ce39)](https://orcid.org/0009-0000-5714-912X)
[![Cite](https://img.shields.io/badge/Cite-BibTeX-009e73)](#cita)

## Resumen

Un PDF firmado con el certificado de la FNMT no se distingue a simple vista de uno sin firmar: la firma vive dentro del fichero y solo la enseña el panel de firmas de un lector. Las administraciones lo resuelven con un recuadro al pie que dice quién firmó y cómo comprobarlo. FirmaManPla es una aplicación de escritorio, en prueba de concepto, que lo hace con un certificado instalado: firma en el formato europeo PAdES, añade en cada página un pie con los datos de la firma y un código QR, y comprueba el resultado, también contra las listas de confianza de la UE sin enviar el documento a ningún servicio. El recuadro solo informa: la validez depende de la firma criptográfica, de la custodia de la clave y de la validación del certificado.

La aplicación nace de la entrada «[Firmar un PDF y dejar constancia visible](https://manpla.net/posts/firmar-pdf-certificado-fnmt/)» de manpla.net. Este repositorio solo lleva la aplicación y sus dependencias fijadas.

> [!WARNING]
> **Sin garantía ni soporte.** Esta aplicación es una prueba de concepto (POC) que se publica tal cual, sin garantía de ningún tipo, sin mantenimiento y sin soporte: no se atienden incidencias ni peticiones. Su uso corre por cuenta y bajo la responsabilidad exclusiva de quien la use, que debe comprobar cada firma antes de confiar en ella. Antes de usarla, lee las [condiciones de uso](#condiciones-de-uso).

## Condiciones de uso

Son las que muestra la aplicación en su pestaña «Condiciones de uso», la primera vez que se abre y con `firmar.py --condiciones` (texto del 19-11-2026, revisión 4).

### 1. Licencia

FirmaManPla se distribuye con la licencia Apache-2.0 (https://www.apache.org/licenses/LICENSE-2.0). Permite usarla, modificarla y redistribuirla, también con fin comercial. Quien la redistribuya, con cambios o sin ellos, entrega una copia de la licencia, conserva los avisos de derechos de autor, patentes, marcas y atribución, indica los ficheros que haya modificado e incluye los avisos de atribución del fichero NOTICE (sección 4). La licencia cubre el código del autor: Qt y PySide6 (LGPL-3.0) y los demás componentes de terceros conservan la suya.

Para una versión comercial de la aplicación, contacte con el autor en https://manpla.net/contacto. La ampliación de la aplicación con sellos de tiempo puede requerir la contratación de servicios de terceros.

### 2. Sin garantía ni soporte

Esta aplicación es una prueba de concepto (POC) que se publica tal cual, sin garantía de ningún tipo, sin mantenimiento y sin soporte: no se atienden incidencias ni peticiones. Su uso corre por cuenta y bajo la responsabilidad exclusiva de quien la use, que debe comprobar cada firma antes de confiar en ella.

La licencia excluye la garantía y la responsabilidad del autor hasta donde la ley lo permite (secciones 7 y 8 de Apache-2.0).

El texto de la licencia está en [LICENSE](LICENSE), con el aviso de [NOTICE](NOTICE). Las licencias de los componentes de terceros están en [LICENCIAS.md](LICENCIAS.md).

## Descargas

| Sistema | Fichero | Estado |
|---|---|---|
| Linux x86-64 | [FirmaManPla-linux-x86_64.AppImage](https://github.com/mmunozpl/firma-pdf/releases/latest/download/FirmaManPla-linux-x86_64.AppImage) | probado con certificados de pruebas |
| Windows x86-64 | [FirmaManPla-windows-amd64.msi](https://github.com/mmunozpl/firma-pdf/releases/latest/download/FirmaManPla-windows-amd64.msi) | autoprueba en su sistema |
| macOS con Apple silicon | [FirmaManPla-macos-arm64.dmg](https://github.com/mmunozpl/firma-pdf/releases/latest/download/FirmaManPla-macos-arm64.dmg) | autoprueba en su sistema |

Cada paquete se construye en su sistema y pasa allí su autoprueba: en Windows, el flujo instala el `.msi`, ejecuta la aplicación instalada y la desinstala; en macOS, monta el `.dmg` y comprueba la firma del paquete. Los enlaces llevan siempre a la última versión. Las huellas SHA-256 de los tres paquetes están en [SHA256SUMS](https://github.com/mmunozpl/firma-pdf/releases/latest/download/SHA256SUMS):

```bash
sha256sum -c --ignore-missing SHA256SUMS
```

Los paquetes no llevan firma de código, así que Windows y macOS avisan al abrirlos la primera vez:

- **Linux.** El AppImage es un solo fichero: se le da permiso de ejecución (`chmod +x FirmaManPla-linux-x86_64.AppImage`) y se abre. Necesita `fusermount3` (paquete `fuse3`); sin él, se arranca con la opción `--appimage-extract-and-run`. Para usar los certificados del navegador hace falta el paquete de herramientas de NSS (`libnss3-tools` en Debian y Ubuntu, que trae `certutil` y `pk12util`). Qt 6 necesita además las bibliotecas gráficas que trae cualquier escritorio (`libegl1`, `libgl1`, `libxkbcommon0`, `libfontconfig1`) y `libxcb-cursor0`; en una instalación mínima pueden faltar.
- **Windows.** El `.msi` instala la aplicación para el usuario actual, sin permisos de administrador, en `%LOCALAPPDATA%\Programs\FirmaManPla`, con un acceso en el menú Inicio; se desinstala desde «Aplicaciones instaladas». SmartScreen avisa de un editor desconocido: «Más información» y «Ejecutar de todas formas». Con el control inteligente de aplicaciones de Windows 11 activado, el instalador no se ejecuta.
- **macOS.** Se abre el `.dmg` y se arrastra `FirmaManPla.app` a Aplicaciones. Gatekeeper lo bloquea la primera vez. En Ajustes del Sistema, «Privacidad y seguridad», aparece la opción «Abrir igualmente». La primera vez que guarde un firmado en Documentos, el Escritorio o Descargas, macOS pide permiso para esa carpeta; si se deniega, el permiso se cambia en «Privacidad y seguridad › Archivos y carpetas», o se elige otra carpeta con «Cambiar…». Solo para Mac con Apple silicon.

## Qué hace

- Firma PDF en PAdES-B-B con un certificado instalado en el sistema (NSS de Firefox y Chrome en Linux, almacén personal en Windows, llavero en macOS) o con un fichero `.p12` o `.pfx`.
- Añade en cada página un pie con firmante (sin el DNI), fecha con su desfase UTC, lugar, identificador, página, motivo, referencia, emisor y número de serie del certificado, formato y huella abreviada del original, una nota con dos enlaces para comprobar la firma (valide.redsara.es y el validador DSS de la Comisión Europea), y un código QR de cuatro líneas en UTF-8: «Firma digital», firmante, número de serie del certificado y huella del original.
- Firma varios documentos a la vez, elegidos o arrastrados: cada uno por separado, junto a su original, o unidos en un solo PDF, con un marcador por documento, que se firma una vez. Los documentos que ya traen firma no se unen, porque su firma no pasaría al PDF unido; por separado, reciben la firma añadida. «Comprobar firma» comprueba todos los firmados de la tanda.
- Añade la firma a un documento que llega ya firmado (un contrato firmado por la otra parte, por ejemplo) sin modificar su contenido: el recuadro va en el hueco en blanco más bajo de la última página, como apariencia del campo de la firma nueva, e indica quién firmó antes según las firmas del propio documento. Las firmas previas siguen valiendo. Si el documento lleva una firma de certificación que no admite cambios, la aplicación se niega.
- Comprueba la firma en local contra AC Raíz FNMT-RCM, con revocación por OCSP, e informa de los cambios añadidos después de cada firma.
- Valida la firma en el propio equipo contra las listas de confianza de la UE con «Validar con las listas de la UE» (o `firmar.py --ue`), con [pyHanko](https://github.com/MatthiasValvekens/pyHanko): la lista de listas de la Comisión y las listas nacionales a las que apunta (31 en la del 9 de noviembre de 2026, de las que se cargan 29: véase «Límites»), con la firma de cada una comprobada, que son las que usa [DSS](https://ec.europa.eu/digital-building-blocks/DSS/webapp-demo/validation), el validador de la Comisión. Dice si el certificado encadena con un servicio cualificado de esas listas, el nivel de la firma (cualificada, avanzada basada en certificado cualificado o avanzada) y si cada sello de tiempo lo emite un servicio de sellado cualificado. Se descargan las listas (unos 27 MB, que se guardan un día en la carpeta de datos) y la revocación: el documento no sale del equipo. La firma se puede validar también en [VALIDe](https://valide.redsara.es) y en Autofirma y Adobe Acrobat Reader, que validan en local.
- Guarda un registro local de firmas con las huellas del original y del firmado, en una carpeta de datos que solo puede leer el usuario.
- Al comprobar o validar un documento ajeno, solo consulta la revocación de los certificados que ya encadenan con un ancla de confianza, y nunca una dirección privada o local: no descarga los certificados que pida el propio documento, así que quien lo envía no sabe cuándo se comprueba. Una firma que no trae su cadena completa queda sin encadenar, con un aviso.
- El firmado no conserva los metadatos del original (título, autor, programa, fechas): solo el firmante, como autor.

## Desde el código

Con Python 3.11 y [uv](https://docs.astral.sh/uv/):

```bash
uv sync --frozen
uv run python firma_gui.py                    # ventana
uv run python firmar.py --help                # línea de órdenes
uv run python firmar.py --condiciones         # condiciones de uso
uv run python firmar.py a.pdf b.pdf --p12 cert.p12   # por separado
uv run python firmar.py a.pdf b.pdf --unir -o ab.pdf --p12 cert.p12
uv run python firmar.py firmado.pdf --ue          # listas de confianza de la UE
uv run python firma_gui.py --autoprueba       # pie, QR, recursos, firma B-B en memoria y lectores de las listas de la UE, sin ventana ni red
uv run --group construir python construir.py  # paquete del sistema en dist/
```

PyInstaller solo construye para el sistema en que se ejecuta, y `construir.py` empaqueta después su resultado: el AppImage con appimagetool 1.9.1 y el runtime de `empaquetado/linux`, los dos fijados por su huella; el `.msi` con WiX 5.0.2 y `empaquetado/windows/Package.wxs`; el `.dmg` con `hdiutil`. El flujo de `.github/workflows/construir.yml` construye los tres paquetes, pasa la autoprueba en cada uno y, al etiquetar una versión `v*`, publica la release con sus huellas.

## Límites

- Se ha probado en Linux con certificados de pruebas (firma, firma añadida, firma de varios documentos y comprobación) y con la autoprueba de cada paquete en su sistema. En Windows y en macOS no se ha probado más allá de esa autoprueba, ni con certificados reales, y en VALIDe no se ha comprobado.
- La validación con las listas de la UE es la de pyHanko 0.38.1, no la de DSS: no carga las listas checa y estonia, cuyos servidores rechazaban la petición de pyHanko el 19 de noviembre de 2026 (respuestas 406 y 403), y omite las entradas de servicio que pyHanko no interpreta (48 con la lista de listas del 9 de noviembre de 2026); cada validación dice cuántas listas cargó y cuáles faltan. Valida en la hora actual: un certificado caducado después de sellarse la firma sale como no válido, y la cualificación del certificado se evalúa en la fecha de la validación. pyHanko no conserva la historia de las listas, así que los sellos de servicios hoy retirados no encadenan y, si el estado vigente de un servicio empezó después del sello, su cualificación en la hora del sello sale como no determinable. Con una firma real de otro Estado miembro que DSS 6.5.1 da por correcta, pyHanko la dio por criptográficamente incorrecta: un resultado negativo se contrasta en DSS o en VALIDe. Las firmas en formato `adbe.pkcs7.sha1` (con SHA-1) no se validan.
- La firma PAdES-B-B no prueba su hora: la fecha del recuadro y la que declara la firma las pone el equipo que firma. Mientras el certificado está vigente, se valida como cualquier PAdES; cuando caduca o se revoca, un validador ya no puede darla por válida.
- El QR no autentica nada: cualquiera puede generar uno igual. Sirve para cotejar el papel con la firma del PDF en un validador.
- La clave privada sale del almacén a la memoria del proceso cuando es exportable. No queda confinada en su almacén, y una tarjeta o un HSM no la dejarían salir.
- Con un certificado guardado en el navegador o en el sistema, la firma es avanzada basada en certificado cualificado, no cualificada: falta un dispositivo cualificado de creación de firma.
- En un documento que llega firmado no se aplican el pie de cada página ni la reducción del contenido, que invalidarían las firmas previas: la firma lleva un solo recuadro, que necesita un hueco en blanco de unos 3 cm de alto (o de 2 cm, en su versión compacta, sin QR). Sin ese hueco en ninguna página, la firma no se hace.
- La reducción de las páginas para dejar sitio al pie no se ha ensayado con formularios, páginas giradas, tamaños mezclados ni documentos PDF/A.

## Cita

```bibtex
@software{munozpla_firmamanpla_2026,
  author  = {Muñoz Plá, Manuel},
  title   = {FirmaManPla. Firma de PDF con pie visible y código QR},
  year    = {2026},
  version = {0.3.1},
  url     = {https://github.com/mmunozpl/firma-pdf},
  license = {Apache-2.0}
}
```

## Licencia

[Apache-2.0](LICENSE), con el aviso de [NOTICE](NOTICE). Prueba de concepto sin garantía ni soporte; para una versión comercial, [contacto](https://manpla.net/contacto). La licencia cubre el código del autor. Qt y PySide6 (LGPL-3.0), la fuente DejaVu Sans de `recursos/fuentes`, que usa el recuadro de la firma añadida a un documento ya firmado ([LICENCIA-DejaVu.txt](recursos/fuentes/LICENCIA-DejaVu.txt)), y los demás componentes de terceros conservan la suya, como detalla [LICENCIAS.md](LICENCIAS.md).
