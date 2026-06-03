"""
Motor OCR con cadena de prioridad:
  1. PaddleOCR (si disponible — mejor precisión en español)
  2. EasyOCR  (puro Python, sin dependencias del sistema)
  3. Azure Document Intelligence (fallback cloud, requiere API key)
"""
from __future__ import annotations
import io
import logging
import os
from typing import Tuple

logger = logging.getLogger(__name__)

_paddle_instance = None
_easy_instance = None


async def ocr_image_bytes(image_bytes: bytes) -> Tuple[str, float]:
    """OCR sobre imagen en bytes. Retorna (texto, confianza 0-1)."""
    preprocessed = await _preprocess(image_bytes)

    # 1. PaddleOCR
    result = await _try_paddle(preprocessed)
    if result and result[1] >= 0.60:
        return result

    # 2. EasyOCR
    result = await _try_easyocr(preprocessed)
    if result and result[1] >= 0.45:
        return result

    # 3. Azure fallback
    result = await _try_azure(image_bytes)
    if result and result[1] > 0:
        return result

    logger.warning("Todos los motores OCR fallaron — instalar PaddleOCR o configurar Azure")
    return '', 0.0


async def _try_paddle(image_bytes: bytes) -> Tuple[str, float]:
    global _paddle_instance
    try:
        if _paddle_instance is None:
            from paddleocr import PaddleOCR
            _paddle_instance = PaddleOCR(use_angle_cls=True, lang='es', show_log=False)
            logger.info("PaddleOCR listo")

        import numpy as np
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        result = _paddle_instance.ocr(np.array(img), cls=True)
        if not result or not result[0]:
            return '', 0.0

        texts, confs = [], []
        for line in result[0]:
            if line and len(line) >= 2:
                texts.append(line[1][0])
                confs.append(float(line[1][1]))

        return '\n'.join(texts), sum(confs) / len(confs) if confs else 0.0

    except ImportError:
        return '', 0.0
    except Exception as e:
        logger.debug(f"PaddleOCR error: {e}")
        return '', 0.0


async def _try_easyocr(image_bytes: bytes) -> Tuple[str, float]:
    global _easy_instance
    try:
        if _easy_instance is None:
            import easyocr
            # Modelos ES + EN para escrituras mexicanas (mezclan ambos idiomas)
            _easy_instance = easyocr.Reader(['es', 'en'], gpu=False, verbose=False)
            logger.info("EasyOCR listo (es+en, CPU)")

        import numpy as np
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        results = _easy_instance.readtext(np.array(img), detail=1, paragraph=False)

        if not results:
            return '', 0.0

        # Ordenar por posición vertical para preservar orden del texto
        results_sorted = sorted(results, key=lambda r: r[0][0][1])

        lines, confs = [], []
        for bbox, text, conf in results_sorted:
            if conf > 0.2 and text.strip():
                lines.append(text.strip())
                confs.append(conf)

        full_text = '\n'.join(lines)
        avg_conf = sum(confs) / len(confs) if confs else 0.0
        logger.info(f"EasyOCR: {len(lines)} líneas, conf={avg_conf:.2f}")
        return full_text, avg_conf

    except ImportError:
        return '', 0.0
    except Exception as e:
        logger.error(f"EasyOCR error: {e}")
        return '', 0.0


async def _try_azure(image_bytes: bytes) -> Tuple[str, float]:
    key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    if not key or not endpoint:
        return '', 0.0
    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential
        client = DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))
        result = client.begin_analyze_document("prebuilt-read", image_bytes).result()
        texts = [p.content for p in (result.paragraphs or [])]
        return '\n'.join(texts), 0.92
    except Exception as e:
        logger.error(f"Azure OCR: {e}")
        return '', 0.0


async def _preprocess(image_bytes: bytes) -> bytes:
    """Normaliza la imagen: upscale, contraste, nitidez."""
    try:
        from PIL import Image, ImageEnhance
        import io as _io

        img = Image.open(_io.BytesIO(image_bytes)).convert('RGB')
        w, h = img.size

        # Upscale si está por debajo de 200 DPI equivalente
        if w < 1200:
            scale = 1200 / w
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        img = ImageEnhance.Contrast(img).enhance(1.4)
        img = ImageEnhance.Sharpness(img).enhance(1.3)

        buf = _io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        return image_bytes
