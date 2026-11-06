import secrets
import threading
import time
from dataclasses import dataclass, field

from services.catalogo import CatalogoModelos
from services.ingesta import IngestaService
from services.validacion import ValidacionService

COOKIE_NAME = "inventario_sesion"
RUTAS_CON_SESION = ("/api/ingesta", "/api/validacion")
TTL_SESION_SEGUNDOS = 12 * 60 * 60
MAX_SESIONES = 200


@dataclass
class Sesion:
    """Datos aislados de un navegador."""

    ingesta: IngestaService
    validacion: ValidacionService
    lock: threading.Lock = field(default_factory=threading.Lock)
    creada: float = field(default_factory=time.monotonic)
    ultimo_uso: float = field(default_factory=time.monotonic)


class SessionStore:
    """Sesiones en memoria, una por cookie de navegador."""

    def __init__(self, catalogo: CatalogoModelos):
        self._catalogo = catalogo
        self._sesiones: dict[str, Sesion] = {}
        self._lock = threading.Lock()

    def obtener_o_crear(
        self, session_id: str | None
    ) -> tuple[str, Sesion, bool]:
        with self._lock:
            ahora = time.monotonic()
            self._limpiar_vencidas(ahora)

            if session_id and session_id in self._sesiones:
                sesion = self._sesiones[session_id]
                sesion.ultimo_uso = ahora
                return session_id, sesion, False

            if len(self._sesiones) >= MAX_SESIONES:
                mas_antigua = min(
                    self._sesiones,
                    key=lambda clave: self._sesiones[clave].ultimo_uso,
                )
                self._sesiones.pop(mas_antigua, None)

            session_id = secrets.token_urlsafe(24)
            sesion = Sesion(
                ingesta=IngestaService(self._catalogo),
                validacion=ValidacionService(),
                creada=ahora,
                ultimo_uso=ahora,
            )
            self._sesiones[session_id] = sesion
            return session_id, sesion, True

    def _limpiar_vencidas(self, ahora: float) -> None:
        vencidas = [
            session_id
            for session_id, sesion in self._sesiones.items()
            if ahora - sesion.ultimo_uso > TTL_SESION_SEGUNDOS
        ]
        for session_id in vencidas:
            self._sesiones.pop(session_id, None)

    def eliminar(self, session_id: str | None) -> None:
        """Descarta una sesión para no reutilizarla en el próximo acceso."""
        if not session_id:
            return
        with self._lock:
            self._sesiones.pop(session_id, None)
