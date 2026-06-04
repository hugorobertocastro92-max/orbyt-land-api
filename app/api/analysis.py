"""Endpoints de consulta de análisis."""
from fastapi import APIRouter, HTTPException
from app.models.predio import Analisis
from app.services.analysis_pipeline import get_analysis

router = APIRouter()


@router.get("/{analisis_id}", response_model=Analisis)
async def get_analisis(analisis_id: str):
    # 1. Buscar en memoria (análisis en curso o reciente)
    data = get_analysis(analisis_id)
    if data:
        return Analisis(**data)

    # 2. Fallback a Supabase (análisis persistido, servidor reiniciado)
    from app.db.supabase_store import get_analysis as db_get
    data = await db_get(analisis_id)
    if data:
        return Analisis(**data)

    raise HTTPException(404, f"Análisis '{analisis_id}' no encontrado")
