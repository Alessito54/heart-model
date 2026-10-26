# Frontend — Predicción de enfermedad cardíaca

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

## Las tres versiones del modelo

El frontend no da por hecho qué versiones existen: al cargar consulta
`GET /models` y construye el selector con lo que responda el backend, incluidas
las métricas (`n_rows`, `accuracy`) de cada una. Si el backend no expone
`/models`, recurre a `model_versions` de `/health`; y si tampoco, muestra una
sola opción.

Hay dos formas de configurarlo:

**Modo A (por defecto)** — un backend que sirve las tres:

```
VITE_API_URL=https://heart-model-api.onrender.com
```

El frontend envía `POST {VITE_API_URL}/score?version=25|50|100`.

**Modo B** — un despliegue por versión:

```
VITE_API_URL_25=https://heart-model-25.onrender.com
VITE_API_URL_50=https://heart-model-50.onrender.com
VITE_API_URL_100=https://heart-model-100.onrender.com
```

Si se define alguna de ellas, el frontend enruta cada versión a su servicio y
no envía el parámetro `?version=`. `VITE_API_URL` deja de usarse.

La casilla «Comparar las 3 versiones» envía el mismo paciente a todas en
paralelo y muestra los `score` en una tabla.

## Contrato consumido

- `GET {base}/health` — estado de la conexión y versiones servidas.
- `GET {base}/models` — versiones con sus métricas.
- `POST {base}/score[?version=N]` con los 13 campos → `{ "score": number, "version": string }`.

Los límites de cada campo en `src/fields.js` replican las validaciones de
`app.py`, de modo que el formulario rechaza en el cliente lo mismo que el
backend devolvería como `422`.

El valor mostrado es la salida literal del campo `score`; la interfaz no lo
reinterpreta como porcentaje de riesgo.
