"""Endpoints de carga y gestión de documentos."""
import uuid
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from app.models.predio import UploadResponse, AnalysisState, DocumentType

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = Path("/tmp/orbyt-land-uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

EXTENSION_TO_TYPE = {
    '.pdf': DocumentType.pdf,
    '.jpg': DocumentType.jpg,
    '.jpeg': DocumentType.jpg,
    '.png': DocumentType.png,
    '.txt': DocumentType.escritura,   # texto plano de escritura
    '.tif': DocumentType.tiff,
    '.tiff': DocumentType.tiff,
    '.kml': DocumentType.kml,
    '.kmz': DocumentType.kmz,
    '.shp': DocumentType.shp,
    '.zip': DocumentType.shp,    # ZIP con shapefile (.shp + .dbf + .shx)
    '.geojson': DocumentType.geojson,
    '.json': DocumentType.geojson,
    '.dxf': DocumentType.dxf,
    '.dwg': DocumentType.dxf,
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
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
    analisis_id = str(uuid.uuid4())

    # Save to temp storage
    file_path = UPLOAD_DIR / f"{documento_id}{ext}"
    file_path.write_bytes(content)

    # Trigger async analysis
    from app.services.analysis_pipeline import run_analysis
    background_tasks.add_task(
        run_analysis,
        analisis_id=analisis_id,
        documento_id=documento_id,
        file_path=str(file_path),
        doc_type=doc_type,
        filename=file.filename or 'documento',
    )

    return UploadResponse(
        documento_id=documento_id,
        analisis_id=analisis_id,
        nombre_archivo=file.filename or 'documento',
        tipo=doc_type,
        estado=AnalysisState.pending,
    )
