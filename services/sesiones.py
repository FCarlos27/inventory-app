import secrets
import threading
from dataclasses import dataclass, field

from services.catalogo import CatalogoModelos
from services.ingesta import IngestaService
from services.validacion import ValidacionService

COOKIE_NAME = "inventario_sesion"
RUTAS_CON_SESION = ("/api/ingesta", "/api/validacion")


@dataclass
class Sesion:
    """Datos aislados de un navegador."""

    ingesta: IngestaService
    validacion: ValidacionService
    lock: threading.Lock = field(default_factory=threading.Lock)


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
            if session_id and session_id in self._sesiones:
                return session_id, self._sesiones[session_id], False

            session_id = secrets.token_urlsafe(24)
            sesion = Sesion(
                ingesta=IngestaService(self._catalogo),
                validacion=ValidacionService(),
            )
            self._sesiones[session_id] = sesion
            return session_id, sesion, True
