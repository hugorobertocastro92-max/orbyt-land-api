"""Endpoints de carga y análisis de documentos prediales."""
import os
import uuid
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, UploadFile, File, HTTPException
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

    documento_id = str(uuid.uuid4())
    analisis_id  = str(uuid.uuid4())
    filename     = file.filename or 'documento'

    file_path = UPLOAD_DIR / f"{documento_id}{ext}"
    file_path.write_bytes(content)

    from app.services.analysis_pipeline import run_analysis

    if IS_SERVERLESS:
        # Serverless: ejecutar síncronamente antes de responder
        await run_analysis(
            analisis_id=analisis_id,
            documento_id=documento_id,
            file_path=str(file_path),
            doc_type=doc_type,
            filename=filename,
        )
    else:
        # Desarrollo local: background task (no bloquea respuesta)
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
