"""Extracción de texto de notas de entrega en PDF o imagen.

El resultado es una lista de páginas con líneas y, cuando la página se
reconoció por OCR, con las coordenadas de cada palabra. El parser común
vive en ``services.nota_parser``.
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

MAX_BYTES_NOTA = 20 * 1024 * 1024
MAX_PAGINAS = 20
MIN_CARACTERES_PDF = 80
TESSERACT_TIMEOUT = 90


class NotaInvalida(ValueError):
    """El archivo no es una nota legible."""


def _es_pdf(contenido: bytes, filename: str) -> bool:
    if contenido[:5] == b"%PDF-":
        return True
    return (filename or "").lower().endswith(".pdf")


def _abrir_imagen(contenido: bytes) -> Image.Image:
    try:
        imagen = Image.open(io.BytesIO(contenido))
        imagen.load()
    except Exception as exc:  # pragma: no cover - depende del archivo
        raise NotaInvalida(
            "El archivo no es una imagen válida. Usa PNG, JPG o PDF."
        ) from exc

    imagen = ImageOps.exif_transpose(imagen)
    if imagen.mode not in ("L", "RGB"):
        imagen = imagen.convert("RGB")
    return imagen


def _preparar_imagen(imagen: Image.Image) -> Image.Image:
    """Normaliza el tamaño sin alterar el contraste original."""
    if imagen.width < 1400:
        factor = 1400 / imagen.width
        imagen = imagen.resize(
            (int(imagen.width * factor), int(imagen.height * factor)),
            Image.LANCZOS,
        )
    elif imagen.width > 4800:
        factor = 4800 / imagen.width
        imagen = imagen.resize(
            (int(imagen.width * factor), int(imagen.height * factor)),
            Image.LANCZOS,
        )

    return imagen.convert("RGB")


def _ocr_tokens(imagen: Image.Image) -> dict[str, Any]:
    """Ejecuta Tesseract y devuelve tokens y líneas de una página."""
    if not shutil.which("tesseract"):
        raise NotaInvalida(
            "No está instalado Tesseract, necesario para leer fotos y PDF "
            "escaneados."
        )

    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "pagina.png"
        _preparar_imagen(imagen).save(ruta, format="PNG")

        comando = [
            "tesseract",
            str(ruta),
            "stdout",
            "--psm",
            "3",
            "-l",
            "spa+eng",
            "tsv",
        ]
        try:
            proceso = subprocess.run(
                comando,
                capture_output=True,
                timeout=TESSERACT_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise NotaInvalida(
                "El OCR tardó demasiado. Intenta con una foto más liviana."
            ) from exc

    if proceso.returncode != 0 or not proceso.stdout:
        detalle = proceso.stderr.decode("utf-8", "replace").strip()
        raise NotaInvalida(
            "No se pudo leer la imagen con OCR."
            + (f" Detalle: {detalle[:160]}" if detalle else "")
        )

    salida = proceso.stdout.decode("utf-8", "replace")
    lector = csv.reader(io.StringIO(salida), delimiter="\t")
    tokens: list[dict[str, Any]] = []
    lineas: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for fila in lector:
        if len(fila) < 12 or fila[0] != "5":
            continue
        try:
            conf = float(fila[10])
        except ValueError:
            continue
        texto = fila[11].strip()
        if conf <= 0 or not texto:
            continue

        x = int(fila[6])
        y = int(fila[7])
        ancho = int(fila[8])
        alto = int(fila[9])
        clave = (fila[1], fila[2], fila[3], fila[4])
        token = {
            "texto": texto,
            "x": x,
            "y": y,
            "x1": x + ancho,
            "y1": y + alto,
            "conf": conf,
        }
        tokens.append(token)
        linea = lineas.setdefault(
            clave,
            {"tokens": [], "x0": x, "x1": x + ancho, "y": y, "y1": y + alto},
        )
        linea["tokens"].append(token)
        linea["x0"] = min(linea["x0"], x)
        linea["x1"] = max(linea["x1"], x + ancho)
        linea["y"] = min(linea["y"], y)
        linea["y1"] = max(linea["y1"], y + alto)

    for linea in lineas.values():
        linea["tokens"].sort(key=lambda item: item["x"])
        linea["texto"] = " ".join(item["texto"] for item in linea["tokens"])

    return {
        "ancho": imagen.width,
        "alto": imagen.height,
        "tokens": tokens,
        "lineas": sorted(lineas.values(), key=lambda item: item["y"]),
    }


def _lineas_pdf_texto(texto: str) -> list[dict[str, Any]]:
    lineas = []
    for indice, cruda in enumerate(texto.splitlines()):
        limpia = " ".join(cruda.split())
        if not limpia:
            continue
        lineas.append(
            {
                "texto": limpia,
                "tokens": [],
                "x0": 0,
                "x1": 0,
                "y": float(indice),
                "y1": float(indice),
            }
        )
    return lineas


def _paginas_pdf(contenido: bytes) -> list[dict[str, Any]]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover
        raise NotaInvalida(
            "Falta la dependencia pypdfium2 para leer PDF."
        ) from exc

    try:
        documento = pdfium.PdfDocument(contenido)
    except Exception as exc:
        raise NotaInvalida("El PDF no se pudo abrir.") from exc

    try:
        total_paginas = len(documento)
    except Exception as exc:
        documento.close()
        raise NotaInvalida("El PDF no se pudo leer.") from exc

    if total_paginas < 1:
        documento.close()
        raise NotaInvalida("El PDF no tiene páginas.")
    if total_paginas > MAX_PAGINAS:
        documento.close()
        raise NotaInvalida(
            f"La nota supera el máximo de {MAX_PAGINAS} páginas."
        )

    paginas = []
    try:
        for numero in range(total_paginas):
            pagina = documento[numero]
            texto = ""
            try:
                texto = pagina.get_textpage().get_text_range()
            except Exception:
                texto = ""

            if len(texto.strip()) >= MIN_CARACTERES_PDF:
                paginas.append(
                    {
                        "numero": numero + 1,
                        "origen": "pdf_texto",
                        "ancho": 0,
                        "alto": 0,
                        "tokens": [],
                        "lineas": _lineas_pdf_texto(texto),
                    }
                )
                continue

            imagen = pagina.render(scale=2.5).to_pil()
            datos = _ocr_tokens(imagen)
            datos.update({"numero": numero + 1, "origen": "ocr"})
            paginas.append(datos)
    finally:
        documento.close()

    return paginas


def extraer_paginas(contenido: bytes, filename: str = "") -> list[dict[str, Any]]:
    """Convierte una nota en páginas con texto y coordenadas."""
    if not contenido:
        raise NotaInvalida("El archivo está vacío.")
    if len(contenido) > MAX_BYTES_NOTA:
        raise NotaInvalida("El archivo supera el tamaño permitido.")

    if _es_pdf(contenido, filename):
        return _paginas_pdf(contenido)

    imagen = _abrir_imagen(contenido)
    datos = _ocr_tokens(imagen)
    datos.update({"numero": 1, "origen": "ocr"})
    return [datos]


def extraer_nota_archivos(
    archivos: list[tuple[bytes, str]],
) -> dict[str, Any]:
    """Extrae y estructura una nota formada por uno o más archivos.

    Cada archivo puede ser una foto de una página o un PDF de varias
    páginas. Las páginas se procesan en el orden recibido para que un
    producto pueda continuar en el archivo siguiente.
    """
    if not archivos:
        raise NotaInvalida("No se recibió ningún archivo.")

    total = sum(len(contenido) for contenido, _ in archivos)
    if total > MAX_BYTES_NOTA:
        raise NotaInvalida(
            "La nota supera el tamaño permitido de 20 MB en total."
        )

    from services.nota_parser import parsear_paginas

    paginas: list[dict[str, Any]] = []
    for contenido, nombre in archivos:
        paginas.extend(extraer_paginas(contenido, nombre))
        if len(paginas) > MAX_PAGINAS:
            raise NotaInvalida(
                f"La nota supera el máximo de {MAX_PAGINAS} páginas."
            )

    for indice, pagina in enumerate(paginas, start=1):
        pagina["numero"] = indice

    resultado = parsear_paginas(paginas)
    resultado["paginas"] = len(paginas)
    nombres = [nombre for _, nombre in archivos if nombre]
    resultado["archivo"] = ", ".join(nombres)[:255]
    return resultado


def extraer_nota(contenido: bytes, filename: str = "") -> dict[str, Any]:
    """Extrae y estructura los productos de un único archivo."""
    return extraer_nota_archivos([(contenido, filename)])
