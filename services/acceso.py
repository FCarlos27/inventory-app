import os
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from services.almacen import DATA_DIR

CLAVE_PATH = DATA_DIR / "clave.txt"
COOKIE_ACCESO = "inventario_acceso"
TTL_TOKEN_SEGUNDOS = 12 * 60 * 60
MAX_INTENTOS = 5
VENTANA_INTENTOS_SEGUNDOS = 5 * 60


def cargar_clave() -> tuple[str, bool]:
    """Devuelve (clave, generada).

    Prioriza la variable de entorno ``INVENTARIO_CLAVE``. Si no existe, usa
    ``data/clave.txt`` o genera una clave nueva y la guarda con permisos 600.
    """
    clave_entorno = os.environ.get("INVENTARIO_CLAVE", "").strip()
    if clave_entorno:
        return clave_entorno, False

    if CLAVE_PATH.exists():
        clave = CLAVE_PATH.read_text(encoding="utf-8").strip()
        if clave:
            return clave, False

    clave = secrets.token_urlsafe(12)
    CLAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLAVE_PATH.write_text(clave + "\n", encoding="utf-8")
    try:
        os.chmod(CLAVE_PATH, 0o600)
    except OSError:
        pass
    return clave, True


class ControlAcceso:
    """Clave compartida con tokens de acceso en memoria."""

    def __init__(self, clave: str):
        self._clave = (clave or "").encode("utf-8")
        self._tokens: dict[str, float] = {}
        self._fallos: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def autenticar(self, clave: str, ip: str) -> tuple[str | None, str | None]:
        """Devuelve (token, error). Un token None indica acceso denegado."""
        ahora = time.monotonic()
        with self._lock:
            self._limpiar_tokens(ahora)
            fallos = self._fallos[ip]
            while fallos and ahora - fallos[0] > VENTANA_INTENTOS_SEGUNDOS:
                fallos.popleft()

            if len(fallos) >= MAX_INTENTOS:
                return None, "Demasiados intentos fallidos. Espera unos minutos."

            if not self._clave or not secrets.compare_digest(
                (clave or "").encode("utf-8"), self._clave
            ):
                fallos.append(ahora)
                return None, "Clave incorrecta."

            fallos.clear()
            token = secrets.token_urlsafe(32)
            self._tokens[token] = ahora + TTL_TOKEN_SEGUNDOS
            return token, None

    def valido(self, token: str | None) -> bool:
        if not token:
            return False

        ahora = time.monotonic()
        with self._lock:
            expira = self._tokens.get(token)
            if expira is None:
                return False
            if expira <= ahora:
                self._tokens.pop(token, None)
                return False
            return True

    def cerrar(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._tokens.pop(token, None)

    def _limpiar_tokens(self, ahora: float) -> None:
        vencidos = [
            token for token, expira in self._tokens.items() if expira <= ahora
        ]
        for token in vencidos:
            self._tokens.pop(token, None)
