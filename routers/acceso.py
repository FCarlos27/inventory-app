from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.acceso import (
    COOKIE_ACCESO,
    TTL_TOKEN_SEGUNDOS,
    VENTANA_INTENTOS_SEGUNDOS,
)
from services.sesiones import COOKIE_NAME

router = APIRouter(prefix="/api", tags=["acceso"])


class ClaveRequest(BaseModel):
    clave: str = Field(min_length=1, max_length=128)


@router.post("/login")
def login(payload: ClaveRequest, request: Request) -> Response:
    """Valida la clave compartida y entrega una cookie de acceso."""
    ip = request.client.host if request.client else "desconocida"
    token, error = request.app.state.acceso.autenticar(payload.clave, ip)

    if token is None:
        headers = {}
        codigo = 401
        if error and error.startswith("Demasiados"):
            codigo = 429
            headers["Retry-After"] = str(VENTANA_INTENTOS_SEGUNDOS)
        return JSONResponse(
            {"detail": error or "Clave incorrecta."},
            status_code=codigo,
            headers=headers,
        )

    respuesta = JSONResponse({"ok": True})
    respuesta.set_cookie(
        COOKIE_ACCESO,
        token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=TTL_TOKEN_SEGUNDOS,
    )
    respuesta.delete_cookie(COOKIE_NAME, path="/")
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/logout")
def logout(request: Request) -> Response:
    """Cierra el acceso actual y elimina la cookie."""
    request.app.state.acceso.cerrar(request.cookies.get(COOKIE_ACCESO))
    request.app.state.sessions.eliminar(request.cookies.get(COOKIE_NAME))
    respuesta = JSONResponse({"ok": True})
    respuesta.delete_cookie(COOKIE_ACCESO, path="/")
    respuesta.delete_cookie(COOKIE_NAME, path="/")
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta
