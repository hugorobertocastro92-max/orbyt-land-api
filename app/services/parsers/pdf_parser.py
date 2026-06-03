"""
Parser PDF — dos caminos:
  1. PDF con texto seleccionable → PyPDF2 extrae directamente (conf 0.95)
  2. PDF escaneado (imagen) → PyMuPDF renderiza páginas → OCR
"""
from __future__ import annotations
import io
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

MIN_TEXT_CHARS = 80  # menos de esto → consideramos PDF escaneado


async def parse_pdf(file_bytes: bytes) -> Tuple[str, float]:
    """Retorna (texto, confianza_ocr)."""
    # Intento 1: texto seleccionable
    text = _extract_text_pypdf2(file_bytes)
    if len(text.strip()) >= MIN_TEXT_CHARS:
        logger.info(f"PDF con texto: {len(text)} chars")
        return text, 0.95

    # Intento 2: PyMuPDF texto embebido
    text = _extract_text_pymupdf(file_bytes)
    if len(text.strip()) >= MIN_TEXT_CHARS:
        logger.info(f"PyMuPDF texto: {len(text)} chars")
        return text, 0.93

    # Intento 3: PDF escaneado — renderizar páginas y OCR
    logger.info("PDF escaneado detectado — iniciando OCR")
    return await _ocr_scanned_pdf(file_bytes)


def _extract_text_pypdf2(file_bytes: bytes) -> str:
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        return '\n'.join(p.extract_text() or '' for p in reader.pages)
    except Exception:
        return ''


def _extract_text_pymupdf(file_bytes: bytes) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype='pdf')
        pages = [doc[i].get_text() for i in range(min(len(doc), 10))]
        return '\n'.join(pages)
    except Exception:
        return ''


async def _ocr_scanned_pdf(file_bytes: bytes) -> Tuple[str, float]:
    """Renderiza páginas del PDF y aplica OCR con EasyOCR/PaddleOCR."""
    images = _render_pdf_pages(file_bytes)
    if not images:
        logger.error("No se pudieron renderizar páginas del PDF")
        return '', 0.0

    from app.services.ocr.paddle_ocr import ocr_image_bytes

    all_text, confs = [], []
    for i, img_bytes in enumerate(images):
        text, conf = await ocr_image_bytes(img_bytes)
        logger.info(f"  Página {i+1}: {len(text)} chars, conf={conf:.2f}")
        all_text.append(text)
        confs.append(conf)

    avg_conf = sum(confs) / len(confs) if confs else 0.0
    return '\n'.join(all_text), avg_conf


def _render_pdf_pages(file_bytes: bytes, max_pages: int = 5, dpi: int = 200) -> list:
    """Renderiza páginas del PDF como imágenes PNG usando PyMuPDF."""
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype='pdf')
        matrix = fitz.Matrix(dpi / 72, dpi / 72)  # 72 DPI base → escalar
        images = []
        for i in range(min(len(doc), max_pages)):
            pix = doc[i].get_pixmap(matrix=matrix, alpha=False)
            images.append(pix.tobytes('png'))
        logger.info(f"PyMuPDF: {len(images)} páginas renderizadas a {dpi} DPI")
        return images
    except Exception as e:
        logger.error(f"PyMuPDF render error: {e}")
        return []
