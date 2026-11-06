from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _pagina(nombre: str) -> FileResponse:
    return FileResponse(
        STATIC_DIR / nombre,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/")
def index() -> FileResponse:
    """Sirve la pantalla principal de la aplicación."""
    return _pagina("index.html")


@router.get("/login")
def login() -> FileResponse:
    """Sirve la pantalla de acceso con clave compartida."""
    return _pagina("login.html")


@router.get("/validacion")
def validacion() -> FileResponse:
    """Sirve el modo de validación estricta de orden."""
    return _pagina("validacion.html")
