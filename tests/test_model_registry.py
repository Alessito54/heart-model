"""Pruebas del descubrimiento de modelos (registro de versiones)."""
import importlib
import pathlib
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_app(monkeypatch, model_dir: pathlib.Path, **env):
    """Reimporta app.py apuntando a otro directorio de modelos."""
    monkeypatch.setenv('MODEL_DIR', str(model_dir))
    monkeypatch.setenv('MODEL_PATH', str(model_dir / 'heart-disease-v1.joblib'))
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
    for v in ('25', '50', '100'):
        shutil.copyfile(ROOT / f'model/heart-disease-{v}.joblib',
                        tmp_path / f'heart-disease-{v}.joblib')
        shutil.copyfile(ROOT / f'model/metrics-{v}.json',
                        tmp_path / f'metrics-{v}.json')
    module = load_app(monkeypatch, tmp_path)
    assert sorted(module.MODELS, key=int) == ['25', '50', '100']
    assert module.DEFAULT_VERSION == '100'


def test_ignora_el_artefacto_de_compatibilidad_v1(monkeypatch, tmp_path):
    """heart-disease-v1.joblib es una copia: no debe aparecer como version extra."""
    for v in ('25', '50', '100'):
        shutil.copyfile(ROOT / f'model/heart-disease-{v}.joblib',
                        tmp_path / f'heart-disease-{v}.joblib')
    shutil.copyfile(ROOT / 'model/heart-disease-v1.joblib',
                    tmp_path / 'heart-disease-v1.joblib')
    module = load_app(monkeypatch, tmp_path)
    assert 'v1' not in module.MODELS
    assert len(module.MODELS) == 3


def test_respaldo_con_un_unico_artefacto_sin_version(monkeypatch, tmp_path):
    """Despliegue antiguo: solo heart-disease-v1.joblib. La API sigue sirviendo."""
    shutil.copyfile(ROOT / 'model/heart-disease-v1.joblib',
                    tmp_path / 'heart-disease-v1.joblib')
    module = load_app(monkeypatch, tmp_path)
    assert list(module.MODELS) == ['default']
    client = TestClient(module.app)
    body = client.post('/score', json={}).json()
    assert body['version'] == 'default'
    assert 0.0 <= body['score'] <= 1.0


def test_default_version_configurable(monkeypatch, tmp_path):
    for v in ('25', '50', '100'):
        shutil.copyfile(ROOT / f'model/heart-disease-{v}.joblib',
                        tmp_path / f'heart-disease-{v}.joblib')
    module = load_app(monkeypatch, tmp_path, DEFAULT_MODEL_VERSION='25')
    assert module.DEFAULT_VERSION == '25'
    assert TestClient(module.app).post('/score', json={}).json()['version'] == '25'


def test_sin_modelos_falla_con_mensaje_claro(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match='No se encontro ningun modelo'):
        load_app(monkeypatch, tmp_path)
