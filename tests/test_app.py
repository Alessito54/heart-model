"""Pruebas del backend de inferencia (contrato real de la API)."""
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import FEATURES, app  # noqa: E402

client = TestClient(app)

VALID_PAYLOAD = {
    "age": 64, "sex": 1, "cp": 3, "trestbps": 120, "chol": 267, "fbs": 0,
    "restecg": 0, "thalach": 99, "exang": 1, "oldpeak": 1.8, "slope": 1,
    "ca": 2, "thal": 2,
}


def test_root_lista_endpoints():
    response = client.get('/')
    assert response.status_code == 200
    assert '/score' in response.json()['endpoints']


def test_health_reporta_modelo_cargado():
    response = client.get('/health')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert body['model_loaded'] is True
    assert body['features'] == FEATURES


def test_score_devuelve_probabilidad_en_rango():
    response = client.post('/score', json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {'score'}
    assert isinstance(body['score'], float)
    assert 0.0 <= body['score'] <= 1.0


def test_score_es_determinista():
    first = client.post('/score', json=VALID_PAYLOAD).json()['score']
    second = client.post('/score', json=VALID_PAYLOAD).json()['score']
    assert first == second


def test_score_depende_del_orden_correcto_de_features():
    """Dos pacientes distintos no deben producir exactamente la misma salida."""
    other = dict(VALID_PAYLOAD, age=29, sex=0, cp=0, thalach=190, exang=0,
                 oldpeak=0.0, ca=0, thal=1)
    assert client.post('/score', json=VALID_PAYLOAD).json()['score'] != \
        client.post('/score', json=other).json()['score']


@pytest.mark.parametrize('campo,valor', [
    ('sex', 2),          # fuera del rango 0-1
    ('cp', 9),           # fuera del rango 0-3
    ('age', -5),         # edad negativa
    ('oldpeak', 99.0),   # fuera del rango 0-10
    ('ca', 7),           # fuera del rango 0-4
])
def test_score_rechaza_valores_fuera_de_rango(campo, valor):
    response = client.post('/score', json=dict(VALID_PAYLOAD, **{campo: valor}))
    assert response.status_code == 422


def test_score_rechaza_tipos_invalidos():
    response = client.post('/score', json=dict(VALID_PAYLOAD, age='sesenta'))
    assert response.status_code == 422


def test_score_usa_valores_por_defecto_si_falta_un_campo():
    """El esquema original define defaults: un cuerpo vacio sigue siendo valido."""
    response = client.post('/score', json={})
    assert response.status_code == 200
    assert 0.0 <= response.json()['score'] <= 1.0


def test_openapi_documenta_score():
    schema = client.get('/openapi.json').json()
    assert '/score' in schema['paths']
    assert 'post' in schema['paths']['/score']
