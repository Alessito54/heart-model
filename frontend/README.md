# Frontend — Incidencia delictiva estatal

React 18 + Vite 5, sin dependencias de UI adicionales.

## Desarrollo

```bash
cp .env.example .env     # ajustar VITE_API_URL
npm install
npm run dev              # http://localhost:5173
```

## Compilación

```bash
npm run build            # genera dist/
npm run preview          # sirve dist/ en $PORT (4173 por defecto)
```

Las variables `VITE_*` se incrustan en tiempo de compilación: al cambiarlas hay
que volver a ejecutar `npm run build`.

## Configuración

Un solo backend sirve las tres versiones del modelo:

```
VITE_API_URL=https://incidencia-model-api.onrender.com
```

El frontend envía `POST {VITE_API_URL}/predict?version=25|50|100`.

## Las tres versiones del modelo

El frontend no da por hecho qué versiones existen: al cargar consulta
`GET /models` y construye con lo que responda el backend tanto las tarjetas de
«Modelos entrenados» (con `n_rows`, `mae`, `rmse`, `r2` y la mejora sobre el
`baseline_mae`) como el selector de versión. Si el backend no expone `/models`,
recurre a `model_versions` de `/health`.

La casilla «Consultar las 3 versiones con los mismos datos» envía el mismo
payload a todas en paralelo y muestra las estimaciones en una tabla.

## El formulario se construye desde el catálogo

`GET /catalog` devuelve los valores válidos de cada campo y la jerarquía del
delito anidada. `src/catalog.js` la usa para encadenar las cuatro listas
desplegables:

```
bien jurídico → tipo → subtipo → modalidad
```

Al cambiar un nivel, los de abajo se recalculan y se corrigen si dejaron de ser
válidos (`cascade`). Así es imposible enviar una combinación que no exista en el
dataset, que el backend rechazaría con un `422`.

## Panel de reentrenamiento

`src/RetrainPanel.jsx` llama a `POST /retrain`, que dispara el workflow de
GitHub Actions y publica una imagen de Docker nueva. El token se envía en la
cabecera `X-Retrain-Token` y se guarda solo en `sessionStorage`: **nunca** en una
variable `VITE_*`, porque esas quedan incrustadas en el JavaScript público.

El panel se deshabilita solo si `GET /health` informa `retrain_enabled: false`,
y explica qué variables de entorno faltan en el backend.

## Contrato consumido

- `GET {base}/health` — estado de la conexión, versiones servidas y si el
  reentrenamiento está habilitado.
- `GET {base}/models` — versiones con sus métricas de regresión.
- `GET {base}/catalog` — valores válidos de cada campo.
- `POST {base}/predict[?version=N]` → `{ prediccion, prediccion_redondeada,
  version, label, entidad, periodo }`.
- `POST {base}/retrain` y `GET {base}/retrain/status` — reentrenamiento.

El valor mostrado es la salida literal del modelo: carpetas de investigación
estimadas, no un pronóstico oficial.
