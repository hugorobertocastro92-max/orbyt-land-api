"""Endpoints de datos geográficos de referencia."""
from fastapi import APIRouter, Query
import httpx

router = APIRouter()

# Municipios BCS con bounding boxes
BCS_MUNICIPIOS = {
    "La Paz": {"bbox": [-110.8, 23.5, -109.5, 24.5], "centroide": [-110.31, 24.14]},
    "Los Cabos": {"bbox": [-110.2, 22.7, -109.3, 23.2], "centroide": [-109.92, 22.89]},
    "Loreto": {"bbox": [-111.5, 25.5, -110.0, 26.5], "centroide": [-111.34, 26.01]},
    "Comondú": {"bbox": [-113.0, 25.5, -111.0, 27.5], "centroide": [-111.82, 26.05]},
    "Mulegé": {"bbox": [-114.5, 26.5, -110.5, 30.0], "centroide": [-111.03, 27.30]},
}


@router.get("/municipios")
async def get_municipios():
    return {"municipios": list(BCS_MUNICIPIOS.keys()), "data": BCS_MUNICIPIOS}


@router.get("/search")
async def search_location(q: str = Query(..., min_length=3)):
    """Búsqueda nominatim OSM para referencias geográficas."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": q, "format": "json", "limit": 5, "countrycodes": "mx"},
                headers={"User-Agent": "ORBYT-LAND-BCS/0.1"},
            )
            results = resp.json()
            return {"results": [
                {
                    "display_name": r["display_name"],
                    "lat": float(r["lat"]),
                    "lng": float(r["lon"]),
                    "type": r.get("type"),
                }
                for r in results
            ]}
        except Exception:
            return {"results": []}
