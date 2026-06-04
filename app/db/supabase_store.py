"""
Capa de persistencia Supabase — reemplaza el dict en memoria.
Sprint 1: análisis completados se persisten; en-proceso viven en memoria.
"""
from __future__ import annotations
import os
import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# ─── cliente ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _client():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY", "")
    )
    if not url or not key:
        return None
    return create_client(url, key)


def is_available() -> bool:
    return _client() is not None


# ─── SHA-256 deduplicación ──────────────────────────────────────────────────

def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def find_by_hash(file_hash: str) -> Optional[dict]:
    """Retorna el análisis existente si el documento ya fue procesado."""
    if not is_available():
        return None
    try:
        def _query():
            return (
                _client()
                .table("documentos")
                .select("analisis_id, orbyt_id, score_confianza, estado, campos_json, poligono_json, created_at")
                .eq("hash_sha256", file_hash)
                .eq("estado", "completed")
                .limit(1)
                .execute()
            )
        result = await asyncio.to_thread(_query)
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning(f"Supabase hash lookup failed: {e}")
        return None


# ─── guardar análisis ────────────────────────────────────────────────────────

async def save_analysis(
    analisis_id: str,
    documento_id: str,
    filename: str,
    doc_type: str,
    file_hash: str,
    analysis_result: dict,
) -> Optional[str]:
    """
    Persiste el análisis completo en Supabase.
    Genera ORBYT-ID si hay polígono disponible.
    Retorna el orbyt_id asignado (o None si falla).
    """
    if not is_available():
        return None

    try:
        extracted = analysis_result.get("datos_extraidos") or {}
        polygon   = analysis_result.get("poligono")
        confianza = analysis_result.get("confianza") or {}
        score     = confianza.get("total")

        # ── 1. Generar o encontrar ORBYT-ID ──────────────────────────────
        orbyt_id = await _assign_orbyt_id(polygon, extracted)

        # ── 2. Crear/actualizar predio si hay polígono ────────────────────
        if orbyt_id and polygon:
            await _upsert_predio(orbyt_id, polygon, extracted, score)

        # ── 3. Guardar documento ──────────────────────────────────────────
        await _save_documento(
            analisis_id=analisis_id,
            orbyt_id=orbyt_id,
            filename=filename,
            doc_type=doc_type,
            file_hash=file_hash,
            analysis_result=analysis_result,
            score=score,
        )

        # ── 4. Guardar propietario si encontrado ──────────────────────────
        if orbyt_id and extracted.get("propietario"):
            await _save_propietario(orbyt_id, extracted, analisis_id)

        # ── 5. Detectar conflictos si hay polígono ────────────────────────
        if orbyt_id and polygon and polygon.get("geojson"):
            await _check_and_save_conflicts(orbyt_id)

        # ── 6. Baseline satelital (background, no bloquea) ────────────────
        if orbyt_id and polygon and polygon.get("geojson"):
            try:
                from app.services.satellite.snapshots import capture_baseline
                asyncio.create_task(capture_baseline(orbyt_id))
            except Exception:
                pass

        logger.info(f"Análisis {analisis_id} persistido → {orbyt_id or 'sin ORBYT-ID'}")
        return orbyt_id

    except Exception as e:
        logger.error(f"Error persistiendo análisis {analisis_id}: {e}", exc_info=True)
        return None


# ─── leer análisis ───────────────────────────────────────────────────────────

async def get_analysis(analisis_id: str) -> Optional[dict]:
    """Lee un análisis desde Supabase y lo convierte al formato de la API."""
    if not is_available():
        return None
    try:
        def _query():
            return (
                _client()
                .table("documentos")
                .select("*")
                .eq("analisis_id", analisis_id)
                .limit(1)
                .execute()
            )
        result = await asyncio.to_thread(_query)
        if not result.data:
            return None
        row = result.data[0]
        return _row_to_analisis(row)
    except Exception as e:
        logger.warning(f"Supabase get_analysis failed: {e}")
        return None


async def list_predios(municipio: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Lista predios con sus últimos documentos."""
    if not is_available():
        return []
    try:
        def _query():
            q = (
                _client()
                .table("documentos")
                .select("analisis_id, orbyt_id, nombre_archivo, campos_json, poligono_json, score_confianza, created_at")
                .eq("estado", "completed")
                .order("created_at", desc=True)
                .limit(limit)
            )
            return q.execute()
        result = await asyncio.to_thread(_query)
        return [_row_to_predio(r) for r in result.data]
    except Exception as e:
        logger.warning(f"Supabase list_predios failed: {e}")
        return []


# ─── helpers privados ─────────────────────────────────────────────────────────

async def _assign_orbyt_id(polygon: Optional[dict], extracted: dict) -> Optional[str]:
    """Genera un ORBYT-ID llamando a la función PostgreSQL."""
    if not polygon:
        return None
    try:
        municipio = extracted.get("municipio", "")
        estado    = extracted.get("estado", "")

        # Mapeo simple estado → código
        estado_codes = {
            "Baja California Sur": "BCS",
            "Baja California":     "BCN",
            "Jalisco":             "JAL",
            "Ciudad de México":    "CMX",
            "Sonora":              "SON",
        }
        municipio_codes = {
            "La Paz":    "LPZ",
            "Los Cabos": "CSB",
            "Loreto":    "LOR",
            "Comondú":   "COM",
            "Mulegé":    "MUL",
        }

        estado_code    = estado_codes.get(estado, "MX0")
        municipio_code = municipio_codes.get(municipio, "GEN")

        def _call():
            return _client().rpc("generate_orbyt_id", {
                "p_pais":           "MX",
                "p_estado_code":    estado_code,
                "p_municipio_code": municipio_code,
                "p_municipio_inegi": municipio_code,
            }).execute()

        result = await asyncio.to_thread(_call)
        return result.data if isinstance(result.data, str) else None
    except Exception as e:
        logger.warning(f"ORBYT-ID generation failed: {e}")
        return None


async def _upsert_predio(orbyt_id: str, polygon: dict, extracted: dict, score: Optional[float]):
    """Inserta o actualiza el registro del predio."""
    centroide = polygon.get("centroide")
    geojson   = polygon.get("geojson")

    predio_data = {
        "orbyt_id":         orbyt_id,
        "area_m2":          polygon.get("area_m2"),
        "perimetro_m":      polygon.get("perimetro_m"),
        "municipio_nombre": extracted.get("municipio"),
        "estado_nombre":    extracted.get("estado"),
        "pais":             "MX",
        "score_confianza":  score,
        "updated_at":       datetime.utcnow().isoformat(),
    }

    # Insertar geometría como WKT via SQL cuando hay polígono
    if geojson and geojson.get("geometry"):
        import json
        geom_str = json.dumps(geojson["geometry"])
        def _with_geom():
            return _client().rpc("upsert_predio_with_geom", {
                "p_orbyt_id":      orbyt_id,
                "p_geom_json":     geom_str,
                "p_area_m2":       polygon.get("area_m2"),
                "p_perimetro":     polygon.get("perimetro_m"),
                "p_centroide_lng": centroide[0] if centroide else None,
                "p_centroide_lat": centroide[1] if centroide else None,
                "p_municipio":     extracted.get("municipio"),
                "p_estado":        extracted.get("estado"),
                "p_score":         score,
            }).execute()
        try:
            await asyncio.to_thread(_with_geom)
            return
        except Exception:
            pass

    # Fallback: sin geometría (solo metadatos)
    def _upsert():
        return (
            _client()
            .table("predios")
            .upsert(predio_data, on_conflict="orbyt_id")
            .execute()
        )
    await asyncio.to_thread(_upsert)


async def _save_documento(
    analisis_id: str, orbyt_id: Optional[str], filename: str,
    doc_type: str, file_hash: str, analysis_result: dict, score: Optional[float]
):
    import json
    row = {
        "analisis_id":     analisis_id,
        "orbyt_id":        orbyt_id,
        "tipo":            doc_type,
        "nombre_archivo":  filename,
        "hash_sha256":     file_hash,
        "ocr_confianza":   (analysis_result.get("confianza") or {}).get("ocr"),
        "campos_json":     analysis_result.get("datos_extraidos"),
        "poligono_json":   analysis_result.get("poligono"),
        "agentes_json":    analysis_result.get("confianza"),
        "score_confianza": score,
        "estado":          analysis_result.get("estado", "completed"),
        "error_mensaje":   analysis_result.get("error_mensaje"),
        "fuentes_usadas":  analysis_result.get("fuentes_usadas", []),
        "updated_at":      datetime.utcnow().isoformat(),
    }

    def _upsert():
        return (
            _client()
            .table("documentos")
            .upsert(row, on_conflict="hash_sha256")
            .execute()
        )
    await asyncio.to_thread(_upsert)


async def _save_propietario(orbyt_id: str, extracted: dict, analisis_id: str):
    row = {
        "orbyt_id":      orbyt_id,
        "nombre":        extracted["propietario"],
        "tipo":          "fisica",
        "vigente_desde": None,
        "vigente_hasta": None,
    }
    def _insert():
        # No duplicar si ya existe mismo nombre+orbyt_id
        existing = (
            _client().table("propietarios")
            .select("id").eq("orbyt_id", orbyt_id)
            .eq("nombre", extracted["propietario"])
            .limit(1).execute()
        )
        if not existing.data:
            _client().table("propietarios").insert(row).execute()
    await asyncio.to_thread(_insert)


async def _check_and_save_conflicts(orbyt_id: str):
    """Detecta overlaps y guarda conflictos."""
    try:
        def _detect():
            return _client().rpc("detect_overlaps", {"p_orbyt_id": orbyt_id}).execute()
        result = await asyncio.to_thread(_detect)
        for row in (result.data or []):
            conflicting = row.get("conflicting_orbyt_id")
            area        = row.get("overlap_area_m2", 0)
            if not conflicting or area < 1:
                continue
            conflict_row = {
                "tipo":        "overlap",
                "orbyt_ids":   [orbyt_id, conflicting],
                "area_m2":     area,
                "descripcion": f"Superposición de {area:.1f} m² entre {orbyt_id} y {conflicting}",
                "estado":      "activo",
            }
            def _save(r=conflict_row):
                _client().table("conflictos").insert(r).execute()
            await asyncio.to_thread(_save)
            logger.warning(f"Conflicto detectado: {orbyt_id} ↔ {conflicting} ({area:.1f} m²)")
    except Exception as e:
        logger.debug(f"Conflict detection skipped: {e}")


# ─── conversores ─────────────────────────────────────────────────────────────

def _row_to_analisis(row: dict) -> dict:
    campos = row.get("campos_json") or {}
    poligono = row.get("poligono_json")
    confianza = row.get("agentes_json")
    # Normalizar tipo (puede venir como "DocumentType.kml" de registros antiguos)
    tipo_raw = row.get("tipo", "pdf")
    tipo = tipo_raw.split(".")[-1] if "." in tipo_raw else tipo_raw
    # Normalizar estado
    estado_raw = row.get("estado", "completed")
    estado_map = {"completed": "completed", "error": "error", "pending": "pending", "processing": "processing"}
    estado = estado_map.get(estado_raw, "completed")
    return {
        "id":              row["analisis_id"],
        "documento_id":    row.get("id", ""),
        "nombre_archivo":  row.get("nombre_archivo", ""),
        "tipo_documento":  tipo,
        "estado":          estado,
        "datos_extraidos": campos,
        "poligono":        poligono,
        "confianza":       confianza,
        "fuentes_usadas":  row.get("fuentes_usadas") or [],
        "error_mensaje":   row.get("error_mensaje"),
        "created_at":      str(row.get("created_at", "")),
        "updated_at":      str(row.get("updated_at", row.get("created_at", ""))),
    }


def _row_to_predio(row: dict) -> dict:
    campos   = row.get("campos_json") or {}
    poligono = row.get("poligono_json") or {}
    centroide = poligono.get("centroide")
    geojson   = poligono.get("geojson")
    return {
        "id":             row.get("orbyt_id") or row.get("analisis_id", ""),
        "analisis_id":    row.get("analisis_id", ""),
        "nombre_archivo": row.get("nombre_archivo", ""),
        "municipio":      campos.get("municipio"),
        "estado_mx":      campos.get("estado"),
        "propietario":    campos.get("propietario"),
        "clave_catastral":campos.get("clave_catastral"),
        "area_m2":        poligono.get("area_m2"),
        "confianza_total":row.get("score_confianza"),
        "confianza_nivel":_nivel_from_score(row.get("score_confianza")),
        "centroide":      centroide,
        "geojson":        geojson,
        "created_at":     str(row.get("created_at", "")),
    }


async def list_conflictos(
    orbyt_id: Optional[str] = None,
    estado: Optional[str] = "activo",
    limit: int = 50,
) -> list[dict]:
    if not is_available():
        return []
    try:
        def _query():
            q = _client().table("conflictos").select("*").order("detected_at", desc=True).limit(limit)
            if estado:
                q = q.eq("estado", estado)
            return q.execute()
        result = await asyncio.to_thread(_query)
        rows = result.data or []
        if orbyt_id:
            rows = [r for r in rows if orbyt_id in (r.get("orbyt_ids") or [])]
        return [_row_to_conflicto(r) for r in rows]
    except Exception as e:
        logger.warning(f"list_conflictos failed: {e}")
        return []


async def get_predio_by_orbyt_id(orbyt_id: str) -> Optional[dict]:
    if not is_available():
        return None
    try:
        def _query():
            return _client().table("predios").select("*").eq("orbyt_id", orbyt_id).limit(1).execute()
        result = await asyncio.to_thread(_query)
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning(f"get_predio_by_orbyt_id failed: {e}")
        return None


async def resolver_conflicto(conflicto_id: str, motivo: str) -> bool:
    if not is_available():
        return False
    try:
        from datetime import datetime
        def _update():
            return _client().table("conflictos").update({
                "estado": "resuelto",
                "resolved_at": datetime.utcnow().isoformat(),
                "metadata": {"motivo_resolucion": motivo},
            }).eq("id", conflicto_id).execute()
        result = await asyncio.to_thread(_update)
        return bool(result.data)
    except Exception as e:
        logger.warning(f"resolver_conflicto failed: {e}")
        return False


def _row_to_conflicto(row: dict) -> dict:
    return {
        "id":           str(row.get("id", "")),
        "tipo":         row.get("tipo", "otro"),
        "orbyt_ids":    row.get("orbyt_ids") or [],
        "area_m2":      float(row["area_m2"]) if row.get("area_m2") else None,
        "estado":       row.get("estado", "activo"),
        "descripcion":  row.get("descripcion"),
        "detected_at":  str(row.get("detected_at", "")),
        "resolved_at":  str(row.get("resolved_at")) if row.get("resolved_at") else None,
    }


def _nivel_from_score(score) -> str:
    if score is None:
        return "sin_datos"
    if score >= 75:
        return "alta"
    if score >= 45:
        return "media"
    return "baja"
