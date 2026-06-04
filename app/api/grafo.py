"""Knowledge Graph y Digital Twin por ORBYT-ID."""
from __future__ import annotations
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


@router.get("/global")
async def get_global_graph():
    """Grafo global: todos los predios como nodos y todas las relaciones como aristas."""
    from app.db.supabase_store import get_global_graph, is_available
    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")
    return await get_global_graph()


class EventoTimeline(BaseModel):
    tipo_evento: str
    titulo: str
    descripcion: Optional[str] = None
    evento_fecha: Optional[str] = None
    metadata: Optional[dict] = None


class RelacionGrafo(BaseModel):
    orbyt_id_origen: str
    orbyt_id_destino: str
    tipo: str
    descripcion: Optional[str] = None
    peso: Optional[float] = None
    area_m2_origen: Optional[float] = None
    area_m2_destino: Optional[float] = None
    municipio_origen: Optional[str] = None
    municipio_destino: Optional[str] = None


class GrafoOut(BaseModel):
    orbyt_id: str
    nodos: List[dict]
    aristas: List[RelacionGrafo]


@router.get("/{orbyt_id}/timeline", response_model=List[EventoTimeline])
async def get_timeline(orbyt_id: str):
    """Timeline completo del predio: creación, análisis, satélite, conflictos."""
    from app.db.supabase_store import _client, is_available
    import asyncio

    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")

    def _query():
        return _client().rpc("get_timeline", {"p_orbyt_id": orbyt_id}).execute()

    result = await asyncio.to_thread(_query)
    rows = result.data or []
    return [EventoTimeline(
        tipo_evento=r.get("tipo_evento", ""),
        titulo=r.get("titulo", ""),
        descripcion=r.get("descripcion"),
        evento_fecha=str(r.get("evento_fecha", ""))[:10] if r.get("evento_fecha") else None,
        metadata=r.get("metadata"),
    ) for r in rows]


@router.get("/{orbyt_id}", response_model=GrafoOut)
async def get_grafo(orbyt_id: str):
    """Grafo de relaciones del predio: vecinos y tipo de relación."""
    from app.db.supabase_store import _client, is_available
    import asyncio

    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")

    def _query():
        return _client().rpc("get_graph", {"p_orbyt_id": orbyt_id}).execute()

    result = await asyncio.to_thread(_query)
    aristas = [RelacionGrafo(**r) for r in (result.data or [])]

    # Construir nodos únicos
    nodo_ids = {orbyt_id}
    for a in aristas:
        nodo_ids.add(a.orbyt_id_origen)
        nodo_ids.add(a.orbyt_id_destino)

    nodos = [{"orbyt_id": nid, "es_central": nid == orbyt_id} for nid in nodo_ids]
    return GrafoOut(orbyt_id=orbyt_id, nodos=nodos, aristas=aristas)


@router.post("/{orbyt_id}/relacion")
async def crear_relacion(
    orbyt_id: str,
    orbyt_id_destino: str,
    tipo: str,
    descripcion: Optional[str] = None,
):
    """Crea una relación manual entre dos predios."""
    tipos_validos = {"colinda_con", "subdividido_de", "fusionado_en", "relacionado_con"}
    if tipo not in tipos_validos:
        raise HTTPException(400, f"Tipo inválido. Opciones: {tipos_validos}")

    from app.db.supabase_store import _client, is_available
    import asyncio

    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")

    def _insert():
        return _client().table("relaciones_predios").upsert({
            "orbyt_id_origen":  orbyt_id,
            "orbyt_id_destino": orbyt_id_destino,
            "tipo":             tipo,
            "descripcion":      descripcion,
        }, on_conflict="orbyt_id_origen,orbyt_id_destino,tipo").execute()

    result = await asyncio.to_thread(_insert)
    return {"status": "ok", "relacion": result.data[0] if result.data else {}}
