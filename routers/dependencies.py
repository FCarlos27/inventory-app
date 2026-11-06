from fastapi import Request, Response
from services.acceso import COOKIE_ACCESO
from services.sesiones import COOKIE_NAME, Sesion

class NoAutorizadoException(Exception):
    """Excepción lanzada cuando el usuario no tiene un token válido."""
    pass

def verificar_acceso(request: Request):
    token = request.cookies.get(COOKIE_ACCESO)
    if not request.app.state.acceso.valido(token):
        raise NoAutorizadoException()

def obtener_sesion(request: Request, response: Response) -> Sesion:
    """Obtiene o crea la sesión y setea la cookie si es nueva."""
    session_id, sesion, creada = request.app.state.sessions.obtener_o_crear(
        request.cookies.get(COOKIE_NAME)
    )
    request.state.sesion = sesion
    
    if creada:
        response.set_cookie(
            COOKIE_NAME,
            session_id,
            httponly=True,
            samesite="lax",
            path="/",
        )
    return sesion