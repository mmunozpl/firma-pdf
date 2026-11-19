# [Software] FirmaManPla. PDF signing with a visible footer and a QR code

🇪🇸 [Español](LEEME.md) · 🇬🇧 English

**Manuel Muñoz Plá**

[![Release](https://img.shields.io/badge/Release-v0.3.0-009e73)](https://github.com/mmunozpl/firma-pdf/releases/tag/v0.3.0)
[![Web](https://img.shields.io/badge/Web-manpla.net-009e73)](https://manpla.net/en/posts/signing-pdf-fnmt-certificate/)
[![License](https://img.shields.io/badge/License-Apache--2.0-009e73)](LICENSE)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0000--5714--912X-a6ce39)](https://orcid.org/0009-0000-5714-912X)
[![Cite](https://img.shields.io/badge/Cite-BibTeX-009e73)](#citation)

## Summary

A PDF signed with an FNMT certificate cannot be told apart at a glance from an unsigned one: the signature lives inside the file and only the signature panel of a reader shows it. Public administrations solve this with a box in the footer that says who signed and how to check it. FirmaManPla is a desktop application, at proof-of-concept stage, that does it with an installed certificate: it signs in the European PAdES format, adds to every page a footer with the signature details and a QR code, and checks the result, also against the EU trusted lists without sending the document to any service. The box only informs: validity depends on the cryptographic signature, on the custody of the key and on the validation of the certificate.

The application comes from the post "[Signing a PDF and leaving visible evidence](https://manpla.net/en/posts/signing-pdf-fnmt-certificate/)" on manpla.net. This repository only holds the application and its pinned dependencies.

> [!WARNING]
> **No warranty or support.** This application is a proof of concept (POC) published as is, without warranty of any kind, without maintenance and without support: issues and requests are not handled. Its use is entirely at the risk and under the sole responsibility of whoever uses it, who must check every signature before relying on it. Before using it, read the [terms of use](#terms-of-use).

## Terms of use

These are the terms the application shows in its "Condiciones de uso" tab, the first time it is opened and with `firmar.py --condiciones` (text of 19-11-2026, revision 4). The application shows them in Spanish; this is their translation.

### 1. Licence

FirmaManPla is distributed under the Apache-2.0 licence (https://www.apache.org/licenses/LICENSE-2.0). It allows it to be used, modified and redistributed, also for a commercial purpose. Whoever redistributes it, with or without changes, passes on a copy of the licence, keeps the copyright, patent, trademark and attribution notices, states the files they have modified and includes the attribution notices of the NOTICE file (section 4). The licence covers the author's code: Qt and PySide6 (LGPL-3.0) and the other third-party components keep their own.

For a commercial version of the application, contact the author at https://manpla.net/en/contacto. Extending the application with time stamps may require contracting third-party services.

### 2. No warranty or support

This application is a proof of concept (POC) published as is, without warranty of any kind, without maintenance and without support: issues and requests are not handled. Its use is entirely at the risk and under the sole responsibility of whoever uses it, who must check every signature before relying on it.

The licence excludes the author's warranty and liability as far as the law allows (sections 7 and 8 of Apache-2.0).

The text of the licence is in [LICENSE](LICENSE), with the notice in [NOTICE](NOTICE). The licences of the third-party components are in [LICENCIAS.md](LICENCIAS.md#firmamanpla-licences).

## Downloads

| System | File | Status |
|---|---|---|
| Linux x86-64 | [FirmaManPla-linux-x86_64.AppImage](https://github.com/mmunozpl/firma-pdf/releases/latest/download/FirmaManPla-linux-x86_64.AppImage) | tested with test certificates |
| Windows x86-64 | [FirmaManPla-windows-amd64.msi](https://github.com/mmunozpl/firma-pdf/releases/latest/download/FirmaManPla-windows-amd64.msi) | self-test on its system |
| macOS on Apple silicon | [FirmaManPla-macos-arm64.dmg](https://github.com/mmunozpl/firma-pdf/releases/latest/download/FirmaManPla-macos-arm64.dmg) | self-test on its system |

Each package is built on its system and passes its self-test there: on Windows, the workflow installs the `.msi`, runs the installed application and uninstalls it; on macOS, it mounts the `.dmg` and checks the signature of the bundle. The links always lead to the latest version. The SHA-256 hashes of the three packages are in [SHA256SUMS](https://github.com/mmunozpl/firma-pdf/releases/latest/download/SHA256SUMS):

```bash
sha256sum -c --ignore-missing SHA256SUMS
```

The packages are not code-signed, so Windows and macOS warn the first time they are opened:

- **Linux.** The AppImage is a single file: give it execute permission (`chmod +x FirmaManPla-linux-x86_64.AppImage`) and open it. It needs `fusermount3` (package `fuse3`); without it, start it with the `--appimage-extract-and-run` option. Using the browser certificates requires the NSS tools package (`libnss3-tools` on Debian and Ubuntu, which provides `certutil` and `pk12util`). Qt 6 also needs the graphics libraries that any desktop ships (`libegl1`, `libgl1`, `libxkbcommon0`, `libfontconfig1`) and `libxcb-cursor0`; on a minimal installation they may be missing.
- **Windows.** The `.msi` installs the application for the current user, without administrator rights, in `%LOCALAPPDATA%\Programs\FirmaManPla`, with an entry in the Start menu; it is uninstalled from "Installed apps". SmartScreen warns of an unknown publisher: "More info" and "Run anyway". With Windows 11 Smart App Control turned on, the installer does not run.
- **macOS.** Open the `.dmg` and drag `FirmaManPla.app` into Applications. Gatekeeper blocks it the first time. Under System Settings, "Privacy & Security", the "Open Anyway" option appears. The first time it saves a signed file in Documents, the Desktop or Downloads, macOS asks for permission for that folder; if it is denied, the permission is changed under "Privacy & Security › Files and Folders", or another folder is chosen with "Cambiar…". Only for Macs with Apple silicon.

The interface and the signature footer are in Spanish.

## What it does

- Signs PDFs in PAdES-B-B with a certificate installed on the system (Firefox and Chrome NSS on Linux, the personal store on Windows, the keychain on macOS) or with a `.p12` or `.pfx` file.
- Adds to every page a footer with the signer (without the national ID number), the date with its UTC offset, place, identifier, page, reason, reference, certificate issuer and serial number, format and shortened hash of the original, a note with two links for checking the signature (valide.redsara.es and the European Commission DSS validator), and a four-line QR code in UTF-8: "Firma digital", signer, certificate serial number and hash of the original.
- Signs several documents at once, chosen or dragged in: each one separately, next to its original, or merged into a single PDF, with a bookmark per document, which is signed once. Documents that already carry a signature are not merged, since their signature would not carry over to the merged PDF; separately, they receive the added signature. "Comprobar firma" checks every signed file of the batch.
- Adds the signature to a document that arrives already signed (a contract signed by the other party, for example) without modifying its content: the box goes in the lowest blank space of the last page, as the appearance of the new signature field, and states who signed before, from the signatures of the document itself. The earlier signatures remain valid. If the document carries a certification signature that allows no changes, the application refuses.
- Checks the signature locally against AC Raíz FNMT-RCM, with revocation over OCSP, and reports the changes appended after each signature.
- Validates the signature on the computer itself against the EU trusted lists with "Validar con las listas de la UE" (or `firmar.py --ue`), using [pyHanko](https://github.com/MatthiasValvekens/pyHanko): the Commission's list of trusted lists and the national lists it points to (31 in that of 9 November 2026, of which 29 are loaded: see "Limits"), with the signature of each one checked, which are the lists [DSS](https://ec.europa.eu/digital-building-blocks/DSS/webapp-demo/validation), the Commission's validator, uses. It reports whether the certificate chains to a qualified service in those lists, the level of the signature (qualified, advanced based on a qualified certificate or advanced) and whether each time stamp is issued by a qualified time-stamping service. The lists (about 27 MB, kept for a day in the data folder) and the revocation data are downloaded: the document never leaves the computer. The signature can also be validated in [VALIDe](https://valide.redsara.es) and in Autofirma and Adobe Acrobat Reader, which validate locally.
- Keeps a local signing log with the hashes of the original and the signed file.

## From the source code

With Python 3.11 and [uv](https://docs.astral.sh/uv/):

```bash
uv sync --frozen
uv run python firma_gui.py                    # window
uv run python firmar.py --help                # command line
uv run python firmar.py --condiciones         # terms of use
uv run python firmar.py a.pdf b.pdf --p12 cert.p12   # separately
uv run python firmar.py a.pdf b.pdf --unir -o ab.pdf --p12 cert.p12
uv run python firmar.py signed.pdf --ue           # EU trusted lists
uv run python firma_gui.py --autoprueba       # footer, QR, resources, a B-B signature in memory and the EU list readers, no window or network
uv run --group construir python construir.py  # package for this system in dist/
```

PyInstaller only builds for the system it runs on, and `construir.py` then packages its output: the AppImage with appimagetool 1.9.1 and the runtime in `empaquetado/linux`, both pinned by their hash; the `.msi` with WiX 5.0.2 and `empaquetado/windows/Package.wxs`; the `.dmg` with `hdiutil`. The workflow in `.github/workflows/construir.yml` builds the three packages, runs the self-test on each and, when a `v*` version is tagged, publishes the release with its hashes.

## Limits

- It has been tested on Linux with test certificates (signing, an added signature, signing several documents and checking) and with the self-test of each package on its system. On Windows and macOS it has not been tested beyond that self-test, nor with real certificates, and it has not been checked in VALIDe.
- The validation against the EU lists is pyHanko 0.38.1's, not DSS's: it does not load the Czech and Estonian lists, whose servers rejected pyHanko's request on 19 November 2026 (responses 406 and 403), and it leaves out the service entries pyHanko does not interpret (48 with the list of trusted lists of 9 November 2026); each validation states how many lists it loaded and which are missing. It validates at the current time: a certificate that expired after the signature was time-stamped is reported as not valid, and the qualification of the certificate is assessed at the date of validation. pyHanko does not keep the history of the lists, so time stamps from services withdrawn today do not chain and, if the current status of a service began after the time stamp, its qualification at the time of the stamp is reported as not determinable. With a real signature from another Member State that DSS 6.5.1 reports as correct, pyHanko reported it as cryptographically incorrect: a negative result is cross-checked in DSS or VALIDe. Signatures in the `adbe.pkcs7.sha1` format (with SHA-1) are not validated.
- A PAdES-B-B signature does not prove its time: the date in the box and the one the signature declares are set by the computer that signs. While the certificate is in force, it is validated like any PAdES signature; once it expires or is revoked, a validator can no longer report it as valid.
- The QR code authenticates nothing: anyone can generate an identical one. It serves to compare the paper with the signature of the PDF in a validator.
- The private key leaves the store for the memory of the process when it is exportable. It is not confined to its store, and a card or an HSM would not let it out.
- With a certificate kept in the browser or the system, the signature is an advanced signature based on a qualified certificate, not a qualified one: a qualified signature creation device is missing.
- On a document that arrives signed, neither the footer on every page nor the shrinking of the content is applied, since they would invalidate the earlier signatures: the signature carries a single box, which needs a blank space about 3 cm high (or 2 cm, in its compact version, without a QR code). Without that space on any page, the signature is not made.
- Reducing the pages to make room for the footer has not been tested with forms, rotated pages, mixed sizes or PDF/A documents.

## Citation

```bibtex
@software{munozpla_firmamanpla_2026,
  author  = {Muñoz Plá, Manuel},
  title   = {FirmaManPla. Firma de PDF con pie visible y código QR},
  year    = {2026},
  version = {0.3.0},
  url     = {https://github.com/mmunozpl/firma-pdf},
  license = {Apache-2.0}
}
```

## Licence

[Apache-2.0](LICENSE), with the notice in [NOTICE](NOTICE). A proof of concept without warranty or support; for a commercial version, [contact](https://manpla.net/en/contacto). The licence covers the author's code. Qt and PySide6 (LGPL-3.0), the DejaVu Sans font in `recursos/fuentes`, which the box of a signature added to an already signed document uses ([LICENCIA-DejaVu.txt](recursos/fuentes/LICENCIA-DejaVu.txt)), and the other third-party components keep their own, as [LICENCIAS.md](LICENCIAS.md#firmamanpla-licences) details.
