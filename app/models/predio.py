from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum
import uuid


class DocumentType(str, Enum):
    pdf = "pdf"
    jpg = "jpg"
    png = "png"
    tiff = "tiff"
    kml = "kml"
    kmz = "kmz"
    shp = "shp"
    geojson = "geojson"
    dxf = "dxf"
    escritura = "escritura"


class AnalysisState(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    error = "error"


class ConfidenceLevel(str, Enum):
    alta = "alta"
    media = "media"
    baja = "baja"
    sin_datos = "sin_datos"


class Vertex(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    numero: int
    rumbo_texto: Optional[str] = None
    rumbo_grados: Optional[float] = None
    distancia_m: Optional[float] = None
    coord_x: Optional[float] = None
    coord_y: Optional[float] = None
    confianza: float = 0.0


class Colindancia(BaseModel):
    lado: str
    descripcion: str
    tipo: str = "otro"
    identificado: bool = False


class ExtractedData(BaseModel):
    coordenadas_utm: Optional[dict] = None
    coordenadas_geo: Optional[dict] = None
    datum: Optional[str] = None
    sistema_coordenadas: Optional[str] = None
    propietario: Optional[str] = None
    clave_catastral: Optional[str] = None
    superficie_escritura: Optional[float] = None
    superficie_unidad: Optional[str] = None
    municipio: Optional[str] = None
    estado: Optional[str] = None
    fecha_escritura: Optional[str] = None
    notaria: Optional[str] = None
    vertices: List[Vertex] = []
    colindancias: List[Colindancia] = []
    texto_bruto: Optional[str] = None


class PolygonData(BaseModel):
    geojson: Optional[dict] = None
    area_m2: Optional[float] = None
    perimetro_m: Optional[float] = None
    centroide: Optional[List[float]] = None
    datum_origen: str = "desconocido"
    datum_normalizado: str = "WGS84"
    closure_error_m: Optional[float] = None   # error de cierre en metros (rumbos+distancias)


class ConfidenceBreakdown(BaseModel):
    ocr: float = 0.0
    completitud: float = 0.0
    referencias_externas: float = 0.0
    coherencia_geometrica: float = 0.0
    total: float = 0.0
    nivel: ConfidenceLevel = ConfidenceLevel.sin_datos
    observaciones: List[str] = []


class Analisis(BaseModel):
    id: str
    documento_id: str
    nombre_archivo: str
    tipo_documento: DocumentType
    estado: AnalysisState
    datos_extraidos: Optional[ExtractedData] = None
    poligono: Optional[PolygonData] = None
    confianza: Optional[ConfidenceBreakdown] = None
    fuentes_usadas: List[str] = []
    error_mensaje: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class Predio(BaseModel):
    id: str
    analisis_id: str
    nombre_archivo: str
    municipio: Optional[str] = None
    estado_mx: Optional[str] = None
    propietario: Optional[str] = None
    clave_catastral: Optional[str] = None
    area_m2: Optional[float] = None
    confianza_total: Optional[float] = None
    confianza_nivel: Optional[ConfidenceLevel] = None
    centroide: Optional[List[float]] = None
    geojson: Optional[dict] = None
    created_at: datetime


class UploadResponse(BaseModel):
    documento_id: str
    analisis_id: str
    nombre_archivo: str
    tipo: DocumentType
    estado: AnalysisState
