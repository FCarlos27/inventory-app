import csv
import io
from typing import Any

from services.csv_seguro import celda_segura

MAX_BYTES_ORDEN = 5 * 1024 * 1024
ENCABEZADOS_EXPORTACION = ["S/N", "Marca", "Modelo", "Procesador", "RAM"]
LONGITUD_MINIMA_CODIGO = 4


class OrdenInvalida(ValueError):
    """El contenido no cumple el formato mínimo de una orden."""


def _decodificar(contenido: bytes | str) -> str:
    if isinstance(contenido, bytes):
        try:
            contenido = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            contenido = contenido.decode("latin-1")
    return contenido.lstrip("\ufeff")


def leer_orden(contenido: bytes | str) -> dict[str, dict[str, str]]:
    """Devuelve {serial: {brand, model, processor, ram}} a partir del CSV.

    Solo la columna ``serial`` es obligatoria. Los encabezados se aceptan
    sin distinguir mayúsculas ni espacios, y los seriales se normalizan a
    mayúsculas.
    """
    lector = csv.DictReader(io.StringIO(_decodificar(contenido)))
    encabezados = [
        (encabezado or "").strip().lower()
        for encabezado in (lector.fieldnames or [])
    ]

    if "serial" not in encabezados:
        raise OrdenInvalida("El CSV debe tener una columna 'serial'.")
    lector.fieldnames = encabezados

    items = {}
    for fila in lector:
        serial = (fila.get("serial") or "").strip().upper()
        if not serial:
            continue

        items[serial] = {
            "brand": (fila.get("brand") or "").strip() or "N/A",
            "model": (fila.get("model") or "").strip() or "N/A",
            "processor": (fila.get("processor") or "").strip(),
            "ram": (fila.get("ram") or "").strip(),
        }

    if not items:
        raise OrdenInvalida(
            "No se encontraron seriales válidos en el archivo."
        )

    return items


class ValidacionService:
    """Estado y reglas del modo validación estricta de una orden."""

    def __init__(self):
        self.expected: dict[str, dict[str, str]] = {}
        self.order_filename = ""
        self.scanned: set[str] = set()
        self.resultados: list[dict[str, str]] = []
        self.por_sufijo: dict[str, list[str]] = {}
        self.ambiguos = 0

    def cargar_orden(
        self, contenido: bytes | str, filename: str = ""
    ) -> dict[str, Any]:
        """Carga una orden. Si el CSV es inválido, conserva la orden anterior."""
        expected = leer_orden(contenido)

        self.expected = expected
        self.order_filename = (filename or "").strip()
        self.scanned.clear()
        self.resultados.clear()
        self._indexar_sufijos()

        mensaje = f"Orden cargada: {len(expected)} ítems."
        if self.ambiguos:
            mensaje += (
                f" {self.ambiguos} terminación(es) de 4 dígitos son ambiguas;"
                " en esos casos escribe el S/N completo."
            )

        return {
            "mensaje": mensaje,
            "estado": self.snapshot(),
        }

    def escanear(self, codigo: str) -> dict[str, Any]:
        codigo = (codigo or "").strip().upper()
        if not codigo:
            raise ValueError("El código escaneado no puede estar vacío.")

        if not self.expected:
            return {
                "evento": "sin_orden",
                "serial": codigo,
                "mensaje": "Carga una orden antes de escanear.",
                "estado": self.snapshot(),
            }

        if (
            len(codigo) < LONGITUD_MINIMA_CODIGO
            and codigo not in self.expected
        ):
            raise ValueError(
                "Escribe al menos los últimos 4 dígitos del S/N."
            )

        coincidencias = self._coincidencias(codigo)
        if not coincidencias:
            return {
                "evento": "fuera_de_orden",
                "serial": codigo,
                "mensaje": f"El S/N {codigo} no pertenece a la orden.",
                "estado": self.snapshot(),
            }

        pendientes = [
            serial for serial in coincidencias if serial not in self.scanned
        ]
        if not pendientes:
            if len(coincidencias) == 1:
                mensaje = f"El S/N {coincidencias[0]} ya fue verificado."
            else:
                mensaje = (
                    f"Los S/N que terminan en {codigo} ya fueron verificados."
                )
            return {
                "evento": "duplicado",
                "serial": codigo,
                "mensaje": mensaje,
                "estado": self.snapshot(),
            }

        if len(coincidencias) > 1:
            cantidad = len(pendientes)
            verbo = "coincide" if cantidad == 1 else "coinciden"
            return {
                "evento": "ambiguo",
                "serial": codigo,
                "coincidencias": cantidad,
                "mensaje": (
                    f"{cantidad} S/N {verbo} con {codigo}. "
                    "Escribe el S/N completo para identificarlo."
                ),
                "estado": self.snapshot(),
            }

        serial = pendientes[0]
        item = self.expected[serial]
        activo = {
            "serial": serial,
            "brand": item["brand"],
            "model": item["model"],
            "processor": item["processor"],
            "ram": item["ram"],
        }
        self.scanned.add(serial)
        self.resultados.append(activo)

        completada = len(self.scanned) == len(self.expected)
        return {
            "evento": "verificado",
            "serial": serial,
            "activo": activo,
            "completada": completada,
            "mensaje": (
                "¡Orden completada con éxito!"
                if completada
                else f"S/N {serial} verificado."
            ),
            "estado": self.snapshot(),
        }

    def reiniciar(self) -> dict[str, Any]:
        self.expected.clear()
        self.order_filename = ""
        self.scanned.clear()
        self.resultados.clear()
        self.por_sufijo.clear()
        self.ambiguos = 0

        return {
            "mensaje": "Validación reiniciada.",
            "estado": self.snapshot(),
        }

    def snapshot(self) -> dict[str, Any]:
        total = len(self.expected)
        escaneados = len(self.scanned)
        completada = total > 0 and escaneados == total

        return {
            "orden": {
                "filename": self.order_filename,
                "cargada": bool(self.expected),
                "total": total,
                "ambiguos": self.ambiguos,
            },
            "escaneados": escaneados,
            "resultados": [dict(resultado) for resultado in self.resultados],
            # Se puede exportar apenas hay resultados, aunque falten S/N.
            "puede_exportar": bool(self.resultados),
            "completada": completada,
        }

    def exportar_csv(self) -> str:
        if not self.resultados:
            return ""

        salida = io.StringIO()
        escritor = csv.DictWriter(
            salida, fieldnames=ENCABEZADOS_EXPORTACION
        )
        escritor.writeheader()
        escritor.writerows(
            {
                "S/N": celda_segura(resultado.get("serial", "")),
                "Marca": celda_segura(resultado.get("brand", "")),
                "Modelo": celda_segura(resultado.get("model", "")),
                "Procesador": celda_segura(
                    resultado.get("processor", "")
                ),
                "RAM": celda_segura(resultado.get("ram", "")),
            }
            for resultado in self.resultados
        )

        # BOM para que Excel abra correctamente los acentos.
        return "\ufeff" + salida.getvalue()

    def _indexar_sufijos(self) -> None:
        self.por_sufijo = {}
        for serial in self.expected:
            sufijo = serial[-LONGITUD_MINIMA_CODIGO:]
            self.por_sufijo.setdefault(sufijo, []).append(serial)

        self.ambiguos = sum(
            1
            for seriales in self.por_sufijo.values()
            if len(seriales) > 1
        )

    def _coincidencias(self, codigo: str) -> list[str]:
        if len(codigo) == LONGITUD_MINIMA_CODIGO:
            return list(self.por_sufijo.get(codigo, ()))

        return [
            serial
            for serial in self.expected
            if serial == codigo or serial.endswith(codigo)
        ]
