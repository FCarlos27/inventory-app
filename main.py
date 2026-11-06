from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from routers import ingesta, pages, sistema, validacion
from services.almacen import CATALOGO_PATH
from services.catalogo import CatalogoModelos
from services.sesiones import COOKIE_NAME, RUTAS_CON_SESION, SessionStore

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Inventario Depósito",
    description="Control y verificación de inventario en depósito.",
    version="0.3.0",
)

app.state.catalogo = CatalogoModelos(CATALOGO_PATH)
app.state.sessions = SessionStore(app.state.catalogo)


@app.middleware("http")
async def adjuntar_sesion(request: Request, call_next):
    """Asigna una sesión independiente a cada navegador."""
    if not request.url.path.startswith(RUTAS_CON_SESION):
        return await call_next(request)

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


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(pages.router)
app.include_router(sistema.router)
app.include_router(ingesta.router)
app.include_router(validacion.router)
