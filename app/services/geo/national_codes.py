"""
Códigos nacionales para generación de ORBYT-ID.
Cobertura: 32 estados de México + municipios principales.
Fuente: INEGI Marco Geoestadístico Nacional 2024.
"""
from __future__ import annotations

# ── Códigos de estado (ISO 3166-2:MX) ────────────────────────────────────────
ESTADO_CODES: dict[str, str] = {
    "Aguascalientes":       "AGU",
    "Baja California":      "BCN",
    "Baja California Sur":  "BCS",
    "Campeche":             "CAM",
    "Chiapas":              "CHP",
    "Chihuahua":            "CHH",
    "Ciudad de México":     "CMX",
    "CDMX":                 "CMX",
    "Coahuila":             "COA",
    "Coahuila de Zaragoza": "COA",
    "Colima":               "COL",
    "Durango":              "DUR",
    "Guanajuato":           "GTO",
    "Guerrero":             "GRO",
    "Hidalgo":              "HID",
    "Jalisco":              "JAL",
    "México":               "MEX",
    "Estado de México":     "MEX",
    "Michoacán":            "MIC",
    "Michoacán de Ocampo":  "MIC",
    "Morelos":              "MOR",
    "Nayarit":              "NAY",
    "Nuevo León":           "NLE",
    "Oaxaca":               "OAX",
    "Puebla":               "PUE",
    "Querétaro":            "QUE",
    "Querétaro de Arteaga": "QUE",
    "Quintana Roo":         "ROO",
    "San Luis Potosí":      "SLP",
    "Sinaloa":              "SIN",
    "Sonora":               "SON",
    "Tabasco":              "TAB",
    "Tamaulipas":           "TAM",
    "Tlaxcala":             "TLA",
    "Veracruz":             "VER",
    "Veracruz de Ignacio de la Llave": "VER",
    "Yucatán":              "YUC",
    "Zacatecas":            "ZAC",
}

# ── Códigos de municipio por estado ──────────────────────────────────────────
MUNICIPIO_CODES: dict[str, str] = {
    # ── Baja California Sur ──────────────────────────────────────────────────
    "La Paz":              "LPZ",
    "Los Cabos":           "CSB",
    "Loreto":              "LOR",
    "Comondú":             "COM",
    "Mulegé":              "MUL",
    # ── Baja California ─────────────────────────────────────────────────────
    "Tijuana":             "TIJ",
    "Mexicali":            "MXL",
    "Ensenada":            "ENS",
    "Tecate":              "TEC",
    "Playas de Rosarito":  "ROS",
    # ── Sonora ──────────────────────────────────────────────────────────────
    "Hermosillo":          "HMO",
    "Cajeme":              "CAJ",
    "Nogales":             "NOG",
    "Guaymas":             "GYM",
    "San Luis Río Colorado": "SLR",
    "Navojoa":             "NAV",
    "Agua Prieta":         "AGP",
    # ── Jalisco ─────────────────────────────────────────────────────────────
    "Guadalajara":         "GDL",
    "Zapopan":             "ZAP",
    "Tlaquepaque":         "TLQ",
    "Tonalá":              "TON",
    "Puerto Vallarta":     "PVR",
    "Tlajomulco de Zúñiga":"TLJ",
    # ── Ciudad de México ────────────────────────────────────────────────────
    "Álvaro Obregón":      "AOB",
    "Azcapotzalco":        "AZC",
    "Benito Juárez":       "BJU",
    "Coyoacán":            "COY",
    "Cuauhtémoc":          "CUH",
    "Iztapalapa":          "IZP",
    "Miguel Hidalgo":      "MHI",
    "Tlalpan":             "TLP",
    "Xochimilco":          "XOC",
    "Gustavo A. Madero":   "GAM",
    "Iztacalco":           "IZC",
    "Venustiano Carranza": "VCA",
    # ── Nuevo León ──────────────────────────────────────────────────────────
    "Monterrey":           "MTY",
    "Guadalupe":           "GUA",
    "San Nicolás de los Garza": "SNG",
    "Apodaca":             "APO",
    "San Pedro Garza García": "SPG",
    "Escobedo":            "ESC",
    "Santa Catarina":      "SCA",
    # ── Veracruz ────────────────────────────────────────────────────────────
    "Veracruz":            "VER",
    "Xalapa":              "XAL",
    "Coatzacoalcos":       "COZ",
    "Córdoba":             "CRD",
    "Orizaba":             "ORI",
    "Poza Rica":           "PZR",
    # ── Puebla ──────────────────────────────────────────────────────────────
    "Puebla":              "PUE",
    "Tehuacán":            "TEH",
    "San Andrés Cholula":  "SAC",
    # ── Chihuahua ───────────────────────────────────────────────────────────
    "Chihuahua":           "CHI",
    "Ciudad Juárez":       "CJS",
    "Delicias":            "DEL",
    "Parral":              "PAR",
    # ── Tamaulipas ──────────────────────────────────────────────────────────
    "Tampico":             "TAM",
    "Reynosa":             "REY",
    "Matamoros":           "MAT",
    "Nuevo Laredo":        "NLD",
    "Ciudad Victoria":     "CVT",
    # ── Coahuila ────────────────────────────────────────────────────────────
    "Saltillo":            "SAL",
    "Torreón":             "TOR",
    "Monclova":            "MON",
    "Piedras Negras":      "PNG",
    # ── Sinaloa ─────────────────────────────────────────────────────────────
    "Culiacán":            "CUL",
    "Mazatlán":            "MAZ",
    "Los Mochis":          "LMO",
    "Guasave":             "GVE",
    # ── Oaxaca ──────────────────────────────────────────────────────────────
    "Oaxaca de Juárez":    "OAX",
    "Salina Cruz":         "SCZ",
    "Juchitán":            "JUC",
    # ── Yucatán ─────────────────────────────────────────────────────────────
    "Mérida":              "MER",
    "Valladolid":          "VLL",
    "Progreso":            "PRO",
    # ── Quintana Roo ────────────────────────────────────────────────────────
    "Cancún":              "CUN",
    "Benito Juárez":       "BJR",   # municipio de Cancún
    "Solidaridad":         "PLY",   # Playa del Carmen
    "Tulum":               "TUL",
    "Cozumel":             "COZ",
    "Othón P. Blanco":     "CHX",   # Chetumal
    # ── Guerrero ────────────────────────────────────────────────────────────
    "Acapulco":            "ACA",
    "Acapulco de Juárez":  "ACA",
    "Zihuatanejo":         "ZIH",
    "Iguala":              "IGU",
    # ── Guanajuato ──────────────────────────────────────────────────────────
    "León":                "LEO",
    "Irapuato":            "IRA",
    "Celaya":              "CEL",
    "Guanajuato":          "GTO",
    "Salamanca":           "SLM",
    # ── Querétaro ───────────────────────────────────────────────────────────
    "Querétaro":           "QRO",
    "El Marqués":          "MRQ",
    "San Juan del Río":    "SJR",
    # ── Hidalgo ─────────────────────────────────────────────────────────────
    "Pachuca":             "PAC",
    "Tula de Allende":     "TUL",
    # ── Morelos ─────────────────────────────────────────────────────────────
    "Cuernavaca":          "CVA",
    "Jiutepec":            "JTU",
    "Cuautla":             "CTL",
    # ── Estado de México ────────────────────────────────────────────────────
    "Ecatepec":            "ECT",
    "Nezahualcóyotl":      "NEZ",
    "Toluca":              "TOL",
    "Naucalpan":           "NAU",
    "Chimalhuacán":        "CHM",
    "Tlalnepantla":        "TLN",
    # ── Michoacán ───────────────────────────────────────────────────────────
    "Morelia":             "MOR",
    "Uruapan":             "URU",
    "Lázaro Cárdenas":     "LCR",
    # ── San Luis Potosí ─────────────────────────────────────────────────────
    "San Luis Potosí":     "SLP",
    "Ciudad Valles":       "CVL",
    "Matehuala":           "MTH",
    # ── Durango ─────────────────────────────────────────────────────────────
    "Durango":             "DGO",
    "Gómez Palacio":       "GOP",
    # ── Tabasco ─────────────────────────────────────────────────────────────
    "Villahermosa":        "VHS",
    "Centro":              "CTR",   # municipio de Villahermosa
    # ── Chiapas ─────────────────────────────────────────────────────────────
    "Tuxtla Gutiérrez":    "TGZ",
    "San Cristóbal de las Casas": "SCL",
    "Tapachula":           "TAP",
    # ── Campeche ────────────────────────────────────────────────────────────
    "Campeche":            "CAM",
    "Ciudad del Carmen":   "CDC",
    # ── Nayarit ─────────────────────────────────────────────────────────────
    "Tepic":               "TEP",
    "Bahía de Banderas":   "BDB",
    # ── Colima ──────────────────────────────────────────────────────────────
    "Colima":              "CLM",
    "Manzanillo":          "MZN",
    # ── Aguascalientes ──────────────────────────────────────────────────────
    "Aguascalientes":      "AGS",
    "Jesús María":         "JSM",
    # ── Zacatecas ───────────────────────────────────────────────────────────
    "Zacatecas":           "ZAC",
    "Fresnillo":           "FRS",
    # ── Tlaxcala ────────────────────────────────────────────────────────────
    "Tlaxcala":            "TLX",
    "Apizaco":             "APZ",
}


def get_estado_code(estado: str) -> str:
    """Retorna el código de 3 letras del estado. Fallback: 'MX0'."""
    return ESTADO_CODES.get(estado, ESTADO_CODES.get(estado.strip().title(), "MX0"))


def get_municipio_code(municipio: str) -> str:
    """Retorna el código de 3 letras del municipio. Fallback: 'GEN'."""
    return MUNICIPIO_CODES.get(municipio, MUNICIPIO_CODES.get(municipio.strip().title(), "GEN"))
