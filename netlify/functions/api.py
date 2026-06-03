"""
Punto de entrada Netlify Functions.
Adapta FastAPI (ASGI) al protocolo Lambda/Netlify via Mangum.
"""
import sys
import os

# Añadir raíz del proyecto al path para que `from app.xxx import` funcione
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from mangum import Mangum
from app.main import app

handler = Mangum(app, lifespan="off")
