"""
Patrones regex para escrituras notariales mexicanas.
Cubre variaciones comunes de notarías en Baja California Sur.
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class RumboDistancia:
    rumbo_texto: str
    rumbo_grados: float
    distancia_m: float
    numero_vertice: Optional[int] = None


# Grados — acepta símbolo ° y la palabra "grados" (para OCR que no lee símbolos)
_DEG = r'(?:[°º]|\s+grados?\s+)'
_MIN = r"(?:[‘`]\s*|\s+minutos?\s+)"
_SEC = r'(?:["¨]\s*|\s+segundos?\s+)?'
_DIR1 = r'(Norte|Sur|N|S)'
_DIR2 = r'(Este|Oeste|Oriente|Poniente|E|O|W)'

# Patrones de rumbos y distancias — escrituras notariales mexicanas
RUMBO_DIST_PATTERNS = [
    # "Del vértice 1 al vértice 2 ... rumbo Norte 89°45' Este ... 49.50 metros"
    # También: "Norte 89 grados 45 minutos Este ... distancia de 49.50 metros"
    re.compile(
        r'(?:del\s+)?v[eé]rtice\s+(\d+)\s+al\s+v[eé]rtice\s+(\d+)'
        r'[\s\S]{0,50}?'
        r'rumbo\s+' + _DIR1 + r'[^\d]*(\d+)' + _DEG + r'(\d+)?' + _MIN + r'(\d+)?' + _SEC
        + _DIR2 + r'[\s\S]{0,40}?'
        r'([\d,]+\.?\d*)\s*(metros?|m[^a-z])',
        re.IGNORECASE
    ),
    # "rumbo Norte 89 grados 45 minutos Este, distancia de 49.50 metros"
    re.compile(
        r'rumbo\s+' + _DIR1 + r'[^\d]*(\d+)' + _DEG + r'(\d+)?' + _MIN + r'(\d+)?' + _SEC
        + _DIR2 + r'[,\s]+(?:distancia\s+de\s+)?'
        r'([\d,]+\.?\d*)\s*(metros?|m[^a-z])',
        re.IGNORECASE
    ),
    # "N 35°30' E, 125.50 m"  o  "Norte 35 grados 30 minutos Este, 125.50 m"
    re.compile(
        _DIR1 + r'\s+(\d+)' + _DEG + r'(\d+)?' + _MIN
        + _DIR2 + r'[,\s]+([\d,]+\.?\d*)\s*(m[^a-z]|metros?)',
        re.IGNORECASE
    ),
    # "Del v1 al v2 rumbo N 35.5 E distancia 125.50 m"
    re.compile(
        r'(?:del\s+)?v[eé]rtice\s+(\d+)\s+al\s+v[eé]rtice\s+(\d+)'
        r'[\s\S]{0,40}?'
        r'rumbo[:\s]+' + _DIR1 + r'\s*(\d+\.?\d*)\s*' + _DIR2
        + r'[,\s]+(?:distancia[:\s]+)?([\d,]+\.?\d*)\s*(m[^a-z]|metros?)',
        re.IGNORECASE
    ),
]

# Coordenadas UTM — acepta formato "Vertice 1  X = 488,150.40  Y = 2,669,830.60"
# y también "X: 488150.40  Y: 2669830.60"
UTM_PATTERN = re.compile(
    r'[XxEe][:\s=]*\s*([\d,]+\.?\d+)\s*[,;\n\s]*'
    r'[YyNn][:\s=]*\s*([\d,]+\.?\d+)',
    re.IGNORECASE
)

# Patrón alternativo para formato "Vertice N:  X = ...  Y = ..."
UTM_VERTEX_PATTERN = re.compile(
    r'[Vv][eé]rtice\s+1[\s\S]{0,40}?'
    r'[XxEe][:\s=]*\s*([\d,]+\.?\d+)[\s\S]{0,40}?'
    r'[YyNn][:\s=]*\s*([\d,]+\.?\d+)',
    re.IGNORECASE
)

# Coordenadas geográficas — separador flexible para "Longitud:" entre coords
GEO_PATTERN = re.compile(
    r'(\d{1,3})[°º]\s*(\d{1,2})\'?\s*(\d{1,2}\.?\d*)?\"?\s*(N|S|Norte|Sur)'
    r'[^0-9]{1,40}'
    r'(\d{1,3})[°º]\s*(\d{1,2})\'?\s*(\d{1,2}\.?\d*)?\"?\s*(E|O|Este|Oeste|W)',
    re.IGNORECASE
)
# Latitud sola (para combinar con longitud por separado)
LAT_PATTERN = re.compile(
    r'(?:latitud[:\s]+)?(\d{1,3})[°º]\s*(\d{1,2})\'?\s*(\d{1,2}\.?\d*)?\"?\s*(N|S|Norte|Sur)',
    re.IGNORECASE
)
LON_PATTERN = re.compile(
    r'(?:longitud[:\s]+)?(\d{1,3})[°º]\s*(\d{1,2})\'?\s*(\d{1,2}\.?\d*)?\"?\s*(E|O|Este|Oeste|W)',
    re.IGNORECASE
)

# Clave catastral BCS (ejemplos de formatos reales)
CLAVE_CATASTRAL_PATTERNS = [
    re.compile(r'\b(\d{3}-\d{4}-\d{3}-\d{3})\b'),          # 001-0001-001-001
    re.compile(r'\bclave\s+catastral[:\s]+([A-Z0-9\-]+)\b', re.IGNORECASE),
    re.compile(r'\bexpediente[:\s]+([A-Z0-9/\-]+)\b', re.IGNORECASE),
]

# Propietario — orden de prioridad: compareciente > otorgante > propiedad de
# Excluye menciones en colindancias usando lookahead negativo
PROPIETARIO_PATTERNS = [
    # "comparece: NOMBRE APELLIDO" — hasta 6 palabras, para nombres completos mexicanos
    re.compile(
        r'(?:comparece[:\s]+|compareciente[:\s]+|el\s+se[ñn]or\s+|la\s+se[ñn]ora\s+)'
        r'([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑA-Za-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑA-Za-záéíóúñ]+){1,5})',
        re.IGNORECASE
    ),
    # "propietario: NOMBRE" — para al final de línea / antes de otro campo
    re.compile(
        r'(?:propietario[:\s]+|a\s+nombre\s+de\s+)'
        r'([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑA-Za-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑA-Za-záéíóúñ]+){1,4})'
        r'(?=\s*[\n,;.]|\s*$|\s+[Cc]lave|\s+[Ss]uperficie|\s+[Mm]unicipio|\s+[Uu]so)',
        re.IGNORECASE | re.MULTILINE
    ),
]

# Notaría
NOTARIA_PATTERN = re.compile(
    r'notari[aío]\s+p[uú]blica?\s+n[uú]mero\s+([\w\s]+?)(?:,|del)',
    re.IGNORECASE
)
NOTARIO_PATTERN = re.compile(
    r'ante\s+m[íi]\s+.{0,30}notario.{0,20}n[uú]mero\s+([\w\s]+?)(?:,|\s+del)',
    re.IGNORECASE
)

# Municipio BCS
MUNICIPIOS_BCS = {
    r'\bla\s+paz\b': 'La Paz',
    r'\blos\s+cabos?\b': 'Los Cabos',
    r'\bloreto\b': 'Loreto',
    r'\bcomondú\b': 'Comondú',
    r'\bcomondu\b': 'Comondú',
    r'\bmuleg[eé]\b': 'Mulegé',
}

# Superficie — acepta "2,452.35 m²" y también "(2,452.35 m²)" en paréntesis
SUPERFICIE_PATTERN = re.compile(
    r'(?:superficie|[aá]rea|extensi[oó]n)[:\s]*(?:total[:\s]*)?'
    r'[\w\s,\.ÀÁÉÍÓÚÑ]*?'                     # texto en letras opcional
    r'\(?([\d,]+\.?\d*)\s*(m(?:etros?)?(?:\s*cuadrados?)?(?:\s*m[²2])?|ha(?:ct[aá]reas?)?|hect[aá]reas?)\)?',
    re.IGNORECASE
)

# Datum / sistema de referencia
DATUM_PATTERNS = [
    (re.compile(r'\bWGS\s*[-\s]?\s*84\b', re.IGNORECASE), 'WGS84'),
    (re.compile(r'\bNAD\s*[-\s]?\s*27\b', re.IGNORECASE), 'NAD27'),
    (re.compile(r'\bITRF\s*20[01]\d\b', re.IGNORECASE), 'ITRF2008'),
    (re.compile(r'\bMGD\b', re.IGNORECASE), 'MGD'),
    (re.compile(r'\butm\s+zona\s+(\d+)\s*([ns])\b', re.IGNORECASE), 'UTM'),
]

# Zona UTM
UTM_ZONA_PATTERN = re.compile(r'zona\s+(\d+)\s*([ns]?)', re.IGNORECASE)

# Varas castellanas → metros (1 vara = 0.8380 m, BCS common)
VARA_PATTERN = re.compile(
    r'([\d,]+\.?\d*)\s*varas?\s*(?:castellanas?)?',
    re.IGNORECASE
)
VARA_TO_METER = 0.8380


def parse_rumbo_grados(dir1: str, grados: str, minutos: Optional[str],
                       segundos: Optional[str], dir2: str) -> float:
    """Convierte rumbo textual a grados decimales desde el norte, en sentido horario."""
    d = float(grados)
    m = float(minutos or 0)
    s = float(segundos or 0)
    angle = d + m / 60 + s / 3600

    d1 = dir1.upper()[0]
    d2 = dir2.upper()[0]

    if d1 == 'N' and d2 == 'E':
        return angle
    elif d1 == 'S' and d2 == 'E':
        return 180 - angle
    elif d1 == 'S' and d2 == 'O':
        return 180 + angle
    elif d1 == 'N' and d2 == 'O':
        return 360 - angle
    return angle


def clean_number(s: str) -> float:
    """Limpia números con comas como separador de miles."""
    return float(s.replace(',', ''))
