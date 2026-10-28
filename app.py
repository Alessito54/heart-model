"""API de inferencia del modelo de incidencia delictiva estatal.

Sirve las versiones entrenadas con el 25 %, 50 % y 100 % del dataset del SESNSP
y expone un endpoint de reentrenamiento que dispara el workflow de GitHub
Actions, el cual publica una imagen de Docker nueva por cada reentrenamiento.
"""
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from urllib.parse import urlparse
import datetime as dt
import json
import os
import pathlib
import re
import secrets

import numpy as np
import pandas as pd
import requests
from joblib import load

from model.schema import FEATURES, HIERARCHY, LABEL, MESES, MES_A_NUMERO

origins = ["*"]

app = FastAPI(
    title='Incidencia Delictiva Estatal',
    description=(
        'API de inferencia del modelo de incidencia delictiva estatal (SESNSP, '
        '2015-2025). Predice el numero de carpetas de investigacion abiertas en '
        'un estado, un mes y una modalidad de delito. Sirve las versiones '
        'entrenadas con el 25 %, 50 % y 100 % del dataset, y permite reentrenar: '
        'cada reentrenamiento publica una imagen de Docker nueva.'
    ),
    version='3.0.0',
)

app.add_middleware(
   CORSMiddleware,
   allow_origins=origins,
   allow_credentials=True,
   allow_methods=["*"],
   allow_headers=["*"]
)

MODEL_DIR = pathlib.Path(os.getenv('MODEL_DIR', 'model'))
# Ruta de respaldo, usada si no hay artefactos versionados.
MODEL_PATH = pathlib.Path(os.getenv('MODEL_PATH', 'model/incidencia-v1.joblib'))
DEFAULT_VERSION = os.getenv('DEFAULT_MODEL_VERSION', '100')

# Solo se exponen versiones numericas (25/50/100). incidencia-v1.joblib es una
# copia de la version por defecto y queda fuera del registro para no duplicarla.
VERSION_PATTERN = re.compile(r'^incidencia-(\d+)\.joblib$')

# --- Reentrenamiento ------------------------------------------------------
# El reentrenamiento no ocurre dentro de este contenedor: se delega al workflow
# de GitHub Actions, que entrena las tres versiones, construye la imagen y la
# publica etiquetada con la etiqueta que se envia aqui. Asi cada reentrenamiento
# produce una imagen de Docker nueva e inmutable.
GITHUB_API = os.getenv('GITHUB_API', 'https://api.github.com')
GITHUB_REPOSITORY = os.getenv('GITHUB_REPOSITORY', '')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')
DISPATCH_TYPE = os.getenv('GITHUB_DISPATCH_TYPE', 'ml_ci_cd')
WORKFLOW_FILE = os.getenv('GITHUB_WORKFLOW_FILE', 'ml_ci_cd.yml')
# Token que debe presentar el cliente para poder reentrenar. Si no se define,
# el endpoint queda deshabilitado: un endpoint abierto permitiria a cualquiera
# lanzar construcciones de imagenes.
RETRAIN_TOKEN = os.getenv('RETRAIN_TOKEN', '')
# Hosts permitidos para las URL de dataset. Vacio = cualquier host https.
ALLOWED_HOSTS = [h.strip() for h in
                 os.getenv('RETRAIN_ALLOWED_HOSTS', 'res.cloudinary.com').split(',')
                 if h.strip()]


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
    """Registra todos los artefactos model/incidencia-<n>.joblib encontrados."""
    registry: Dict[str, dict] = {}
    for candidate in sorted(MODEL_DIR.glob('incidencia-*.joblib')):
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

    # Respaldo: despliegue con un unico artefacto sin version.
    if MODEL_PATH.exists():
        registry['default'] = {
            'version': 'default',
            'path': str(MODEL_PATH),
            'model': load(MODEL_PATH),
            'metrics': None,
        }
    return registry


def _load_catalog() -> dict:
    """Valores validos de cada campo, escritos por model/train.py."""
    path = MODEL_DIR / 'catalog.json'
    if not path.exists():
        raise RuntimeError(
            f'No se encontro el catalogo en {path}. '
            'Ejecuta: python scripts/train_all_versions.py'
        )
    return json.loads(path.read_text())


MODELS = _discover_models()
if not MODELS:
    raise RuntimeError(
        f'No se encontro ningun modelo en {MODEL_DIR}. '
        'Ejecuta: python scripts/train_all_versions.py'
    )

CATALOG = _load_catalog()
ENTIDAD_POR_CLAVE = {e['clave_ent']: e['entidad'] for e in CATALOG['entidades']}
CLAVE_POR_ENTIDAD = {e['entidad']: e['clave_ent'] for e in CATALOG['entidades']}

# Version servida cuando la peticion no indica ninguna.
if DEFAULT_VERSION not in MODELS:
    DEFAULT_VERSION = _sorted_versions()[-1]


# --- Modelos de datos ----------------------------------------------------

class InputData(BaseModel):
    anio: int = Field(2025, ge=1990, le=2100,
                      description='Anio del periodo (el dataset cubre 2015-2025)')
    mes: int = Field(6, ge=1, le=12, description='Mes del periodo (1 = Enero)')
    clave_ent: Optional[int] = Field(
        9, ge=1, le=32,
        description='Clave de la entidad federativa (1-32). Alternativa a "entidad".')
    entidad: Optional[str] = Field(
        None, description='Nombre de la entidad federativa. Alternativa a "clave_ent".')
    bien_juridico_afectado: str = Field(
        'El patrimonio', description='Bien juridico afectado')
    tipo_delito: str = Field('Robo', description='Tipo de delito')
    subtipo_delito: str = Field('Robo de vehículo automotor', description='Subtipo de delito')
    modalidad: str = Field('Robo de coche de 4 ruedas Con violencia',
                           description='Modalidad del delito')

    class Config:
        schema_extra = {
            'example': {
                'anio': 2025, 'mes': 6, 'clave_ent': 9,
                'bien_juridico_afectado': 'El patrimonio',
                'tipo_delito': 'Robo',
                'subtipo_delito': 'Robo de vehículo automotor',
                'modalidad': 'Robo de coche de 4 ruedas Con violencia',
            }
        }


class OutputData(BaseModel):
    prediccion: float = Field(..., description='Carpetas de investigacion estimadas')
    prediccion_redondeada: int = Field(..., description='La prediccion redondeada a entero')
    version: str = Field(..., description='Version del modelo que respondio')
    label: str = Field(LABEL, description='Variable predicha')
    entidad: str = Field(..., description='Entidad resuelta')
    periodo: str = Field(..., description='Periodo consultado, como "Junio 2025"')


class ModelInfo(BaseModel):
    version: str
    path: str
    is_default: bool
    n_rows: Optional[int] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    r2: Optional[float] = None
    baseline_mae: Optional[float] = None
    dataset: Optional[str] = None


class RetrainRequest(BaseModel):
    """Datasets con los que reentrenar. Se esperan URL de Cloudinary (https).

    Hay dos modos:
      - las tres versiones ya preparadas: dataseturl_25 + _50 + _100
      - un unico dataset completo: dataseturl (los subconjuntos se derivan en CI)
    Si no se envia ninguna URL, el workflow reentrena con el dataset del repositorio.
    """
    dataseturl: Optional[str] = Field(None, description='URL del dataset completo')
    dataseturl_25: Optional[str] = Field(None, description='URL del dataset al 25 %')
    dataseturl_50: Optional[str] = Field(None, description='URL del dataset al 50 %')
    dataseturl_100: Optional[str] = Field(None, description='URL del dataset al 100 %')
    tag: Optional[str] = Field(
        None, description='Etiqueta de la imagen Docker. Si se omite, se genera una.')
    nota: Optional[str] = Field(None, max_length=200,
                                description='Nota libre para identificar la corrida')


class RetrainResponse(BaseModel):
    dispatched: bool
    tag: str
    repository: str
    dispatch_type: str
    datasets: List[str]
    actions_url: str
    mensaje: str


# --- Utilidades ----------------------------------------------------------

def _model_info(entry: dict) -> ModelInfo:
    metrics = entry['metrics'] or {}
    return ModelInfo(
        version=entry['version'],
        path=entry['path'],
        is_default=entry['version'] == DEFAULT_VERSION,
        n_rows=metrics.get('n_rows'),
        mae=metrics.get('mae'),
        rmse=metrics.get('rmse'),
        r2=metrics.get('r2'),
        baseline_mae=metrics.get('baseline_mae'),
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


def _resolve_entidad(data: InputData) -> tuple[int, str]:
    """Acepta clave_ent o el nombre de la entidad y devuelve ambos.

    'entidad' tiene prioridad: clave_ent lleva un valor por defecto para que el
    ejemplo de /docs funcione sin editarlo, asi que un nombre explicito debe
    poder ganarle.
    """
    if data.entidad:
        if data.entidad not in CLAVE_POR_ENTIDAD:
            raise HTTPException(
                status_code=422,
                detail=(f"La entidad '{data.entidad}' no existe en el catalogo. "
                        'Consulta GET /catalog para los nombres validos.'))
        return CLAVE_POR_ENTIDAD[data.entidad], data.entidad
    if data.clave_ent is not None:
        if data.clave_ent not in ENTIDAD_POR_CLAVE:
            raise HTTPException(
                status_code=422,
                detail=f'clave_ent {data.clave_ent} no existe en el catalogo.')
        return data.clave_ent, ENTIDAD_POR_CLAVE[data.clave_ent]
    raise HTTPException(
        status_code=422,
        detail='Indica "clave_ent" (1-32) o "entidad" (nombre del estado).')


def _validate_hierarchy(data: InputData) -> None:
    """Comprueba que la cadena bien -> tipo -> subtipo -> modalidad exista."""
    nivel = CATALOG['jerarquia']
    recorrido = [data.bien_juridico_afectado, data.tipo_delito,
                 data.subtipo_delito, data.modalidad]
    for i, valor in enumerate(recorrido):
        campo = HIERARCHY[i]
        if isinstance(nivel, dict):
            opciones = list(nivel)
        else:  # ultimo nivel: lista de modalidades
            opciones = list(nivel)
        if valor not in opciones:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"El valor '{valor}' no es valido para '{campo}' con la "
                    f'seleccion anterior. Opciones validas: {sorted(opciones)[:15]}'
                    f"{' ...' if len(opciones) > 15 else ''}. "
                    'Consulta GET /catalog para la jerarquia completa.'
                ),
            )
        if isinstance(nivel, dict):
            nivel = nivel[valor]


def _require_retrain_auth(token: Optional[str]) -> None:
    if not RETRAIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail=(
                'El reentrenamiento no esta configurado en este despliegue. '
                'Define las variables de entorno RETRAIN_TOKEN, GITHUB_TOKEN y '
                'GITHUB_REPOSITORY en el servicio.'
            ),
        )
    # compare_digest evita filtrar la longitud del token por tiempo de respuesta.
    if not token or not secrets.compare_digest(token, RETRAIN_TOKEN):
        raise HTTPException(
            status_code=401,
            detail='Falta la cabecera X-Retrain-Token o su valor es incorrecto.')


def _validate_dataset_url(url: str, campo: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise HTTPException(
            status_code=422,
            detail=f'{campo} debe ser una URL https (se recibio "{parsed.scheme}").')
    if ALLOWED_HOSTS and parsed.netloc not in ALLOWED_HOSTS:
        raise HTTPException(
            status_code=422,
            detail=(f'{campo} apunta a "{parsed.netloc}", que no esta en la lista '
                    f'de hosts permitidos: {ALLOWED_HOSTS}. Ajusta '
                    'RETRAIN_ALLOWED_HOSTS si usas otro proveedor.'))
    return url


# --- Endpoints -----------------------------------------------------------

@app.get('/')
def root():
    return {
        'service': 'Incidencia Delictiva Estatal',
        'version': app.version,
        'docs': '/docs',
        'endpoints': ['/predict', '/models', '/catalog', '/health', '/retrain'],
        'label': LABEL,
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
        'label': LABEL,
        'retrain_enabled': bool(RETRAIN_TOKEN and GITHUB_TOKEN and GITHUB_REPOSITORY),
    }


@app.get('/catalog')
def catalog():
    """Valores validos de cada campo, con la jerarquia del delito anidada.

    El frontend lo usa para poblar listas desplegables encadenadas, de modo que
    no se pueda enviar una combinacion de delito inexistente.
    """
    return CATALOG


@app.get('/models', response_model=List[ModelInfo])
def models():
    """Versiones del modelo disponibles en este despliegue, con sus metricas."""
    return [_model_info(MODELS[v]) for v in _sorted_versions()]


@app.post('/predict', response_model=OutputData)
def predict(
    data: InputData,
    version: Optional[str] = Query(
        None,
        description=('Version del modelo a usar (25, 50 o 100). '
                     'Si se omite se usa la version por defecto.'),
    ),
):
    """Estima las carpetas de investigacion de un estado, mes y delito."""
    entry = _resolve(version)
    clave_ent, entidad = _resolve_entidad(data)
    _validate_hierarchy(data)

    fila = {
        'anio': data.anio,
        'mes': data.mes,
        'clave_ent': clave_ent,
        'bien_juridico_afectado': data.bien_juridico_afectado,
        'tipo_delito': data.tipo_delito,
        'subtipo_delito': data.subtipo_delito,
        'modalidad': data.modalidad,
    }
    model_input = pd.DataFrame([[fila[f] for f in FEATURES]], columns=FEATURES)

    try:
        crudo = entry['model'].predict(model_input)
    except Exception as exc:  # modelo incompatible con la entrada
        raise HTTPException(
            status_code=500,
            detail=f'No fue posible calcular la prediccion: {exc}',
        )

    # Mismo recorte que en el entrenamiento: un conteo negativo no existe.
    valor = float(np.clip(crudo, 0, None)[0])
    return {
        'prediccion': valor,
        'prediccion_redondeada': int(round(valor)),
        'version': entry['version'],
        'label': LABEL,
        'entidad': entidad,
        'periodo': f'{MESES[data.mes - 1]} {data.anio}',
    }


@app.post('/retrain', response_model=RetrainResponse)
def retrain(
    body: RetrainRequest,
    x_retrain_token: Optional[str] = Header(None, alias='X-Retrain-Token'),
):
    """Lanza un reentrenamiento que publica una imagen de Docker nueva.

    No entrena dentro de este contenedor: dispara el workflow de GitHub Actions
    (repository_dispatch), que reentrena las tres versiones del modelo,
    construye la imagen y la publica etiquetada con "tag". Cada reentrenamiento
    produce por tanto una imagen distinta e inmutable.
    """
    _require_retrain_auth(x_retrain_token)
    if not (GITHUB_TOKEN and GITHUB_REPOSITORY):
        raise HTTPException(
            status_code=503,
            detail=('Faltan GITHUB_TOKEN o GITHUB_REPOSITORY en el entorno del '
                    'servicio, asi que no se puede disparar el workflow.'))

    por_version = {k: getattr(body, f'dataseturl_{k}') for k in ('25', '50', '100')}
    definidas = {k: v for k, v in por_version.items() if v}
    if definidas and len(definidas) != 3:
        raise HTTPException(
            status_code=422,
            detail=(f'Se recibieron {len(definidas)} de 3 URL por version '
                    f'({sorted(definidas)}). Envia dataseturl_25, dataseturl_50 y '
                    'dataseturl_100, o solo dataseturl.'))
    if definidas and body.dataseturl:
        raise HTTPException(
            status_code=422,
            detail='Envia dataseturl o las tres URL por version, no ambas cosas.')

    payload: Dict[str, str] = {}
    usados: List[str] = []
    for clave, url in definidas.items():
        payload[f'dataseturl_{clave}'] = _validate_dataset_url(url, f'dataseturl_{clave}')
        usados.append(f'{clave} %')
    if body.dataseturl:
        payload['dataseturl'] = _validate_dataset_url(body.dataseturl, 'dataseturl')
        usados.append('dataset completo')
    if not usados:
        usados.append('dataset del repositorio')

    # La etiqueta viaja como client_payload.sha y es la que lleva la imagen.
    tag = body.tag or f"retrain-{dt.datetime.now(dt.timezone.utc):%Y%m%d-%H%M%S}"
    if not re.match(r'^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$', tag):
        raise HTTPException(
            status_code=422,
            detail=('"tag" no es una etiqueta Docker valida: usa letras, numeros, '
                    'punto, guion y guion bajo (max 128 caracteres).'))
    payload['sha'] = tag
    if body.nota:
        payload['nota'] = body.nota

    url = f'{GITHUB_API}/repos/{GITHUB_REPOSITORY}/dispatches'
    try:
        response = requests.post(
            url,
            json={'event_type': DISPATCH_TYPE, 'client_payload': payload},
            headers={
                'Accept': 'application/vnd.github+json',
                'Authorization': f'Bearer {GITHUB_TOKEN}',
                'X-GitHub-Api-Version': '2022-11-28',
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f'No se pudo contactar con la API de GitHub: {exc}')

    if response.status_code == 204:
        return {
            'dispatched': True,
            'tag': tag,
            'repository': GITHUB_REPOSITORY,
            'dispatch_type': DISPATCH_TYPE,
            'datasets': usados,
            'actions_url': (f'https://github.com/{GITHUB_REPOSITORY}'
                            f'/actions/workflows/{WORKFLOW_FILE}'),
            'mensaje': (
                f'Reentrenamiento lanzado. Cuando el workflow termine habra una '
                f'imagen nueva etiquetada "{tag}". Apunta el servicio de Render a '
                f'esa etiqueta para servirla.'
            ),
        }

    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=502,
            detail=('GitHub rechazo las credenciales. El GITHUB_TOKEN necesita '
                    'permiso de escritura en "contents" del repositorio.'))
    if response.status_code == 404:
        raise HTTPException(
            status_code=502,
            detail=(f'GitHub devolvio 404 para el repositorio "{GITHUB_REPOSITORY}". '
                    'Revisa el nombre (formato owner/repo) y el alcance del token.'))
    raise HTTPException(
        status_code=502,
        detail=f'GitHub respondio {response.status_code}: {response.text[:300]}')


@app.get('/retrain/status')
def retrain_status(
    x_retrain_token: Optional[str] = Header(None, alias='X-Retrain-Token'),
    limit: int = Query(5, ge=1, le=20),
):
    """Ultimas corridas del workflow de reentrenamiento, con su etiqueta."""
    _require_retrain_auth(x_retrain_token)
    if not (GITHUB_TOKEN and GITHUB_REPOSITORY):
        raise HTTPException(status_code=503,
                            detail='Faltan GITHUB_TOKEN o GITHUB_REPOSITORY.')

    url = (f'{GITHUB_API}/repos/{GITHUB_REPOSITORY}/actions/workflows/'
           f'{WORKFLOW_FILE}/runs')
    try:
        response = requests.get(
            url,
            params={'per_page': limit},
            headers={
                'Accept': 'application/vnd.github+json',
                'Authorization': f'Bearer {GITHUB_TOKEN}',
                'X-GitHub-Api-Version': '2022-11-28',
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502,
                            detail=f'No se pudo contactar con la API de GitHub: {exc}')
    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail=f'GitHub respondio {response.status_code}: {response.text[:300]}')

    runs = response.json().get('workflow_runs', [])
    return {
        'repository': GITHUB_REPOSITORY,
        'runs': [
            {
                'id': r.get('id'),
                'status': r.get('status'),
                'conclusion': r.get('conclusion'),
                'event': r.get('event'),
                'created_at': r.get('created_at'),
                'updated_at': r.get('updated_at'),
                'url': r.get('html_url'),
            }
            for r in runs
        ],
    }
