"""
Punto de entrada Netlify Functions.
Adapta FastAPI (ASGI) al protocolo Lambda/Netlify via Mangum.
"""
import sys
import os

# Añadir raíz del proyecto al path para que `from app.xxx import` funcione
# Netlify bundlea la función en /var/task; el root del proyecto queda en el mismo dir
# En dev local, subimos dos niveles para encontrar app/
_root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.insert(0, os.path.abspath(_root))
sys.path.insert(0, os.path.dirname(__file__))

from mangum import Mangum
from app.main import app

handler = Mangum(app, lifespan="off")
