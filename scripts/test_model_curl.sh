#!/usr/bin/env bash
# Prueba el modelo con cURL usando SIEMPRE el mismo payload contra las tres
# versiones (25 %, 50 %, 100 %), tal como pide la rubrica de la practica.
#
# Uso:
#   ./scripts/test_model_curl.sh                       # http://localhost:8000
#   ./scripts/test_model_curl.sh https://mi.onrender.com
#   API_URL=https://mi.onrender.com ./scripts/test_model_curl.sh
set -euo pipefail

API_URL="${1:-${API_URL:-http://localhost:8000}}"
API_URL="${API_URL%/}"

PAYLOAD='{"anio":2025,"mes":6,"clave_ent":9,"bien_juridico_afectado":"El patrimonio","tipo_delito":"Robo","subtipo_delito":"Robo de vehículo automotor","modalidad":"Robo de coche de 4 ruedas Con violencia"}'

echo "API: $API_URL"
echo

echo "== 1. GET /health =="
curl -fsS "$API_URL/health"; echo; echo

echo "== 2. GET /models (versiones disponibles, con metricas) =="
curl -fsS "$API_URL/models"; echo; echo

echo "== 3. GET /catalog (valores validos; se muestran los primeros 300 bytes) =="
curl -fsS "$API_URL/catalog" | head -c 300; echo; echo

echo "== 4. POST /predict — mismo payload, las tres versiones =="
echo "payload: $PAYLOAD"
echo
preds=""
for v in 25 50 100; do
  body=$(curl -fsS -X POST "$API_URL/predict?version=$v" \
    -H 'Content-Type: application/json' -d "$PAYLOAD")
  printf '  %3s%%  ->  %s\n' "$v" "$body"
  preds="${preds}$(printf '%s' "$body" | sed -E 's/.*"prediccion":([0-9.eE+-]+).*/\1/')
"
done
echo
distinct=$(printf '%s' "$preds" | sort -u | grep -c . || true)
echo "Salidas distintas: $distinct de 3"
if [ "$distinct" -lt 2 ]; then
  echo "AVISO: las tres versiones devuelven la misma prediccion; revisa que los"
  echo "       artefactos no se hayan sobrescrito entre si."
fi
echo

echo "== 5. POST /predict sin parametro (version por defecto) =="
curl -fsS -X POST "$API_URL/predict" \
  -H 'Content-Type: application/json' -d "$PAYLOAD"
echo; echo

echo "== 6. POST /predict con version inexistente (se espera HTTP 404) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/predict?version=77" \
  -H 'Content-Type: application/json' -d "$PAYLOAD")
echo "HTTP $code"
[ "$code" = "404" ] || { echo "FALLO: se esperaba 404"; exit 1; }
echo

echo "== 7. POST /predict con una modalidad inexistente (se espera HTTP 422) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/predict" \
  -H 'Content-Type: application/json' \
  -d '{"anio":2025,"mes":6,"clave_ent":9,"bien_juridico_afectado":"El patrimonio","tipo_delito":"Robo","subtipo_delito":"Robo de vehículo automotor","modalidad":"no existe"}')
echo "HTTP $code"
[ "$code" = "422" ] || { echo "FALLO: se esperaba 422"; exit 1; }
echo

echo "== 8. POST /retrain sin token (se espera 401 si esta configurado, 503 si no) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/retrain" \
  -H 'Content-Type: application/json' -d '{}')
echo "HTTP $code"
case "$code" in
  401|503) ;;
  *) echo "FALLO: se esperaba 401 o 503, nunca un reentrenamiento abierto"; exit 1 ;;
esac
echo
echo "Todas las comprobaciones pasaron."
