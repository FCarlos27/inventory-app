from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from routers import acceso, nota, pages, sistema, validacion
from services.acceso import (
    CLAVE_PATH,
    COOKIE_ACCESO,
    ControlAcceso,
    cargar_clave,
)
from services.almacen import CATALOGO_PATH
from services.catalogo import CatalogoModelos
from services.sesiones import COOKIE_NAME, RUTAS_CON_SESION, SessionStore

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Inventario Depósito",
    description="Control y verificación de inventario en depósito.",
    version="0.4.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

clave, clave_generada = cargar_clave()
app.state.catalogo = CatalogoModelos(CATALOGO_PATH)
app.state.sessions = SessionStore(app.state.catalogo)
app.state.acceso = ControlAcceso(clave)

if clave_generada:
    print("\n" + "=" * 64)
    print("Clave de acceso generada para esta instalación:")
    print(f"  {clave}")
    print(f"  Archivo: {CLAVE_PATH}")
    print("=" * 64 + "\n")

RUTAS_PUBLICAS = {"/login", "/api/login", "/api/logout", "/api/health"}
MAX_CUERPO_JSON = 64 * 1024
MAX_CUERPO_ORDEN = 6 * 1024 * 1024
MAX_CUERPO_NOTA = 21 * 1024 * 1024

CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def _es_publica(path: str) -> bool:
    return (
        path in RUTAS_PUBLICAS
        or path == "/static"
        or path.startswith("/static/")
        or path == "/favicon.ico"
    )


def _limite_cuerpo(path: str) -> int:
    if path == "/api/validacion/orden":
        return MAX_CUERPO_ORDEN
    if path == "/api/nota/extraer":
        return MAX_CUERPO_NOTA
    return MAX_CUERPO_JSON


@app.middleware("http")
async def sesion_y_acceso(request: Request, call_next):
    """Exige la clave de acceso y asigna una sesión de trabajo."""
    path = request.url.path

    if request.method in ("POST", "PUT", "PATCH"):
        largo = request.headers.get("content-length")
        if largo and largo.isdigit() and int(largo) > _limite_cuerpo(path):
            return JSONResponse(
                {"detail": "La solicitud supera el tamaño permitido."},
                status_code=413,
            )

    if not _es_publica(path):
        token = request.cookies.get(COOKIE_ACCESO)
        if not request.app.state.acceso.valido(token):
            if path.startswith("/api/"):
                return JSONResponse(
                    {"detail": "Acceso no autorizado."},
                    status_code=401,
                )
            return RedirectResponse("/login", status_code=303)

    creada = False
    if path.startswith(RUTAS_CON_SESION):
        session_id, sesion, creada = request.app.state.sessions.obtener_o_crear(
            request.cookies.get(COOKIE_NAME)
        )
        request.state.sesion = sesion

    response = await call_next(request)
    if creada:
        response.set_cookie(
            COOKIE_NAME,
            session_id,
            httponly=True,
            samesite="lax",
            path="/",
        )
    return response


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    """Agrega cabeceras defensivas a todas las respuestas."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    if request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    if request.url.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000"
        )
    return response


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(acceso.router)
app.include_router(pages.router)
app.include_router(sistema.router)
app.include_router(nota.router)
app.include_router(validacion.router)
