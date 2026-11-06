from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/")
def index() -> FileResponse:
    """Sirve la pantalla principal de la aplicación."""
    return FileResponse(STATIC_DIR / "index.html")
