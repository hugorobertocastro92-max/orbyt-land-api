"""Endpoints de carga y análisis de documentos prediales."""
import os
import uuid
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from app.models.predio import UploadResponse, AnalysisState, DocumentType

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = Path("/tmp/orbyt-land-uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Entorno serverless (Netlify Functions) — sin background tasks
IS_SERVERLESS = os.getenv("NETLIFY", "") == "true" or os.getenv("AWS_LAMBDA_FUNCTION_NAME", "") != ""

EXTENSION_TO_TYPE = {
    '.pdf':     DocumentType.pdf,
    '.jpg':     DocumentType.jpg,
    '.jpeg':    DocumentType.jpg,
    '.png':     DocumentType.png,
    '.tif':     DocumentType.tiff,
    '.tiff':    DocumentType.tiff,
    '.txt':     DocumentType.escritura,
    '.kml':     DocumentType.kml,
    '.kmz':     DocumentType.kmz,
    '.shp':     DocumentType.shp,
    '.zip':     DocumentType.shp,
    '.geojson': DocumentType.geojson,
    '.json':    DocumentType.geojson,
    '.dxf':     DocumentType.dxf,
    '.dwg':     DocumentType.dxf,
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: Annotated[UploadFile, File(description="Documento predial")],
):
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "Archivo demasiado grande. Máximo 50 MB.")

    ext = Path(file.filename or '').suffix.lower()
    doc_type = EXTENSION_TO_TYPE.get(ext)
    if not doc_type:
        raise HTTPException(400, f"Formato '{ext}' no soportado.")

    # Deduplicación por SHA-256
    from app.db.supabase_store import sha256_of_bytes, find_by_hash
    file_hash = sha256_of_bytes(content)
    existing = await find_by_hash(file_hash)
    if existing:
        logger.info(f"Documento duplicado detectado — hash={file_hash[:12]}… → analisis_id={existing['analisis_id']}")
        return UploadResponse(
            documento_id=existing.get("id", str(uuid.uuid4())),
            analisis_id=existing["analisis_id"],
            nombre_archivo=file.filename or 'documento',
            tipo=doc_type,
            estado=AnalysisState.completed,
        )

    documento_id = str(uuid.uuid4())
    analisis_id  = str(uuid.uuid4())
    filename     = file.filename or 'documento'

    file_path = UPLOAD_DIR / f"{documento_id}{ext}"
    file_path.write_bytes(content)

    from app.services.analysis_pipeline import run_analysis, _analyses
    from datetime import datetime
    _analyses[analisis_id] = {
        "id": analisis_id,
        "documento_id": documento_id,
        "nombre_archivo": filename,
        "tipo_documento": doc_type,
        "estado": AnalysisState.pending,
        "_file_hash": file_hash,
        "datos_extraidos": None,
        "poligono": None,
        "confianza": None,
        "fuentes_usadas": [],
        "error_mensaje": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    from app.services.analysis_pipeline import run_analysis
    if IS_SERVERLESS:
        await run_analysis(
            analisis_id=analisis_id,
            documento_id=documento_id,
            file_path=str(file_path),
            doc_type=doc_type,
            filename=filename,
        )
    else:
        import asyncio
        asyncio.create_task(run_analysis(
            analisis_id=analisis_id,
            documento_id=documento_id,
            file_path=str(file_path),
            doc_type=doc_type,
            filename=filename,
        ))

    return UploadResponse(
        documento_id=documento_id,
        analisis_id=analisis_id,
        nombre_archivo=filename,
        tipo=doc_type,
        estado=AnalysisState.completed if IS_SERVERLESS else AnalysisState.pending,
    )


@router.post("/upload-text", response_model=UploadResponse)
async def upload_text(texto: str = Form(...), titulo: str = Form(default="Texto pegado")):
    """Analiza texto predial pegado directamente (sin archivo)."""
    if not texto.strip():
        raise HTTPException(400, "El texto no puede estar vacío.")
    if len(texto) > 100_000:
        raise HTTPException(400, "Texto demasiado largo. Máximo 100,000 caracteres.")

    documento_id = str(uuid.uuid4())
    analisis_id  = str(uuid.uuid4())
    filename     = f"{titulo}.txt"

    file_path = UPLOAD_DIR / f"{documento_id}.txt"
    file_path.write_text(texto, encoding="utf-8")

    if IS_SERVERLESS:
        await run_analysis(
            analisis_id=analisis_id,
            documento_id=documento_id,
            file_path=str(file_path),
            doc_type=DocumentType.escritura,
            filename=filename,
        )
    else:
        import asyncio
        asyncio.create_task(run_analysis(
            analisis_id=analisis_id,
            documento_id=documento_id,
            file_path=str(file_path),
            doc_type=DocumentType.escritura,
            filename=filename,
        ))

    return UploadResponse(
        documento_id=documento_id,
        analisis_id=analisis_id,
        nombre_archivo=filename,
        tipo=DocumentType.escritura,
        estado=AnalysisState.completed if IS_SERVERLESS else AnalysisState.pending,
    )


@router.post("/batch")
async def batch_upload(
    files: list[Annotated[UploadFile, File(description="Hasta 5 documentos prediales")]],
):
    """
    Procesa hasta 5 documentos en paralelo.
    Retorna un array con el analisis_id de cada archivo.
    """
    MAX_BATCH = 5
    if not files:
        raise HTTPException(400, "Se requiere al menos un archivo.")
    if len(files) > MAX_BATCH:
        raise HTTPException(400, f"Máximo {MAX_BATCH} archivos por lote.")

    import asyncio
    from fastapi import Request

    async def _process_one(file: UploadFile) -> dict:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            return {"nombre_archivo": file.filename, "error": "Archivo demasiado grande (>50 MB)", "estado": "error"}
        ext = Path(file.filename or '').suffix.lower()
        doc_type = EXTENSION_TO_TYPE.get(ext)
        if not doc_type:
            return {"nombre_archivo": file.filename, "error": f"Formato '{ext}' no soportado", "estado": "error"}
        from app.db.supabase_store import sha256_of_bytes, find_by_hash
        file_hash = sha256_of_bytes(content)
        existing  = await find_by_hash(file_hash)
        if existing:
            return {
                "nombre_archivo": file.filename,
                "analisis_id":    existing["analisis_id"],
                "estado":         "completed",
                "duplicado":      True,
            }
        documento_id = str(uuid.uuid4())
        analisis_id  = str(uuid.uuid4())
        filename     = file.filename or "documento"
        file_path    = UPLOAD_DIR / f"{documento_id}{ext}"
        file_path.write_bytes(content)

        from app.services.analysis_pipeline import run_analysis, _analyses
        from datetime import datetime
        _analyses[analisis_id] = {
            "id": analisis_id, "documento_id": documento_id,
            "nombre_archivo": filename, "tipo_documento": doc_type,
            "estado": AnalysisState.pending, "_file_hash": file_hash,
            "datos_extraidos": None, "poligono": None, "confianza": None,
            "fuentes_usadas": [], "error_mensaje": None,
            "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
        }
        if IS_SERVERLESS:
            await run_analysis(analisis_id=analisis_id, documento_id=documento_id,
                               file_path=str(file_path), doc_type=doc_type,
                               filename=filename, file_hash=file_hash)
        else:
            asyncio.create_task(run_analysis(analisis_id=analisis_id, documento_id=documento_id,
                                             file_path=str(file_path), doc_type=doc_type,
                                             filename=filename, file_hash=file_hash))
        return {
            "nombre_archivo": filename,
            "analisis_id":    analisis_id,
            "estado":         "completed" if IS_SERVERLESS else "processing",
        }

    results = await asyncio.gather(*[_process_one(f) for f in files], return_exceptions=False)
    return {"total": len(results), "resultados": list(results)}
