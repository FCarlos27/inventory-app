import csv
import os
import threading
from pathlib import Path

from services.almacen import CATALOGO_PATH

FIELDNAMES = ["brand", "p_n", "model"]


class CatalogoInvalido(ValueError):
    """El archivo de catálogo no tiene el formato esperado."""


class CatalogoModelos:
    """Catálogo P/N -> marca/modelo persistido en CSV.

    Se lee desde disco en cada consulta para que todos los navegadores vean
    las mismas actualizaciones sin mantener cachés separadas.
    """

    def __init__(self, path: Path = CATALOGO_PATH):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.asegurar_archivo()

    def asegurar_archivo(self) -> None:
        """Crea el catálogo con encabezados si todavía no existe."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            self._escribir({})

    def _leer(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}

        with open(self.path, mode="r", encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo)
            encabezados = [
                (encabezado or "").strip().lower()
                for encabezado in (lector.fieldnames or [])
            ]
            if "p_n" not in encabezados:
                raise CatalogoInvalido(
                    "El catálogo debe tener una columna 'p_n'."
                )
            lector.fieldnames = encabezados

            items = {}
            for fila in lector:
                p_n = (fila.get("p_n") or "").strip().upper()
                if not p_n:
                    continue

                items[p_n] = {
                    "brand": (fila.get("brand") or "").strip() or "N/A",
                    "model": (fila.get("model") or "").strip() or "N/A",
                }

            return items

    def _escribir(self, items: dict[str, dict[str, str]]) -> None:
        """Reescribe el catálogo de forma atómica para no dejarlo a medias."""
        temporal = self.path.with_name(self.path.name + ".tmp")
        with open(temporal, mode="w", encoding="utf-8-sig", newline="") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=FIELDNAMES)
            escritor.writeheader()
            for p_n, item in items.items():
                escritor.writerow(
                    {
                        "brand": item["brand"],
                        "p_n": p_n,
                        "model": item["model"],
                    }
                )
        os.replace(temporal, self.path)

    def buscar(self, p_n: str) -> dict[str, str] | None:
        """Devuelve marca/modelo del P/N, o None si no está registrado."""
        p_n = (p_n or "").strip().upper()
        if not p_n:
            return None

        with self._lock:
            return self._leer().get(p_n)

    def agregar(self, p_n: str, brand: str, model: str) -> dict[str, str]:
        """Agrega un P/N nuevo. Si ya existe, devuelve el existente."""
        p_n = (p_n or "").strip().upper()
        if not p_n:
            raise ValueError("El P/N no puede estar vacío.")

        with self._lock:
            items = self._leer()
            if p_n in items:
                return items[p_n]

            item = {
                "brand": (brand or "").strip() or "N/A",
                "model": (model or "").strip() or "N/A",
            }
            items[p_n] = item
            self._escribir(items)
            return item
