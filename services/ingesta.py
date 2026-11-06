import csv
import io
from typing import Any

from services.catalogo import CatalogoModelos

FIELDNAMES = ["serial", "p_n", "brand", "model", "status"]
ESTADO_INGRESADO = "INGRESADO"


class IngestaError(ValueError):
    """Operación inválida dentro del flujo de ingesta."""


class IngestaService:
    """Estado y reglas de una sesión de ingesta directa.

    Flujo: primer escaneo = S/N, segundo escaneo = P/N. Si el P/N no está en
    el catálogo, queda pendiente hasta que el operador ingrese marca/modelo.
    """

    def __init__(self, catalogo: CatalogoModelos):
        self.catalogo = catalogo
        self.pending_serial: str | None = None
        self.pending_pn: str | None = None
        self.scanned: set[str] = set()
        self.activos: list[dict[str, str]] = []

    def escanear(self, codigo: str) -> dict[str, Any]:
        codigo = (codigo or "").strip().upper()
        if not codigo:
            raise IngestaError("El código escaneado no puede estar vacío.")
        if self.pending_pn is not None:
            raise IngestaError(
                "Hay un P/N pendiente de marca y modelo. Resolvelo antes de seguir."
            )

        if self.pending_serial is None:
            if codigo in self.scanned:
                return {
                    "evento": "duplicado",
                    "serial": codigo,
                    "mensaje": f"El S/N {codigo} ya fue registrado en esta sesión.",
                    "estado": self.snapshot(),
                }

            self.pending_serial = codigo
            return {
                "evento": "sn_capturado",
                "serial": codigo,
                "mensaje": "S/N capturado. Escaneá el P/N.",
                "estado": self.snapshot(),
            }

        p_n = codigo
        item = self.catalogo.buscar(p_n)
        if item is None:
            self.pending_pn = p_n
            return {
                "evento": "requiere_modelo",
                "serial": self.pending_serial,
                "p_n": p_n,
                "mensaje": (
                    f"El P/N {p_n} no está en el catálogo. "
                    "Ingresá marca y modelo."
                ),
                "estado": self.snapshot(),
            }

        return self._registrar(p_n, item["brand"], item["model"])

    def resolver_modelo(
        self,
        p_n: str,
        brand: str | None = None,
        model: str | None = None,
        omitir: bool = False,
    ) -> dict[str, Any]:
        if self.pending_serial is None or self.pending_pn is None:
            raise IngestaError("No hay un P/N pendiente de resolver.")

        p_n = (p_n or "").strip().upper()
        if p_n != self.pending_pn:
            raise IngestaError(
                "El P/N enviado no coincide con el que está pendiente."
            )

        if omitir:
            item = {"brand": "N/A", "model": "N/A"}
        else:
            brand = (brand or "").strip()
            if not brand:
                raise IngestaError(
                    "La marca es obligatoria para agregar el P/N al catálogo."
                )
            item = self.catalogo.agregar(p_n, brand, model or "")

        return self._registrar(p_n, item["brand"], item["model"])

    def _registrar(self, p_n: str, brand: str, model: str) -> dict[str, Any]:
        serial = self.pending_serial
        if serial is None:
            raise IngestaError("No hay un S/N pendiente.")

        activo = {
            "serial": serial,
            "p_n": p_n,
            "brand": brand or "N/A",
            "model": model or "N/A",
            "status": ESTADO_INGRESADO,
        }
        self.scanned.add(serial)
        self.activos.append(activo)
        self.pending_serial = None
        self.pending_pn = None

        return {
            "evento": "registrado",
            "activo": activo,
            "mensaje": f"Activo {serial} registrado.",
            "estado": self.snapshot(),
        }

    def cancelar_pendiente(self) -> dict[str, Any]:
        habia_pendiente = (
            self.pending_serial is not None or self.pending_pn is not None
        )
        self.pending_serial = None
        self.pending_pn = None

        return {
            "cancelado": habia_pendiente,
            "mensaje": (
                "Captura cancelada."
                if habia_pendiente
                else "No había una captura pendiente."
            ),
            "estado": self.snapshot(),
        }

    def reiniciar(self) -> dict[str, Any]:
        self.pending_serial = None
        self.pending_pn = None
        self.scanned.clear()
        self.activos.clear()

        return {
            "mensaje": "Sesión reiniciada.",
            "estado": self.snapshot(),
        }

    def snapshot(self) -> dict[str, Any]:
        pendiente = None
        necesita_modelo = None
        if self.pending_serial is not None:
            pendiente = {
                "serial": self.pending_serial,
                "p_n": self.pending_pn,
            }
        if self.pending_serial is not None and self.pending_pn is not None:
            necesita_modelo = {
                "serial": self.pending_serial,
                "p_n": self.pending_pn,
            }

        return {
            "pendiente": pendiente,
            "necesita_modelo": necesita_modelo,
            "activos": [dict(activo) for activo in self.activos],
            "total": len(self.activos),
            "puede_exportar": bool(self.activos),
            "puede_cancelar": self.pending_serial is not None,
        }

    def exportar_csv(self) -> str:
        if not self.activos:
            return ""

        salida = io.StringIO()
        escritor = csv.DictWriter(salida, fieldnames=FIELDNAMES)
        escritor.writeheader()
        escritor.writerows(self.activos)

        # BOM para que Excel abra correctamente los acentos.
        return "\ufeff" + salida.getvalue()
