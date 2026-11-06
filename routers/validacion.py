from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field

from routers.dependencies import verificar_acceso, obtener_sesion
from services.sesiones import Sesion
from services.validacion import MAX_BYTES_ORDEN, OrdenInvalida

router = APIRouter(prefix="/api/validacion", tags=["validacion"], dependencies=[Depends(verificar_acceso)])


class EscaneoRequest(BaseModel):
    codigo: str = Field(min_length=1, max_length=64)




@router.get("/estado")
def estado(sesion: Sesion = Depends(obtener_sesion)) -> dict:
    """Estado actual de la validación de la orden."""
    with sesion.lock:
        return sesion.validacion.snapshot()


@router.post("/orden")
async def cargar_orden(
    file: UploadFile = File(...),
    sesion: Sesion = Depends(obtener_sesion),
) -> dict:
    """Carga el CSV de la orden y reinicia la verificación."""
    contenido = await file.read(MAX_BYTES_ORDEN + 1)

    if len(contenido) > MAX_BYTES_ORDEN:
        raise HTTPException(
            status_code=413,
            detail="El archivo supera el límite de 5 MB.",
        )

    try:
        with sesion.lock:
            return sesion.validacion.cargar_orden(
                contenido,
                (file.filename or "")[:255],
            )
    except OrdenInvalida as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/escanear")
def escanear(
    payload: EscaneoRequest,
    sesion: Sesion = Depends(obtener_sesion),
) -> dict:
    """Valida un S/N contra la orden cargada."""
    try:
        with sesion.lock:
            return sesion.validacion.escanear(payload.codigo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reiniciar")
def reiniciar(sesion: Sesion = Depends(obtener_sesion)) -> dict:
    """Descarta la orden y los resultados de la sesión."""
    with sesion.lock:
        return sesion.validacion.reiniciar()


@router.get("/exportar")
def exportar(sesion: Sesion = Depends(obtener_sesion)) -> Response:
    """Descarga los S/N verificados como CSV."""
    with sesion.lock:
        contenido = sesion.validacion.exportar_csv()

    if not contenido:
        raise HTTPException(
            status_code=404,
            detail="No hay resultados para exportar.",
        )

    return Response(
        content=contenido,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="verificacion.csv"',
            "Cache-Control": "no-store",
        },
    )
