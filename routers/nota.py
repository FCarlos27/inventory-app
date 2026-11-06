from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from services.nota import (
    MAX_BYTES_NOTA,
    NotaInvalida,
    extraer_nota_archivos,
)

router = APIRouter(prefix="/api/nota", tags=["nota"])


@router.post("/extraer")
async def extraer(files: list[UploadFile] = File(...)) -> dict:
    """Extrae los productos de una nota en una o más fotos o PDF."""
    archivos: list[tuple[bytes, str]] = []
    total = 0

    for file in files:
        contenido = await file.read(MAX_BYTES_NOTA + 1)
        total += len(contenido)
        if total > MAX_BYTES_NOTA:
            raise HTTPException(
                status_code=413,
                detail="La nota supera el límite de 20 MB en total.",
            )
        archivos.append((contenido, file.filename or ""))

    try:
        return await run_in_threadpool(extraer_nota_archivos, archivos)
    except NotaInvalida as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
