from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from routers.dependencies import verificar_acceso, obtener_sesion
from services.catalogo import CatalogoInvalido
from services.ingesta import IngestaError
from services.sesiones import Sesion

router = APIRouter(prefix="/api/ingesta", tags=["ingesta"], dependencies=[Depends(verificar_acceso)])


class EscaneoRequest(BaseModel):
    codigo: str = Field(min_length=1, max_length=64)


class ModeloRequest(BaseModel):
    p_n: str = Field(min_length=1, max_length=64)
    brand: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    omitir: bool = False


@router.get("/estado")
def estado(sesion: Sesion = Depends(obtener_sesion)) -> dict:
    """Estado actual de la sesión de ingesta."""
    with sesion.lock:
        return sesion.ingesta.snapshot()


@router.post("/escanear")
def escanear(
    payload: EscaneoRequest,
    sesion: Sesion = Depends(obtener_sesion),
) -> dict:
    """Procesa un código: primero S/N, después P/N."""
    try:
        with sesion.lock:
            return sesion.ingesta.escanear(payload.codigo)
    except IngestaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CatalogoInvalido as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/modelo")
def resolver_modelo(
    payload: ModeloRequest,
    sesion: Sesion = Depends(obtener_sesion),
) -> dict:
    """Agrega un P/N al catálogo y completa la captura pendiente."""
    try:
        with sesion.lock:
            return sesion.ingesta.resolver_modelo(
                payload.p_n,
                payload.brand,
                payload.model,
                payload.omitir,
            )
    except IngestaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CatalogoInvalido as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/cancelar")
def cancelar(sesion: Sesion = Depends(obtener_sesion)) -> dict:
    """Cancela la captura pendiente sin registrar el activo."""
    with sesion.lock:
        return sesion.ingesta.cancelar_pendiente()


@router.post("/reiniciar")
def reiniciar(sesion: Sesion = Depends(obtener_sesion)) -> dict:
    """Limpia los activos capturados en esta sesión."""
    with sesion.lock:
        return sesion.ingesta.reiniciar()


@router.get("/exportar")
def exportar(sesion: Sesion = Depends(obtener_sesion)) -> Response:
    """Descarga los activos capturados como CSV."""
    with sesion.lock:
        contenido = sesion.ingesta.exportar_csv()

    if not contenido:
        raise HTTPException(
            status_code=404,
            detail="No hay activos para exportar.",
        )

    return Response(
        content=contenido,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="activos.csv"',
            "Cache-Control": "no-store",
        },
    )
