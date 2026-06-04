"""
Motor de valoración automatizada ORBYT LAND.

Metodología: Comparativo de mercado BCS v1
- Precios base por municipio/zona (MXN/m², 2025)
- Ajustes multiplicativos: score_dinamico, riesgo, conflictos, NDVI, tipo de predio
- Score dinámico ponderado en 4 dimensiones
"""
from __future__ import annotations
from typing import Optional

# ── Tabla de precios base MXN/m² (mercado BCS 2025) ─────────────────────────

PRECIOS_BASE: dict[str, float] = {
    "Los Cabos":  16_000.0,
    "La Paz":      7_000.0,
    "Loreto":      9_500.0,
    "Comondú":     1_600.0,
    "Mulegé":      3_200.0,
}
PRECIO_DEFAULT = 4_000.0

# ── Score dinámico — pesos de cada dimensión ─────────────────────────────────

PESOS = {
    "confianza":   0.35,   # Calidad del análisis documental
    "juridica":    0.25,   # Estado legal: conflictos, overlaps
    "completitud": 0.20,   # Datos completos: geo, propietario, catastral
    "contextual":  0.20,   # Satélite, relaciones, refs externas
}


def calcular_score_dinamico(
    score_confianza: Optional[float],
    conflictos: list[dict],
    predio: dict,
    tiene_satelite: bool,
    n_relaciones: int,
    fuentes_usadas: list[str],
) -> dict:
    """
    Retorna score_total (0-100) y breakdown por dimensión.
    """

    # ── Dimensión 1: Confianza del documento ─────────────────────────────────
    dim_confianza = float(score_confianza or 0)

    # ── Dimensión 2: Jurídica — penalizar por conflictos activos ─────────────
    dim_juridica = 100.0
    for c in conflictos:
        tipo = c.get("tipo", "overlap")
        if tipo == "doble_venta":
            dim_juridica -= 60
        elif tipo == "overlap":
            area_c  = float(c.get("area_m2") or 0)
            area_p  = float(predio.get("area_m2") or 1)
            pct     = min(area_c / area_p * 100, 100)
            dim_juridica -= min(40, pct * 0.8)
        elif tipo == "invasion":
            dim_juridica -= 45
        elif tipo in ("inconsistencia_catastral", "inconsistencia_registral"):
            dim_juridica -= 20
    dim_juridica = max(0.0, dim_juridica)

    # ── Dimensión 3: Completitud ──────────────────────────────────────────────
    completitud_pts = 0
    if predio.get("area_m2"):            completitud_pts += 35
    if predio.get("municipio_nombre"):   completitud_pts += 20
    if predio.get("geom") is not None or predio.get("area_m2"):
        completitud_pts += 25             # polígono reconstruido
    if predio.get("score_confianza") and float(predio.get("score_confianza") or 0) > 50:
        completitud_pts += 20             # datos suficientemente ricos
    dim_completitud = min(100.0, float(completitud_pts))

    # ── Dimensión 4: Contextual ───────────────────────────────────────────────
    contextual_pts = 0
    if tiene_satelite:          contextual_pts += 40
    if n_relaciones > 0:        contextual_pts += 30
    n_fuentes = len([f for f in fuentes_usadas if f not in ("texto_directo",)])
    contextual_pts += min(30, n_fuentes * 10)
    dim_contextual = min(100.0, float(contextual_pts))

    # ── Score total ponderado ─────────────────────────────────────────────────
    score_total = (
        dim_confianza   * PESOS["confianza"]   +
        dim_juridica    * PESOS["juridica"]    +
        dim_completitud * PESOS["completitud"] +
        dim_contextual  * PESOS["contextual"]
    )
    score_total = round(min(100.0, max(0.0, score_total)), 1)

    return {
        "score_total": score_total,
        "nivel": _nivel(score_total),
        "breakdown": {
            "confianza":   round(dim_confianza,   1),
            "juridica":    round(dim_juridica,    1),
            "completitud": round(dim_completitud, 1),
            "contextual":  round(dim_contextual,  1),
        },
        "pesos": PESOS,
    }


def calcular_valoracion(
    orbyt_id: str,
    predio: dict,
    score_dinamico: dict,
    ndvi_mean: Optional[float] = None,
) -> dict:
    """
    Calcula la valoración estimada del predio en MXN.

    Factores de ajuste multiplicativos:
    - score_dinamico: 0.50x (score=0) → 1.00x (score=100)
    - conflicto activo: -25%
    - NDVI alto (>0.4): +8%
    - score_confianza bajo (<50): descuento adicional
    """
    area_m2    = float(predio.get("area_m2") or 0)
    municipio  = predio.get("municipio_nombre") or ""
    score      = score_dinamico.get("score_total", 50.0)

    if area_m2 <= 0:
        return _empty_valuation(orbyt_id, "sin_area")

    # Precio base por municipio
    precio_base_m2 = PRECIOS_BASE.get(municipio, PRECIO_DEFAULT)

    # Factores de ajuste
    factores: dict[str, float] = {}

    # 1. Score dinámico → confianza en el valor (0.5 a 1.0 lineal)
    f_score = 0.50 + (score / 100.0) * 0.50
    factores["score_dinamico"] = round(f_score, 3)

    # 2. Conflicto jurídico activo
    dim_juridica = score_dinamico["breakdown"]["juridica"]
    if dim_juridica < 60:
        f_juridico = 0.70
        factores["conflicto_juridico"] = f_juridico
    else:
        f_juridico = 1.0

    # 3. NDVI — vegetación/uso de suelo
    if ndvi_mean is not None and ndvi_mean > 0:
        if ndvi_mean >= 0.5:
            f_ndvi = 1.08
        elif ndvi_mean >= 0.3:
            f_ndvi = 1.04
        elif ndvi_mean < 0.1:
            f_ndvi = 0.95
        else:
            f_ndvi = 1.0
        factores["ndvi"] = round(f_ndvi, 3)
    else:
        f_ndvi = 1.0

    # Precio/m² ajustado
    f_total        = f_score * f_juridico * f_ndvi
    precio_adj_m2  = precio_base_m2 * f_total
    valor_total    = area_m2 * precio_adj_m2
    valor_base     = area_m2 * precio_base_m2

    return {
        "orbyt_id":        orbyt_id,
        "area_m2":         round(area_m2, 2),
        "municipio":       municipio,
        "valor_base_mxn":  round(valor_base, 2),
        "valor_ajust_mxn": round(valor_total, 2),
        "precio_m2_mxn":   round(precio_adj_m2, 2),
        "rango_min_mxn":   round(valor_total * 0.85, 2),
        "rango_max_mxn":   round(valor_total * 1.15, 2),
        "score_dinamico":  score,
        "factores":        factores,
        "breakdown":       score_dinamico["breakdown"],
        "metodologia":     "comparativo_mercado_bcs_v1",
        "nivel_confianza": score_dinamico["nivel"],
    }


def _nivel(score: float) -> str:
    if score >= 80: return "alto"
    if score >= 60: return "medio"
    if score >= 40: return "bajo"
    return "critico"


def _empty_valuation(orbyt_id: str, motivo: str) -> dict:
    return {
        "orbyt_id":        orbyt_id,
        "area_m2":         None,
        "municipio":       None,
        "valor_base_mxn":  None,
        "valor_ajust_mxn": None,
        "precio_m2_mxn":   None,
        "rango_min_mxn":   None,
        "rango_max_mxn":   None,
        "score_dinamico":  None,
        "factores":        {},
        "breakdown":       {},
        "metodologia":     "comparativo_mercado_bcs_v1",
        "nivel_confianza": None,
        "sin_datos":       motivo,
    }
