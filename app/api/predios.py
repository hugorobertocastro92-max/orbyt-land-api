"""Endpoints de gestión y exportación de predios."""
from __future__ import annotations
import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from app.models.predio import Predio
from app.services.analysis_pipeline import _analyses

router = APIRouter()


def _analysis_to_predio(a: dict) -> Predio:
    pol   = a.get("poligono") or {}
    conf  = a.get("confianza") or {}
    datos = a.get("datos_extraidos") or {}
    return Predio(
        id=a.get("orbyt_id") or a["id"],
        analisis_id=a["id"],
        nombre_archivo=a["nombre_archivo"],
        municipio=datos.get("municipio"),
        estado_mx=datos.get("estado"),
        propietario=datos.get("propietario"),
        clave_catastral=datos.get("clave_catastral"),
        area_m2=pol.get("area_m2"),
        confianza_total=conf.get("total"),
        confianza_nivel=conf.get("nivel"),
        centroide=pol.get("centroide"),
        geojson=pol.get("geojson"),
        created_at=a["created_at"],
    )


@router.get("", response_model=List[Predio])
async def list_predios(
    municipio: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    # 1. Predios en memoria (sesión actual)
    mem_results = []
    for a in list(_analyses.values()):
        if a.get("estado") != "completed":
            continue
        datos = a.get("datos_extraidos") or {}
        if municipio and datos.get("municipio") != municipio:
            continue
        mem_results.append(_analysis_to_predio(a))

    # 2. Predios persistidos en Supabase (sesiones anteriores)
    from app.db.supabase_store import list_predios as db_list, is_available
    if is_available():
        db_results = await db_list(municipio=municipio, limit=limit)
        # Evitar duplicados: ids en memoria
        mem_ids = {p.analisis_id for p in mem_results}
        for r in db_results:
            if r.get("analisis_id") not in mem_ids:
                try:
                    mem_results.append(Predio(**r))
                except Exception:
                    pass

    return mem_results[:limit]


@router.get("/{predio_id}", response_model=Predio)
async def get_predio(predio_id: str):
    # Buscar por analisis_id en memoria
    a = _analyses.get(predio_id)
    if a:
        return _analysis_to_predio(a)

    # Buscar por orbyt_id en memoria
    for v in _analyses.values():
        if v.get("orbyt_id") == predio_id:
            return _analysis_to_predio(v)

    raise HTTPException(404, "Predio no encontrado")


@router.get("/{predio_id}/export")
async def export_predio(predio_id: str, format: str = Query("geojson")):
    a = _analyses.get(predio_id)
    if not a:
        # Intentar desde Supabase
        from app.db.supabase_store import get_analysis as db_get
        a = await db_get(predio_id)
    if not a:
        raise HTTPException(404, "Predio no encontrado")

    pol     = a.get("poligono") or {}
    geojson = pol.get("geojson")

    if not geojson:
        raise HTTPException(400, "Este predio no tiene geometría exportable")

    if format == "geojson":
        return Response(
            content=json.dumps(geojson, ensure_ascii=False),
            media_type="application/geo+json",
            headers={"Content-Disposition": f"attachment; filename=predio-{predio_id[:8]}.geojson"},
        )

    if format == "kml":
        return Response(
            content=_geojson_to_kml(geojson, predio_id),
            media_type="application/vnd.google-earth.kml+xml",
            headers={"Content-Disposition": f"attachment; filename=predio-{predio_id[:8]}.kml"},
        )

    raise HTTPException(400, f"Formato '{format}' no soportado")


def _geojson_to_kml(geojson: dict, name: str) -> str:
    coords = geojson.get("geometry", {}).get("coordinates", [[]])[0]
    coord_str = " ".join(f"{c[0]},{c[1]},0" for c in coords)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Placemark>
    <name>Predio {name[:8]}</name>
    <Style>
      <LineStyle><color>ffC6F0A8</color><width>2</width></LineStyle>
      <PolyStyle><color>26C6F0A8</color></PolyStyle>
    </Style>
    <Polygon>
      <outerBoundaryIs><LinearRing>
        <coordinates>{coord_str}</coordinates>
      </LinearRing></outerBoundaryIs>
    </Polygon>
  </Placemark>
</kml>"""
