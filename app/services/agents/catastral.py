"""
AgenteCatastral — especializado en identificación catastral.

Extrae: clave catastral, municipio, estado, superficie, uso de suelo.
Modelo: Haiku (volumen, bajo costo, respuesta rápida).
"""
from .base import BaseAgent

_SYSTEM = """Eres el Agente Catastral de ORBYT LAND, especializado en documentos catastrales mexicanos.

MISIÓN: Extraer únicamente datos de identificación catastral y superficies.

OUTPUT — JSON estricto, solo estos campos (null si no existe):
{
  "clave_catastral": "formato exacto como aparece (ej: 1-03-159-1073)",
  "municipio": "nombre oficial del municipio",
  "estado": "nombre oficial del estado mexicano",
  "pais": "México",
  "superficie_escritura": 1234.56,
  "superficie_unidad": "m²|ha|varas²",
  "uso_suelo": "habitacional|comercial|industrial|agropecuario|ejidal|otro|null",
  "tipo_predio": "urbano|suburbano|rustico|ejidal|null",
  "delegacion_municipal": "nombre de la delegación o localidad si existe"
}

REGLAS CRÍTICAS:
- Clave catastral: transcribir EXACTAMENTE como aparece (guiones, puntos, letras)
- Si la clave aparece como "1-03-159-1073" NO transformar a otro formato
- Municipio: nombre oficial completo (no abreviar)
- Estado: nombre completo (no abreviatura) — ej: "Baja California Sur" no "BCS"
- Superficie: solo números, sin unidad en el valor
- Si hay varias superficies (terreno, construcción, total) preferir superficie total del terreno
- Solo JSON válido, sin explicaciones."""


class AgenteCatastral(BaseAgent):
    model = "claude-haiku-4-5-20251001"
    system_prompt = _SYSTEM
    max_tokens = 400
    relevant_patterns = [
        r'catastral|clave|cuenta\s+predial|folio|expediente',
        r'municipio|delegaci[oó]n|localidad|colonia',
        r'superficie|[aá]rea|extensi[oó]n|m[²2]|hect[aá]rea',
        r'uso\s+de\s+suelo|tipo\s+de\s+predio|r[uú]stico|urbano|ejidal',
        r'ayuntamiento|catastro|direcci[oó]n\s+general',
    ]

    def _build_user_prompt(self, text: str, base_data) -> str:
        existing = []
        if base_data.clave_catastral: existing.append(f"clave_catastral ya detectada: {base_data.clave_catastral}")
        if base_data.municipio:       existing.append(f"municipio ya detectado: {base_data.municipio}")
        if base_data.superficie_escritura: existing.append(f"superficie ya detectada: {base_data.superficie_escritura}")

        context = f"Ya extraído por NLP: {', '.join(existing)}\n\n" if existing else ""
        return f"{context}Documento predial:\n\n{text}"

    def _score(self, parsed: dict) -> float:
        fields = ["clave_catastral", "municipio", "estado", "superficie_escritura"]
        filled = sum(1 for f in fields if parsed.get(f))
        return filled / len(fields)
