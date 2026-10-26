from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import pandas as pd
from joblib import load
import pathlib
import json
import os
import re

origins = ["*"]

app = FastAPI(
    title='Heart Disease Prediction',
    description=(
        'API de inferencia del modelo de prediccion de enfermedad cardiaca. '
        'Sirve las versiones entrenadas con el 25 %, 50 % y 100 % del dataset.'
    ),
    version='2.0.0',
)

app.add_middleware(
   CORSMiddleware,
   allow_origins=origins,
   allow_credentials=True,
   allow_methods=["*"],
   allow_headers=["*"]
)

MODEL_DIR = pathlib.Path(os.getenv('MODEL_DIR', 'model'))
# Ruta historica, usada como respaldo si no hay artefactos versionados.
MODEL_PATH = pathlib.Path(os.getenv('MODEL_PATH', 'model/heart-disease-v1.joblib'))
DEFAULT_VERSION = os.getenv('DEFAULT_MODEL_VERSION', '100')

# Orden exacto de las columnas con las que se entreno el modelo (data/heart-disease.csv
# sin la columna 'target'). No cambiar: predict_proba depende de este orden.
FEATURES = ['age', 'sex', 'cp', 'trestbps', 'chol', 'fbs', 'restecg',
            'thalach', 'exang', 'oldpeak', 'slope', 'ca', 'thal']

# Solo se exponen versiones numericas (25/50/100). heart-disease-v1.joblib es una
# copia de la version por defecto y queda fuera del registro para no duplicarla.
VERSION_PATTERN = re.compile(r'^heart-disease-(\d+)\.joblib$')


def _sorted_versions() -> List[str]:
    """Ordena 25 < 50 < 100 (numericamente, no alfabeticamente)."""
    return sorted(MODELS, key=lambda v: (not v.isdigit(), int(v) if v.isdigit() else v))


def _load_metrics(version: str) -> Optional[dict]:
    path = MODEL_DIR / f'metrics-{version}.json'
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _discover_models() -> Dict[str, dict]:
    """Registra todos los artefactos model/heart-disease-<n>.joblib encontrados."""
    registry: Dict[str, dict] = {}
    for candidate in sorted(MODEL_DIR.glob('heart-disease-*.joblib')):
        match = VERSION_PATTERN.match(candidate.name)
        if not match:
            continue
        version = match.group(1)
        registry[version] = {
            'version': version,
            'path': str(candidate),
            'model': load(candidate),
            'metrics': _load_metrics(version),
        }

    if registry:
        return registry

    # Respaldo: despliegue antiguo con un unico artefacto sin version.
    if MODEL_PATH.exists():
        registry['default'] = {
            'version': 'default',
            'path': str(MODEL_PATH),
            'model': load(MODEL_PATH),
            'metrics': None,
        }
    return registry


MODELS = _discover_models()
if not MODELS:
    raise RuntimeError(
        f'No se encontro ningun modelo en {MODEL_DIR}. '
        'Ejecuta: python scripts/train_all_versions.py'
    )

# Version servida cuando la peticion no indica ninguna.
if DEFAULT_VERSION not in MODELS:
    DEFAULT_VERSION = _sorted_versions()[-1]


class InputData(BaseModel):
    age:int=Field(64, ge=1, le=120, description='Edad en anios')
    sex:int=Field(1, ge=0, le=1, description='0 = mujer, 1 = hombre')
    cp:int=Field(3, ge=0, le=3, description='Tipo de dolor toracico (0-3)')
    trestbps:int=Field(120, ge=50, le=250, description='Presion arterial en reposo (mm Hg)')
    chol:int=Field(267, ge=100, le=700, description='Colesterol serico (mg/dl)')
    fbs:int=Field(0, ge=0, le=1, description='Glucosa en ayunas > 120 mg/dl (0/1)')
    restecg:int=Field(0, ge=0, le=2, description='Electrocardiograma en reposo (0-2)')
    thalach:int=Field(99, ge=50, le=250, description='Frecuencia cardiaca maxima alcanzada (lpm)')
    exang:int=Field(1, ge=0, le=1, description='Angina inducida por ejercicio (0/1)')
    oldpeak:float=Field(1.8, ge=0.0, le=10.0, description='Depresion ST inducida por ejercicio')
    slope:int=Field(1, ge=0, le=2, description='Pendiente del segmento ST (0-2)')
    ca:int=Field(2, ge=0, le=4, description='Vasos principales coloreados por fluoroscopia (0-4)')
    thal:int=Field(2, ge=0, le=3, description='Talasemia (0-3)')

class OutputData(BaseModel):
    score:float=0.80318881046519
    version:str='100'

class ModelInfo(BaseModel):
    version:str
    path:str
    is_default:bool
    n_rows:Optional[int]=None
    accuracy:Optional[float]=None
    roc_auc:Optional[float]=None
    dataset:Optional[str]=None


def _model_info(entry: dict) -> ModelInfo:
    metrics = entry['metrics'] or {}
    return ModelInfo(
        version=entry['version'],
        path=entry['path'],
        is_default=entry['version'] == DEFAULT_VERSION,
        n_rows=metrics.get('n_rows'),
        accuracy=metrics.get('accuracy'),
        roc_auc=metrics.get('roc_auc'),
        dataset=metrics.get('dataset'),
    )


def _resolve(version: Optional[str]) -> dict:
    if version is None or version == '':
        return MODELS[DEFAULT_VERSION]
    if version not in MODELS:
        raise HTTPException(
            status_code=404,
            detail=(
                f"La version '{version}' no esta disponible en este despliegue. "
                f'Versiones cargadas: {_sorted_versions()}.'
            ),
        )
    return MODELS[version]


@app.get('/')
def root():
    return {
        'service': 'Heart Disease Prediction',
        'version': app.version,
        'docs': '/docs',
        'endpoints': ['/score', '/models', '/health'],
        'model_versions': _sorted_versions(),
        'default_version': DEFAULT_VERSION,
    }

@app.get('/health')
def health():
    return {
        'status': 'ok',
        'model_loaded': bool(MODELS),
        'model_path': MODELS[DEFAULT_VERSION]['path'],
        'model_versions': _sorted_versions(),
        'default_version': DEFAULT_VERSION,
        'features': FEATURES,
    }

@app.get('/models', response_model = List[ModelInfo])
def models():
    """Versiones del modelo disponibles en este despliegue, con sus metricas."""
    return [_model_info(MODELS[v]) for v in _sorted_versions()]

@app.post('/score', response_model = OutputData)
def score(
    data:InputData,
    version:Optional[str]=Query(
        None,
        description=(
            'Version del modelo a usar (25, 50 o 100). '
            'Si se omite se usa la version por defecto.'
        ),
    ),
):
    entry = _resolve(version)
    payload = data.dict()
    model_input = pd.DataFrame([[payload[f] for f in FEATURES]], columns=FEATURES)
    try:
        result = entry['model'].predict_proba(model_input)[:, -1]
    except Exception as exc:  # modelo incompatible con la entrada
        raise HTTPException(
            status_code=500,
            detail=f'No fue posible calcular la prediccion: {exc}',
        )

    return {'score': float(result[0]), 'version': entry['version']}
