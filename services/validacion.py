import csv
import io
from typing import Any

MAX_BYTES_ORDEN = 5 * 1024 * 1024
FIELDNAMES = ["serial", "brand", "model", "status"]
ESTADO_VERIFICADO = "VERIFICADO"


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
    """Devuelve {serial: {brand, model}} a partir del CSV de la orden.

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

    def cargar_orden(
        self, contenido: bytes | str, filename: str = ""
    ) -> dict[str, Any]:
        """Carga una orden. Si el CSV es inválido, conserva la orden anterior."""
        expected = leer_orden(contenido)

        self.expected = expected
        self.order_filename = (filename or "").strip()
        self.scanned.clear()
        self.resultados.clear()

        return {
            "mensaje": f"Orden cargada: {len(expected)} ítems.",
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
                "mensaje": "Cargá una orden antes de escanear.",
                "estado": self.snapshot(),
            }

        if codigo in self.scanned:
            return {
                "evento": "duplicado",
                "serial": codigo,
                "mensaje": f"El S/N {codigo} ya fue verificado.",
                "estado": self.snapshot(),
            }

        item = self.expected.get(codigo)
        if item is None:
            return {
                "evento": "fuera_de_orden",
                "serial": codigo,
                "mensaje": f"El S/N {codigo} no pertenece a la orden.",
                "estado": self.snapshot(),
            }

        activo = {
            "serial": codigo,
            "brand": item["brand"],
            "model": item["model"],
            "status": ESTADO_VERIFICADO,
        }
        self.scanned.add(codigo)
        self.resultados.append(activo)

        completada = len(self.scanned) == len(self.expected)
        return {
            "evento": "verificado",
            "serial": codigo,
            "activo": activo,
            "completada": completada,
            "mensaje": (
                "¡Orden completada con éxito!"
                if completada
                else f"S/N {codigo} verificado."
            ),
            "estado": self.snapshot(),
        }

    def reiniciar(self) -> dict[str, Any]:
        self.expected.clear()
        self.order_filename = ""
        self.scanned.clear()
        self.resultados.clear()

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
            },
            "escaneados": escaneados,
            "resultados": [dict(resultado) for resultado in self.resultados],
            # La app anterior habilitaba la exportación al completar la orden.
            "puede_exportar": completada,
            "completada": completada,
        }

    def exportar_csv(self) -> str:
        if not self.resultados:
            return ""

        salida = io.StringIO()
        escritor = csv.DictWriter(salida, fieldnames=FIELDNAMES)
        escritor.writeheader()
        escritor.writerows(self.resultados)

        # BOM para que Excel abra correctamente los acentos.
        return "\ufeff" + salida.getvalue()
