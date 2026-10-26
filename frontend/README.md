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

`VITE_API_URL` se incrusta en tiempo de compilación: al cambiarla hay que
volver a ejecutar `npm run build`.

## Contrato consumido

- `GET {VITE_API_URL}/health` — indicador de estado de la conexión.
- `POST {VITE_API_URL}/score` con los 13 campos del dataset → `{ "score": number }`.

Los límites de cada campo en `src/fields.js` replican las validaciones de
`app.py`, de modo que el formulario rechaza en el cliente lo mismo que el
backend devolvería como `422`.

El valor mostrado es la salida literal del campo `score`; la interfaz no lo
reinterpreta como porcentaje de riesgo.
