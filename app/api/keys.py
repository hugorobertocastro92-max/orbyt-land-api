"""Gestión de API Keys para acceso público a ORBYT LAND API."""
from __future__ import annotations
import os
import secrets
import hashlib
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

router = APIRouter()


class KeyRequest(BaseModel):
    name: str
    email: str


class KeyResponse(BaseModel):
    api_key:    str      # retornada UNA sola vez
    key_prefix: str
    name:       str
    email:      str
    plan:       str
    message:    str


@router.post("", response_model=KeyResponse)
async def generate_api_key(body: KeyRequest):
    """
    Genera un API key para acceso a la API pública ORBYT LAND.
    El key se muestra UNA sola vez — guárdalo de inmediato.
    """
    # Generar key: formato `ol_<48 chars aleatorios>`
    raw_key    = "ol_" + secrets.token_urlsafe(36)
    key_prefix = raw_key[:11]  # "ol_" + 8 chars
    key_hash   = hashlib.sha256(raw_key.encode()).hexdigest()

    # Guardar en Supabase
    from app.db.supabase_store import _client, is_available
    import asyncio

    if is_available():
        def _save():
            return _client().table("api_keys").insert({
                "key_prefix": key_prefix,
                "key_hash":   key_hash,
                "name":       body.name[:120],
                "email":      body.email[:200],
                "plan":       "beta",
            }).execute()
        try:
            await asyncio.to_thread(_save)
        except Exception as e:
            raise HTTPException(500, f"Error guardando key: {e}")

    return KeyResponse(
        api_key    = raw_key,
        key_prefix = key_prefix,
        name       = body.name,
        email      = body.email,
        plan       = "beta",
        message    = "Guarda este API key ahora — no se vuelve a mostrar.",
    )


@router.get("/validate")
async def validate_key(x_api_key: str):
    """Verifica si un API key es válido (sin revelar datos del titular)."""
    import hashlib
    from app.db.supabase_store import _client, is_available
    import asyncio

    if not is_available():
        return {"valid": True, "note": "Supabase no disponible — acceso abierto en beta"}

    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()

    def _check():
        return _client().rpc("validate_api_key", {"p_hash": key_hash}).execute()

    try:
        result = await asyncio.to_thread(_check)
        return {"valid": bool(result.data)}
    except Exception:
        return {"valid": False}
