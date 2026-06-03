from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import documents, analysis, predios, geodata
from app.db.connection import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="ORBYT LAND BCS API",
    description="Plataforma de geolocalización predial inteligente",
    version="0.1.0",
    lifespan=lifespan,
)

import os

_EXTRA_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
_ORIGINS = [
    "http://localhost:3000",
    "https://orbyt-land-bcs.vercel.app",
    *_EXTRA_ORIGINS,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_origin_regex=r"https://orbyt-land-.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(predios.router, prefix="/api/predios", tags=["predios"])
app.include_router(geodata.router, prefix="/api/geodata", tags=["geodata"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "service": "ORBYT LAND BCS"}
