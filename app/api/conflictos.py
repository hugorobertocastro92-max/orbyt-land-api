"""Endpoints de detección y gestión de conflictos prediales."""
from __future__ import annotations
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()


class ConflictoOut(BaseModel):
    id: str
    tipo: str
    orbyt_ids: List[str]
    area_m2: Optional[float] = None
    estado: str
    descripcion: Optional[str] = None
    detected_at: str
    resolved_at: Optional[str] = None


class RiesgoOut(BaseModel):
    orbyt_id: str
    nivel_riesgo: str          # bajo | medio | alto | critico
    score_riesgo: float        # 0-100
    flags: List[str]
    conflictos_activos: int
    recomendaciones: List[str]


@router.get("", response_model=List[ConflictoOut])
async def list_conflictos(
    estado: Optional[str] = Query("activo"),
    orbyt_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Lista conflictos activos. Filtra por estado y/o predio."""
    from app.db.supabase_store import list_conflictos as db_list
    rows = await db_list(estado=estado, orbyt_id=orbyt_id, limit=limit)
    return [ConflictoOut(**r) for r in rows]


@router.get("/{orbyt_id}/riesgo", response_model=RiesgoOut)
async def get_riesgo_predio(orbyt_id: str):
    """Calcula el score de riesgo de un predio."""
    from app.db.supabase_store import list_conflictos as db_list, get_predio_by_orbyt_id
    from app.services.agents.riesgo import calcular_riesgo

    predio = await get_predio_by_orbyt_id(orbyt_id)
    if not predio:
        raise HTTPException(404, f"Predio '{orbyt_id}' no encontrado")

    conflictos = await db_list(orbyt_id=orbyt_id, estado="activo", limit=20)
    riesgo = calcular_riesgo(orbyt_id, predio, conflictos)
    return riesgo


@router.patch("/{conflicto_id}/resolver")
async def resolver_conflicto(conflicto_id: str, motivo: str = Query(...)):
    """Marca un conflicto como resuelto."""
    from app.db.supabase_store import resolver_conflicto as db_resolver
    ok = await db_resolver(conflicto_id, motivo)
    if not ok:
        raise HTTPException(404, "Conflicto no encontrado")
    return {"status": "resuelto", "conflicto_id": conflicto_id}
