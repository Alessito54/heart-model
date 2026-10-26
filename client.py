"""Cliente de prueba del endpoint /score.

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
    "age": 64,
    "sex": 1,
    "cp": 3,
    "trestbps": 120,
    "chol": 267,
    "fbs": 0,
    "restecg": 0,
    "thalach": 99,
    "exang": 1,
    "oldpeak": 1.8,
    "slope": 1,
    "ca": 2,
    "thal": 2
    }

response = requests.post(url=f'{API_URL}/score', json=body, timeout=30)
response.raise_for_status()
print(response.json())
