"""Endpoints de Score Dinámico y Valoración automatizada."""
from __future__ import annotations
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class BreakdownOut(BaseModel):
    confianza:   float
    juridica:    float
    completitud: float
    contextual:  float


class ScoreOut(BaseModel):
    orbyt_id:     str
    score_total:  float
    nivel:        str
    breakdown:    BreakdownOut
    pesos:        dict


class ValuacionOut(BaseModel):
    orbyt_id:        str
    area_m2:         Optional[float]
    municipio:       Optional[str]
    valor_base_mxn:  Optional[float]
    valor_ajust_mxn: Optional[float]
    precio_m2_mxn:   Optional[float]
    rango_min_mxn:   Optional[float]
    rango_max_mxn:   Optional[float]
    score_dinamico:  Optional[float]
    factores:        dict
    breakdown:       dict
    metodologia:     str
    nivel_confianza: Optional[str]


@router.get("/{orbyt_id}/score", response_model=ScoreOut)
async def get_score_dinamico(orbyt_id: str):
    """Score dinámico del predio ponderado en 4 dimensiones."""
    from app.db.supabase_store import (
        get_predio_by_orbyt_id, list_conflictos, get_satelite_info, get_relaciones_count,
        get_fuentes_predio, is_available,
    )
    from app.services.agents.valuacion import calcular_score_dinamico

    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")

    predio = await get_predio_by_orbyt_id(orbyt_id)
    if not predio:
        raise HTTPException(404, f"Predio '{orbyt_id}' no encontrado")

    conflictos     = await list_conflictos(orbyt_id=orbyt_id, estado="activo", limit=20)
    satelite       = await get_satelite_info(orbyt_id)
    n_relaciones   = await get_relaciones_count(orbyt_id)
    fuentes        = await get_fuentes_predio(orbyt_id)

    score_data = calcular_score_dinamico(
        score_confianza = predio.get("score_confianza"),
        conflictos      = conflictos,
        predio          = predio,
        tiene_satelite  = satelite.get("tiene_satelite", False),
        n_relaciones    = n_relaciones,
        fuentes_usadas  = fuentes,
    )

    return ScoreOut(
        orbyt_id    = orbyt_id,
        score_total = score_data["score_total"],
        nivel       = score_data["nivel"],
        breakdown   = BreakdownOut(**score_data["breakdown"]),
        pesos       = score_data["pesos"],
    )


@router.get("/{orbyt_id}", response_model=ValuacionOut)
async def get_valoracion(orbyt_id: str, recalcular: bool = False):
    """
    Valoración automatizada del predio.
    Por defecto devuelve la última guardada. Con ?recalcular=true fuerza nuevo cálculo.
    """
    from app.db.supabase_store import (
        get_predio_by_orbyt_id, list_conflictos, get_satelite_info,
        get_relaciones_count, get_fuentes_predio, get_valoracion_db,
        save_valoracion, is_available,
    )
    from app.services.agents.valuacion import calcular_score_dinamico, calcular_valoracion

    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")

    # Devolver caché si existe y no se pide recalcular
    if not recalcular:
        cached = await get_valoracion_db(orbyt_id)
        if cached:
            return ValuacionOut(**cached)

    predio = await get_predio_by_orbyt_id(orbyt_id)
    if not predio:
        raise HTTPException(404, f"Predio '{orbyt_id}' no encontrado")

    conflictos   = await list_conflictos(orbyt_id=orbyt_id, estado="activo", limit=20)
    satelite     = await get_satelite_info(orbyt_id)
    n_relaciones = await get_relaciones_count(orbyt_id)
    fuentes      = await get_fuentes_predio(orbyt_id)

    score_data = calcular_score_dinamico(
        score_confianza = predio.get("score_confianza"),
        conflictos      = conflictos,
        predio          = predio,
        tiene_satelite  = satelite.get("tiene_satelite", False),
        n_relaciones    = n_relaciones,
        fuentes_usadas  = fuentes,
    )

    val = calcular_valoracion(
        orbyt_id       = orbyt_id,
        predio         = predio,
        score_dinamico = score_data,
        ndvi_mean      = satelite.get("ndvi_mean"),
    )

    await save_valoracion(val)
    return ValuacionOut(**val)


@router.get("/{orbyt_id}/historia")
async def get_historia_valoraciones(orbyt_id: str, limit: int = 10):
    """Historial de valoraciones del predio (últimas N)."""
    from app.db.supabase_store import list_valoraciones_db, is_available

    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")

    rows = await list_valoraciones_db(orbyt_id, limit)
    return rows
