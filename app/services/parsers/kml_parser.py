"""Parser para KML y KMZ — extrae geometría y metadata de Placemarks."""
from __future__ import annotations
import io
import zipfile
import logging
import re
from typing import Optional, List

logger = logging.getLogger(__name__)


async def parse_kml(file_bytes: bytes, is_kmz: bool = False):
    """
    Extrae polígono y texto descriptivo de KML/KMZ.
    Retorna (geojson_feature, texto_para_nlp, confianza).
    """
    try:
        kml_bytes = file_bytes
        if is_kmz:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                kml_name = next((n for n in zf.namelist() if n.endswith('.kml')), None)
                if not kml_name:
                    raise ValueError("KMZ sin archivo KML interno")
                kml_bytes = zf.read(kml_name)

        kml_text = kml_bytes.decode('utf-8', errors='replace')

        # Extraer todos los Placemarks
        placemarks = _extract_placemarks(kml_text)
        # Usar el primero con coordenadas
        placemark = next((p for p in placemarks if p['coords']), None)

        if not placemark:
            # Fallback: buscar coordenadas en cualquier lugar del KML
            coords = _parse_coordinates_block(
                re.search(r'<coordinates>(.*?)</coordinates>', kml_text, re.DOTALL)
            )
            name = _clean_text(re.search(r'<name>(.*?)</name>', kml_text, re.DOTALL))
            desc = _clean_description(
                re.search(r'<description>(.*?)</description>', kml_text, re.DOTALL | re.IGNORECASE)
            )
            if not coords or len(coords) < 3:
                return None, f"{name}\n{desc}".strip(), 0.2
            placemark = {'name': name, 'description': desc, 'coords': coords}

        coords = placemark['coords']
        name = placemark['name']

        # Combinar todos los textos descriptivos para el NLP
        all_text_parts = [name, placemark['description']]
        # Añadir también los textos de otros placemarks (extended data, etc.)
        for p in placemarks:
            if p.get('extended_data'):
                all_text_parts.append(p['extended_data'])
        full_text = '\n'.join(t for t in all_text_parts if t).strip()

        geojson = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {"name": name, "description": placemark['description']},
        }

        return geojson, full_text, 0.98

    except Exception as e:
        logger.error(f"KML parse error: {e}")
        return None, '', 0.0


def _extract_placemarks(kml: str) -> List[dict]:
    """Extrae todos los Placemarks del KML con nombre, descripción y coords."""
    results = []
    for pm_match in re.finditer(r'<Placemark[^>]*>([\s\S]*?)</Placemark>', kml, re.IGNORECASE):
        pm = pm_match.group(1)

        name = _clean_text(re.search(r'<name>(.*?)</name>', pm, re.DOTALL))
        desc = _clean_description(re.search(r'<description>(.*?)</description>', pm, re.DOTALL | re.IGNORECASE))

        # ExtendedData key-value pairs
        extended = []
        for ed in re.finditer(r'<SimpleData\s+name=["\'](\w+)["\']>(.*?)</SimpleData>', pm, re.DOTALL):
            extended.append(f"{ed.group(1)}: {ed.group(2).strip()}")
        for ed in re.finditer(r'<Data\s+name=["\']([^"\']+)["\']>[\s\S]*?<value>(.*?)</value>', pm, re.DOTALL):
            extended.append(f"{ed.group(1)}: {ed.group(2).strip()}")

        coords_match = re.search(r'<coordinates>(.*?)</coordinates>', pm, re.DOTALL)
        coords = _parse_coordinates_block(coords_match)

        results.append({
            'name': name,
            'description': desc,
            'extended_data': '\n'.join(extended),
            'coords': coords,
        })

    return results


def _parse_coordinates_block(match) -> List[List[float]]:
    if not match:
        return []
    raw = match.group(1).strip()
    coords = []
    for point in raw.split():
        parts = point.strip().split(',')
        if len(parts) >= 2:
            try:
                coords.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def _clean_text(match) -> str:
    if not match:
        return ''
    return match.group(1).strip()


def _clean_description(match) -> str:
    if not match:
        return ''
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', match.group(1))
    text = re.sub(r'<[^>]+>', ' ', text)
    # Normalizar espacios múltiples y líneas
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()[:1000]
