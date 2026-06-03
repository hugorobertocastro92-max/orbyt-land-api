import os
import logging

logger = logging.getLogger(__name__)

# El pipeline de análisis usa almacenamiento en memoria (_analyses dict).
# La base de datos es opcional para persistencia — no bloquea el arranque.

async def init_db():
    """Inicializa la DB si está disponible. Falla silenciosamente en desarrollo."""
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url or "localhost" in db_url:
        logger.info("DB no configurada — usando almacenamiento en memoria (modo desarrollo)")
        return
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Base de datos conectada correctamente")
    except Exception as e:
        logger.warning(f"DB no disponible ({e}) — modo memoria activo")
