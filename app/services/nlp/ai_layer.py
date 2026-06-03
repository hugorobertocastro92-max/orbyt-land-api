"""
Capa 2 de extracción — Claude API.
Solo se activa si la confianza de la capa 1 es < 0.75.
"""
import os
import json
import logging
from app.models.predio import ExtractedData

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un experto en análisis de escrituras notariales mexicanas y documentos catastrales.
Tu tarea es extraer información geoespacial de documentos prediales.

Extrae en JSON con exactamente estas claves (null si no se encuentra):
{
  "propietario": "Nombre completo del propietario",
  "clave_catastral": "Clave catastral del predio",
  "municipio": "Municipio del predio",
  "estado": "Estado (ej: Baja California Sur)",
  "datum": "WGS84|NAD27|ITRF2008|otro",
  "superficie_escritura": 1234.56,
  "superficie_unidad": "m²|ha",
  "fecha_escritura": "DD de mes de AAAA",
  "notaria": "Notaría N° X",
  "coordenadas_utm": {"x": 123456.0, "y": 2345678.0, "zona": "12N"},
  "coordenadas_geo": {"lat": 23.1234, "lng": -109.4567},
  "vertices": [
    {
      "numero": 1,
      "rumbo_texto": "N 35°30' E",
      "rumbo_grados": 35.5,
      "distancia_m": 125.50
    }
  ],
  "colindancias": [
    {"lado": "Norte", "descripcion": "Calle Revolución", "tipo": "calle"}
  ]
}

Reglas:
- Para rumbos: convertir a grados decimales desde el Norte en sentido horario (N0°E=0, N90°E=90, S90°E=90, etc.)
- Varas castellanas: convertir a metros (1 vara = 0.8380 m)
- Si hay ambigüedad en datum, inferir por contexto (BCS usa principalmente UTM 12N/WGS84)
- Solo devuelve JSON válido, sin texto adicional."""


async def extract_with_ai(text: str, base_data: ExtractedData) -> tuple[ExtractedData, float]:
    """
    Enriquece la extracción base con Claude API.
    Retorna (ExtractedData mejorado, confianza 0-1).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY no configurada — saltando capa IA")
        return base_data, 0.5

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)

        # Limit text to avoid excessive tokens
        text_excerpt = text[:3000]

        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Analiza este documento predial y extrae la información:\n\n{text_excerpt}"
            }]
        )

        raw = message.content[0].text.strip()
        # Clean JSON if wrapped in markdown
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)
        enriched = _merge_data(base_data, parsed)

        # Count non-null fields for confidence
        filled = sum(1 for v in [
            enriched.propietario, enriched.clave_catastral, enriched.municipio,
            enriched.coordenadas_utm, enriched.coordenadas_geo,
            enriched.vertices if enriched.vertices else None,
        ] if v is not None)
        confianza = min(filled / 6, 1.0)

        return enriched, confianza

    except Exception as e:
        logger.error(f"AI extraction error: {e}")
        return base_data, 0.4


def _merge_data(base: ExtractedData, ai: dict) -> ExtractedData:
    """Merges AI results into base data, preferring AI for missing fields."""
    import uuid
    from app.models.predio import Vertex, Colindancia

    def get(key: str):
        return ai.get(key) or getattr(base, key, None)

    vertices = base.vertices
    if not vertices and ai.get("vertices"):
        vertices = [
            Vertex(
                numero=v.get("numero", i+1),
                rumbo_texto=v.get("rumbo_texto"),
                rumbo_grados=v.get("rumbo_grados"),
                distancia_m=v.get("distancia_m"),
                confianza=0.75,
            )
            for i, v in enumerate(ai["vertices"])
        ]

    colindancias = base.colindancias
    if not colindancias and ai.get("colindancias"):
        colindancias = [
            Colindancia(
                lado=c.get("lado", ""),
                descripcion=c.get("descripcion", ""),
                tipo=c.get("tipo", "otro"),
            )
            for c in ai["colindancias"]
        ]

    return ExtractedData(
        propietario=get("propietario"),
        clave_catastral=get("clave_catastral"),
        municipio=get("municipio"),
        estado=get("estado"),
        datum=get("datum"),
        sistema_coordenadas=base.sistema_coordenadas,
        superficie_escritura=get("superficie_escritura"),
        superficie_unidad=get("superficie_unidad"),
        fecha_escritura=get("fecha_escritura"),
        notaria=get("notaria"),
        coordenadas_utm=get("coordenadas_utm"),
        coordenadas_geo=get("coordenadas_geo"),
        vertices=vertices,
        colindancias=colindancias,
        texto_bruto=base.texto_bruto,
    )
