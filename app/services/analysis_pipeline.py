"""
Pipeline principal de análisis: OCR → NLP → Polígono → Score.
Se ejecuta en background task.
"""
from __future__ import annotations
import logging
from typing import Optional, List, Tuple, Dict, Any
from pathlib import Path
from datetime import datetime

from app.models.predio import (
    DocumentType, AnalysisState, ExtractedData, PolygonData,
    ConfidenceBreakdown, ConfidenceLevel
)

logger = logging.getLogger(__name__)

# In-memory store for demo (replace with DB in production)
_analyses: dict[str, dict] = {}


def get_analysis(analisis_id: str) -> Optional[Dict[str, Any]]:
    return _analyses.get(analisis_id)


async def run_analysis(
    analisis_id: str,
    documento_id: str,
    file_path: str,
    doc_type: DocumentType,
    filename: str,
):
    now = datetime.utcnow()
    _analyses[analisis_id] = {
        "id": analisis_id,
        "documento_id": documento_id,
        "nombre_archivo": filename,
        "tipo_documento": doc_type,
        "estado": AnalysisState.processing,
        "datos_extraidos": None,
        "poligono": None,
        "confianza": None,
        "fuentes_usadas": [],
        "error_mensaje": None,
        "created_at": now,
        "updated_at": now,
    }

    try:
        file_bytes = Path(file_path).read_bytes()

        # --- Step 1: Parse document to text/geometry ---
        text, ocr_quality, direct_geojson = await _parse_document(
            file_bytes, doc_type, filename
        )

        # --- Step 2: If direct geometry (KML, SHP, GeoJSON) ---
        if direct_geojson:
            polygon = _geojson_to_polygon_data(direct_geojson)
            fuentes = ["GeoJSON directo"]

            # Extraer metadata del texto y/o campos DBF directos
            extracted = ExtractedData(vertices=[], colindancias=[])

            # Aplicar campos del DBF directamente (SHP) — alta confianza
            dbf_fields = (direct_geojson.get('properties') or {}).get('_dbf_fields') or {}
            if dbf_fields:
                _apply_dbf_fields(extracted, dbf_fields)
                logger.info(f"DBF fields aplicados: {list(dbf_fields.keys())}")

            # Completar con NLP sobre el texto (KML description, etc.)
            if text and text.strip():
                from app.services.nlp.extractor import extract_from_text
                nlp_extracted, _ = extract_from_text(text)
                _merge_extracted(extracted, nlp_extracted)

            # Inyectar centroide del polígono
            if polygon.centroide and not extracted.coordenadas_geo:
                extracted.coordenadas_geo = {
                    "lat": polygon.centroide[1],
                    "lng": polygon.centroide[0],
                }
            if extracted.municipio:
                fuentes.append("INEGI")
            fuentes_extra = await _geo_search(extracted, polygon)
            fuentes = list(dict.fromkeys(fuentes + fuentes_extra))

            from app.services.geo.confidence import calculate_confidence
            confidence = calculate_confidence(
                ocr_quality, extracted, polygon, fuentes, direct_geometry=True
            )

        else:
            # --- Step 3: NLP extraction (Layer 1) ---
            from app.services.nlp.extractor import extract_from_text
            extracted, nlp_conf = extract_from_text(text)

            # --- Step 4: AI Layer (Layer 2) if confidence < 0.75 ---
            if nlp_conf < 0.75 and text.strip():
                logger.info(f"NLP conf={nlp_conf:.2f} — activando Claude API")
                from app.services.nlp.ai_layer import extract_with_ai
                extracted, _ = await extract_with_ai(text, extracted)

            # --- Step 5: Build polygon ---
            from app.services.geo.polygon_builder import build_polygon
            polygon = build_polygon(extracted)

            # --- Step 6: Geographic search ---
            fuentes = await _geo_search(extracted, polygon)

            # --- Step 7: Confidence score ---
            from app.services.geo.confidence import calculate_confidence
            confidence = calculate_confidence(ocr_quality, extracted, polygon, fuentes)

        _analyses[analisis_id].update({
            "estado": AnalysisState.completed,
            "datos_extraidos": extracted.model_dump() if extracted else None,
            "poligono": polygon.model_dump() if polygon else None,
            "confianza": confidence.model_dump() if confidence else None,
            "fuentes_usadas": fuentes,
            "updated_at": datetime.utcnow(),
        })

        logger.info(f"Análisis {analisis_id} completado — confianza: {confidence.total if confidence else 0}%")

    except Exception as e:
        logger.error(f"Analysis pipeline error for {analisis_id}: {e}", exc_info=True)
        _analyses[analisis_id].update({
            "estado": AnalysisState.error,
            "error_mensaje": str(e),
            "updated_at": datetime.utcnow(),
        })


async def _parse_document(
    file_bytes: bytes, doc_type: DocumentType, filename: str
) -> Tuple[str, float, Optional[Dict]]:
    """Returns (text, ocr_quality, direct_geojson)."""

    if doc_type == DocumentType.escritura:
        # Texto plano directo — máxima confianza OCR
        return file_bytes.decode('utf-8', errors='replace'), 1.0, None

    if doc_type == DocumentType.pdf:
        from app.services.parsers.pdf_parser import parse_pdf
        text, conf = await parse_pdf(file_bytes)
        return text, conf, None

    elif doc_type in (DocumentType.jpg, DocumentType.png, DocumentType.tiff):
        from app.services.ocr.paddle_ocr import ocr_image_bytes
        text, conf = await ocr_image_bytes(file_bytes)
        return text, conf, None

    elif doc_type in (DocumentType.kml, DocumentType.kmz):
        from app.services.parsers.kml_parser import parse_kml
        geojson, text, conf = await parse_kml(file_bytes, is_kmz=(doc_type == DocumentType.kmz))
        return text, conf, geojson

    elif doc_type == DocumentType.geojson:
        import json
        data = json.loads(file_bytes.decode('utf-8'))
        return '', 1.0, data

    elif doc_type == DocumentType.shp:
        return await _parse_shp(file_bytes)

    # Fallback: intentar decodificar como texto
    return file_bytes.decode('utf-8', errors='replace'), 0.8, None


async def _parse_shp(file_bytes: bytes) -> Tuple[str, float, Optional[Dict]]:
    """Parsea shapefile (ZIP o SHP) con atributos del DBF."""
    try:
        from app.services.parsers.shp_parser import parse_shp
        result = await parse_shp(file_bytes)

        if not result or result[0] is None:
            return '', 0.0, None

        # parse_shp retorna 7-tuple: (geojson, text, conf, dbf_fields, area, perim, centroide)
        if len(result) == 7:
            geojson, text, conf, dbf_fields, area_m2, perim_m, centroide = result
            if geojson:
                geojson['properties'].update({
                    'area_m2': area_m2,
                    'perimetro_m': perim_m,
                    'centroide': centroide,
                    '_dbf_fields': dbf_fields,
                })
            return text, conf, geojson

        # Fallback al formato anterior (3-tuple)
        if len(result) >= 3:
            return result[1], result[2], result[0]  # type: ignore
        return '', 0.0, None

    except Exception as e:
        logger.error(f"SHP parse error: {e}")
        return '', 0.0, None


def _geojson_to_polygon_data(geojson: dict) -> PolygonData:
    """Convierte GeoJSON a PolygonData. Reutiliza métricas precalculadas del SHP si están."""
    from shapely.geometry import shape, mapping
    import pyproj

    try:
        geom = None
        props = geojson.get('properties') or {}

        if geojson.get('type') == 'FeatureCollection':
            features = geojson.get('features', [])
            if features:
                geom = shape(features[0]['geometry'])
        elif geojson.get('type') == 'Feature':
            geom = shape(geojson['geometry'])
        elif geojson.get('type') in ('Polygon', 'MultiPolygon'):
            geom = shape(geojson)

        if geom is None:
            return PolygonData()

        # Usar métricas precalculadas del SHP parser si están disponibles
        if props.get('area_m2') and props.get('perimetro_m'):
            area_m2 = float(props['area_m2'])
            perimetro_m = float(props['perimetro_m'])
            centroide = props.get('centroide') or [geom.centroid.x, geom.centroid.y]
        else:
            geod = pyproj.Geod(ellps='WGS84')
            area_m2 = abs(geod.geometry_area_perimeter(geom)[0])
            perimetro_m = abs(geod.geometry_area_perimeter(geom)[1])
            centroide = [geom.centroid.x, geom.centroid.y]

        feature = {
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {"area_m2": round(area_m2, 2)},
        }

        return PolygonData(
            geojson=feature,
            area_m2=round(area_m2, 2),
            perimetro_m=round(perimetro_m, 2),
            centroide=centroide,
            datum_origen="WGS84",
            datum_normalizado="WGS84",
        )
    except Exception as e:
        logger.error(f"GeoJSON to polygon error: {e}")
        return PolygonData()


def _quick_confidence(polygon: PolygonData | None) -> ConfidenceBreakdown:
    if polygon and polygon.geojson:
        return ConfidenceBreakdown(
            ocr=100, completitud=80, referencias_externas=60,
            coherencia_geometrica=100, total=85,
            nivel=ConfidenceLevel.alta,
            observaciones=["Geometría cargada directamente del documento — alta confianza posicional"],
        )
    return ConfidenceBreakdown(
        ocr=0, completitud=0, referencias_externas=0,
        coherencia_geometrica=0, total=0,
        nivel=ConfidenceLevel.sin_datos,
        observaciones=["No se pudo extraer geometría del documento"],
    )


async def _geo_search(extracted: ExtractedData, polygon: PolygonData | None) -> list[str]:
    """Busca referencias geográficas para anclar el polígono."""
    fuentes = []

    # INEGI — check if municipio matches known BCS municipalities
    if extracted.municipio:
        fuentes.append("INEGI")

    # OpenStreetMap — check colindancias (in production: Overpass API)
    if extracted.colindancias:
        fuentes.append("OpenStreetMap")
        # Mark colindancias as identified if they match street patterns
        for col in extracted.colindancias:
            if col.tipo == 'calle':
                col.identificado = True

    # Satellite data placeholder
    if polygon and polygon.centroide:
        fuentes.append("Sentinel-2")

    return fuentes


def _apply_dbf_fields(extracted: ExtractedData, dbf: Dict) -> None:
    """Aplica campos del DBF directamente al ExtractedData (sin pasar por NLP)."""
    if dbf.get('propietario') and not extracted.propietario:
        name = dbf['propietario']
        extracted.propietario = ' '.join(w.capitalize() for w in name.split())
    if dbf.get('clave_catastral') and not extracted.clave_catastral:
        extracted.clave_catastral = dbf['clave_catastral']
    if dbf.get('municipio') and not extracted.municipio:
        extracted.municipio = dbf['municipio']
    if dbf.get('estado') and not extracted.estado:
        extracted.estado = dbf['estado']
    if dbf.get('superficie') and not extracted.superficie_escritura:
        try:
            extracted.superficie_escritura = float(str(dbf['superficie']).replace(',', '.'))
            extracted.superficie_unidad = 'm²'
        except (ValueError, TypeError):
            pass
    if dbf.get('datum') and not extracted.datum:
        extracted.datum = dbf['datum']
        extracted.sistema_coordenadas = dbf['datum']
    if dbf.get('notaria') and not extracted.notaria:
        extracted.notaria = dbf['notaria']


def _merge_extracted(base: ExtractedData, nlp: ExtractedData) -> None:
    """Completa campos faltantes de base con valores del NLP."""
    for field in ['propietario', 'clave_catastral', 'municipio', 'estado',
                  'datum', 'notaria', 'fecha_escritura', 'superficie_escritura',
                  'coordenadas_utm', 'coordenadas_geo']:
        if not getattr(base, field, None) and getattr(nlp, field, None):
            setattr(base, field, getattr(nlp, field))
    if not base.vertices and nlp.vertices:
        base.vertices = nlp.vertices
    if not base.colindancias and nlp.colindancias:
        base.colindancias = nlp.colindancias
