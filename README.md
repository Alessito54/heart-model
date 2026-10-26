# heart-model — Reentrenamiento de un modelo de ML con GitHub Actions

Práctica de MLOps: un clasificador de enfermedad cardíaca servido con FastAPI,
reentrenado desde GitHub Actions mediante `repository_dispatch`, empaquetado en
Docker, publicado en Docker Hub y consumido desde un frontend React.

```
data/heart-disease.csv ──► model/train.py ──► model/heart-disease-v1.joblib
                                                      │
                                      Dockerfile ─────┤
                                                      ▼
                        Docker Hub  ──►  Render (API)  ◄──  frontend/ (React)
```

## Estructura

| Ruta | Contenido |
|---|---|
| `app.py` | API FastAPI: `GET /`, `GET /health`, `POST /score` |
| `model/train.py` | Entrenamiento de **una** versión del `RandomForestClassifier` |
| `scripts/train_all_versions.py` | Entrena las tres versiones (25/50/100) |
| `model/heart-disease-{25,50,100}.joblib` | Un artefacto por versión |
| `model/metrics-{25,50,100}.json` | Métricas de cada versión |
| `model/heart-disease-v1.joblib` | Copia de la versión por defecto (compatibilidad) |
| `data/heart-disease.csv` | Dataset base (1025 registros, 13 variables + `target`) |
| `scripts/make_datasets.py` | Genera las versiones al 25 %, 50 % y 100 % |
| `scripts/test_model_curl.sh` | Pruebas del modelo desplegado con cURL |
| `tests/test_app.py` | Pruebas del backend (pytest) |
| `postman/` | Colección y entorno de Postman |
| `specs/heart-model.openapi.json` | Especificación OpenAPI exportada |
| `frontend/` | Frontend React + Vite |
| `.github/workflows/ml_ci_cd.yml` | Pipeline CI/CD |
| `render.yaml` | Blueprint de despliegue en Render |

## Contrato de la API

El backend carga **las tres versiones del modelo** a la vez y las sirve desde el
mismo despliegue.

### `GET /models`

```json
[
  {"version":"25","path":"model/heart-disease-25.joblib","is_default":false,
   "n_rows":256,"accuracy":0.8846,"roc_auc":0.9289,"dataset":"data/versions/heart-disease_25.csv"},
  {"version":"50", "...": "..."},
  {"version":"100","is_default":true, "...": "..."}
]
```

### `POST /score` y `POST /score?version=25|50|100`

```json
{"age":64,"sex":1,"cp":3,"trestbps":120,"chol":267,"fbs":0,"restecg":0,
 "thalach":99,"exang":1,"oldpeak":1.8,"slope":1,"ca":2,"thal":2}
```

Respuesta:

```json
{"score": 0.3423109827696645, "version": "100"}
```

Sin el parámetro `version` se usa la versión por defecto
(`DEFAULT_MODEL_VERSION`, `100` si no se define). Una versión no cargada
devuelve `404`; valores fuera de los rangos declarados, `422`.

El mismo paciente contra las tres versiones:

| Versión | Registros de entrenamiento | `score` |
|---|---|---|
| 25 % | 256 | 0.2990207072002889 |
| 50 % | 512 | 0.4450901281006757 |
| 100 % | 1025 | 0.3423109827696645 |

`score` es `predict_proba` de la clase 1 (presencia de enfermedad): la proporción
de árboles del bosque que votan por esa clase. **No es un riesgo clínico
calibrado ni un porcentaje de riesgo.** Las diferencias entre versiones provienen
solo del volumen de datos de entrenamiento.

`GET /health` devuelve `{"status","model_loaded","model_path","model_versions",
"default_version","features"}`. Documentación interactiva en `/docs`.

## Ejecución local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

python scripts/make_datasets.py       # genera data/versions/*.csv
python scripts/train_all_versions.py  # entrena las 3 versiones del modelo
pytest tests/ -q                      # pruebas del backend
uvicorn app:app --reload --port 8000 # API en http://localhost:8000/docs
```

Con Docker:

```bash
docker build -t heart-model:local .
docker run --rm -p 8000:80 heart-model:local
./scripts/test_model_curl.sh http://localhost:8000
```

Frontend:

```bash
cd frontend
cp .env.example .env     # ajustar VITE_API_URL
npm install
npm run dev              # http://localhost:5173
npm run build            # genera frontend/dist
```

`VITE_API_URL` se incrusta en **tiempo de compilación**: tras cambiarla hay que
reconstruir.

El frontend consulta `GET /models` al cargar y muestra un selector con las
versiones que el backend realmente sirve, además de un modo «comparar» que envía
el mismo paciente a las tres y muestra los resultados en una tabla.

## Pipeline de GitHub Actions

`.github/workflows/ml_ci_cd.yml` se dispara con `push` y `pull_request` sobre
`main`, y con `repository_dispatch` de tipo `ml_ci_cd`. Tiene dos trabajos:

1. **`train`** — instala dependencias, prepara los tres datasets, ejecuta
   `scripts/train_all_versions.py` (que llama a `model/train.py` una vez por
   versión, escribiendo artefactos con nombres distintos), corre las pruebas y
   sube los tres modelos como artefacto. No accede a ningún secreto.
2. **`publish`** — descarga los artefactos, construye **una imagen que contiene
   las tres versiones**, hace un *smoke test* que pide una predicción a cada una
   y falla si las tres devuelven el mismo `score` (señal de que los artefactos se
   sobrescribieron), inicia sesión en Docker Hub y publica.
   Se omite en `pull_request` (`if: github.event_name != 'pull_request'`), de
   modo que un PR no confiable nunca obtiene acceso a los secretos.

### De dónde salen los tres datasets

El paso «preparar datasets» resuelve la fuente en este orden:

| Caso | `client_payload` | Comportamiento |
|---|---|---|
| 1 | `dataseturl_25`, `dataseturl_50`, `dataseturl_100` | Descarga las tres (deben estar las tres; si faltan, error) |
| 2 | `dataseturl` | Descarga el dataset completo y **deriva** los subconjuntos con muestreo estratificado |
| 3 | *(ninguno)* | Usa `data/heart-disease.csv` del repositorio y deriva los subconjuntos |

Solo se aceptan URLs `https`. La URL nunca se imprime en los registros (puede
llevar un token de Firebase).

Etiqueta de la imagen: `client_payload.sha` si se recibe, y `github.sha` en caso
contrario. La etiqueta se valida contra el formato permitido por Docker antes de
usarse. Cada dispatch produce una etiqueta distinta, así que **las imágenes no se
sobrescriben entre sí**; dentro de cada imagen, los tres modelos viven en
archivos con nombres distintos y cada `metrics-<version>.json` registra de qué
dataset salió.

### Secretos requeridos

En *Settings → Secrets and variables → Actions*:

| Secreto | Valor |
|---|---|
| `DOCKER_USER` | Usuario de Docker Hub |
| `DOCKER_PASSWORD` | Token de acceso de Docker Hub |
| `MODEL_NAME` | Nombre del repositorio de la imagen, p. ej. `heart-model` |

El login usa `--password-stdin`, por lo que la credencial no aparece en la línea
de comandos ni en los registros.

### Disparar el workflow

Hace falta un *personal access token* clásico con ámbito `workflow`.

```bash
curl -X POST https://api.github.com/repos/Alessito54/heart-model/dispatches \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{
        "event_type": "ml_ci_cd",
        "client_payload": {
          "dataseturl_25":  "https://.../heart-disease_25.csv",
          "dataseturl_50":  "https://.../heart-disease_50.csv",
          "dataseturl_100": "https://.../heart-disease_100.csv",
          "sha": "heart-disease-all"
        }
      }'
```

Respuesta esperada: `204 No Content`.

Desde Postman: importar `postman/heart-model.postman_collection.json` y
`postman/heart-model.postman_environment.json`, rellenar `github_token`
(variable de tipo *secret*) y las tres `dataset_url_*`.

## Versiones del dataset (25 % / 50 % / 100 %)

```bash
python scripts/make_datasets.py
```

Genera en `data/versions/`:

| Archivo | Registros | Proporción de `target` |
|---|---|---|
| `heart-disease_25.csv` | 256 | 0: 48.83 % · 1: 51.17 % |
| `heart-disease_50.csv` | 512 | 0: 48.63 % · 1: 51.37 % |
| `heart-disease_100.csv` | 1025 | 0: 48.68 % · 1: 51.32 % |

El muestreo es estratificado sobre `target` (`random_state=42`, reproducible) y
conserva encabezado, columnas y tipos. `data/versions/` está en `.gitignore`:
los archivos se regeneran con el script y se suben al almacenamiento externo.

### Subirlos a Firebase Storage

1. Crear un proyecto en <https://console.firebase.google.com> y activar *Storage*.
2. Subir los tres CSV desde la consola web (*Storage → Upload file*).
3. En cada archivo, copiar la **URL de descarga** (incluye `?alt=media&token=…`).
4. Pegar esas URLs en las variables `dataset_url_25/50/100` del entorno de
   Postman, o pasarlas en `client_payload.dataseturl`.

Si se automatiza la subida, las credenciales del servicio deben ir en variables
de entorno o GitHub Secrets. **Nunca se comete un archivo de credenciales al
repositorio.** La URL de descarga de Firebase contiene un token: trátala como
secreto y no la publiques en capturas o registros.

Cloudinary (alternativa mencionada en la práctica) sirve igual: subir como
*raw* y usar la URL resultante.

## Despliegue en Render

### Modo A (recomendado) — un servicio para las tres versiones

La imagen publicada contiene los tres modelos, así que basta **un** servicio.

**Backend** — *New → Web Service → Deploy an existing image*:

- Imagen: `docker.io/<DOCKER_USER>/<MODEL_NAME>:<TAG>`
- Health check path: `/health`
- Variable opcional: `DEFAULT_MODEL_VERSION` (`100` por defecto)

**Frontend** — *New → Static Site*:

- Root directory: `frontend`
- Build command: `npm ci && npm run build`
- Publish directory: `dist`
- Variable de entorno: `VITE_API_URL` = URL pública del backend

El frontend llama a `GET /models` al cargar y construye el selector con lo que
el backend diga que sirve. No hay nada más que configurar para las tres
versiones.

### Modo B — un servicio por versión

Si prefieres un despliegue por etiqueta de imagen (tres dispatches con `sha`
distintos), crea tres Web Services y define en el frontend:

```
VITE_API_URL_25=https://heart-model-25.onrender.com
VITE_API_URL_50=https://heart-model-50.onrender.com
VITE_API_URL_100=https://heart-model-100.onrender.com
```

Si alguna de esas tres variables está definida, el frontend enruta cada versión
a su propio servicio y deja de enviar `?version=`. `VITE_API_URL` se ignora.

El contenedor escucha en `$PORT` (y en el 80 si no se define), que es lo que
Render inyecta. `render.yaml` contiene el modo A como *blueprint*.

## Pruebas del modelo con cURL

```bash
./scripts/test_model_curl.sh https://<tu-servicio>.onrender.com
```

Envía el mismo payload de referencia a las tres versiones, imprime las tres
salidas, comprueba que no son idénticas y verifica los códigos `404` (versión
inexistente) y `422` (datos inválidos).

## Limitaciones del modelo

El conjunto UCI Heart Disease es pequeño (303 pacientes originales, ampliados a
1025 por remuestreo: hay 723 filas duplicadas), antiguo y no representativo de
la población general. El bosque se entrena con 10 árboles y profundidad máxima
2, y no está calibrado. Este proyecto es una demostración de un flujo de MLOps,
no una herramienta de diagnóstico.
