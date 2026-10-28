"""Pruebas del descubrimiento de modelos (registro de versiones)."""
import importlib
import pathlib
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _copiar_artefactos(destino: pathlib.Path, versiones=('25', '50', '100'),
                       con_metricas=True, con_v1=False) -> None:
    """Prepara un directorio de modelos de prueba.

    catalog.json se copia siempre: app.py lo necesita para arrancar, porque de
    ahi salen los valores validos de cada campo.
    """
    shutil.copyfile(ROOT / 'model/catalog.json', destino / 'catalog.json')
    for v in versiones:
        shutil.copyfile(ROOT / f'model/incidencia-{v}.joblib',
                        destino / f'incidencia-{v}.joblib')
        if con_metricas:
            shutil.copyfile(ROOT / f'model/metrics-{v}.json',
                            destino / f'metrics-{v}.json')
    if con_v1:
        shutil.copyfile(ROOT / 'model/incidencia-v1.joblib',
                        destino / 'incidencia-v1.joblib')


def load_app(monkeypatch, model_dir: pathlib.Path, **env):
    """Reimporta app.py apuntando a otro directorio de modelos."""
    monkeypatch.setenv('MODEL_DIR', str(model_dir))
    monkeypatch.setenv('MODEL_PATH', str(model_dir / 'incidencia-v1.joblib'))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop('app', None)
    module = importlib.import_module('app')
    return module


@pytest.fixture(autouse=True)
def _restaurar_app():
    yield
    # Deja el modulo en su configuracion normal para el resto de la suite.
    sys.modules.pop('app', None)


def test_descubre_las_tres_versiones(monkeypatch, tmp_path):
    _copiar_artefactos(tmp_path)
    module = load_app(monkeypatch, tmp_path)
    assert sorted(module.MODELS, key=int) == ['25', '50', '100']
    assert module.DEFAULT_VERSION == '100'


def test_ignora_el_artefacto_de_compatibilidad_v1(monkeypatch, tmp_path):
    """incidencia-v1.joblib es una copia: no debe aparecer como version extra."""
    _copiar_artefactos(tmp_path, con_v1=True)
    module = load_app(monkeypatch, tmp_path)
    assert 'v1' not in module.MODELS
    assert len(module.MODELS) == 3


def test_respaldo_con_un_unico_artefacto_sin_version(monkeypatch, tmp_path):
    """Despliegue con un solo artefacto sin version. La API sigue sirviendo."""
    _copiar_artefactos(tmp_path, versiones=(), con_v1=True)
    module = load_app(monkeypatch, tmp_path)
    assert list(module.MODELS) == ['default']
    client = TestClient(module.app)
    body = client.post('/predict', json={}).json()
    assert body['version'] == 'default'
    assert body['prediccion'] >= 0


def test_default_version_configurable(monkeypatch, tmp_path):
    _copiar_artefactos(tmp_path)
    module = load_app(monkeypatch, tmp_path, DEFAULT_MODEL_VERSION='25')
    assert module.DEFAULT_VERSION == '25'
    assert TestClient(module.app).post('/predict', json={}).json()['version'] == '25'


def test_version_por_defecto_inexistente_cae_en_la_mayor(monkeypatch, tmp_path):
    _copiar_artefactos(tmp_path)
    module = load_app(monkeypatch, tmp_path, DEFAULT_MODEL_VERSION='77')
    assert module.DEFAULT_VERSION == '100'


def test_sin_modelos_falla_con_mensaje_claro(monkeypatch, tmp_path):
    shutil.copyfile(ROOT / 'model/catalog.json', tmp_path / 'catalog.json')
    with pytest.raises(RuntimeError, match='No se encontro ningun modelo'):
        load_app(monkeypatch, tmp_path)


def test_sin_catalogo_falla_con_mensaje_claro(monkeypatch, tmp_path):
    """Sin catalog.json la API no puede validar entradas: debe fallar al arrancar."""
    _copiar_artefactos(tmp_path)
    (tmp_path / 'catalog.json').unlink()
    with pytest.raises(RuntimeError, match='No se encontro el catalogo'):
        load_app(monkeypatch, tmp_path)


def test_metricas_ausentes_no_rompen_el_registro(monkeypatch, tmp_path):
    """Un despliegue sin metrics-*.json sigue sirviendo, solo sin metricas."""
    _copiar_artefactos(tmp_path, con_metricas=False)
    module = load_app(monkeypatch, tmp_path)
    body = TestClient(module.app).get('/models').json()
    assert [m['version'] for m in body] == ['25', '50', '100']
    assert all(m['mae'] is None for m in body)
