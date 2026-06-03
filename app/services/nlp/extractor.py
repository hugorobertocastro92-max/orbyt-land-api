"""
Capa 1 de extracción NLP — spaCy + regex.
Cubre ~70% de escrituras sin consumir tokens de IA.
"""
import re
import logging
from typing import Optional
from app.models.predio import ExtractedData, Vertex, Colindancia
from app.services.nlp.patterns import (
    RUMBO_DIST_PATTERNS, UTM_PATTERN, UTM_VERTEX_PATTERN, GEO_PATTERN, LAT_PATTERN, LON_PATTERN,
    CLAVE_CATASTRAL_PATTERNS, PROPIETARIO_PATTERNS, NOTARIA_PATTERN, NOTARIO_PATTERN,
    MUNICIPIOS_BCS, SUPERFICIE_PATTERN, DATUM_PATTERNS,
    UTM_ZONA_PATTERN, VARA_PATTERN, VARA_TO_METER,
    parse_rumbo_grados, clean_number,
)

logger = logging.getLogger(__name__)


def extract_from_text(text: str):  # -> tuple[ExtractedData, float]
    """
    Extrae datos de escritura. Retorna (ExtractedData, confianza 0-1).
    """
    data = ExtractedData(texto_bruto=text[:2000])
    fields_found = 0
    total_fields = 8

    # --- Coordenadas UTM ---
    # Priorizar Vertice 1 si el texto tiene formato multi-vértice
    utm_match = UTM_VERTEX_PATTERN.search(text) or UTM_PATTERN.search(text)
    if utm_match:
        x = clean_number(utm_match.group(1))
        y = clean_number(utm_match.group(2))
        zona_match = UTM_ZONA_PATTERN.search(text)
        zona = f"{zona_match.group(1)}{(zona_match.group(2) or 'N').upper()}" if zona_match else "12N"
        data.coordenadas_utm = {"x": x, "y": y, "zona": zona}
        fields_found += 2

    # --- Coordenadas geográficas ---
    geo_match = GEO_PATTERN.search(text)
    if geo_match:
        lat = _dms_to_decimal(
            float(geo_match.group(1)), float(geo_match.group(2)),
            float(geo_match.group(3) or 0), geo_match.group(4)
        )
        lng = _dms_to_decimal(
            float(geo_match.group(5)), float(geo_match.group(6)),
            float(geo_match.group(7) or 0), geo_match.group(8)
        )
        data.coordenadas_geo = {"lat": lat, "lng": lng}
        fields_found += 1
    else:
        # Fallback: buscar lat y lon por separado
        lat_m = LAT_PATTERN.search(text)
        lon_m = LON_PATTERN.search(text)
        if lat_m and lon_m:
            lat = _dms_to_decimal(
                float(lat_m.group(1)), float(lat_m.group(2)),
                float(lat_m.group(3) or 0), lat_m.group(4)
            )
            lng = _dms_to_decimal(
                float(lon_m.group(1)), float(lon_m.group(2)),
                float(lon_m.group(3) or 0), lon_m.group(4)
            )
            data.coordenadas_geo = {"lat": lat, "lng": lng}
            fields_found += 1

    # --- Rumbos y distancias (vértices) ---
    vertices = _extract_vertices(text)
    if vertices:
        data.vertices = vertices
        fields_found += 1

    # --- Clave catastral ---
    for pat in CLAVE_CATASTRAL_PATTERNS:
        m = pat.search(text)
        if m:
            data.clave_catastral = m.group(1).strip()
            fields_found += 1
            break

    # --- Propietario ---
    for pat in PROPIETARIO_PATTERNS:
        m = pat.search(text)
        if m:
            name = m.group(1).strip()
            if len(name) > 5 and len(name.split()) <= 6:
                data.propietario = _title_case(name)
                fields_found += 1
                break

    # --- Municipio ---
    text_lower = text.lower()
    for pattern, municipio in MUNICIPIOS_BCS.items():
        if re.search(pattern, text_lower):
            data.municipio = municipio
            data.estado = "Baja California Sur"
            fields_found += 1
            break

    # --- Superficie ---
    sup_match = SUPERFICIE_PATTERN.search(text)
    if sup_match:
        raw_value = clean_number(sup_match.group(1))
        unit = sup_match.group(2).lower()
        if 'ha' in unit:
            data.superficie_escritura = raw_value
            data.superficie_unidad = 'ha'
        else:
            # Check varas
            data.superficie_escritura = raw_value
            data.superficie_unidad = 'm²'
        fields_found += 0.5

    # --- Varas → metros en vértices sin conversión ---
    vara_matches = VARA_PATTERN.findall(text)
    if vara_matches and not data.vertices:
        # Solo logging, conversión ocurre en polygon_builder
        logger.info(f"Varas detectadas: {len(vara_matches)}")

    # --- Datum ---
    for pat, datum_name in DATUM_PATTERNS:
        if pat.search(text):
            data.datum = datum_name
            data.sistema_coordenadas = datum_name
            break
    if not data.datum:
        data.datum = "WGS84"
        data.sistema_coordenadas = "WGS84 (inferido)"

    # --- Colindancias ---
    colindancias = _extract_colindancias(text)
    if colindancias:
        data.colindancias = colindancias

    # --- Notaría (número de escritura y notario) ---
    m_not = NOTARIO_PATTERN.search(text) or NOTARIA_PATTERN.search(text)
    if m_not:
        num = m_not.group(1).strip().rstrip(',').strip()
        data.notaria = f"Notaría {num}"
    # Número de escritura pública
    escritura_num = re.search(r'escritura\s+p[uú]blica\s+n[uú]mero\s+([\w\s]+?)(?:\n|,)', text, re.IGNORECASE)
    if escritura_num and not data.notaria:
        data.notaria = f"Escritura N° {escritura_num.group(1).strip()}"

    # --- Fecha ---
    fecha_match = re.search(
        r'\b(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|'
        r'septiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})\b',
        text, re.IGNORECASE
    )
    if fecha_match:
        data.fecha_escritura = f"{fecha_match.group(1)} de {fecha_match.group(2)} de {fecha_match.group(3)}"

    confianza = min(fields_found / total_fields, 1.0)
    return data, confianza


def _extract_vertices(text: str):  # -> list[Vertex]
    vertices = []
    seen = set()
    counter = [0]  # mutable counter for patterns without vertex number

    for pat_idx, pat in enumerate(RUMBO_DIST_PATTERNS):
        for m in pat.finditer(text):
            groups = m.groups()
            try:
                v_num, dir1, deg, mins, secs, dir2, dist_str = _parse_vertex_groups(
                    groups, pat_idx, counter
                )
                if v_num is None:
                    continue

                dist = clean_number(dist_str.rstrip('.,'))
                rumbo = parse_rumbo_grados(dir1, deg, mins, secs, dir2)
                mins_str = mins or '0'
                rumbo_txt = f"{dir1.capitalize()} {deg}°{mins_str}' {dir2.capitalize()}"

                key = (v_num, round(dist, 1))
                if key in seen:
                    continue
                seen.add(key)

                vertices.append(Vertex(
                    numero=v_num,
                    rumbo_texto=rumbo_txt,
                    rumbo_grados=round(rumbo, 4),
                    distancia_m=dist,
                    confianza=0.85,
                ))
            except (ValueError, IndexError, TypeError) as e:
                logger.debug(f"Vertex parse error pat={pat_idx} groups={groups}: {e}")
                continue

    return sorted(vertices, key=lambda v: v.numero)


def _parse_vertex_groups(groups, pat_idx, counter):
    """Extrae (v_num, dir1, deg, mins, secs, dir2, dist_str) de los grupos del match."""
    g = [g or '' for g in groups]

    if pat_idx == 0:
        # (v1, v2, dir1, deg, mins, secs, dir2, dist, unit)
        v_num = int(g[0]) if g[0].isdigit() else (counter[0] + 1)
        dir1, deg, mins, secs, dir2, dist_str = g[2], g[3], g[4], g[5], g[6], g[7]
    elif pat_idx == 1:
        # (dir1, deg, mins, secs, dir2, dist, unit)
        counter[0] += 1
        v_num = counter[0]
        dir1, deg, mins, secs, dir2, dist_str = g[0], g[1], g[2], g[3], g[4], g[5]
    elif pat_idx == 2:
        # (dir1, deg, mins, dir2, dist, unit)
        counter[0] += 1
        v_num = counter[0]
        dir1, deg, mins, secs, dir2, dist_str = g[0], g[1], g[2], '', g[3], g[4]
    elif pat_idx == 3:
        # (v1, v2, dir1, deg, dir2, dist, unit)
        v_num = int(g[0]) if g[0].isdigit() else (counter[0] + 1)
        dir1, deg, mins, secs, dir2, dist_str = g[2], g[3], '', '', g[4], g[5]
    else:
        return None, None, None, None, None, None, None

    if not deg or not dir1 or not dir2 or not dist_str:
        return None, None, None, None, None, None, None

    return v_num, dir1, deg, mins or None, secs or None, dir2, dist_str


def _extract_colindancias(text: str) -> list[Colindancia]:
    colindancias = []
    patterns = [
        (re.compile(r'al\s+(norte|sur|este|oeste|oriente|poniente)[:\s]+(?:con\s+)?([^;.\n]{5,80})', re.IGNORECASE), 'cardinal'),
        (re.compile(r'colinda\s+(?:al\s+)?(norte|sur|este|oeste)[:\s]+(?:con\s+)?([^;.\n]{5,60})', re.IGNORECASE), 'cardinal'),
    ]
    seen_lados = set()
    for pat, _ in patterns:
        for m in pat.finditer(text):
            lado = m.group(1).capitalize()
            desc = m.group(2).strip()
            if lado in seen_lados or len(desc) < 5:
                continue
            seen_lados.add(lado)
            tipo = _classify_colindancia(desc)
            colindancias.append(Colindancia(lado=lado, descripcion=desc, tipo=tipo))

    return colindancias


def _classify_colindancia(desc: str) -> str:
    desc_lower = desc.lower()
    if any(w in desc_lower for w in ['calle', 'avenida', 'bulevar', 'carretera', 'boulevard']):
        return 'calle'
    if any(w in desc_lower for w in ['río', 'arroyo', 'canal', 'laguna', 'estero']):
        return 'rio'
    if any(w in desc_lower for w in ['ejido', 'comunal', 'comunidad', 'parcela']):
        return 'ejido'
    if any(w in desc_lower for w in ['predio', 'lote', 'fracción']):
        return 'predio'
    return 'propietario'


def _dms_to_decimal(deg: float, mins: float, secs: float, direction: str) -> float:
    decimal = deg + mins / 60 + secs / 3600
    if direction.upper() in ('S', 'SUR', 'O', 'OESTE', 'W'):
        decimal = -decimal
    return round(decimal, 8)


def _title_case(s: str) -> str:
    return ' '.join(w.capitalize() for w in s.split())
