"""Webhooks — notificación async cuando un análisis completa."""
from __future__ import annotations
import hashlib
import hmac
import secrets
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class WebhookCreate(BaseModel):
    url:         str
    description: Optional[str] = None
    events:      List[str] = ["analysis.completed"]


class WebhookOut(BaseModel):
    id:          str
    url:         str
    description: Optional[str]
    events:      List[str]
    is_active:   bool
    total_fired: int
    last_fired_at:    Optional[str]
    last_status_code: Optional[int]
    created_at:  str
    secret_prefix: str    # primeros 8 chars del secret (para identificación)


@router.post("", response_model=dict)
async def create_webhook(body: WebhookCreate):
    """
    Registra un webhook. Se notificará con POST cuando ocurran los eventos.
    El secret se muestra UNA sola vez — úsalo para validar la firma HMAC-SHA256.
    """
    from app.db.supabase_store import _client, is_available
    import asyncio

    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")

    secret = "whs_" + secrets.token_urlsafe(32)

    def _save():
        return _client().table("webhooks").insert({
            "url":         body.url[:500],
            "secret":      secret,
            "events":      body.events,
            "description": body.description,
        }).execute()

    result = await asyncio.to_thread(_save)
    row = result.data[0] if result.data else {}

    return {
        "id":      row.get("id"),
        "url":     body.url,
        "secret":  secret,
        "events":  body.events,
        "message": "Guarda el secret ahora — no se vuelve a mostrar. Úsalo para verificar X-Orbyt-Signature.",
    }


@router.get("", response_model=List[WebhookOut])
async def list_webhooks():
    """Lista todos los webhooks activos."""
    from app.db.supabase_store import _client, is_available
    import asyncio

    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")

    def _q():
        return _client().table("webhooks").select("*").eq("is_active", True).execute()

    result = await asyncio.to_thread(_q)
    rows = result.data or []
    return [WebhookOut(
        id=r["id"], url=r["url"],
        description=r.get("description"),
        events=r.get("events") or ["analysis.completed"],
        is_active=r.get("is_active", True),
        total_fired=r.get("total_fired", 0),
        last_fired_at=str(r["last_fired_at"])[:19] if r.get("last_fired_at") else None,
        last_status_code=r.get("last_status_code"),
        created_at=str(r["created_at"])[:19],
        secret_prefix=r.get("secret", "")[:12],
    ) for r in rows]


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str):
    """Desactiva un webhook."""
    from app.db.supabase_store import _client, is_available
    import asyncio

    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")

    def _upd():
        return _client().table("webhooks").update({"is_active": False}).eq("id", webhook_id).execute()

    await asyncio.to_thread(_upd)
    return {"status": "deleted", "id": webhook_id}


@router.post("/{webhook_id}/test")
async def test_webhook(webhook_id: str):
    """Envía un payload de prueba al webhook."""
    from app.db.supabase_store import _client, is_available, dispatch_webhook_payload
    import asyncio

    if not is_available():
        raise HTTPException(503, "Base de datos no disponible")

    def _q():
        return _client().table("webhooks").select("*").eq("id", webhook_id).eq("is_active", True).limit(1).execute()

    result = await asyncio.to_thread(_q)
    if not result.data:
        raise HTTPException(404, "Webhook no encontrado")

    row = result.data[0]
    test_payload = {
        "event":       "test",
        "orbyt_id":    "ORBYT-MX-BCS-LPZ-TEST",
        "analisis_id": "test-00000000",
        "estado":      "completed",
        "score":       85.0,
        "message":     "Este es un payload de prueba de ORBYT LAND",
    }
    status = await dispatch_webhook_payload(row["id"], row["url"], row["secret"], test_payload)
    return {"status": "dispatched", "http_status": status}
