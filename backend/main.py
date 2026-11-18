"""API de la plantilla. Ejecuta: .venv/Scripts/uvicorn backend.main:app --reload"""
import os
from pathlib import Path


def cargar_env():
    f = Path(__file__).resolve().parent.parent / ".env"
    if f.exists():
        for linea in f.read_text(encoding="utf-8-sig").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


cargar_env()

from fastapi import FastAPI  # noqa: E402

from backend.app import router as router_compartido  # noqa: E402
from backend.modulo_a_kareem import router as router_kareem  # noqa: E402
from backend.modulo_b_emilio import router as router_emilio  # noqa: E402

app = FastAPI(title="Hackathon NFL UNAM")

app.include_router(router_compartido)
app.include_router(router_kareem)
app.include_router(router_emilio)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
