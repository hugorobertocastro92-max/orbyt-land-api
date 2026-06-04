"""
AgenteJurídico — especializado en actos jurídicos y cadena de propiedad.

Extrae: tipo de acto, propietario, notaría, fecha, vigencia, partes involucradas.
Modelo: Sonnet (texto legal complejo, requiere razonamiento jurídico).
"""
from .base import BaseAgent

_SYSTEM = """Eres el Agente Jurídico de ORBYT LAND, experto en derecho inmobiliario mexicano.

MISIÓN: Interpretar el acto jurídico contenido en el documento predial.

OUTPUT — JSON estricto:
{
  "tipo_acto": "compraventa|donacion|hipoteca|subdivision|fusion|testamento|adjudicacion|permuta|cesion|poder|escritura_constitutiva|titulo_agrario|certificado_parcelario|resolucion_judicial|contrato_privado|otro",
  "propietario_actual": "nombre completo del adquirente/nuevo propietario",
  "propietario_anterior": "nombre del enajenante/vendedor si aplica",
  "representante_legal": "nombre si hay apoderado o representante",
  "notaria": "Notaría Pública N° X del municipio de Y",
  "notario": "nombre del notario",
  "numero_escritura": "número de instrumento notarial",
  "fecha_escritura": "DD de mes de AAAA",
  "fecha_registro": "DD de mes de AAAA o null",
  "folio_registro": "número de folio en Registro Público si aparece",
  "precio_operacion": 1234567.89,
  "moneda": "MXN|USD|null",
  "vigente": true,
  "observaciones_juridicas": "flags de riesgo, cargas, gravámenes, litigios mencionados"
}

REGLAS CRÍTICAS:
- tipo_acto: elegir el PRINCIPAL si hay varios (ej: compraventa sobre hipoteca previa)
- propietario_actual: quien ADQUIERE el bien (comprador, donatario, adjudicatario)
- propietario_anterior: quien ENAJENA (vendedor, donante)
- vigente: true si el documento transmite o acredita propiedad vigente
- observaciones_juridicas: mencionar hipotecas, embargos, litigios, servidumbres si aparecen
- Si es certificado parcelario o título agrario: tipo_acto = "titulo_agrario"
- Solo JSON válido, sin texto adicional."""


class AgenteJuridico(BaseAgent):
    model = "claude-sonnet-4-6"  # Sonnet para razonamiento jurídico complejo
    system_prompt = _SYSTEM
    max_tokens = 700
    relevant_patterns = [
        r'comparece|compareciente|otorgante|adquirente|vendedor|comprador',
        r'escritura|instrumento|protocolo|acto\s+jurídico',
        r'notari[ao]|ante\s+mí|ante\s+mi',
        r'hipoteca|embargo|gravamen|carga|servidumbre|litigio',
        r'precio|valor|contraprestaci[oó]n|pago',
        r'fecha|día|mes|año|ante',
        r'registro\s+p[uú]blico|folio|inscripci[oó]n',
        r'dona|vende|adjudica|cede|permuta|hereda',
        r'parcela|ejidal|comunal|ran|certificado',
        r'poder\s+notarial|apoderado|representante',
    ]

    def _build_user_prompt(self, text: str, base_data) -> str:
        existing = []
        if base_data.propietario: existing.append(f"propietario NLP: {base_data.propietario}")
        if base_data.notaria:      existing.append(f"notaría NLP: {base_data.notaria}")
        if base_data.fecha_escritura: existing.append(f"fecha NLP: {base_data.fecha_escritura}")

        context = f"Datos ya extraídos: {', '.join(existing)}\n\n" if existing else ""
        return (
            f"{context}"
            "Analiza este documento jurídico-predial e identifica el acto jurídico, "
            "partes involucradas y datos registrales:\n\n"
            f"{text}"
        )

    def _score(self, parsed: dict) -> float:
        fields = ["tipo_acto", "propietario_actual", "notaria", "fecha_escritura"]
        filled = sum(1 for f in fields if parsed.get(f))
        return filled / len(fields)
