**FirmaManPla**: firma de PDF en PAdES-B-B con certificado instalado o fichero `.p12`, pie visible con código QR en cada página, comprobación de la firma y validación en local contra las listas de confianza de la UE.

| Fichero | Sistema | Estado |
|---|---|---|
| `FirmaManPla-linux-x86_64.AppImage` | Linux x86-64 | probado con certificados de pruebas |
| `FirmaManPla-windows-amd64.msi` | Windows x86-64 | autoprueba en su sistema |
| `FirmaManPla-macos-arm64.dmg` | macOS con Apple silicon | autoprueba en su sistema |

**Qué hace la 0.3.1.**

- **Firma PAdES-B-B** con un certificado del sistema o un fichero `.p12` o `.pfx`, de uno o de varios documentos (por separado o unidos), y añade la firma a un documento que llega ya firmado sin invalidar las firmas previas.
- **Pie en cada página**, en dos bloques: arriba, Firmante, Fecha de firma, Lugar, Motivo y Referencia; abajo, Emisor del certificado, Nº de serie del certificado, Formato, Huella original (SHA-256), Id. documento y Página. La nota final, centrada, da los dos validadores, y el QR de 21 mm va a su derecha.
- **Comprobar firma**, en local contra AC Raíz FNMT-RCM, con revocación por OCSP y los cambios añadidos después de cada firma.
- **Validar con las listas de la UE**, en el propio equipo y con pyHanko: la lista de listas de la Comisión y las listas nacionales, con su firma comprobada, como las usa DSS, el validador de la Comisión (29 de las 31 de la lista del 9 de noviembre de 2026: los servidores checo y estonio rechazan la petición de pyHanko; cada validación dice cuáles faltan). Da el nivel de la firma, la cualificación del certificado y la de cada sello de tiempo. Se descargan las listas y la revocación; el documento no sale del equipo.
- **Privacidad al comprobar.** Comprobar o validar un documento ajeno no descarga los certificados que pida el propio documento, y solo consulta la revocación de cadenas que llegan a un ancla de confianza, nunca en una dirección privada o local. El firmado no conserva los metadatos del original, y la carpeta de datos y el registro solo los puede leer el usuario.
- **Licencia Apache-2.0.** Para una versión comercial de la aplicación, contacte con el autor en <https://manpla.net/contacto>. La ampliación de la aplicación con sellos de tiempo puede requerir la contratación de servicios de terceros.

Las huellas SHA-256 están en `SHA256SUMS` (`sha256sum -c --ignore-missing SHA256SUMS`). Los paquetes no llevan firma de código: Windows y macOS avisarán al abrirlos. Instrucciones en el [LEEME](LEEME.md).

> **Sin garantía ni soporte.** Esta aplicación es una prueba de concepto (POC) que se publica tal cual, sin garantía de ningún tipo, sin mantenimiento y sin soporte: no se atienden incidencias ni peticiones. Su uso corre por cuenta y bajo la responsabilidad exclusiva de quien la use, que debe comprobar cada firma antes de confiar en ella.

---

**FirmaManPla**: PAdES-B-B signing of PDFs with an installed certificate or a `.p12` file, a visible footer with a QR code on every page, signature checking and local validation against the EU trusted lists.

**What 0.3.1 does.**

- **PAdES-B-B signature** with a system certificate or a `.p12` or `.pfx` file, of one or several documents (separately or merged), and adds the signature to a document that arrives already signed without invalidating the earlier signatures.
- **A footer on every page**, in two blocks: above, Firmante, Fecha de firma, Lugar, Motivo and Referencia; below, Emisor del certificado, Nº de serie del certificado, Formato, Huella original (SHA-256), Id. documento and Página. The centred closing note gives the two validators, and the 21 mm QR code sits to its right.
- **Comprobar firma** (check signature), locally against AC Raíz FNMT-RCM, with revocation over OCSP and the changes appended after each signature.
- **Validar con las listas de la UE** (validate against the EU lists), on the computer itself and with pyHanko: the Commission's list of trusted lists and the national lists, with their signature checked, as DSS, the Commission's validator, uses them (29 of the 31 in the list of 9 November 2026: the Czech and Estonian servers reject pyHanko's request; each validation states which are missing). It reports the level of the signature, the qualification of the certificate and that of each time stamp. The lists and the revocation data are downloaded; the document never leaves the computer.
- **Privacy when checking.** Checking or validating someone else's document does not download the certificates the document itself asks for, and only queries revocation for chains that reach a trust anchor, never at a private or local address. The signed file does not keep the metadata of the original, and the data folder and the log can only be read by the user.
- **Apache-2.0 licence.** For a commercial version of the application, contact the author at <https://manpla.net/en/contacto>. Extending the application with time stamps may require contracting third-party services.

SHA-256 hashes are in `SHA256SUMS` (`sha256sum -c --ignore-missing SHA256SUMS`). The packages are not code-signed: Windows and macOS will warn when opening them. Instructions in the [README](README.md).

> **No warranty or support.** This application is a proof of concept (POC) published as is, without warranty of any kind, without maintenance and without support: issues and requests are not handled. Its use is entirely at the risk and under the sole responsibility of whoever uses it, who must check every signature before relying on it.
