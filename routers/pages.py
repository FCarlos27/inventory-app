from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from routers.dependencies import verificar_acceso

router = APIRouter(include_in_schema=False)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _pagina(nombre: str) -> FileResponse:
    return FileResponse(
        STATIC_DIR / nombre,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/")
def index(acceso=Depends(verificar_acceso)) -> FileResponse:
    return _pagina("index.html")

@router.get("/login")
def login() -> FileResponse: # <- Esta queda sin Depends porque es pública
    return _pagina("login.html")

@router.get("/validacion")
def validacion(acceso=Depends(verificar_acceso)) -> FileResponse:
    return _pagina("validacion.html")
