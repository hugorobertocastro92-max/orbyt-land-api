"""Endpoints de monitoreo satelital por ORBYT-ID."""
from __future__ import annotations
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from datetime import date

router = APIRouter()


class SnapshotOut(BaseModel):
    id: Optional[str] = None
    orbyt_id: str
    fuente: str = "sentinel-2"
    scene_id: Optional[str] = None
    fecha_imagen: Optional[str] = None
    cloud_cover_pct: Optional[float] = None
    thumbnail_url: Optional[str] = None
    ndvi_mean: Optional[float] = None
    ndvi_min: Optional[float] = None
    ndvi_max: Optional[float] = None
    cambio_detectado: bool = False
    cambio_magnitud: Optional[float] = None
    cambio_descripcion: Optional[str] = None
    es_baseline: bool = False
    created_at: Optional[str] = None
    mensaje: Optional[str] = None


@router.get("/{orbyt_id}/snapshots", response_model=List[SnapshotOut])
async def get_snapshots(orbyt_id: str, limit: int = Query(12, le=50)):
    """Retorna el historial de snapshots satelitales de un predio."""
    from app.services.satellite.snapshots import get_snapshots
    snaps = await get_snapshots(orbyt_id, limit=limit)
    return [SnapshotOut(**{k: v for k, v in s.items() if k in SnapshotOut.model_fields}) for s in snaps]


@router.post("/{orbyt_id}/baseline", response_model=SnapshotOut)
async def capture_baseline(orbyt_id: str, background_tasks: BackgroundTasks):
    """
    Captura la imagen de referencia (baseline) del predio.
    Si ya existe, retorna el baseline actual sin re-capturar.
    Se ejecuta en background si la captura toma tiempo.
    """
    from app.services.satellite.snapshots import capture_baseline
    snap = await capture_baseline(orbyt_id)
    if not snap:
        raise HTTPException(404, f"No se pudo capturar baseline para {orbyt_id}")
    return SnapshotOut(**{k: v for k, v in snap.items() if k in SnapshotOut.model_fields})


@router.post("/{orbyt_id}/monitor", response_model=SnapshotOut)
async def monitor_cambios(orbyt_id: str):
    """
    Captura una nueva imagen y la compara con el baseline.
    Detecta cambios en vegetación, construcciones o uso de suelo.
    """
    from app.services.satellite.snapshots import capture_snapshot
    snap = await capture_snapshot(orbyt_id)
    if not snap:
        raise HTTPException(404, f"No se pudo capturar snapshot para {orbyt_id}")
    return SnapshotOut(**{k: v for k, v in snap.items() if k in SnapshotOut.model_fields})


@router.get("/{orbyt_id}/escenas")
async def buscar_escenas_disponibles(
    orbyt_id: str,
    fecha_inicio: Optional[str] = Query(None, description="YYYY-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """Lista escenas Sentinel-2 disponibles para el predio (sin descargar)."""
    from app.db.supabase_store import _client, is_available
    from app.services.satellite.sentinel import buscar_escenas
    import asyncio

    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")

    def _bbox():
        return _client().rpc("get_predio_bbox", {"p_orbyt_id": orbyt_id}).execute()
    result = await asyncio.to_thread(_bbox)
    if not result.data:
        raise HTTPException(404, f"Predio {orbyt_id} sin geometría")

    row = result.data[0]
    bbox = (float(row["lng_min"]), float(row["lat_min"]),
            float(row["lng_max"]), float(row["lat_max"]))

    fi = date.fromisoformat(fecha_inicio) if fecha_inicio else None
    ff = date.fromisoformat(fecha_fin) if fecha_fin else None

    escenas = await buscar_escenas(bbox, fecha_inicio=fi, fecha_fin=ff, max_results=20)
    return {
        "orbyt_id": orbyt_id,
        "bbox":     list(bbox),
        "total":    len(escenas),
        "escenas":  escenas,
    }
