"""Parser común para notas de entrega (OCR o PDF con texto).

La nota lista un bloque de encabezado por producto (código, descripción y
cantidad) seguido de una columna de seriales. Un producto nuevo comienza
cuando aparece otro encabezado después de los seriales del anterior. Si una
página termina en medio de un grupo, los seriales de la página siguiente se
agregan al último producto.
"""

from __future__ import annotations

import difflib
import re
import statistics
import unicodedata
from typing import Any

TIPOS = {
    "LAPTOP",
    "MEMORIA",
    "MONITOR",
    "IMPRESORA",
    "TABLET",
    "DESKTOP",
    "SERVIDOR",
    "PROYECTOR",
    "NOTEBOOK",
    "COMPUTADORA",
    "TODO EN UNO",
    "ALL IN ONE",
}

FAMILIAS = {
    "PROBOOK",
    "ELITEBOOK",
    "THINKPAD",
    "IDEAPAD",
    "LATITUDE",
    "INSPIRON",
    "VOSTRO",
    "MACBOOK",
    "PAVILION",
    "VICTUS",
    "ASPIR",
    "SWIFT",
    "NITRO",
    "PREDATOR",
    "TUF",
    "ROG",
    "ZENBOOK",
    "VIVOBOOK",
    "EXPERTBOOK",
}

MARCAS = [
    "WESTERN DIGITAL",
    "KINGSTON",
    "LENOVO",
    "SAMSUNG",
    "MICROSOFT",
    "TOSHIBA",
    "BROTHER",
    "LOGITECH",
    "KENSINGTON",
    "EPSON",
    "CANON",
    "APPLE",
    "HUAWEI",
    "XIAOMI",
    "DELL",
    "ACER",
    "ASUS",
    "HP",
    "LG",
]

MARCAS_ESCRITAS = {
    "HP": "HP",
    "LG": "LG",
    "ASUS": "ASUS",
    "ACER": "Acer",
    "DELL": "Dell",
    "LENOVO": "Lenovo",
    "KINGSTON": "Kingston",
    "SAMSUNG": "Samsung",
    "APPLE": "Apple",
    "EPSON": "Epson",
    "CANON": "Canon",
    "BROTHER": "Brother",
    "HUAWEI": "Huawei",
    "XIAOMI": "Xiaomi",
    "TOSHIBA": "Toshiba",
    "MICROSOFT": "Microsoft",
    "LOGITECH": "Logitech",
    "KENSINGTON": "Kensington",
    "WESTERN DIGITAL": "Western Digital",
}

PALABRAS_IGNORADAS = {
    "LAPTOP",
    "MEMORIA",
    "MONITOR",
    "IMPRESORA",
    "TABLET",
    "DESKTOP",
    "SERVIDOR",
    "PROYECTOR",
    "NOTEBOOK",
    "COMPUTADORA",
    "HP",
    "UND",
    "UNIDAD",
    "UNIDADES",
    "CANTIDAD",
    "DESCRIPCION",
    "DESCRIPCIÓN",
    "ARTICULO",
    "ARTÍCULO",
    "PRECIO",
    "UNITARIO",
    "TOTAL",
    "BS",
    "SSD",
    "HDD",
    "NVME",
    "DDR3",
    "DDR4",
    "DDR5",
    "WINDOWS",
    "WIND",
    "WINE",
    "PRO",
    "HOME",
    "GB",
    "TB",
    "MT/S",
}

# Tokens que sí aportan a la descripción al fusionar filas, aunque no
# contengan dígitos.
TOKENS_EXTRA = (
    TIPOS
    | FAMILIAS
    | {marca.upper() for marca in MARCAS}
    | {
        "AMD",
        "INTEL",
        "CORE",
        "ULTRA",
        "RYZEN",
        "CELERON",
        "ATHLON",
        "SSD",
        "HDD",
        "NVME",
        "EMMC",
        "WINDOWS",
        "WIND",
        "WINE",
        "AI",
        "AL",
        "GB",
        "TB",
        "DDR3",
        "DDR4",
        "DDR5",
        "MT/S",
        "PRO",
        "HOME",
    }
)

PATRON_CODIGO = re.compile(r"[A-Z0-9]{4,}#[A-Z0-9]{2,}")
PATRON_CODIGO_GUION = re.compile(r"^[A-Z]{2,}[A-Z0-9]*-\d+$")
PATRON_SERIAL_HP = re.compile(r"^[5S]CD[0-9A-Z]{6,9}$")
PATRON_SERIAL = re.compile(r"^[A-Z0-9]{8,20}$")
PATRON_PROCESADOR = re.compile(
    r"\b(?:INTEL\s+CORE\s+)?(?:ULTRA\s+)?([IU])([3579])"
    r"(?:-|\s+)(\d{3,4}[A-Z]{0,2})\b"
)
PATRON_RYZEN = re.compile(r"\bRYZEN\s+([3579])\s+(\d{4}[A-Z]{0,2})\b")
PATRON_RAM = re.compile(
    r"\b(\d{1,3})\s*GB"
    r"(?:\s*\(\s*(\d+)\s*[Xx]\s*(\d+)\s*GB\s*\))?"
    r"(?:\s*(DDR[345]))?"
    r"(?:\s*(\d{3,5})\s*MT/S)?",
    re.IGNORECASE,
)
PATRON_ALMACENAMIENTO = re.compile(
    r"\b(?:\d{3,4}\s*GB|\d\s*TB)\s*(?:SSD|HDD|NVME|EMMC|M\.2)\b",
    re.IGNORECASE,
)


def _sin_acentos(texto: str) -> str:
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )


def _limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").replace("\ufeff", "")).strip()


def _limpiar_token(texto: str) -> str:
    return re.sub(r"^[^A-Za-z0-9(]+|[^A-Za-z0-9)\"]+$", "", texto or "")


def _normalizar_serial(texto: str) -> tuple[str, list[str]]:
    advertencias: list[str] = []
    serial = _limpiar_token(texto).upper()
    if serial.startswith("SCD") and PATRON_SERIAL_HP.match(serial):
        serial = "5" + serial[1:]
        advertencias.append("Se corrigió el prefijo SCD por 5CD.")
    if serial.startswith("5CD") and len(serial) > 10:
        recortado = serial[:10]
        advertencias.append(
            f"Se recortó el S/N {serial} a {recortado} por un carácter "
            "sobrante del OCR."
        )
        serial = recortado
    if (
        serial.startswith("5CD")
        and len(serial) >= 4
        and not serial[3].isdigit()
    ):
        advertencias.append(
            f"El S/N {serial} tiene un carácter no numérico después de 5CD; "
            "revisa el OCR."
        )
    return serial, advertencias


def _es_serial(texto: str) -> bool:
    serial = _limpiar_token(texto).upper()
    if not PATRON_SERIAL.fullmatch(serial):
        return False
    if not re.search(r"[A-Z]", serial) or not re.search(r"\d", serial):
        return False
    if serial in PALABRAS_IGNORADAS:
        return False
    if any(
        palabra in serial
        for palabra in (
            "LAPTOP",
            "PROBOOK",
            "MEMORIA",
            "KINGSTON",
            "DISCO",
            "PRECIO",
            "TOTAL",
            "CANTIDAD",
            "DESCRIPCION",
            "ARTICULO",
            "ENTREGA",
            "PEDIDO",
            "COTIZACION",
            "EMISION",
            "CLIENTE",
            "VENDEDOR",
            "ORDEN",
            "COMPRA",
            "WINDOWS",
        )
    ):
        return False
    return True


def _es_probable_serial(token: dict[str, Any], ancho: int) -> bool:
    texto = _limpiar_token(token["texto"]).upper()
    if not texto:
        return False
    x = token["x"] / ancho if ancho else 0
    if x < 0.20 or x > 0.60:
        return False
    return _es_serial(texto)


def _token_header(texto: str) -> bool:
    limpio = _sin_acentos(_limpiar_token(texto).upper())
    return limpio in TIPOS or limpio in FAMILIAS


def _fila_header(fila: dict[str, Any], ancho: int) -> bool:
    if not fila.get("tokens"):
        return False
    for token in fila["tokens"]:
        if _token_header(token["texto"]):
            if ancho and token["x"] > 0.70 * ancho:
                continue
            return True

    # Respaldo: algunas fotos pierden la palabra del tipo de producto, pero
    # la fila conserva la cantidad "UND" y la descripción en la columna
    # central. Las filas de seriales no traen "UND".
    if not ancho:
        return False
    tiene_und = any(
        _limpiar_token(token["texto"]).upper() == "UND"
        and token["x"] > 0.58 * ancho
        for token in fila["tokens"]
    )
    if not tiene_und:
        return False
    utiles = [
        token
        for token in fila["tokens"]
        if 0.17 * ancho <= token["x"] <= 0.62 * ancho
        and _limpiar_token(token["texto"])
        and not _es_serial(_limpiar_token(token["texto"]).upper())
    ]
    return len(utiles) >= 2


def _tokens_modelo(fila: dict[str, Any]) -> set[str]:
    tokens = set()
    for token in fila["tokens"]:
        limpio = _sin_acentos(_limpiar_token(token["texto"]).upper())
        if len(limpio) < 3 or limpio in PALABRAS_IGNORADAS:
            continue
        if re.fullmatch(r"\d+", limpio):
            continue
        tokens.add(limpio)
    return tokens


def _agrupar_headers(filas: list[dict[str, Any]], ancho: int) -> list[dict[str, Any]]:
    candidatos = [fila for fila in filas if _fila_header(fila, ancho)]
    grupos: list[dict[str, Any]] = []
    for fila in candidatos:
        modelo = _tokens_modelo(fila)
        if grupos:
            ultimo = grupos[-1]
            distancia = fila["y"] - ultimo["y1"]
            if distancia <= 130 and modelo & ultimo["modelo"]:
                ultimo["filas"].append(fila)
                ultimo["modelo"] |= modelo
                ultimo["y1"] = max(ultimo["y1"], fila["y1"])
                ultimo["y"] = min(ultimo["y"], fila["y"])
                continue
        grupos.append(
            {
                "filas": [fila],
                "modelo": set(modelo),
                "y": fila["y"],
                "y1": fila["y1"],
            }
        )
    return grupos


def _tokens_utiles(fila: dict[str, Any], ancho: int) -> list[str]:
    """Tokens de la columna de descripción, sin código ni cantidad/precio."""
    utiles = []
    for token in fila["tokens"]:
        if ancho and (token["x"] < 0.17 * ancho or token["x"] > 0.62 * ancho):
            continue
        texto = _limpiar_token(token["texto"]).upper()
        if not texto:
            continue
        if texto in {"UND", "BS", "0.00", "TOTAL", "UNITARIO", "PRECIO"}:
            continue
        if "#" in texto and len(texto) > 8:
            continue
        if texto.isdigit() and int(texto) > 17:
            continue
        utiles.append(texto)
    return utiles


def _puntaje_fila(tokens: list[str]) -> float:
    texto = " ".join(tokens)
    puntaje = len(tokens) * 0.1
    if any(token in TIPOS for token in tokens):
        puntaje += 10
    if any(token in FAMILIAS for token in tokens):
        puntaje += 20
    if _marca(texto):
        puntaje += 10
    if _procesador(texto):
        puntaje += 8
    if _ram(texto):
        puntaje += 12
    if PATRON_ALMACENAMIENTO.search(texto):
        puntaje += 8
    if re.search(r"\bG\d{1,2}[A-Z]?\b", texto):
        puntaje += 20
    return puntaje


def _fusionar_tokens(base: list[str], extra: list[str]) -> list[str]:
    """Agrega a ``base`` los tokens de ``extra`` que faltan, conservando orden."""
    resultado = list(base)
    matcher = difflib.SequenceMatcher(None, base, extra)
    desplazamiento = 0
    for etiqueta, i1, i2, j1, j2 in matcher.get_opcodes():
        if etiqueta in ("insert", "replace"):
            faltantes = [
                token
                for token in extra[j1:j2]
                if token not in resultado
                and (any(caracter.isdigit() for caracter in token) or token in TOKENS_EXTRA)
            ]
            if faltantes:
                posicion = i2 + desplazamiento
                resultado[posicion:posicion] = faltantes
                desplazamiento += len(faltantes)
    return resultado


def _descripcion_grupo(grupo: dict[str, Any], ancho: int) -> str:
    filas_tokens = [
        _tokens_utiles(fila, ancho) for fila in grupo["filas"]
    ]
    filas_tokens = [tokens for tokens in filas_tokens if tokens]
    if not filas_tokens:
        return ""

    base = max(filas_tokens, key=_puntaje_fila)
    for tokens in filas_tokens:
        if tokens is base:
            continue
        base = _fusionar_tokens(base, tokens)

    texto = " ".join(base)
    texto = re.sub(r"\b\d{1,4}\s+UND\b", " ", texto)
    texto = re.sub(r"\bUND\b", " ", texto)
    texto = re.sub(r"\bBS\.?\s*0\.?00\b", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()

    texto = re.sub(r"\bG2(?=[\s!]|$)", "G2I", texto)
    if "PROBOOK" in texto:
        texto = re.sub(r"\bG21\b", "G2I", texto)
    texto = re.sub(r"\bG2I\s+14\s+AL\b", "G2I 14 AI", texto)

    if ("PROBOOK" in texto or "ELITEBOOK" in texto) and "LAPTOP" not in texto:
        texto = "LAPTOP " + texto
    texto = re.sub(r"\bLAPTOP\b\s+.*?\bHP\b\s*(?=PROBOOK\b)", "LAPTOP HP ", texto)
    texto = re.sub(r"\bLAPTOP\b\s+(?!HP\b).*?(?=PROBOOK\b)", "LAPTOP ", texto)
    if "HP" in texto:
        texto = re.sub(r"\bLAPTOP\s+(?=PROBOOK\b)", "LAPTOP HP ", texto)
        texto = re.sub(r"\bLAPTOP\s+P\s+(?=PROBOOK\b)", "LAPTOP HP ", texto)
    texto = re.sub(r"^P\s+(?=PROBOOK\b)", "HP ", texto)
    texto = re.sub(r"\s+P\s+(?=PROBOOK\b)", " HP ", texto)
    if texto.startswith("HP PROBOOK") and "LAPTOP" not in texto:
        texto = "LAPTOP " + texto
    if texto.endswith(" HP"):
        texto = texto[:-3].strip()

    texto = re.sub(r"^[A-Z0-9#\-]+?(?=(?:LAPTOP|MEMORIA|MONITOR|IMPRESORA|"
                   r"TABLET|DESKTOP|SERVIDOR|PROYECTOR|NOTEBOOK|"
                   r"COMPUTADORA|ALL IN ONE))", "", texto)
    return _limpiar(texto)


def _marca(texto: str) -> str:
    for marca in MARCAS:
        if re.search(rf"\b{re.escape(marca)}\b", texto):
            return MARCAS_ESCRITAS[marca]
    return ""


def _procesador(texto: str) -> str:
    coincidencia = PATRON_PROCESADOR.search(texto)
    if coincidencia:
        familia, generacion, numero = coincidencia.groups()
        if familia == "U":
            return f"Intel Core Ultra {generacion} {numero}".strip()
        return f"Intel Core i{generacion}-{numero}".strip()

    coincidencia = PATRON_RYZEN.search(texto)
    if coincidencia:
        generacion, numero = coincidencia.groups()
        return f"AMD Ryzen {generacion} {numero}".strip()

    if re.search(r"\bCELERON\b", texto):
        return "Intel Celeron"
    if re.search(r"\bATHLON\b", texto):
        return "AMD Athlon"
    return ""


def _ram(texto: str) -> str:
    for coincidencia in PATRON_RAM.finditer(texto):
        inicio, fin = coincidencia.span()
        despues = texto[fin : fin + 8].upper()
        antes = texto[max(0, inicio - 8) : inicio].upper()
        if re.match(r"\s*(SSD|HDD|NVME|EMMC)", despues):
            continue
        if re.search(r"(SSD|DISCO|ALMACENAMIENTO)\s*$", antes):
            continue

        total, cantidad, tamano, generacion, velocidad = coincidencia.groups()
        partes = [f"{total}GB"]
        if cantidad and tamano:
            partes.append(f"({cantidad.lower()}x{tamano}GB)")
        elif generacion:
            partes.append(generacion.upper())
            if velocidad:
                partes.append(f"{velocidad}MT/S")
        return " ".join(partes)
    return ""


def _modelo(texto: str, marca: str) -> str:
    resto = texto
    if marca:
        resto = re.sub(
            rf"\b{re.escape(marca.upper())}\b", " ", resto, count=1
        )
    sin_marca = _limpiar(resto)

    cortes = []
    for patron in (PATRON_PROCESADOR, PATRON_RYZEN, PATRON_RAM):
        coincidencia = patron.search(sin_marca)
        if coincidencia:
            cortes.append(coincidencia.start())
    almacenamiento = PATRON_ALMACENAMIENTO.search(sin_marca)
    if almacenamiento:
        cortes.append(almacenamiento.start())
    corte_pantalla = re.search(r"\b\d{2}(?:\.\d)?\"", sin_marca)
    if corte_pantalla:
        cortes.append(corte_pantalla.start())

    if cortes:
        resto = sin_marca[: min(cortes)]
    else:
        resto = sin_marca
    resto = _limpiar(resto)
    resto = re.sub(
        r"^(?:LAPTOP|MEMORIA|MONITOR|IMPRESORA|TABLET|DESKTOP|SERVIDOR|"
        r"PROYECTOR|NOTEBOOK|COMPUTADORA|ALL IN ONE|TODO EN UNO)\s+",
        "",
        resto,
    )
    if not resto or resto in TIPOS:
        resto = re.sub(
            r"^(?:LAPTOP|MEMORIA|MONITOR|IMPRESORA|TABLET|DESKTOP|SERVIDOR|"
            r"PROYECTOR|NOTEBOOK|COMPUTADORA|ALL IN ONE|TODO EN UNO)\s+",
            "",
            sin_marca,
        )
    resto = re.sub(r"[#\-]+$", "", resto).strip()
    if "PROBOOK" in resto:
        resto = re.sub(r"\bG21\b", "G2I", resto)
    resto = re.sub(r"\bG2I\s+14\s+AL\b", "G2i 14 AI", resto, flags=re.IGNORECASE)
    resto = re.sub(r"\bG2I\b", "G2i", resto)
    return _limpiar(resto)


def parsear_descripcion(texto: str) -> dict[str, str]:
    limpio = _limpiar((texto or "").upper())
    marca = _marca(limpio)
    return {
        "descripcion": limpio,
        "marca": marca,
        "modelo": _modelo(limpio, marca),
        "procesador": _procesador(limpio),
        "ram": _ram(limpio),
    }


def _codigo_limpio(texto: str) -> str:
    token = _limpiar_token(texto).upper()
    if not token:
        return ""
    coincidencia = PATRON_CODIGO.search(token)
    if coincidencia:
        return coincidencia.group(0)
    if PATRON_CODIGO_GUION.fullmatch(token):
        return token
    for palabra in (
        "LAPTOP",
        "MEMORIA",
        "MONITOR",
        "IMPRESORA",
        "TABLET",
        "DESKTOP",
        "SERVIDOR",
        "PROYECTOR",
        "NOTEBOOK",
        "COMPUTADORA",
    ):
        posicion = token.find(palabra)
        if posicion > 0:
            token = token[:posicion]
            break
    return token


def _mejor_codigo(
    tokens: list[dict[str, Any]], grupo: dict[str, Any], ancho: int
) -> str:
    candidatos = []
    for token in tokens:
        if token["x"] > 0.25 * ancho:
            continue
        texto = _limpiar_token(token["texto"]).upper()
        if len(texto) < 6:
            continue
        if not re.search(r"[A-Z]{2,}", texto) or not re.search(r"\d", texto):
            continue
        if texto in PALABRAS_IGNORADAS:
            continue
        if re.fullmatch(r"[\d\-.]+", texto):
            continue
        if token["y"] < grupo["y"] - 90 or token["y"] > grupo["y1"] + 90:
            continue
        codigo = _codigo_limpio(texto)
        if not codigo or len(codigo) < 5:
            continue
        if grupo["y"] <= token["y"] <= grupo["y1"]:
            distancia = 0
        else:
            distancia = min(
                abs(token["y"] - grupo["y"]),
                abs(token["y"] - grupo["y1"]),
            )
        candidatos.append((distancia, len(codigo), -token["conf"], codigo))
    if not candidatos:
        return ""
    candidatos.sort()
    return candidatos[0][3]


def _detectar_cantidades(tokens: list[dict[str, Any]], ancho: int) -> list[dict[str, Any]]:
    cantidades = []
    for token in tokens:
        if _limpiar_token(token["texto"]).upper() != "UND":
            continue
        if token["x"] < 0.58 * ancho:
            continue
        centro = (token["y"] + token["y1"]) / 2
        mejor = None
        for numero in tokens:
            if not re.fullmatch(r"\d{1,4}", _limpiar_token(numero["texto"])):
                continue
            if numero["x"] >= token["x"]:
                continue
            if token["x"] - numero["x1"] > 120:
                continue
            centro_numero = (numero["y"] + numero["y1"]) / 2
            if abs(centro_numero - centro) > 28:
                continue
            if mejor is None or numero["x"] > mejor["x"]:
                mejor = numero
        if mejor is not None:
            cantidades.append(
                {
                    "cantidad": int(_limpiar_token(mejor["texto"])),
                    "y": (mejor["y"] + mejor["y1"]) / 2,
                }
            )
    return cantidades


def _bloques_seriales(
    seriales: list[dict[str, Any]],
    headers: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    if not seriales:
        return []
    ordenados = sorted(seriales, key=lambda item: item["y"])
    separaciones = [
        ordenados[i + 1]["y"] - ordenados[i]["y"]
        for i in range(len(ordenados) - 1)
        if ordenados[i + 1]["y"] > ordenados[i]["y"]
    ]
    base = statistics.median(separaciones) if separaciones else 50
    umbral = max(110.0, base * 2.5)
    posiciones_header = [header["y"] for header in headers]

    bloques = [[ordenados[0]]]
    for anterior, actual in zip(ordenados, ordenados[1:]):
        salto = actual["y"] - anterior["y"]
        cruza_header = any(
            anterior["y"] < posicion <= actual["y"]
            for posicion in posiciones_header
        )
        if salto > umbral or cruza_header:
            bloques.append([actual])
        else:
            bloques[-1].append(actual)
    return bloques


def _item_desde_header(
    grupo: dict[str, Any], tokens: list[dict[str, Any]], ancho: int
) -> dict[str, Any]:
    campos = parsear_descripcion(_descripcion_grupo(grupo, ancho))
    return {
        "codigo": _mejor_codigo(tokens, grupo, ancho),
        "descripcion": campos["descripcion"],
        "marca": campos["marca"],
        "modelo": campos["modelo"],
        "procesador": campos["procesador"],
        "ram": campos["ram"],
        "cantidad": None,
        "seriales": [],
        "advertencias": [],
    }


def _agregar_seriales(item: dict[str, Any], seriales: list[dict[str, Any]]) -> None:
    for registro in seriales:
        if registro["serial"] not in item["seriales"]:
            item["seriales"].append(registro["serial"])
        if registro.get("advertencias"):
            item["advertencias"].extend(registro["advertencias"])
        if registro.get("conf", 100) < 60:
            item["advertencias"].append(
                f"El S/N {registro['serial']} tiene baja confianza de OCR; "
                "revisa el último carácter."
            )


def _asignar_cantidades(
    items: list[dict[str, Any]],
    headers: list[dict[str, Any]],
    cantidades: list[dict[str, Any]],
) -> None:
    for registro in cantidades:
        mejor = None
        mejor_distancia = None
        for item, header in zip(items, headers):
            if header["y"] - 60 <= registro["y"] <= header["y1"] + 80:
                distancia = abs(registro["y"] - header["y"])
            else:
                distancia = min(
                    abs(registro["y"] - header["y"]),
                    abs(registro["y"] - header["y1"]),
                )
            if mejor is None or distancia < mejor_distancia:
                mejor = item
                mejor_distancia = distancia
        if mejor is not None and mejor_distancia is not None and mejor_distancia <= 160:
            mejor["cantidad"] = registro["cantidad"]


def _parsear_pagina_ocr(
    pagina: dict[str, Any],
    estado: dict[str, Any],
) -> list[dict[str, Any]]:
    tokens = pagina["tokens"]
    ancho = pagina["ancho"] or 1
    filas = sorted(pagina.get("lineas", []), key=lambda fila: fila["y"])

    inicio_tabla = 0.0
    for fila in filas:
        texto = _sin_acentos(fila.get("texto", "").upper())
        if "DESCRIPCION" in texto and (
            "ARTICULO" in texto or "CANTIDAD" in texto or "UNIDAD" in texto
        ):
            inicio_tabla = fila["y"]
            break
        if "N DE ARTICULO" in texto or "N° DE ARTICULO" in texto:
            inicio_tabla = fila["y"]
            break

    filas_tabla = [fila for fila in filas if fila["y"] >= inicio_tabla - 5]
    headers = _agrupar_headers(filas_tabla, ancho)

    seriales: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for token in tokens:
        if token["y"] < inicio_tabla - 5:
            continue
        if not _es_probable_serial(token, ancho):
            continue
        serial, advertencias = _normalizar_serial(token["texto"])
        if not _es_serial(serial):
            continue
        if serial in vistos:
            continue
        vistos.add(serial)
        seriales.append(
            {
                "serial": serial,
                "y": (token["y"] + token["y1"]) / 2,
                "conf": token["conf"],
                "advertencias": advertencias,
            }
        )

    items_pagina = [
        _item_desde_header(grupo, tokens, ancho) for grupo in headers
    ]
    bloques = _bloques_seriales(seriales, headers)

    ultimo_con_seriales: dict[str, Any] | None = None
    for bloque in bloques:
        primera_y = bloque[0]["y"]
        candidatos = [
            (indice, header)
            for indice, header in enumerate(headers)
            if header["y"] <= primera_y + 30
        ]
        if candidatos:
            indice, _ = max(candidatos, key=lambda par: par[1]["y"])
            _agregar_seriales(items_pagina[indice], bloque)
            ultimo_con_seriales = items_pagina[indice]
        elif estado.get("ultimo") is not None:
            _agregar_seriales(estado["ultimo"], bloque)
            ultimo_con_seriales = estado["ultimo"]
        else:
            item = {
                "codigo": "",
                "descripcion": "Producto sin encabezado detectado",
                "marca": "",
                "modelo": "",
                "procesador": "",
                "ram": "",
                "cantidad": None,
                "seriales": [],
                "advertencias": [
                    "No se encontró el encabezado del producto para estos "
                    "seriales."
                ],
            }
            _agregar_seriales(item, bloque)
            items_pagina.append(item)
            ultimo_con_seriales = item

    _asignar_cantidades(
        items_pagina, headers, _detectar_cantidades(tokens, ancho)
    )

    if ultimo_con_seriales is not None:
        estado["ultimo"] = ultimo_con_seriales
    elif items_pagina:
        estado["ultimo"] = items_pagina[-1]

    return items_pagina


def _codigo_de_linea(texto: str) -> str:
    """Extrae el código de artículo del inicio de una línea de PDF."""
    for token in texto.split():
        limpio = _limpiar_token(token).upper()
        if not limpio:
            continue
        if _token_header(limpio):
            break
        codigo = _codigo_limpio(limpio)
        if (
            len(codigo) >= 5
            and re.search(r"[A-Z]", codigo)
            and re.search(r"\d", codigo)
        ):
            return codigo
    return ""


def _quitar_columnas_texto(texto: str) -> str:
    """Quita cantidad y precios de una línea de PDF con texto."""
    limpio = re.sub(
        r"\bBs\.?\s*[\d.,]+\b", " ", texto, flags=re.IGNORECASE
    )
    limpio = re.sub(
        r"\b\d{1,4}\s+UND\b.*$", " ", limpio, flags=re.IGNORECASE
    )
    limpio = re.sub(r"\bUND\b.*$", " ", limpio, flags=re.IGNORECASE)
    return _limpiar(limpio)


def _parsear_pagina_texto(
    pagina: dict[str, Any],
    estado: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    actual: dict[str, Any] | None = None

    for linea in pagina["lineas"]:
        texto = _limpiar(linea["texto"])
        if not texto:
            continue
        mayusculas = _sin_acentos(texto.upper())

        tokens = texto.split()
        seriales_linea = [
            token
            for token in tokens
            if _es_serial(_normalizar_serial(token)[0])
        ]

        es_header = any(
            re.search(rf"\b{re.escape(palabra)}\b", mayusculas)
            for palabra in TIPOS | FAMILIAS
        )
        if es_header:
            codigo = _codigo_de_linea(texto)
            descripcion = _quitar_columnas_texto(texto)
            if codigo:
                descripcion = re.sub(
                    rf"^{re.escape(codigo)}\s*",
                    "",
                    descripcion,
                    flags=re.IGNORECASE,
                )
            campos = parsear_descripcion(descripcion)
            actual = {
                "codigo": codigo,
                "descripcion": campos["descripcion"],
                "marca": campos["marca"],
                "modelo": campos["modelo"],
                "procesador": campos["procesador"],
                "ram": campos["ram"],
                "cantidad": None,
                "seriales": [],
                "advertencias": [],
            }
            items.append(actual)

        if seriales_linea:
            destino = actual or estado.get("ultimo")
            if destino is None:
                destino = {
                    "codigo": "",
                    "descripcion": "Producto sin encabezado detectado",
                    "marca": "",
                    "modelo": "",
                    "procesador": "",
                    "ram": "",
                    "cantidad": None,
                    "seriales": [],
                    "advertencias": [],
                }
                items.append(destino)
            for token in seriales_linea:
                serial, advertencias = _normalizar_serial(token)
                if serial not in destino["seriales"]:
                    destino["seriales"].append(serial)
                destino["advertencias"].extend(advertencias)
            actual = destino

        cantidad = re.search(r"\b(\d{1,4})\s+UND\b", mayusculas)
        if cantidad and actual is not None:
            actual["cantidad"] = int(cantidad.group(1))

    if actual is not None:
        estado["ultimo"] = actual
    elif items:
        estado["ultimo"] = items[-1]

    return items


def _finalizar(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in items:
        cantidad = item.get("cantidad")
        seriales = item.get("seriales", [])
        if not seriales:
            item["advertencias"].append(
                "El producto no tiene seriales; no se podrá validar por S/N."
            )
        elif cantidad is not None and cantidad != len(seriales):
            item["advertencias"].append(
                f"La nota declara {cantidad} unidades y se detectaron "
                f"{len(seriales)} seriales."
            )
        if not item.get("marca"):
            item["advertencias"].append("No se pudo determinar la marca.")
        if not item.get("modelo"):
            item["advertencias"].append("No se pudo determinar el modelo.")
        item["advertencias"] = list(dict.fromkeys(item["advertencias"]))
    return items


def parsear_paginas(paginas: list[dict[str, Any]]) -> dict[str, Any]:
    estado: dict[str, Any] = {"ultimo": None}
    items: list[dict[str, Any]] = []
    advertencias: list[str] = []

    for pagina in paginas:
        if pagina.get("origen") == "pdf_texto":
            nuevos = _parsear_pagina_texto(pagina, estado)
        else:
            nuevos = _parsear_pagina_ocr(pagina, estado)
        if not nuevos and pagina.get("origen") != "pdf_texto":
            advertencias.append(
                f"La página {pagina.get('numero', '?')} no aportó productos."
            )
        items.extend(nuevos)

    items = _finalizar(items)
    total_seriales = sum(len(item["seriales"]) for item in items)

    if not items:
        advertencias.append(
            "No se detectaron productos en la nota. Prueba con una foto más "
            "nítida o revisa el archivo."
        )

    return {
        "items": items,
        "advertencias": advertencias,
        "seriales_total": total_seriales,
    }
