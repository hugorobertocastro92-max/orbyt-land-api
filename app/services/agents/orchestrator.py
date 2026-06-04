"""
Orchestrator — cerebro del sistema multiagente de ORBYT LAND.

Decisiones:
1. ¿Qué agentes activar? (basado en gaps de la extracción NLP)
2. ¿En paralelo o secuencial? (siempre en paralelo cuando es posible)
3. ¿Cómo fusionar resultados? (prioridad por confianza por campo)

Economía de tokens:
- NLP conf ≥ 0.85: no se activa ningún agente
- NLP conf ≥ 0.65: solo agentes para campos faltantes
- NLP conf < 0.65: todos los agentes relevantes
- Texto < 100 chars: skip (muy poco contenido para IA)
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from typing import Optional
from app.models.predio import ExtractedData, Vertex, Colindancia
from .base import AgentResult

logger = logging.getLogger(__name__)

# Umbral mínimo de confianza NLP para activar agentes
NLP_THRESHOLD_SKIP_ALL  = 0.85  # NLP excelente → no gastar tokens
NLP_THRESHOLD_SELECTIVE = 0.65  # NLP bueno → solo llenar gaps


async def orchestrate(
    text: str,
    base_data: ExtractedData,
    nlp_conf: float,
    doc_type: str = "pdf",
) -> tuple[ExtractedData, dict]:
    """
    Punto de entrada principal del sistema multiagente.

    Returns:
        (ExtractedData enriquecido, metadata de agentes para logging)
    """
    # Texto insuficiente para IA (documentos binarios, errores OCR)
    if not text or len(text.strip()) < 100:
        return base_data, {"agentes": [], "motivo_skip": "texto_insuficiente"}

    # NLP fue suficientemente bueno → no gastar tokens
    if nlp_conf >= NLP_THRESHOLD_SKIP_ALL:
        return base_data, {"agentes": [], "motivo_skip": f"nlp_conf={nlp_conf:.2f}>=0.85"}

    # Documentos con geometría directa (KML/SHP/GeoJSON) no necesitan agente topográfico
    is_direct_geometry = doc_type in ("kml", "kmz", "shp", "geojson")

    # Identificar qué campos faltan
    gaps = _identify_gaps(base_data, nlp_conf)

    if not any(vars(gaps).values()):
        return base_data, {"agentes": [], "motivo_skip": "sin_gaps"}

    # Seleccionar agentes según gaps
    tasks = {}

    if gaps.needs_catastral:
        from .catastral import AgenteCatastral
        tasks["catastral"] = AgenteCatastral().run(text, base_data)

    if gaps.needs_topografico and not is_direct_geometry:
        from .topografico import AgenteTopografico
        tasks["topografico"] = AgenteTopografico().run(text, base_data)

    if gaps.needs_juridico:
        from .juridico import AgenteJuridico
        tasks["juridico"] = AgenteJuridico().run(text, base_data)

    if not tasks:
        return base_data, {"agentes": [], "motivo_skip": "sin_agentes_necesarios"}

    logger.info(f"Orchestrator activando: {list(tasks.keys())} (nlp_conf={nlp_conf:.2f})")

    # Ejecutar todos en paralelo
    names = list(tasks.keys())
    results_raw = await asyncio.gather(*tasks.values(), return_exceptions=True)

    results: dict[str, AgentResult] = {}
    for name, res in zip(names, results_raw):
        if isinstance(res, Exception):
            logger.error(f"Agente {name} excepción: {res}")
            results[name] = AgentResult(agent_name=name, data={}, error=str(res))
        else:
            results[name] = res

    # Fusionar resultados con base_data
    enriched = _merge_all(base_data, results)

    # Metadata para trazabilidad
    meta = {
        "agentes": [
            {
                "nombre": r.agent_name,
                "confianza": r.confianza,
                "tokens_input": r.tokens_input,
                "tokens_output": r.tokens_output,
                "cached_tokens": r.cached_tokens,
                "error": r.error,
            }
            for r in results.values()
        ],
        "total_tokens": sum(r.tokens_input + r.tokens_output for r in results.values()),
    }

    logger.info(
        f"Orchestrator completado: {len(enriched.vertices)} vértices, "
        f"propietario={'✓' if enriched.propietario else '✗'}, "
        f"tokens_total={meta['total_tokens']}"
    )
    return enriched, meta


# ── Gap detection ─────────────────────────────────────────────────────────────

class Gaps:
    needs_catastral: bool = False
    needs_topografico: bool = False
    needs_juridico: bool = False


def _identify_gaps(data: ExtractedData, nlp_conf: float) -> Gaps:
    g = Gaps()
    selective = nlp_conf >= NLP_THRESHOLD_SELECTIVE

    # Catastral: falta clave o municipio
    catastral_ok = bool(data.clave_catastral and data.municipio and data.superficie_escritura)
    g.needs_catastral = not catastral_ok

    # Topográfico: falta vértices o coordenadas
    topo_ok = bool(data.vertices or (data.coordenadas_utm or data.coordenadas_geo))
    g.needs_topografico = not topo_ok

    # Jurídico: siempre útil para propietario y tipo de acto
    # En modo selectivo solo si falta propietario o notaría
    if selective:
        g.needs_juridico = not bool(data.propietario and data.notaria)
    else:
        g.needs_juridico = True

    return g


# ── Fusión de resultados ──────────────────────────────────────────────────────

def _merge_all(base: ExtractedData, results: dict[str, AgentResult]) -> ExtractedData:
    """Fusiona resultados de todos los agentes sobre los datos base."""
    merged = base.model_copy(deep=True)

    # Orden de prioridad: jurídico > catastral > topográfico
    for agent_name in ["juridico", "catastral", "topografico"]:
        result = results.get(agent_name)
        if not result or result.error or not result.data:
            continue
        merged = _apply_agent_result(merged, result, agent_name)

    return merged


def _apply_agent_result(data: ExtractedData, result: AgentResult, agent_name: str) -> ExtractedData:
    ai = result.data

    def take(key: str, current_val):
        """Toma el valor del agente solo si el campo actual está vacío."""
        new_val = ai.get(key)
        if new_val is not None and not current_val:
            return new_val
        return current_val

    if agent_name == "catastral":
        data.clave_catastral    = take("clave_catastral", data.clave_catastral)
        data.municipio          = take("municipio", data.municipio)
        data.estado             = take("estado", data.estado)
        data.superficie_escritura = take("superficie_escritura", data.superficie_escritura)
        data.superficie_unidad  = take("superficie_unidad", data.superficie_unidad)

    elif agent_name == "topografico":
        data.datum              = take("datum", data.datum)
        data.sistema_coordenadas = take("zona_utm", data.sistema_coordenadas)

        if not data.coordenadas_utm and ai.get("coordenadas_utm"):
            data.coordenadas_utm = ai["coordenadas_utm"]
        if not data.coordenadas_geo and ai.get("coordenadas_geo"):
            data.coordenadas_geo = ai["coordenadas_geo"]

        # Vértices: preferir los del agente si extrajo más
        if ai.get("vertices") and len(ai["vertices"]) > len(data.vertices):
            data.vertices = _parse_vertices(ai["vertices"])

    elif agent_name == "juridico":
        # El agente jurídico puede dar propietario_actual (nuevo dueño)
        prop = ai.get("propietario_actual") or ai.get("propietario")
        data.propietario    = take("propietario_actual", data.propietario) if prop else data.propietario
        if prop and not data.propietario:
            data.propietario = prop

        data.notaria         = take("notaria", data.notaria)
        data.fecha_escritura = take("fecha_escritura", data.fecha_escritura)

    return data


def _parse_vertices(raw_vertices: list) -> list[Vertex]:
    vertices = []
    for i, v in enumerate(raw_vertices):
        if not isinstance(v, dict):
            continue
        try:
            vertices.append(Vertex(
                numero=int(v.get("numero", i + 1)),
                rumbo_texto=v.get("rumbo_texto"),
                rumbo_grados=_to_float(v.get("rumbo_grados")),
                distancia_m=_to_float(v.get("distancia_m")),
                coord_x=_to_float(v.get("coord_x")),
                coord_y=_to_float(v.get("coord_y")),
                confianza=0.80,
            ))
        except Exception:
            continue
    return vertices


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
