from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routers import pages, sistema

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Inventario Depósito",
    description="Control y verificación de inventario en depósito.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(pages.router)
app.include_router(sistema.router)
