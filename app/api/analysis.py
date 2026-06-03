"""Endpoints de consulta de análisis."""
from fastapi import APIRouter, HTTPException
from app.models.predio import Analisis
from app.services.analysis_pipeline import get_analysis

router = APIRouter()


@router.get("/{analisis_id}", response_model=Analisis)
async def get_analisis(analisis_id: str):
    data = get_analysis(analisis_id)
    if not data:
        raise HTTPException(404, f"Análisis '{analisis_id}' no encontrado")
    return Analisis(**data)
