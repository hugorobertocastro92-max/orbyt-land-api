"""
Gestión de snapshots satelitales por ORBYT-ID.

Flujo:
1. capture_baseline(orbyt_id) — captura la imagen más reciente como baseline
2. capture_snapshot(orbyt_id) — captura imagen actual y la compara con el baseline
3. get_snapshots(orbyt_id) — retorna historial de snapshots
4. Programado mensualmente via pg_cron en Supabase
"""
from __future__ import annotations
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


async def capture_baseline(orbyt_id: str) -> Optional[dict]:
    """
    Captura la imagen satelital más reciente disponible como baseline del predio.
    Solo si no existe baseline previo.
    """
    from app.db.supabase_store import is_available
    if not is_available():
        return None

    # Verificar si ya hay baseline
    existing = await _get_existing_snapshots(orbyt_id, es_baseline=True)
    if existing:
        logger.info(f"Baseline ya existe para {orbyt_id}")
        return existing[0]

    return await _capture(orbyt_id, es_baseline=True)


async def capture_snapshot(orbyt_id: str) -> Optional[dict]:
    """
    Captura snapshot actual y detecta cambios vs baseline.
    """
    return await _capture(orbyt_id, es_baseline=False)


async def get_snapshots(orbyt_id: str, limit: int = 12) -> list[dict]:
    """Retorna historial de snapshots ordenado por fecha."""
    return await _get_existing_snapshots(orbyt_id, limit=limit)


async def _capture(orbyt_id: str, es_baseline: bool) -> Optional[dict]:
    from app.db.supabase_store import _client, is_available
    from app.services.satellite.sentinel import buscar_escenas, calcular_ndvi, detectar_cambio

    if not is_available():
        return None

    # Obtener bbox del predio desde PostGIS
    try:
        def _bbox():
            return _client().rpc("get_predio_bbox", {"p_orbyt_id": orbyt_id}).execute()
        result = await __import__('asyncio').to_thread(_bbox)
        if not result.data:
            logger.warning(f"Predio {orbyt_id} sin geometría — no se puede capturar satélite")
            return None
        bbox_row = result.data[0]
        bbox = (
            float(bbox_row["lng_min"]),
            float(bbox_row["lat_min"]),
            float(bbox_row["lng_max"]),
            float(bbox_row["lat_max"]),
        )
    except Exception as e:
        logger.error(f"Error obteniendo bbox de {orbyt_id}: {e}")
        return None

    # Buscar escenas disponibles
    escenas = await buscar_escenas(bbox, max_results=5)
    if not escenas:
        logger.warning(f"Sin escenas Sentinel-2 disponibles para {orbyt_id}")
        return _create_mock_snapshot(orbyt_id, bbox, es_baseline)

    escena = escenas[0]

    # Calcular NDVI (puede fallar silenciosamente si rasterio no está)
    ndvi = await calcular_ndvi(escena, bbox)

    # Detectar cambios vs baseline
    cambio_detectado = False
    cambio_magnitud = 0.0
    cambio_desc = None

    if not es_baseline and ndvi:
        baseline_list = await _get_existing_snapshots(orbyt_id, es_baseline=True, limit=1)
        if baseline_list:
            cambio_detectado, cambio_magnitud, cambio_desc = detectar_cambio(
                {"ndvi_mean": ndvi.get("ndvi_mean")},
                {"ndvi_mean": baseline_list[0].get("ndvi_mean")},
            )

    # Guardar snapshot
    snapshot = await _save_snapshot(
        orbyt_id=orbyt_id,
        escena=escena,
        bbox=bbox,
        ndvi=ndvi,
        es_baseline=es_baseline,
        cambio_detectado=cambio_detectado,
        cambio_magnitud=cambio_magnitud,
        cambio_desc=cambio_desc,
    )

    if cambio_detectado:
        logger.warning(f"CAMBIO DETECTADO en {orbyt_id}: {cambio_desc}")

    return snapshot


def _create_mock_snapshot(orbyt_id: str, bbox: tuple, es_baseline: bool) -> dict:
    """Snapshot sin imagen real (sin escenas disponibles o rasterio no instalado)."""
    return {
        "orbyt_id":         orbyt_id,
        "fuente":           "sentinel-2",
        "scene_id":         "no-scene-available",
        "fecha_imagen":     date.today().isoformat(),
        "cloud_cover_pct":  None,
        "thumbnail_url":    None,
        "ndvi_mean":        None,
        "cambio_detectado": False,
        "es_baseline":      es_baseline,
        "mensaje":          "Sin escenas disponibles — revisar cobertura Sentinel-2 para esta área",
    }


async def _save_snapshot(
    orbyt_id: str, escena: dict, bbox: tuple,
    ndvi: Optional[dict], es_baseline: bool,
    cambio_detectado: bool, cambio_magnitud: float, cambio_desc: Optional[str]
) -> dict:
    from app.db.supabase_store import _client
    import asyncio

    row = {
        "orbyt_id":           orbyt_id,
        "fuente":             "sentinel-2",
        "scene_id":           escena.get("scene_id"),
        "fecha_imagen":       escena.get("fecha"),
        "cloud_cover_pct":    escena.get("cloud_cover"),
        "thumbnail_url":      escena.get("thumbnail_url"),
        "ndvi_mean":          ndvi.get("ndvi_mean") if ndvi else None,
        "ndvi_min":           ndvi.get("ndvi_min") if ndvi else None,
        "ndvi_max":           ndvi.get("ndvi_max") if ndvi else None,
        "indices_json":       ndvi,
        "bbox_wkt":           f"BBOX({bbox[0]} {bbox[1]},{bbox[2]} {bbox[3]})",
        "cambio_detectado":   cambio_detectado,
        "cambio_magnitud":    cambio_magnitud,
        "cambio_descripcion": cambio_desc,
        "es_baseline":        es_baseline,
    }

    def _insert():
        return _client().table("satellite_snapshots").insert(row).execute()

    result = await asyncio.to_thread(_insert)
    saved = result.data[0] if result.data else row
    return {**saved, "orbyt_id": orbyt_id}


async def _get_existing_snapshots(
    orbyt_id: str,
    es_baseline: Optional[bool] = None,
    limit: int = 12,
) -> list[dict]:
    from app.db.supabase_store import _client, is_available
    import asyncio

    if not is_available():
        return []
    try:
        def _query():
            q = (_client().table("satellite_snapshots")
                 .select("*")
                 .eq("orbyt_id", orbyt_id)
                 .order("fecha_imagen", desc=True)
                 .limit(limit))
            if es_baseline is not None:
                q = q.eq("es_baseline", es_baseline)
            return q.execute()
        result = await asyncio.to_thread(_query)
        return result.data or []
    except Exception as e:
        logger.warning(f"get_existing_snapshots failed: {e}")
        return []
