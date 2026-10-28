"""Pruebas del backend de inferencia (contrato real de la API)."""
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import CATALOG, DEFAULT_VERSION, FEATURES, MODELS, app  # noqa: E402

client = TestClient(app)

AVAILABLE = sorted(MODELS, key=lambda v: (not v.isdigit(), int(v) if v.isdigit() else v))


def _primer_delito_con_varias_modalidades() -> dict:
    """Busca en el catalogo una rama con mas de una modalidad.

    Sirve para probar que cambiar solo la modalidad altera la prediccion.
    """
    for bien, tipos in CATALOG['jerarquia'].items():
        for tipo, subtipos in tipos.items():
            for subtipo, modalidades in subtipos.items():
                if len(modalidades) > 1:
                    return {'bien_juridico_afectado': bien, 'tipo_delito': tipo,
                            'subtipo_delito': subtipo, 'modalidades': modalidades}
    raise AssertionError('El catalogo no tiene ninguna rama con varias modalidades.')


DELITO = _primer_delito_con_varias_modalidades()

VALID_PAYLOAD = {
    'anio': 2025,
    'mes': 6,
    'clave_ent': 9,
    'bien_juridico_afectado': DELITO['bien_juridico_afectado'],
    'tipo_delito': DELITO['tipo_delito'],
    'subtipo_delito': DELITO['subtipo_delito'],
    'modalidad': DELITO['modalidades'][0],
}


def test_root_lista_endpoints():
    response = client.get('/')
    assert response.status_code == 200
    body = response.json()
    assert '/predict' in body['endpoints']
    assert '/models' in body['endpoints']
    assert '/catalog' in body['endpoints']
    assert body['label'] == 'incidencia_delictiva'


def test_health_reporta_modelo_cargado():
    response = client.get('/health')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert body['model_loaded'] is True
    assert body['features'] == FEATURES
    assert body['default_version'] == DEFAULT_VERSION
    assert body['model_versions'] == AVAILABLE


def test_models_lista_versiones_con_metricas():
    response = client.get('/models')
    assert response.status_code == 200
    body = response.json()
    assert [m['version'] for m in body] == AVAILABLE
    assert sum(1 for m in body if m['is_default']) == 1
    for m in body:
        assert m['path'].endswith('.joblib')
        # Son metricas de regresion: deben venir informadas y ser coherentes.
        assert m['mae'] is not None and m['mae'] >= 0
        assert m['rmse'] is not None and m['rmse'] >= m['mae']
        assert m['r2'] is not None


def test_el_modelo_bate_a_la_media_del_dataset():
    """Un modelo que no mejora la media no serviria para nada."""
    for m in client.get('/models').json():
        assert m['mae'] < m['baseline_mae'], (
            f"La version {m['version']} no mejora la media: "
            f"mae={m['mae']} vs baseline={m['baseline_mae']}")


def test_catalog_expone_entidades_y_jerarquia():
    body = client.get('/catalog').json()
    assert len(body['entidades']) == 32
    assert len(body['meses']) == 12
    assert body['anios'][0] <= body['anios'][1]
    assert len(body['jerarquia']) >= 1
    for entidad in body['entidades']:
        assert 1 <= entidad['clave_ent'] <= 32
        assert entidad['entidad']


def test_predict_devuelve_un_conteo_no_negativo():
    response = client.post('/predict', json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {'prediccion', 'prediccion_redondeada', 'version',
                         'label', 'entidad', 'periodo'}
    assert isinstance(body['prediccion'], float)
    # La etiqueta es un conteo de carpetas de investigacion: nunca negativo.
    assert body['prediccion'] >= 0
    assert body['prediccion_redondeada'] == round(body['prediccion'])
    assert body['entidad'] == 'Ciudad de México'
    assert body['periodo'] == 'Junio 2025'


def test_predict_sin_version_usa_la_version_por_defecto():
    assert client.post('/predict', json=VALID_PAYLOAD).json()['version'] == DEFAULT_VERSION


@pytest.mark.parametrize('version', AVAILABLE)
def test_predict_responde_para_cada_version(version):
    response = client.post(f'/predict?version={version}', json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body['version'] == version
    assert body['prediccion'] >= 0


@pytest.mark.skipif(len(AVAILABLE) < 2, reason='requiere varias versiones cargadas')
def test_las_versiones_son_modelos_distintos():
    """Mismo payload, modelos entrenados con distinto volumen: no deben coincidir todos."""
    preds = {v: client.post(f'/predict?version={v}', json=VALID_PAYLOAD).json()['prediccion']
             for v in AVAILABLE}
    assert len(set(preds.values())) > 1, f'Artefactos posiblemente duplicados: {preds}'


@pytest.mark.skipif(len(AVAILABLE) < 2, reason='requiere varias versiones cargadas')
def test_cada_version_carga_un_artefacto_distinto():
    paths = [m['path'] for m in client.get('/models').json()]
    assert len(set(paths)) == len(paths), f'Rutas repetidas: {paths}'


def test_predict_rechaza_version_desconocida():
    response = client.post('/predict?version=77', json=VALID_PAYLOAD)
    assert response.status_code == 404
    assert '77' in response.json()['detail']


def test_predict_es_determinista():
    first = client.post('/predict', json=VALID_PAYLOAD).json()['prediccion']
    second = client.post('/predict', json=VALID_PAYLOAD).json()['prediccion']
    assert first == second


def test_la_entidad_cambia_la_prediccion():
    """Dos estados con poblaciones muy distintas no deben dar el mismo numero."""
    cdmx = client.post('/predict', json=dict(VALID_PAYLOAD, clave_ent=9)).json()
    colima = client.post('/predict', json=dict(VALID_PAYLOAD, clave_ent=6)).json()
    assert cdmx['prediccion'] != colima['prediccion']
    assert cdmx['entidad'] != colima['entidad']


def test_la_modalidad_cambia_la_prediccion():
    a = dict(VALID_PAYLOAD, modalidad=DELITO['modalidades'][0])
    b = dict(VALID_PAYLOAD, modalidad=DELITO['modalidades'][1])
    assert client.post('/predict', json=a).json()['prediccion'] != \
        client.post('/predict', json=b).json()['prediccion']


def test_predict_acepta_la_entidad_por_nombre():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != 'clave_ent'}
    response = client.post('/predict', json=dict(payload, entidad='Jalisco'))
    assert response.status_code == 200
    assert response.json()['entidad'] == 'Jalisco'


def test_el_nombre_de_entidad_tiene_prioridad_sobre_la_clave():
    """clave_ent trae un default para /docs; un nombre explicito debe ganarle."""
    response = client.post('/predict', json=dict(VALID_PAYLOAD, entidad='Jalisco'))
    assert response.json()['entidad'] == 'Jalisco'


@pytest.mark.parametrize('campo,valor', [
    ('anio', 1800),      # fuera del rango 1990-2100
    ('mes', 0),          # fuera del rango 1-12
    ('mes', 13),
    ('clave_ent', 0),    # fuera del rango 1-32
    ('clave_ent', 99),
])
def test_predict_rechaza_valores_fuera_de_rango(campo, valor):
    response = client.post('/predict', json=dict(VALID_PAYLOAD, **{campo: valor}))
    assert response.status_code == 422


@pytest.mark.parametrize('campo', [
    'bien_juridico_afectado', 'tipo_delito', 'subtipo_delito', 'modalidad',
])
def test_predict_rechaza_categorias_inexistentes(campo):
    response = client.post('/predict', json=dict(VALID_PAYLOAD, **{campo: 'no existe'}))
    assert response.status_code == 422
    assert campo in response.json()['detail']


def test_predict_rechaza_una_combinacion_incoherente():
    """La modalidad debe pertenecer al subtipo elegido, no a cualquiera."""
    otra_rama = None
    for bien, tipos in CATALOG['jerarquia'].items():
        for tipo, subtipos in tipos.items():
            for subtipo, modalidades in subtipos.items():
                if subtipo != VALID_PAYLOAD['subtipo_delito']:
                    otra_rama = modalidades[0]
                    break
            if otra_rama:
                break
        if otra_rama:
            break
    if otra_rama in DELITO['modalidades']:
        pytest.skip('La modalidad de la otra rama coincide con la valida.')
    response = client.post('/predict', json=dict(VALID_PAYLOAD, modalidad=otra_rama))
    assert response.status_code == 422


def test_predict_rechaza_entidad_inexistente():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != 'clave_ent'}
    response = client.post('/predict', json=dict(payload, entidad='Narnia'))
    assert response.status_code == 422


def test_predict_rechaza_tipos_invalidos():
    response = client.post('/predict', json=dict(VALID_PAYLOAD, anio='dos mil'))
    assert response.status_code == 422


def test_predict_usa_valores_por_defecto_si_falta_un_campo():
    """El esquema define defaults: un cuerpo vacio sigue siendo valido."""
    response = client.post('/predict', json={})
    assert response.status_code == 200
    assert response.json()['prediccion'] >= 0


def test_retrain_sin_configuracion_responde_503():
    """Sin RETRAIN_TOKEN el endpoint queda deshabilitado, no abierto."""
    response = client.post('/retrain', json={})
    assert response.status_code == 503
    assert 'RETRAIN_TOKEN' in response.json()['detail']


def test_openapi_documenta_predict_models_y_retrain():
    schema = client.get('/openapi.json').json()
    assert 'post' in schema['paths']['/predict']
    assert 'get' in schema['paths']['/models']
    assert 'get' in schema['paths']['/catalog']
    assert 'post' in schema['paths']['/retrain']
