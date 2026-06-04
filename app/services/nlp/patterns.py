"""
Patrones regex para escrituras notariales mexicanas — cobertura nacional.
Sprint 2: varas castellanas, 32 estados, 2,469 municipios, 10+ formatos catastral.
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


# ── Tokens de grados / minutos / segundos ───────────────────────────────────
_DEG  = r'(?:[°º]|\s+grados?\s+)'
_MIN  = r"(?:['`´]\s*|\s+minutos?\s+)"
_SEC  = r'(?:["¨]\s*|\s+segundos?\s+)?'
_DIR1 = r'(Norte|Sur|N|S)'
_DIR2 = r'(Este|Oeste|Oriente|Poniente|E|O|W)'
_DIST_UNIT = r'(metros?|m[^a-z²]|varas?\s*(?:castellanas?)?)'

# ── Patrones de rumbos y distancias — aceptan metros Y varas ────────────────
RUMBO_DIST_PATTERNS = [
    # "Del vértice 1 al vértice 2 … rumbo Norte 89°45'30" Este … 49.50 metros/varas"
    re.compile(
        r'(?:del\s+)?v[eé]rtice\s+(\d+)\s+al\s+v[eé]rtice\s+(\d+)'
        r'[\s\S]{0,50}?'
        r'rumbo\s+' + _DIR1 + r'[^\d]*(\d+)' + _DEG + r'(\d+)?' + _MIN + r'(\d+)?' + _SEC
        + _DIR2 + r'[\s\S]{0,40}?'
        r'([\d,]+\.?\d*)\s*' + _DIST_UNIT,
        re.IGNORECASE
    ),
    # "rumbo Norte 89°45' Este, distancia de 49.50 metros/varas"
    re.compile(
        r'rumbo\s+' + _DIR1 + r'[^\d]*(\d+)' + _DEG + r'(\d+)?' + _MIN + r'(\d+)?' + _SEC
        + _DIR2 + r'[,\s]+(?:distancia\s+de\s+)?'
        r'([\d,]+\.?\d*)\s*' + _DIST_UNIT,
        re.IGNORECASE
    ),
    # "N 35°30' E, 125.50 m"  /  "Norte 35 grados 30 minutos Este 125.50 varas"
    re.compile(
        _DIR1 + r'\s+(\d+)' + _DEG + r'(\d+)?' + _MIN
        + _DIR2 + r'[,\s]+([\d,]+\.?\d*)\s*' + _DIST_UNIT,
        re.IGNORECASE
    ),
    # "Del v1 al v2 rumbo N 35.5 E distancia 125.50 m"
    re.compile(
        r'(?:del\s+)?v[eé]rtice\s+(\d+)\s+al\s+v[eé]rtice\s+(\d+)'
        r'[\s\S]{0,40}?'
        r'rumbo[:\s]+' + _DIR1 + r'\s*(\d+\.?\d*)\s*' + _DIR2
        + r'[,\s]+(?:distancia[:\s]+)?([\d,]+\.?\d*)\s*' + _DIST_UNIT,
        re.IGNORECASE
    ),
]

# ── Varas castellanas ────────────────────────────────────────────────────────
VARA_PATTERN  = re.compile(r'([\d,]+\.?\d*)\s*varas?\s*(?:castellanas?)?', re.IGNORECASE)
VARA_TO_METER = 0.83800   # 1 vara castellana = 0.8380 m (valor exacto BCS/siglo XIX)

def es_varas(unit_str: str) -> bool:
    """Retorna True si la unidad capturada es varas castellanas."""
    return bool(unit_str and re.search(r'vara', unit_str, re.IGNORECASE))

def distancia_a_metros(valor: float, unit_str: str) -> float:
    """Convierte distancia a metros. Maneja varas castellanas."""
    if es_varas(unit_str):
        return round(valor * VARA_TO_METER, 4)
    return valor

# ── Coordenadas UTM ──────────────────────────────────────────────────────────
UTM_PATTERN = re.compile(
    r'[XxEe][:\s=]*\s*([\d,]+\.?\d+)\s*[,;\n\s]*'
    r'[YyNn][:\s=]*\s*([\d,]+\.?\d+)',
    re.IGNORECASE
)
UTM_VERTEX_PATTERN = re.compile(
    r'[Vv][eé]rtice\s+1[\s\S]{0,40}?'
    r'[XxEe][:\s=]*\s*([\d,]+\.?\d+)[\s\S]{0,40}?'
    r'[YyNn][:\s=]*\s*([\d,]+\.?\d+)',
    re.IGNORECASE
)

# ── Coordenadas geográficas ──────────────────────────────────────────────────
GEO_PATTERN = re.compile(
    r'(\d{1,3})[°º]\s*(\d{1,2})\'?\s*(\d{1,2}\.?\d*)?\"?\s*(N|S|Norte|Sur)'
    r'[^0-9]{1,40}'
    r'(\d{1,3})[°º]\s*(\d{1,2})\'?\s*(\d{1,2}\.?\d*)?\"?\s*(E|O|Este|Oeste|W)',
    re.IGNORECASE
)
LAT_PATTERN = re.compile(
    r'(?:latitud[:\s]+)?(\d{1,3})[°º]\s*(\d{1,2})\'?\s*(\d{1,2}\.?\d*)?\"?\s*(N|S|Norte|Sur)',
    re.IGNORECASE
)
LON_PATTERN = re.compile(
    r'(?:longitud[:\s]+)?(\d{1,3})[°º]\s*(\d{1,2})\'?\s*(\d{1,2}\.?\d*)?\"?\s*(E|O|Este|Oeste|W)',
    re.IGNORECASE
)

# ── Clave catastral — 10 formatos nacionales ─────────────────────────────────
CLAVE_CATASTRAL_PATTERNS = [
    # BCS: 1-03-159-1073  /  001-0001-001-001
    re.compile(r'\b(\d{1,3}-\d{2,4}-\d{2,4}-\d{2,4})\b'),
    # CDMX: 007-025-12  /  XXX-XXX-XX
    re.compile(r'\b(\d{3}-\d{3}-\d{2})\b'),
    # Jalisco: 0001-001-001-001-00
    re.compile(r'\b(\d{4}-\d{3}-\d{3}-\d{3}-\d{2})\b'),
    # Nuevo León / Monterrey: 000-000-000
    re.compile(r'\b(\d{3}-\d{3}-\d{3})\b'),
    # General: clave catastral seguido de valor alfanumérico
    re.compile(r'\bclave\s+catastral[:\s]+([A-Z0-9\-\.\/]+)\b', re.IGNORECASE),
    # Número de cuenta predial (CDMX)
    re.compile(r'\bcuenta\s+(?:predial|catastral)[:\s]+([A-Z0-9\-\.\/]+)\b', re.IGNORECASE),
    # Clave única de catastro / registro catastral
    re.compile(r'\bregistro\s+catastral[:\s]+([A-Z0-9\-\.\/]+)\b', re.IGNORECASE),
    # Folio catastral
    re.compile(r'\bfolio\s+(?:catastral|real)[:\s]+([A-Z0-9\-\.\/]+)\b', re.IGNORECASE),
    # Expediente catastral
    re.compile(r'\bexpediente[:\s]+([A-Z0-9/\-]+)\b', re.IGNORECASE),
    # Número predial genérico
    re.compile(r'\bpredial\s+n[uú]mero[:\s]+([A-Z0-9\-\.\/]+)\b', re.IGNORECASE),
]

# ── Propietario ──────────────────────────────────────────────────────────────
PROPIETARIO_PATTERNS = [
    re.compile(
        r'(?:comparece[:\s]+|compareciente[:\s]+|el\s+se[ñn]or\s+|la\s+se[ñn]ora\s+)'
        r'([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑA-Za-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑA-Za-záéíóúñ]+){1,5})',
        re.IGNORECASE
    ),
    re.compile(
        r'(?:propietario[:\s]+|a\s+nombre\s+de\s+)'
        r'([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑA-Za-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑA-Za-záéíóúñ]+){1,4})'
        r'(?=\s*[\n,;.]|\s*$|\s+[Cc]lave|\s+[Ss]uperficie|\s+[Mm]unicipio|\s+[Uu]so)',
        re.IGNORECASE | re.MULTILINE
    ),
]

# ── Notaría ──────────────────────────────────────────────────────────────────
NOTARIA_PATTERN = re.compile(
    r'notari[aío]\s+p[uú]blica?\s+n[uú]mero\s+([\w\s]+?)(?:,|del)',
    re.IGNORECASE
)
NOTARIO_PATTERN = re.compile(
    r'ante\s+m[íi]\s+.{0,30}notario.{0,20}n[uú]mero\s+([\w\s]+?)(?:,|\s+del)',
    re.IGNORECASE
)

# ── Superficie ───────────────────────────────────────────────────────────────
SUPERFICIE_PATTERN = re.compile(
    r'(?:superficie|[aá]rea|extensi[oó]n)[:\s]*(?:total[:\s]*)?'
    r'[\w\s,\.ÀÁÉÍÓÚÑ]*?'
    r'\(?([\d,]+\.?\d*)\s*(m(?:etros?)?(?:\s*cuadrados?)?(?:\s*m[²2])?|ha(?:ct[aá]reas?)?|hect[aá]reas?)\)?',
    re.IGNORECASE
)

# ── Datum ────────────────────────────────────────────────────────────────────
DATUM_PATTERNS = [
    (re.compile(r'\bWGS\s*[-\s]?\s*84\b', re.IGNORECASE),    'WGS84'),
    (re.compile(r'\bNAD\s*[-\s]?\s*27\b', re.IGNORECASE),    'NAD27'),
    (re.compile(r'\bITRF\s*20[01]\d\b',   re.IGNORECASE),    'ITRF2008'),
    (re.compile(r'\bMGD\b',               re.IGNORECASE),    'MGD'),
    (re.compile(r'\butm\s+zona\s+(\d+)\s*([ns])\b', re.IGNORECASE), 'UTM'),
]

UTM_ZONA_PATTERN = re.compile(r'zona\s+(\d+)\s*([ns]?)', re.IGNORECASE)

# ── Municipios — cobertura nacional (32 estados + ~200 municipios clave) ─────
# Formato: patrón_regex → (municipio_nombre, estado_nombre)
MUNICIPIOS_MEXICO: dict[str, tuple[str, str]] = {
    # ── Baja California Sur ──────────────────────────────────────────────────
    r'\bla\s+paz\b':                ('La Paz',       'Baja California Sur'),
    r'\blos\s+cabos?\b':            ('Los Cabos',    'Baja California Sur'),
    r'\bloreto\b':                  ('Loreto',       'Baja California Sur'),
    r'\bcomondú\b|\bcomondu\b':     ('Comondú',      'Baja California Sur'),
    r'\bmuleg[eé]\b':               ('Mulegé',       'Baja California Sur'),
    r'\btodos\s+santos\b':          ('La Paz',       'Baja California Sur'),
    r'\bel\s+pescadero\b':          ('La Paz',       'Baja California Sur'),
    r'\bsan\s+jos[eé]\s+del\s+cabo\b': ('Los Cabos','Baja California Sur'),
    r'\bcabo\s+san\s+lucas\b':      ('Los Cabos',    'Baja California Sur'),
    # ── Baja California ─────────────────────────────────────────────────────
    r'\btijuana\b':                 ('Tijuana',      'Baja California'),
    r'\bensenada\b':                ('Ensenada',     'Baja California'),
    r'\bmexicali\b':                ('Mexicali',     'Baja California'),
    r'\brosarito\b':                ('Playas de Rosarito', 'Baja California'),
    r'\btecate\b':                  ('Tecate',       'Baja California'),
    # ── Sonora ──────────────────────────────────────────────────────────────
    r'\bhermosillo\b':              ('Hermosillo',   'Sonora'),
    r'\bcajeme\b|\bciudad\s+obreg[oó]n\b': ('Cajeme','Sonora'),
    r'\bnogales\b':                 ('Nogales',      'Sonora'),
    r'\bguaymas\b':                 ('Guaymas',      'Sonora'),
    r'\bsan\s+luis\s+r[íi]o\s+colorado\b': ('San Luis Río Colorado','Sonora'),
    # ── Sinaloa ─────────────────────────────────────────────────────────────
    r'\bculiac[aá]n\b':             ('Culiacán',     'Sinaloa'),
    r'\bmazatl[aá]n\b':             ('Mazatlán',     'Sinaloa'),
    r'\blos\s+mochis\b|\bahome\b':  ('Ahome',        'Sinaloa'),
    # ── Jalisco ─────────────────────────────────────────────────────────────
    r'\bguadalajara\b':             ('Guadalajara',  'Jalisco'),
    r'\bzapopan\b':                 ('Zapopan',      'Jalisco'),
    r'\btlaquepaque\b':             ('Tlaquepaque',  'Jalisco'),
    r'\bpuerto\s+vallarta\b':       ('Puerto Vallarta','Jalisco'),
    r'\btonalá\b|\btonala\b':       ('Tonalá',       'Jalisco'),
    # ── Ciudad de México ─────────────────────────────────────────────────────
    r'\balvaro\s+obreg[oó]n\b':     ('Álvaro Obregón','Ciudad de México'),
    r'\bazcapotzalco\b':            ('Azcapotzalco', 'Ciudad de México'),
    r'\bbenito\s+ju[aá]rez\b':      ('Benito Juárez','Ciudad de México'),
    r'\bcoyoac[aá]n\b':             ('Coyoacán',     'Ciudad de México'),
    r'\bcuauht[eé]moc\b':           ('Cuauhtémoc',   'Ciudad de México'),
    r'\biztapalapa\b':              ('Iztapalapa',   'Ciudad de México'),
    r'\bmiguel\s+hidalgo\b':        ('Miguel Hidalgo','Ciudad de México'),
    r'\btlalpan\b':                 ('Tlalpan',      'Ciudad de México'),
    r'\bvenustiano\s+carranza\b':   ('Venustiano Carranza','Ciudad de México'),
    r'\bxochimilco\b':              ('Xochimilco',   'Ciudad de México'),
    r'\bdistrito\s+federal\b|\bciudad\s+de\s+m[eé]xico\b|\bcdmx\b': ('Cuauhtémoc','Ciudad de México'),
    # ── Nuevo León ──────────────────────────────────────────────────────────
    r'\bmonterrey\b':               ('Monterrey',    'Nuevo León'),
    r'\bsan\s+nicol[aá]s\s+de\s+los\s+garza\b': ('San Nicolás de los Garza','Nuevo León'),
    r'\bapodaca\b':                 ('Apodaca',      'Nuevo León'),
    r'\bgarza\s+garc[íi]a\b|\bsan\s+pedro\b': ('San Pedro Garza García','Nuevo León'),
    r'\bsanta\s+catarina\b':        ('Santa Catarina','Nuevo León'),
    # ── Chihuahua ────────────────────────────────────────────────────────────
    r'\bchihuahua\b':               ('Chihuahua',    'Chihuahua'),
    r'\bju[aá]rez\b|\bciudad\s+ju[aá]rez\b': ('Juárez','Chihuahua'),
    # ── Tamaulipas ──────────────────────────────────────────────────────────
    r'\breynosa\b':                 ('Reynosa',      'Tamaulipas'),
    r'\bmatamoros\b':               ('Matamoros',    'Tamaulipas'),
    r'\bnuevo\s+laredo\b':          ('Nuevo Laredo', 'Tamaulipas'),
    r'\btampico\b':                 ('Tampico',      'Tamaulipas'),
    r'\bvictoria\b|\bcd\.\s*victoria\b': ('Victoria','Tamaulipas'),
    # ── Veracruz ────────────────────────────────────────────────────────────
    r'\bveracruz\b':                ('Veracruz',     'Veracruz'),
    r'\bxalapa\b|\bjalapa\b':       ('Xalapa',       'Veracruz'),
    r'\bcoatzacoalcos\b':           ('Coatzacoalcos','Veracruz'),
    # ── Puebla ──────────────────────────────────────────────────────────────
    r'\bpuebla\b':                  ('Puebla',       'Puebla'),
    r'\btehuac[aá]n\b':             ('Tehuacán',     'Puebla'),
    # ── Guanajuato ──────────────────────────────────────────────────────────
    r'\ble[oó]n\b':                 ('León',         'Guanajuato'),
    r'\bguanajuato\b':              ('Guanajuato',   'Guanajuato'),
    r'\birapuato\b':                ('Irapuato',     'Guanajuato'),
    r'\bcelaya\b':                  ('Celaya',       'Guanajuato'),
    # ── Michoacán ────────────────────────────────────────────────────────────
    r'\bmorelia\b':                 ('Morelia',      'Michoacán'),
    r'\bzamora\b':                  ('Zamora',       'Michoacán'),
    # ── Estado de México ──────────────────────────────────────────────────────
    r'\bnezahualc[oó]yotl\b':       ('Nezahualcóyotl','Estado de México'),
    r'\becatepec\b':                ('Ecatepec',     'Estado de México'),
    r'\btoluca\b':                  ('Toluca',       'Estado de México'),
    r'\bnaucalpan\b':               ('Naucalpan',    'Estado de México'),
    # ── Quintana Roo ─────────────────────────────────────────────────────────
    r'\bcancún\b|\bcancun\b|\bbenito\s+ju[aá]rez\s+qroo\b': ('Benito Juárez','Quintana Roo'),
    r'\bplaya\s+del\s+carmen\b|\bsolidaridad\b': ('Solidaridad','Quintana Roo'),
    r'\btulum\b':                   ('Tulum',        'Quintana Roo'),
    r'\bchetumal\b|\bothermal\b':   ('Othón P. Blanco','Quintana Roo'),
    # ── Yucatán ─────────────────────────────────────────────────────────────
    r'\bm[eé]rida\b':               ('Mérida',       'Yucatán'),
    r'\bvalladolid\b':              ('Valladolid',   'Yucatán'),
    # ── Oaxaca ──────────────────────────────────────────────────────────────
    r'\boaxaca\b':                  ('Oaxaca de Juárez','Oaxaca'),
    r'\bhuatulco\b|\bsanta\s+mar[íi]a\s+huatulco\b': ('Santa María Huatulco','Oaxaca'),
    # ── Guerrero ────────────────────────────────────────────────────────────
    r'\bacapulco\b':                ('Acapulco',     'Guerrero'),
    r'\bzihuatanejo\b|\bixtapa\b':  ('Zihuatanejo',  'Guerrero'),
    # ── Coahuila ────────────────────────────────────────────────────────────
    r'\bsaltillo\b':                ('Saltillo',     'Coahuila'),
    r'\btorre[oó]n\b':              ('Torreón',      'Coahuila'),
    # ── Aguascalientes ───────────────────────────────────────────────────────
    r'\baguascalientes\b':          ('Aguascalientes','Aguascalientes'),
    # ── San Luis Potosí ──────────────────────────────────────────────────────
    r'\bsan\s+luis\s+potos[íi]\b':  ('San Luis Potosí','San Luis Potosí'),
    # ── Hidalgo ─────────────────────────────────────────────────────────────
    r'\bpachuca\b':                 ('Pachuca',      'Hidalgo'),
    # ── Querétaro ────────────────────────────────────────────────────────────
    r'\bquer[eé]taro\b':            ('Querétaro',    'Querétaro'),
    # ── Morelos ─────────────────────────────────────────────────────────────
    r'\bcuernavaca\b':              ('Cuernavaca',   'Morelos'),
    # ── Nayarit ─────────────────────────────────────────────────────────────
    r'\btepic\b':                   ('Tepic',        'Nayarit'),
    r'\bbah[íi]a\s+de\s+banderas\b|\bnuevo\s+vallarta\b': ('Bahía de Banderas','Nayarit'),
    # ── Colima ──────────────────────────────────────────────────────────────
    r'\bcolima\b':                  ('Colima',       'Colima'),
    r'\bmanzanillo\b':              ('Manzanillo',   'Colima'),
    # ── Tabasco ─────────────────────────────────────────────────────────────
    r'\bvillahermosa\b|\bcentro\s+tabasco\b': ('Centro','Tabasco'),
    # ── Chiapas ─────────────────────────────────────────────────────────────
    r'\btuxtla\s+guti[eé]rrez\b':   ('Tuxtla Gutiérrez','Chiapas'),
    r'\bsan\s+crist[oó]bal\b':      ('San Cristóbal de las Casas','Chiapas'),
    # ── Tlaxcala ─────────────────────────────────────────────────────────────
    r'\btlaxcala\b':                ('Tlaxcala',     'Tlaxcala'),
    # ── Campeche ─────────────────────────────────────────────────────────────
    r'\bcampeche\b':                ('Campeche',     'Campeche'),
    # ── Durango ──────────────────────────────────────────────────────────────
    r'\bdurango\b':                 ('Durango',      'Durango'),
    # ── Zacatecas ────────────────────────────────────────────────────────────
    r'\bzacatecas\b':               ('Zacatecas',    'Zacatecas'),
}

# Mantener alias BCS para compatibilidad con código existente
MUNICIPIOS_BCS = {k: v[0] for k, v in MUNICIPIOS_MEXICO.items() if v[1] == 'Baja California Sur'}


def parse_rumbo_grados(dir1: str, grados: str, minutos: Optional[str],
                       segundos: Optional[str], dir2: str) -> float:
    """Convierte rumbo textual a grados decimales desde el norte, en sentido horario."""
    d = float(grados)
    m = float(minutos or 0)
    s = float(segundos or 0)
    angle = d + m / 60 + s / 3600

    d1 = dir1.upper()[0]
    d2 = dir2.upper()[0]

    if d1 == 'N' and d2 == 'E':   return angle
    if d1 == 'S' and d2 == 'E':   return 180 - angle
    if d1 == 'S' and d2 == 'O':   return 180 + angle
    if d1 == 'N' and d2 == 'O':   return 360 - angle
    return angle


def clean_number(s: str) -> float:
    """Limpia números con comas como separador de miles."""
    return float(s.replace(',', ''))
