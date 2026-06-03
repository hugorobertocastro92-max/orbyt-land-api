"""
Parser para Shapefiles (SHP).
Acepta:
  - ZIP con .shp + .dbf + .shx + .prj (formato estándar de distribución)
  - SHP individual (requiere que dbf/shx estén en el mismo path)

Extrae geometría WGS84 y atributos del DBF como texto para el NLP.
"""
from __future__ import annotations
import io
import logging
import zipfile
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# Mapeo de nombres de campo DBF comunes → campos de ExtractedData
DBF_FIELD_MAP = {
    # Propietario
    'PROPIETARI': 'propietario', 'PROPIETARIO': 'propietario',
    'OWNER': 'propietario', 'NOMBRE': 'propietario',
    # Clave catastral
    'CLAVE_CAT': 'clave_catastral', 'CLAVE': 'clave_catastral',
    'CATASTRO': 'clave_catastral', 'CVE_CAT': 'clave_catastral',
    'FOLIO': 'clave_catastral',
    # Municipio
    'MUNICIPIO': 'municipio', 'MUN': 'municipio', 'MUNICIPALITY': 'municipio',
    # Estado
    'ESTADO': 'estado', 'STATE': 'estado',
    # Superficie
    'SUPERFICIE': 'superficie', 'AREA': 'superficie', 'AREA_M2': 'superficie',
    # Datum
    'DATUM': 'datum', 'CRS': 'datum',
    # Notaría
    'NOTARIA': 'notaria', 'NOTARIO': 'notaria',
}


async def parse_shp(file_bytes: bytes) -> Tuple[Optional[Dict], str, float]:
    """
    Parsea SHP/ZIP y retorna (geojson_feature, texto_metadata, confianza).
    """
    try:
        import geopandas as gpd
        import pyproj
        from shapely.geometry import mapping

        # Leer con geopandas (acepta ZIP directamente)
        buf = io.BytesIO(file_bytes)
        if _is_zip(file_bytes):
            gdf = gpd.read_file(buf)
        else:
            # SHP suelto — intentar leer directamente
            gdf = gpd.read_file(buf)

        if gdf is None or gdf.empty:
            return None, '', 0.2

        # Tomar primera feature con geometría
        row = gdf[gdf.geometry.notna()].iloc[0]
        geom = row.geometry

        # Reproyectar a WGS84 si necesario
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf_wgs = gdf.to_crs(epsg=4326)
            row = gdf_wgs[gdf_wgs.geometry.notna()].iloc[0]
            geom = row.geometry
            logger.info(f"SHP reproyectado de {gdf.crs} a WGS84")

        # Calcular métricas geodésicas
        geod = pyproj.Geod(ellps='WGS84')
        area_m2 = abs(geod.geometry_area_perimeter(geom)[0])
        perim_m = abs(geod.geometry_area_perimeter(geom)[1])
        centroide = [round(geom.centroid.x, 8), round(geom.centroid.y, 8)]

        geojson = {
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {"area_m2": round(area_m2, 2)},
        }

        # Extraer atributos del DBF para NLP
        attrs = {k: v for k, v in row.items() if k != 'geometry' and v is not None}
        metadata_text = _attrs_to_text(attrs)
        extracted_fields = _map_dbf_fields(attrs)

        logger.info(f"SHP: {len(gdf)} feat, area={area_m2:.1f}m², attrs={list(attrs.keys())}")

        return (
            geojson,
            metadata_text,
            0.98,
            extracted_fields,
            round(area_m2, 2),
            round(perim_m, 2),
            centroide,
        )

    except Exception as e:
        logger.error(f"SHP parse error: {e}", exc_info=True)
        return None, '', 0.0


def _is_zip(data: bytes) -> bool:
    return data[:4] == b'PK\x03\x04'


def _attrs_to_text(attrs: Dict) -> str:
    """Convierte atributos DBF a texto legible para el NLP."""
    lines = []
    for k, v in attrs.items():
        if v and str(v).strip() and str(v) != 'None':
            lines.append(f"{k}: {v}")
    return '\n'.join(lines)


def _map_dbf_fields(attrs: Dict) -> Dict[str, Any]:
    """Mapea campos DBF a nombres del modelo ExtractedData."""
    result: Dict[str, Any] = {}
    for dbf_key, val in attrs.items():
        mapped = DBF_FIELD_MAP.get(dbf_key.upper())
        if mapped and val and str(val).strip() not in ('None', ''):
            result[mapped] = str(val).strip()
    return result
