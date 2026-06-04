"""
AgenteRiesgo — calcula score de riesgo predial.

Analiza flags de riesgo sin llamar a la API de Claude (reglas deterministas).
Escala: 0 (sin riesgo) → 100 (riesgo crítico).
"""
from __future__ import annotations
from typing import Optional


NIVEL_LABELS = {
    (0, 20):  "bajo",
    (20, 50): "medio",
    (50, 75): "alto",
    (75, 100): "critico",
}


def calcular_riesgo(orbyt_id: str, predio: dict, conflictos: list[dict]) -> dict:
    """
    Calcula score de riesgo basado en:
    - Conflictos activos (overlaps, dobles ventas, invasiones)
    - Calidad del análisis (score de confianza)
    - Completitud de datos (clave catastral, propietario, coordenadas)
    - Discrepancia de área
    """
    flags: list[str] = []
    score = 0.0

    # ── Conflictos activos ───────────────────────────────────────────────────
    n_conflictos = len(conflictos)
    if n_conflictos > 0:
        for c in conflictos:
            tipo = c.get("tipo", "otro")
            if tipo == "doble_venta":
                score += 40
                flags.append(f"DOBLE VENTA detectada con {_other_predio(c, orbyt_id)}")
            elif tipo == "overlap":
                area = c.get("area_m2") or 0
                pct = (area / float(predio.get("area_m2") or 1)) * 100 if predio.get("area_m2") else 0
                score += min(30, pct * 0.8)
                flags.append(f"Superposición de {area:.0f} m² ({pct:.1f}%) con {_other_predio(c, orbyt_id)}")
            elif tipo == "invasion":
                score += 35
                flags.append(f"Invasión detectada con {_other_predio(c, orbyt_id)}")
            elif tipo in ("inconsistencia_catastral", "inconsistencia_registral"):
                score += 20
                flags.append(f"Inconsistencia {tipo.replace('_', ' ')}")

    # ── Score de confianza bajo ───────────────────────────────────────────────
    conf = float(predio.get("score_confianza") or 0)
    if conf < 40:
        score += 25
        flags.append(f"Score de confianza muy bajo ({conf:.0f}%) — datos insuficientes para validar")
    elif conf < 60:
        score += 12
        flags.append(f"Score de confianza bajo ({conf:.0f}%) — verificar documento original")

    # ── Sin geometría / polígono ──────────────────────────────────────────────
    if not predio.get("area_m2"):
        score += 20
        flags.append("Sin polígono reconstruido — ubicación no verificable")

    # ── Sin clave catastral ───────────────────────────────────────────────────
    # (inferir desde documentos relacionados si disponible)
    # Por ahora lo detectamos si score < 50 y no hay área
    if conf < 50 and not predio.get("area_m2"):
        flags.append("Datos insuficientes para due diligence — requiere revisión manual")

    score = min(round(score, 1), 100.0)
    nivel = _nivel(score)

    recomendaciones = _build_recomendaciones(flags, score, n_conflictos)

    return {
        "orbyt_id":          orbyt_id,
        "nivel_riesgo":      nivel,
        "score_riesgo":      score,
        "flags":             flags,
        "conflictos_activos": n_conflictos,
        "recomendaciones":   recomendaciones,
    }


def _nivel(score: float) -> str:
    for (lo, hi), label in NIVEL_LABELS.items():
        if lo <= score < hi:
            return label
    return "critico" if score >= 75 else "bajo"


def _other_predio(conflicto: dict, orbyt_id: str) -> str:
    others = [oid for oid in (conflicto.get("orbyt_ids") or []) if oid != orbyt_id]
    return others[0] if others else "predio desconocido"


def _build_recomendaciones(flags: list[str], score: float, n_conflictos: int) -> list[str]:
    recs = []
    if n_conflictos > 0:
        recs.append("Solicitar certificado de libertad de gravamen actualizado")
        recs.append("Verificar antecedentes registrales en el Registro Público de la Propiedad")
    if score >= 50:
        recs.append("Realizar estudio de título completo antes de cualquier transacción")
        recs.append("Contratar perito topógrafo para deslinde físico del predio")
    if score >= 75:
        recs.append("SUSPENDER cualquier transacción hasta resolver conflictos activos")
    if not recs:
        recs.append("Predio sin alertas mayores — proceder con due diligence estándar")
    return recs
