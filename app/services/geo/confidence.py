"""
Motor de score de confianza para análisis prediales.
Calcula un porcentaje 0-100 con desglose por dimensión.
"""
from __future__ import annotations
from typing import Optional, List
from app.models.predio import ExtractedData, PolygonData, ConfidenceBreakdown, ConfidenceLevel


def calculate_confidence(
    ocr_quality: float,
    extracted: ExtractedData,
    polygon: Optional[PolygonData],
    fuentes_externas: List[str],
    direct_geometry: bool = False,
) -> ConfidenceBreakdown:

    # 1. Calidad OCR (proporcionada por el motor OCR)
    ocr_score = round(ocr_quality * 100, 1)

    # 2. Completitud de datos
    completitud = _score_completitud(extracted, direct_geometry=direct_geometry)

    # 3. Referencias externas encontradas
    refs_score = _score_referencias(fuentes_externas, extracted)

    # 4. Coherencia geométrica
    geo_score = _score_geometria(polygon, extracted)

    # Ponderación
    total = round(
        ocr_score * 0.25 +
        completitud * 0.30 +
        refs_score * 0.25 +
        geo_score * 0.20,
        1
    )

    nivel = _classify_nivel(total)
    observaciones = _build_observaciones(
        ocr_score, completitud, refs_score, geo_score, extracted, polygon,
        direct_geometry=direct_geometry
    )

    return ConfidenceBreakdown(
        ocr=ocr_score,
        completitud=completitud,
        referencias_externas=refs_score,
        coherencia_geometrica=geo_score,
        total=total,
        nivel=nivel,
        observaciones=observaciones,
    )


def _score_completitud(data: ExtractedData, direct_geometry: bool = False) -> float:
    # Para KML/GeoJSON con geometría directa, vértices y coordenadas se dan por cumplidos
    has_location = (
        direct_geometry or
        data.coordenadas_utm is not None or
        data.coordenadas_geo is not None
    )
    has_vertices = direct_geometry or len(data.vertices) >= 3
    checks = [
        data.propietario is not None,
        data.clave_catastral is not None,
        data.municipio is not None,
        data.datum is not None and 'inferido' not in (data.datum or ''),
        has_vertices,
        has_location,
        len(data.colindancias) >= 2,
        data.superficie_escritura is not None,
    ]
    return round(sum(checks) / len(checks) * 100, 1)


def _score_referencias(fuentes: list[str], data: ExtractedData) -> float:
    score = 0.0
    if 'INEGI' in fuentes:
        score += 35
    if 'OpenStreetMap' in fuentes:
        score += 25
    if 'Catastro' in fuentes:
        score += 30
    if 'Sentinel-2' in fuentes:
        score += 10
    # If colindancias identified
    identified = sum(1 for c in data.colindancias if c.identificado)
    if identified > 0:
        score += min(identified * 10, 30)
    return min(round(score, 1), 100.0)


def _score_geometria(polygon: Optional[PolygonData], data: ExtractedData) -> float:
    if polygon is None:
        return 0.0

    score = 40.0  # Base: tenemos un polígono

    # Consistencia de área vs. escritura
    if polygon.area_m2 and data.superficie_escritura:
        ratio = polygon.area_m2 / data.superficie_escritura
        if 0.95 <= ratio <= 1.05:   score += 40
        elif 0.90 <= ratio <= 1.10: score += 25
        elif 0.80 <= ratio <= 1.20: score += 10

    # Número de vértices
    if data.vertices:
        score += min(len(data.vertices) * 3, 20)

    # Centroide presente
    if polygon.centroide:
        score += 10

    # Penalización por error de cierre (Sprint 2)
    if polygon.closure_error_m is not None:
        ce = polygon.closure_error_m
        if ce > 10:    score -= 30   # error grave — probablemente rumbo mal extraído
        elif ce > 2:   score -= 15   # error moderado
        elif ce > 0.5: score -= 5    # error leve

    return min(max(round(score, 1), 0.0), 100.0)


def _classify_nivel(total: float) -> ConfidenceLevel:
    if total >= 75:
        return ConfidenceLevel.alta
    elif total >= 45:
        return ConfidenceLevel.media
    elif total > 0:
        return ConfidenceLevel.baja
    return ConfidenceLevel.sin_datos


def _build_observaciones(ocr: float, comp: float, refs: float,
                          geo: float, data: ExtractedData,
                          polygon: Optional[PolygonData],
                          direct_geometry: bool = False) -> List[str]:
    obs = []

    if ocr < 60:
        obs.append("Calidad de imagen baja — considera subir una versión de mayor resolución")
    if not data.clave_catastral:
        obs.append("Clave catastral no identificada — búsqueda en catastro no disponible")
    if 'inferido' in (data.datum or ''):
        obs.append("Datum inferido (no explícito en documento) — puede haber desplazamiento de hasta 200m")
    if not direct_geometry:
        if not data.vertices:
            obs.append("Sin vértices extraídos — ubicación aproximada basada en centroide")
        elif len(data.vertices) < 3:
            obs.append(f"Solo {len(data.vertices)} vértice(s) — polígono incompleto")
    if polygon and data.superficie_escritura and polygon.area_m2:
        diff = abs(polygon.area_m2 - data.superficie_escritura) / data.superficie_escritura * 100
        msg = "posible error en polígono vs. superficie declarada" if direct_geometry else "posible error en rumbos"
        if diff > 10:
            obs.append(f"Diferencia de área vs. declarada: {diff:.1f}% — {msg}")
    if refs < 30:
        obs.append("Pocas referencias externas encontradas — ubicación basada principalmente en documento")
    # Closure error
    if polygon and polygon.closure_error_m is not None:
        ce = polygon.closure_error_m
        if ce > 10:
            obs.append(f"Error de cierre alto: {ce:.1f}m — verificar rumbos y distancias del documento")
        elif ce > 2:
            obs.append(f"Error de cierre moderado: {ce:.1f}m — polígono aproximado")

    if not obs:
        obs.append("Análisis completo — todos los indicadores dentro del rango esperado")

    return obs
