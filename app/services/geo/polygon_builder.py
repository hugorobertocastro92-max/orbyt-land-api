"""
Reconstruye polígonos prediales a partir de vértices (rumbos + distancias)
o coordenadas directas usando Shapely + GeoPandas.
"""
from __future__ import annotations
import math
import logging
from typing import Optional, List, Tuple
from shapely.geometry import Polygon, mapping
from shapely.ops import transform
import pyproj

from app.models.predio import ExtractedData, PolygonData, Vertex
from app.services.nlp.patterns import VARA_TO_METER

logger = logging.getLogger(__name__)


def build_polygon(data: ExtractedData) -> Optional[PolygonData]:
    """Intenta construir un polígono a partir de los datos extraídos."""

    # Prioridad 1: GeoJSON ya incluido (KML, SHP, GeoJSON)
    # → manejado en parsers, llega directo como polígono

    # Prioridad 2: Coordenadas directas de vértices
    if data.vertices and _has_coordinates(data.vertices):
        return _build_from_coords(data)

    # Prioridad 3: Rumbos + distancias desde un punto de anclaje
    if data.vertices and _has_bearings(data.vertices):
        anchor = _find_anchor(data)
        if anchor:
            return _build_from_bearings(data.vertices, anchor, data.datum or 'WGS84')

    # Prioridad 4: Solo coordenadas del centroide (sin polígono)
    if data.coordenadas_utm or data.coordenadas_geo:
        centroide = _extract_centroide(data)
        if centroide:
            return PolygonData(
                geojson=None,
                area_m2=None,
                perimetro_m=None,
                centroide=list(centroide),
                datum_origen=data.datum or 'desconocido',
            )

    return None


def _has_coordinates(vertices: list[Vertex]) -> bool:
    return any(v.coord_x is not None and v.coord_y is not None for v in vertices)


def _has_bearings(vertices: list[Vertex]) -> bool:
    return any(v.rumbo_grados is not None and v.distancia_m is not None for v in vertices)


def _build_from_coords(data: ExtractedData) -> Optional[PolygonData]:
    """Construye polígono a partir de coordenadas absolutas de vértices."""
    coords = [
        (v.coord_x, v.coord_y)
        for v in sorted(data.vertices, key=lambda v: v.numero)
        if v.coord_x is not None and v.coord_y is not None
    ]
    if len(coords) < 3:
        return None

    # Determine if UTM or geo
    is_utm = data.coordenadas_utm is not None or (
        coords[0][0] > 180 or coords[0][0] < -180
    )

    if is_utm:
        zona = data.coordenadas_utm.get('zona', '12N') if data.coordenadas_utm else '12N'
        coords_wgs84 = _utm_to_wgs84(coords, zona, data.datum or 'WGS84')
    else:
        coords_wgs84 = coords

    return _finalize_polygon(coords_wgs84, data.datum or 'desconocido')


def _build_from_bearings(vertices: list[Vertex], anchor: tuple[float, float],
                          datum: str) -> Optional[PolygonData]:
    """
    Construye polígono aplicando rumbos y distancias desde un punto de anclaje.
    anchor = (lng, lat) en WGS84
    """
    # Project to local UTM for accurate distance calculation
    lng, lat = anchor
    zona_num = int((lng + 180) / 6) + 1
    epsg_utm = 32600 + zona_num if lat >= 0 else 32700 + zona_num

    transformer_to_utm = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg_utm}", always_xy=True)
    transformer_to_wgs = pyproj.Transformer.from_crs(f"EPSG:{epsg_utm}", "EPSG:4326", always_xy=True)

    x0, y0 = transformer_to_utm.transform(lng, lat)

    utm_coords = [(x0, y0)]
    x, y = x0, y0

    sorted_v = sorted(vertices, key=lambda v: v.numero)
    for v in sorted_v:
        if v.rumbo_grados is None or v.distancia_m is None:
            continue
        dist = _convert_distance(v.distancia_m, datum)
        bearing_rad = math.radians(v.rumbo_grados)
        dx = dist * math.sin(bearing_rad)
        dy = dist * math.cos(bearing_rad)
        x = x + dx
        y = y + dy
        utm_coords.append((x, y))

    if len(utm_coords) < 3:
        return None

    # Close polygon
    if utm_coords[0] != utm_coords[-1]:
        utm_coords.append(utm_coords[0])

    # Error de cierre — diferencia entre último vértice calculado y el primero
    closure_error = math.sqrt(
        (utm_coords[-2][0] - utm_coords[0][0])**2 +
        (utm_coords[-2][1] - utm_coords[0][1])**2
    )
    logger.info(f"Closure error: {closure_error:.2f}m")

    wgs84_coords = [transformer_to_wgs.transform(x, y) for x, y in utm_coords]
    result = _finalize_polygon(wgs84_coords, datum)
    if result:
        result.closure_error_m = round(closure_error, 3)
    return result


def _finalize_polygon(coords_wgs84: list[tuple], datum_origen: str) -> Optional[PolygonData]:
    """Crea PolygonData final con GeoJSON, área, perímetro y centroide."""
    if len(coords_wgs84) < 3:
        return None

    try:
        poly = Polygon(coords_wgs84)
        if not poly.is_valid:
            poly = poly.buffer(0)  # Fix self-intersections
        if poly.is_empty:
            return None

        # Calculate area in m² using equal-area projection
        proj_area = pyproj.Proj(proj='aea', lat_1=poly.bounds[1], lat_2=poly.bounds[3],
                                lon_0=(poly.bounds[0] + poly.bounds[2]) / 2)
        proj_wgs84 = pyproj.Proj(proj='latlong', datum='WGS84')
        transformer = pyproj.Transformer.from_proj(proj_wgs84, proj_area, always_xy=True)
        poly_proj = transform(transformer.transform, poly)
        area_m2 = round(poly_proj.area, 2)

        # Perimeter in meters using geodesic
        geod = pyproj.Geod(ellps='WGS84')
        perimetro_m = round(abs(geod.geometry_length(poly)), 2)

        centroide_point = poly.centroid
        centroide = [round(centroide_point.x, 8), round(centroide_point.y, 8)]

        geojson = {
            "type": "Feature",
            "geometry": mapping(poly),
            "properties": {"area_m2": area_m2, "datum_origen": datum_origen},
        }

        return PolygonData(
            geojson=geojson,
            area_m2=area_m2,
            perimetro_m=perimetro_m,
            centroide=centroide,
            datum_origen=datum_origen,
            datum_normalizado="WGS84",
        )

    except Exception as e:
        logger.error(f"Polygon finalization error: {e}")
        return None


def _utm_to_wgs84(coords: list[tuple], zona: str, datum: str) -> list[tuple]:
    """Convierte coordenadas UTM a WGS84."""
    zona_num = int(re.sub(r'[NS]', '', zona)) if isinstance(zona, str) else int(zona)
    is_north = 'S' not in str(zona).upper()
    epsg = 32600 + zona_num if is_north else 32700 + zona_num

    src_crs = "EPSG:4326"
    if datum == 'NAD27':
        src_crs = f"EPSG:{26700 + zona_num if not is_north else 26600 + zona_num}"
    else:
        src_crs = f"EPSG:{epsg}"

    transformer = pyproj.Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
    return [transformer.transform(x, y) for x, y in coords]


def _find_anchor(data: ExtractedData) -> Optional[tuple[float, float]]:
    """
    Busca un punto de anclaje geográfico para los rumbos.
    Nivel 1: coordenadas GPS/UTM explícitas en el documento.
    Nivel 2: geocodificación de colindancias via Nominatim OSM.
    Nivel 3: geocodificación del municipio como punto aproximado.
    """
    # Nivel 1 — coordenadas directas
    if data.coordenadas_geo:
        return (data.coordenadas_geo['lng'], data.coordenadas_geo['lat'])
    if data.coordenadas_utm:
        utm = data.coordenadas_utm
        results = _utm_to_wgs84([(utm['x'], utm['y'])], utm.get('zona', '12N'), data.datum or 'WGS84')
        if results:
            return results[0]

    # Nivel 2 — ancla por colindancia de calle identificable
    if data.colindancias and data.municipio:
        calles = [c for c in data.colindancias if c.tipo == 'calle']
        for col in calles[:2]:
            anchor = _geocode_nominatim(col.descripcion, data.municipio, data.estado)
            if anchor:
                logger.info(f"Ancla por colindancia '{col.descripcion}': {anchor}")
                return anchor

    # Nivel 3 — ancla aproximada por municipio
    if data.municipio:
        anchor = _geocode_nominatim(data.municipio, data.estado or 'México', '')
        if anchor:
            logger.info(f"Ancla aproximada por municipio '{data.municipio}': {anchor}")
            return anchor

    return None


def _geocode_nominatim(query: str, municipio: str, estado: str) -> Optional[tuple[float, float]]:
    """Geocodifica via Nominatim OSM. Retorna (lng, lat) o None."""
    try:
        import urllib.request, urllib.parse, json as _json, time
        search = f"{query}, {municipio}, {estado}, México".strip(', ')
        params = urllib.parse.urlencode({
            'q': search, 'format': 'json', 'limit': 1,
            'countrycodes': 'mx', 'addressdetails': 0,
        })
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        req = urllib.request.Request(url, headers={'User-Agent': 'ORBYT-LAND/0.1 (orbytland.mx)'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read())
        if data:
            lng = float(data[0]['lon'])
            lat = float(data[0]['lat'])
            # Validar que las coords estén dentro de México aproximadamente
            if -118 <= lng <= -86 and 14 <= lat <= 33:
                return (lng, lat)
    except Exception as e:
        logger.debug(f"Nominatim geocode failed for '{query}': {e}")
    return None


def _extract_centroide(data: ExtractedData) -> Optional[tuple[float, float]]:
    if data.coordenadas_geo:
        return (data.coordenadas_geo['lng'], data.coordenadas_geo['lat'])
    if data.coordenadas_utm:
        utm = data.coordenadas_utm
        results = _utm_to_wgs84([(utm['x'], utm['y'])], utm.get('zona', '12N'), data.datum or 'WGS84')
        if results:
            return results[0]
    return None


def _convert_distance(dist: float, datum: str) -> float:
    """Distancias ya vienen en metros desde el extractor (varas convertidas ahí)."""
    return dist


import re
