from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["sistema"])


@router.get("/health")
def health(request: Request) -> dict:
    """Comprueba que el servidor está en línea."""
    return {
        "status": "ok",
        "app": request.app.title,
        "version": request.app.version,
    }
