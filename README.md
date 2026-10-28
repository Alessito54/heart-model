# incidencia-model — Reentrenamiento de un modelo de ML con GitHub Actions

Modelo de **incidencia delictiva estatal** servido con FastAPI, empaquetado en
Docker y reentrenable desde la propia interfaz: cada reentrenamiento publica una
imagen de Docker nueva.

El modelo estima `incidencia_delictiva`, el número de carpetas de investigación
abiertas en un estado, un mes y una modalidad de delito, a partir de los datos
abiertos del SESNSP (2015–2025, 413 952 registros).

Se entrenan y despliegan **tres versiones** del mismo modelo, con el 25 %, 50 %
y 100 % del dataset, para poder comparar el efecto del volumen de datos:

| Versión | Registros | MAE | RMSE | R² | MAE de referencia |
|--------:|----------:|----:|-----:|---:|------------------:|
|  25 %   |   103 488 | 12.53 | 48.91 | 0.9354 | 74.50 |
|  50 %   |   206 976 | 11.89 | 54.30 | 0.9351 | 76.80 |
| 100 %   |   413 952 | 10.61 | 39.36 | 0.9582 | 74.84 |

MAE y RMSE están en carpetas de investigación, así que son directamente
comparables entre versiones. El «MAE de referencia» es el que se obtendría
prediciendo siempre la media del dataset: el modelo del 100 % lo mejora en un
86 %.

## Estructura

```
app.py                       API de FastAPI (inferencia + reentrenamiento)
client.py                    cliente de ejemplo de POST /predict
Dockerfile                   imagen de la API
render.yaml                  blueprint de Render (backend + frontend)
model/
  schema.py                  esquema compartido por entrenamiento e inferencia
  train.py                   entrenamiento de una versión
  incidencia-{25,50,100}.joblib    los tres modelos
  metrics-{25,50,100}.json         métricas de cada versión
  catalog.json               valores válidos de cada campo (lo sirve GET /catalog)
data/
  catalogo_delitos.csv       98 filas: id_delito -> jerarquía del delito
  catalogo_entidades.csv     32 filas: clave_ent -> nombre del estado
  versions/                  datasets generados (no se versionan en git)
scripts/
  make_datasets.py           genera catálogos y las versiones 25/50/100
  train_all_versions.py      entrena las tres versiones de una pasada
  test_model_curl.sh         prueba la API desplegada con cURL
frontend/                    interfaz React + Vite
postman/                     colección y entorno de Postman
specs/                       especificación OpenAPI
tests/                       pruebas de la API y del registro de modelos
```

## El dataset y por qué está codificado

El CSV original del SESNSP pesa 47 MB con las categorías en texto, y Cloudinary
—donde se alojan los datasets para que el CI los descargue— limita los archivos
a 10 MB.

En lugar de recortar registros, los CSV se escriben con identificadores:

```
anio,mes,clave_ent,id_delito,incidencia_delictiva
2015,4,1,0,22
```

`id_delito` indexa las 98 combinaciones de la jerarquía del delito
(`bien_juridico_afectado` → `tipo_delito` → `subtipo_delito` → `modalidad`) y
`clave_ent` indexa los 32 estados. Las dos tablas de consulta viven en el
repositorio y pesan 9 KB entre las dos.

Así el dataset **completo** baja de 47 MB a 6.35 MB y las tres versiones entran
en el límite sin perder un solo registro:

| Versión | Registros | CSV |
|--------:|----------:|----:|
| 100 %   |   413 952 | 6.35 MB |
|  50 %   |   206 976 | 3.18 MB |
|  25 %   |   103 488 | 1.59 MB |

`model/train.py` reconstruye las categorías en texto antes de entrenar, y la API
publica el catálogo completo en `GET /catalog` para que el frontend arme sus
listas desplegables.

## Contrato de la API

### `GET /health`

Estado del servicio, versiones cargadas y si el reentrenamiento está habilitado.

### `GET /models`

Las tres versiones con sus métricas (`mae`, `rmse`, `r2`, `baseline_mae`,
`n_rows`) y la ruta de su artefacto.

### `GET /catalog`

Valores válidos de cada campo: los 32 estados, los 12 meses, el rango de años y
la jerarquía del delito anidada. El frontend lo usa para encadenar las listas
desplegables, de modo que no se pueda enviar una combinación inexistente.

### `POST /predict` y `POST /predict?version=25|50|100`

Entrada — los siete campos del modelo. `entidad` (nombre) y `clave_ent` (1–32)
son intercambiables; si se envían los dos, gana el nombre:

```json
{
  "anio": 2025,
  "mes": 6,
  "clave_ent": 9,
  "bien_juridico_afectado": "El patrimonio",
  "tipo_delito": "Robo",
  "subtipo_delito": "Robo de vehículo automotor",
  "modalidad": "Robo de coche de 4 ruedas Con violencia"
}
```

Salida:

```json
{
  "prediccion": 43.96539358178889,
  "prediccion_redondeada": 44,
  "version": "100",
  "label": "incidencia_delictiva",
  "entidad": "Ciudad de México",
  "periodo": "Junio 2025"
}
```

Sin `?version=` responde la versión por defecto (`DEFAULT_MODEL_VERSION`, 100 %).
Una versión que el despliegue no sirve devuelve **404**; una categoría
inexistente o una combinación de delito imposible devuelve **422** indicando el
campo.

### `POST /retrain` y `GET /retrain/status`

Lanzan y consultan el reentrenamiento. Ver la sección siguiente.

## Reentrenamiento: una imagen de Docker por reentrenamiento

El entrenamiento **no ocurre dentro del contenedor de la API**. `POST /retrain`
dispara el workflow de GitHub Actions (`repository_dispatch`), que:

1. descarga los tres datasets de Cloudinary,
2. entrena las versiones 25 %, 50 % y 100 %,
3. corre las pruebas,
4. construye la imagen y la publica en Docker Hub **con su propia etiqueta**,
   moviendo además `latest` a esa misma imagen.

De ahí que cada reentrenamiento produzca una imagen nueva e inmutable. La API
sigue sirviendo el modelo anterior hasta que se redespliegue con la imagen nueva
(automático si se define el secreto `RENDER_DEPLOY_HOOK`).

### Configuración

El endpoint está **cerrado por defecto**: sin `RETRAIN_TOKEN` responde 503. Si
estuviera abierto, cualquiera podría lanzar construcciones de imágenes. Para
habilitarlo, define en el servicio del backend:

| Variable | Qué es |
|---|---|
| `RETRAIN_TOKEN` | El token que el cliente envía en la cabecera `X-Retrain-Token`. Inventa uno largo. |
| `GITHUB_TOKEN` | PAT de GitHub con permiso de escritura en *contents* del repositorio. |
| `GITHUB_REPOSITORY` | El repositorio, en formato `usuario/repo`. |
| `RETRAIN_ALLOWED_HOSTS` | Hosts permitidos para las URL de dataset. Por defecto `res.cloudinary.com`. |

### Desde la interfaz

El panel «Reentrenar el modelo» pide el token, permite cambiar las URL de los
datasets y la etiqueta de la imagen, y enlaza la corrida en GitHub Actions. El
token se guarda solo en `sessionStorage`, nunca en una variable `VITE_*` (esas
quedan incrustadas en el JavaScript público).

### Desde la línea de comandos

```bash
curl -X POST https://<tu-api>.onrender.com/retrain \
  -H 'X-Retrain-Token: <RETRAIN_TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{
    "dataseturl_25":  "https://res.cloudinary.com/.../incidencia_25_....csv",
    "dataseturl_50":  "https://res.cloudinary.com/.../incidencia_50_....csv",
    "dataseturl_100": "https://res.cloudinary.com/.../incidencia_100_....csv",
    "nota": "datos de enero"
  }'
```

También se puede disparar el workflow directamente:

```bash
curl -X POST https://api.github.com/repos/<usuario>/<repo>/dispatches \
  -H 'Accept: application/vnd.github+json' \
  -H 'Authorization: Bearer <PAT>' \
  -d '{"event_type":"ml_ci_cd","client_payload":{"sha":"mi-etiqueta"}}'
```

## Ejecución local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 1. Generar catálogos y las tres versiones del dataset
#    (requiere data/INM_estatal_dic25.csv, el CSV original del SESNSP)
python scripts/make_datasets.py

# 2. Entrenar las tres versiones
python scripts/train_all_versions.py

# 3. Servir la API
uvicorn app:app --reload --port 8000

# 4. Probar
python client.py
./scripts/test_model_curl.sh
python -m pytest tests/ -q
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env     # VITE_API_URL=http://localhost:8000
npm run dev
```

Con Docker:

```bash
docker build -t incidencia-model .
docker run --rm -p 8000:80 incidencia-model
```

## Pipeline de GitHub Actions

`.github/workflows/ml_ci_cd.yml` tiene dos trabajos:

- **train** — se ejecuta en `push`, `pull_request` y `repository_dispatch`. No
  accede a ningún secreto, así que es seguro para PRs externos.
- **publish** — no se ejecuta en `pull_request`, de modo que un PR no confiable
  nunca obtiene acceso a los secretos de Docker Hub. Construye la imagen, le
  hace un *smoke test* (comprueba que las tres versiones responden y que no
  devuelven todas lo mismo, lo que delataría artefactos duplicados) y la publica.

### De dónde salen los datasets

| Caso | Qué llega | Qué hace el workflow |
|---|---|---|
| 1 | `client_payload.dataseturl` | Lo trata como el CSV original del SESNSP: regenera las tablas de consulta y las tres versiones. |
| 2 | `client_payload.dataseturl_25/_50/_100` | Descarga las tres versiones ya codificadas. |
| 3 | nada (push, PR) | Usa las URL de Cloudinary definidas en el bloque `env` del workflow. |

Las URL deben ser `https`. Si el archivo viene comprimido (`.csv.gz`), el
workflow lo descomprime solo.

### Secretos requeridos

| Secreto | Para qué |
|---|---|
| `DOCKER_USER` | Usuario de Docker Hub. |
| `DOCKER_PASSWORD` | Token de acceso de Docker Hub. |
| `MODEL_NAME` | Nombre del repositorio de imagen. |
| `RENDER_DEPLOY_HOOK` | Opcional: si existe, Render redespliega al publicar la imagen. |

## Despliegue en Render

Un solo servicio de backend sirve las tres versiones; el frontend elige con
`?version=`.

1. **Backend** — *New → Web Service → Deploy an existing image*, apuntando a
   `docker.io/<DOCKER_USER>/<MODEL_NAME>:latest`. Variables de entorno: `PORT=10000`,
   `DEFAULT_MODEL_VERSION=100` y, para habilitar el reentrenamiento,
   `RETRAIN_TOKEN`, `GITHUB_TOKEN` y `GITHUB_REPOSITORY`. *Health check path*:
   `/health`.
2. **Frontend** — *New → Static Site*, `rootDir: frontend`,
   `buildCommand: npm ci && npm run build`, `staticPublishPath: ./dist`, y
   `VITE_API_URL` con la URL pública del backend.

O bien importar `render.yaml` como *Blueprint*.

> En el plan gratuito el servicio se duerme tras ~15 min sin tráfico y la primera
> petición puede tardar hasta un minuto. El frontend lo contempla: reintenta tres
> veces y espera hasta 75 s.

## Pruebas

```bash
python -m pytest tests/ -q                 # 41 pruebas de la API
./scripts/test_model_curl.sh <URL>         # comprobaciones con cURL
npx newman run postman/incidencia-model.postman_collection.json \
  --env-var api_url=<URL>                  # 37 aserciones
```

## Limitaciones del modelo

Uso académico y demostrativo. El modelo aprende el histórico de carpetas de
investigación **registradas**, que no es lo mismo que el delito real: la cifra
negra y los cambios en la forma de registrar quedan dentro de los datos. El
43 % de los registros vale 0 y la cola llega a casi 10 000, así que el MAE hay
que leerlo junto al MAE de referencia. Fuera del rango 2015–2025 el modelo
extrapola, y una categoría que no estuviera en el entrenamiento se trata como
valor ausente.
