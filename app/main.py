from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import documents, analysis, predios, geodata, conflictos, satellite
from app.db.connection import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="ORBYT LAND API",
    description="Plataforma de geolocalización predial inteligente",
    version="0.1.0",
    lifespan=lifespan,
)

import os

_EXTRA_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
_ORIGINS = [
    "http://localhost:3000",
    "https://orbytland.mx",
    "https://www.orbytland.mx",
    *_EXTRA_ORIGINS,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_origin_regex=r"https://(.*\.)?orbytland\.mx",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(predios.router, prefix="/api/predios", tags=["predios"])
app.include_router(geodata.router,    prefix="/api/geodata",    tags=["geodata"])
app.include_router(conflictos.router, prefix="/api/conflictos", tags=["conflictos"])
app.include_router(satellite.router,  prefix="/api/satellite",  tags=["satellite"])


@app.get("/health")
async def health():
    from app.db.supabase_store import is_available
    sb_url = os.getenv("SUPABASE_URL", "")
    sb_key = bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY"))
    return {
        "status": "ok",
        "version": "0.1.0",
        "service": "ORBYT LAND",
        "supabase_url": sb_url[:30] + "..." if sb_url else "",
        "supabase_key_set": sb_key,
        "supabase_available": is_available(),
    }
