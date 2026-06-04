"""
AgenteTopografico — especializado en geometría predial.

Extrae: vértices, rumbos, distancias, coordenadas, datum, zona UTM.
Modelo: Haiku (patrones estructurados, respuesta determinista).
"""
from .base import BaseAgent

_SYSTEM = """Eres el Agente Topográfico de ORBYT LAND, especializado en geometría predial mexicana.

MISIÓN: Extraer TODOS los vértices, rumbos, distancias y coordenadas del documento.

OUTPUT — JSON estricto:
{
  "datum": "WGS84|NAD27|ITRF2008|MGD|null",
  "zona_utm": "12N|13N|null",
  "coordenadas_utm": {"x": 488150.40, "y": 2669830.60, "zona": "12N"},
  "coordenadas_geo": {"lat": 23.1234, "lng": -109.4567},
  "vertices": [
    {
      "numero": 1,
      "rumbo_texto": "N 89°45' E",
      "rumbo_grados": 89.75,
      "distancia_m": 49.50,
      "coord_x": null,
      "coord_y": null
    }
  ],
  "perimetro_m": 180.0,
  "area_declarada_m2": null
}

REGLAS CRÍTICAS:
- Varas castellanas: convertir a metros (1 vara = 0.8380 m)
- Rumbos en grados decimales desde el Norte en sentido horario:
  N0°E=0°, N90°E=90°, S90°E=90°, S0°E=180°, S90°W=270°, N90°W=270°
- Formato N/S + grados + E/O: "Norte 89°45' Este" → rumbo_grados=89.75
- Si el documento tiene segundos: "N 35°30'45\" E" → 35 + 30/60 + 45/3600 = 35.5125°
- Si las distancias son en varas: multiplicar × 0.8380 y anotar en distancia_m
- Extraer TODOS los vértices, no solo los primeros
- Si hay coordenadas UTM del vértice 1, incluirlas en coordenadas_utm
- Solo JSON válido."""


class AgenteTopografico(BaseAgent):
    model = "claude-haiku-4-5-20251001"
    system_prompt = _SYSTEM
    max_tokens = 1200
    relevant_patterns = [
        r'v[eé]rtice|rumbo|distancia',
        r'norte|sur|este|oeste|oriente|poniente',
        r'grado|minuto|segundo|°|\'|"',
        r'metro|vara|m\b',
        r'utm|wgs|nad|itrf|datum|zona',
        r'[XxEe]\s*[=:]\s*[\d,]+|[YyNn]\s*[=:]\s*[\d,]+',
        r'latitud|longitud|coordenada',
        r'colindancia|colinda',
    ]

    def _build_user_prompt(self, text: str, base_data) -> str:
        existing = []
        if base_data.vertices:
            existing.append(f"{len(base_data.vertices)} vértice(s) ya extraídos por NLP")
        if base_data.datum:
            existing.append(f"datum detectado: {base_data.datum}")
        if base_data.coordenadas_utm:
            existing.append(f"UTM detectado: X={base_data.coordenadas_utm.get('x')}")

        context = f"NLP previo: {', '.join(existing)}\n\n" if existing else ""
        return f"{context}Sección topográfica del documento:\n\n{text}"

    def _score(self, parsed: dict) -> float:
        score = 0.0
        if parsed.get("vertices"):          score += 0.5
        if parsed.get("datum"):             score += 0.15
        if parsed.get("coordenadas_utm") or parsed.get("coordenadas_geo"): score += 0.2
        if parsed.get("zona_utm"):          score += 0.1
        if parsed.get("perimetro_m"):       score += 0.05
        return min(score, 1.0)
