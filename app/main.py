from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import documents, analysis, predios, geodata, conflictos, satellite, grafo, valoracion, keys, webhooks
from app.db.connection import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="ORBYT LAND API",
    description=(
        "## Plataforma de inteligencia territorial — México\n\n"
        "Convierte escrituras, planos, KML, SHP y cualquier documento predial en polígonos precisos "
        "con ORBYT-ID permanente, score de confianza, valoración automatizada y monitoreo satelital.\n\n"
        "**Base URL:** `https://orbyt-land-api.onrender.com`  \n"
        "**Versión pública:** `/v1/`  \n"
        "**Autenticación:** Header `X-API-Key: ol_...` (genera tu key en `/api/keys`)"
    ),
    version="1.0.0",
    contact={"name": "ORBYT LAND", "url": "https://orbyt-land-bcs.netlify.app"},
    license_info={"name": "Propietario — Beta privada"},
    lifespan=lifespan,
    openapi_tags=[
        {"name": "v1 · documents",   "description": "Subir y analizar documentos prediales"},
        {"name": "v1 · analysis",    "description": "Consultar resultados de análisis"},
        {"name": "v1 · predios",     "description": "Gestión de predios con ORBYT-ID"},
        {"name": "v1 · grafo",       "description": "Knowledge graph y Digital Twin"},
        {"name": "v1 · valoracion",  "description": "Score dinámico y valoración automatizada"},
        {"name": "v1 · conflictos",  "description": "Detección de conflictos prediales"},
        {"name": "v1 · satellite",   "description": "Monitoreo satelital Sentinel-2"},
        {"name": "v1 · geodata",     "description": "Datos geoespaciales de referencia"},
        {"name": "keys",             "description": "Gestión de API keys"},
        {"name": "documents",        "description": "Legacy — usar v1"},
        {"name": "analysis",         "description": "Legacy — usar v1"},
        {"name": "predios",          "description": "Legacy — usar v1"},
        {"name": "grafo",            "description": "Legacy — usar v1"},
        {"name": "valoracion",       "description": "Legacy — usar v1"},
        {"name": "conflictos",       "description": "Legacy — usar v1"},
        {"name": "satellite",        "description": "Legacy — usar v1"},
        {"name": "geodata",          "description": "Legacy — usar v1"},
    ],
)

import os

_EXTRA_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
_ORIGINS = [
    "http://localhost:3000",
    "https://orbytland.mx",
    "https://www.orbytland.mx",
    "https://orbyt-land-bcs.netlify.app",
    *_EXTRA_ORIGINS,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_origin_regex=r"https://(.*\.)?(orbytland\.mx|netlify\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Legacy /api/* (backward compat) ──────────────────────────────────────────
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(analysis.router,  prefix="/api/analysis",  tags=["analysis"])
app.include_router(predios.router,   prefix="/api/predios",   tags=["predios"])
app.include_router(geodata.router,   prefix="/api/geodata",   tags=["geodata"])
app.include_router(conflictos.router,prefix="/api/conflictos",tags=["conflictos"])
app.include_router(satellite.router, prefix="/api/satellite", tags=["satellite"])
app.include_router(grafo.router,     prefix="/api/grafo",     tags=["grafo"])
app.include_router(valoracion.router,prefix="/api/valoracion",tags=["valoracion"])

# ── API Pública v1 ────────────────────────────────────────────────────────────
app.include_router(documents.router, prefix="/v1/documents",  tags=["v1 · documents"])
app.include_router(analysis.router,  prefix="/v1/analysis",   tags=["v1 · analysis"])
app.include_router(predios.router,   prefix="/v1/predios",    tags=["v1 · predios"])
app.include_router(geodata.router,   prefix="/v1/geodata",    tags=["v1 · geodata"])
app.include_router(conflictos.router,prefix="/v1/conflictos", tags=["v1 · conflictos"])
app.include_router(satellite.router, prefix="/v1/satellite",  tags=["v1 · satellite"])
app.include_router(grafo.router,     prefix="/v1/grafo",      tags=["v1 · grafo"])
app.include_router(valoracion.router,prefix="/v1/valoracion", tags=["v1 · valoracion"])

# ── API Keys + Webhooks ───────────────────────────────────────────────────────
app.include_router(keys.router,     prefix="/api/keys",     tags=["keys"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])
app.include_router(webhooks.router, prefix="/v1/webhooks",  tags=["v1 · webhooks"])


@app.get("/ping")
async def ping():
    """Lightweight liveness check — no DB, zero latency."""
    return {"ok": True}


@app.get("/health")
async def health():
    from app.db.supabase_store import is_available
    sb_url = os.getenv("SUPABASE_URL", "")
    sb_key = bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY"))
    return {
        "status":             "ok",
        "version":            "1.0.0",
        "service":            "ORBYT LAND",
        "cobertura":          "México — 32 estados",
        "supabase_available": is_available(),
        "endpoints":          46,
    }
