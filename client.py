"""Cliente de prueba del endpoint /predict.

Uso:
    python client.py                        # usa http://localhost:8000
    API_URL=https://mi-api.onrender.com python client.py
    python client.py https://mi-api.onrender.com
"""
import os
import sys

import requests

API_URL = (sys.argv[1] if len(sys.argv) > 1
           else os.getenv('API_URL', 'http://localhost:8000')).rstrip('/')

body = {
    "anio": 2025,
    "mes": 6,
    "clave_ent": 9,
    "bien_juridico_afectado": "El patrimonio",
    "tipo_delito": "Robo",
    "subtipo_delito": "Robo de vehículo automotor",
    "modalidad": "Robo de coche de 4 ruedas Con violencia"
    }

# Se consulta cada version para ver el efecto del volumen de entrenamiento.
for version in ('25', '50', '100'):
    response = requests.post(url=f'{API_URL}/predict',
                             params={'version': version},
                             json=body, timeout=30)
    response.raise_for_status()
    data = response.json()
    print(f"version {data['version']:>3} % -> "
          f"{data['prediccion_redondeada']:>6} carpetas "
          f"({data['prediccion']:.4f}) | {data['entidad']} | {data['periodo']}")
