"""
Motor Sentinel-2 — ORBYT LAND Sprint 5.

Fuente: Element84 Earth Search (STAC API, gratuita, sin autenticación)
URL:    https://earth-search.aws.element84.com/v1
Colección: sentinel-2-l2a (Level-2A, corregido atmosféricamente)

Capacidades:
- Buscar escenas disponibles por bbox + rango de fechas
- Filtrar por cobertura de nubes (máx. 20%)
- Obtener thumbnail URL de cada escena
- Calcular NDVI desde bandas COG en S3 (via rasterio overview)
- Detectar cambios entre snapshots
"""
from __future__ import annotations
import logging
import urllib.request
import urllib.parse
import json
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

STAC_BASE = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"
MAX_CLOUD_COVER = 30   # porcentaje máximo de nubes
BUFFER_DEG = 0.005     # buffer ~500m alrededor del predio


def _http_post(url: str, payload: dict, timeout: int = 12) -> Optional[dict]:
    """HTTP POST JSON sin dependencias externas."""
    try:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json", "User-Agent": "ORBYT-LAND/0.1 (orbytland.mx)"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.debug(f"HTTP POST {url[:80]} failed: {e}")
        return None


async def buscar_escenas(
    bbox: tuple[float, float, float, float],
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    max_results: int = 10,
) -> list[dict]:
    """
    Busca escenas Sentinel-2 en Microsoft Planetary Computer (gratis, sin auth).
    Retorna lista ordenada por fecha descendente, con thumbnails y URLs de bandas.
    """
    import asyncio

    if fecha_fin is None:
        fecha_fin = date.today()
    if fecha_inicio is None:
        fecha_inicio = fecha_fin - timedelta(days=365)

    lng_min, lat_min, lng_max, lat_max = bbox
    buf = BUFFER_DEG
    bbox_expanded = [lng_min - buf, lat_min - buf, lng_max + buf, lat_max + buf]

    payload = {
        "collections": [COLLECTION],
        "bbox":        bbox_expanded,
        "limit":       max_results,
        "sortby":      [{"field": "datetime", "direction": "desc"}],
        "query":       {"eo:cloud_cover": {"lte": MAX_CLOUD_COVER}},
    }

    def _fetch():
        return _http_post(f"{STAC_BASE}/search", payload)

    data = await asyncio.to_thread(_fetch)
    if not data or "features" not in data:
        logger.warning(f"Planetary Computer sin resultados para bbox={bbox_expanded}")
        return []

    escenas = []
    for feat in data["features"]:
        props  = feat.get("properties", {})
        assets = feat.get("assets", {})
        thumbnail = (
            assets.get("rendered_preview", {}).get("href") or
            assets.get("thumbnail", {}).get("href") or
            assets.get("visual", {}).get("href", "")
        )
        escenas.append({
            "scene_id":      feat.get("id", ""),
            "fecha":         props.get("datetime", "")[:10],
            "cloud_cover":   round(float(props.get("eo:cloud_cover", 0)), 1),
            "thumbnail_url": thumbnail,
            "bbox":          feat.get("bbox", []),
            "assets_href": {
                "b04": assets.get("B04", assets.get("red", {})).get("href", ""),
                "b08": assets.get("B08", assets.get("nir", {})).get("href", ""),
                "scl": assets.get("SCL", assets.get("scl", {})).get("href", ""),
            },
        })

    logger.info(f"Sentinel-2 (MPC): {len(escenas)} escenas para bbox cercano a {bbox}")
    return escenas


async def calcular_ndvi(scene: dict, bbox: tuple[float, float, float, float]) -> Optional[dict]:
    """
    Calcula NDVI (Normalized Difference Vegetation Index) para el área del predio.
    Usa el overview (baja resolución) del COG de S3 para evitar descargar toda la escena.
    Retorna dict con ndvi_mean, ndvi_min, ndvi_max o None si falla.
    """
    import asyncio

    b04_url = scene.get("assets_href", {}).get("b04", "")
    b08_url = scene.get("assets_href", {}).get("b08", "")

    if not b04_url or not b08_url:
        return None

    def _compute():
        try:
            import rasterio
            from rasterio.windows import from_bounds
            from rasterio.enums import Resampling
            import numpy as np

            lng_min, lat_min, lng_max, lat_max = bbox

            results = {}
            for band_name, url in [("red", b04_url), ("nir", b08_url)]:
                with rasterio.open(url) as src:
                    # Leer solo el overview más pequeño (nivel 3 típicamente)
                    overview_level = min(3, len(src.overviews(1)) - 1) if src.overviews(1) else 0
                    window = from_bounds(lng_min, lat_min, lng_max, lat_max, src.transform)
                    data = src.read(1, window=window, out_shape=(64, 64),
                                    resampling=Resampling.bilinear,
                                    overview_level=overview_level)
                    results[band_name] = data.astype(float)

            red = results.get("red")
            nir = results.get("nir")
            if red is None or nir is None:
                return None

            # NDVI = (NIR - Red) / (NIR + Red)
            denom = nir + red
            denom = np.where(denom == 0, 1e-10, denom)
            ndvi = (nir - red) / denom
            ndvi_valid = ndvi[(ndvi >= -1) & (ndvi <= 1)]

            if len(ndvi_valid) == 0:
                return None

            return {
                "ndvi_mean": round(float(np.mean(ndvi_valid)), 4),
                "ndvi_min":  round(float(np.min(ndvi_valid)), 4),
                "ndvi_max":  round(float(np.max(ndvi_valid)), 4),
                "pixels":    int(len(ndvi_valid)),
            }
        except ImportError:
            logger.debug("rasterio no disponible — NDVI omitido")
            return None
        except Exception as e:
            logger.debug(f"NDVI computation failed: {e}")
            return None

    return await asyncio.to_thread(_compute)


def detectar_cambio(snapshot_nuevo: dict, snapshot_base: dict) -> tuple[bool, float, str]:
    """
    Detecta cambios entre dos snapshots comparando NDVI.
    Retorna (cambio_detectado, magnitud_0_100, descripcion).
    """
    ndvi_nuevo = snapshot_nuevo.get("ndvi_mean")
    ndvi_base  = snapshot_base.get("ndvi_mean")

    if ndvi_nuevo is None or ndvi_base is None:
        return False, 0.0, "NDVI no disponible para comparación"

    delta = abs(ndvi_nuevo - ndvi_base)
    magnitud = min(delta * 200, 100.0)  # escalar a 0-100

    if delta > 0.25:
        return True, magnitud, f"Cambio severo de vegetación (ΔNDVI={delta:.3f}) — posible desmonte o construcción"
    elif delta > 0.15:
        return True, magnitud, f"Cambio moderado de vegetación (ΔNDVI={delta:.3f}) — monitorear"
    elif delta > 0.08:
        return True, magnitud, f"Cambio leve de vegetación (ΔNDVI={delta:.3f})"
    else:
        return False, magnitud, f"Sin cambios significativos (ΔNDVI={delta:.3f})"
