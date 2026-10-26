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

PAYLOAD='{"age":64,"sex":1,"cp":3,"trestbps":120,"chol":267,"fbs":0,"restecg":0,"thalach":99,"exang":1,"oldpeak":1.8,"slope":1,"ca":2,"thal":2}'

echo "API: $API_URL"
echo

echo "== 1. GET /health =="
curl -fsS "$API_URL/health"; echo; echo

echo "== 2. GET /models (versiones disponibles) =="
curl -fsS "$API_URL/models"; echo; echo

echo "== 3. POST /score — mismo payload, las tres versiones =="
echo "payload: $PAYLOAD"
echo
scores=""
for v in 25 50 100; do
  body=$(curl -fsS -X POST "$API_URL/score?version=$v" \
    -H 'Content-Type: application/json' -d "$PAYLOAD")
  printf '  %3s%%  ->  %s\n' "$v" "$body"
  scores="${scores}$(printf '%s' "$body" | sed -E 's/.*"score":([0-9.eE+-]+).*/\1/')
"
done
echo
distinct=$(printf '%s' "$scores" | sort -u | grep -c . || true)
echo "Salidas distintas: $distinct de 3"
if [ "$distinct" -lt 2 ]; then
  echo "AVISO: las tres versiones devuelven el mismo score; revisa que los"
  echo "       artefactos no se hayan sobrescrito entre si."
fi
echo

echo "== 4. POST /score sin parametro (version por defecto) =="
curl -fsS -X POST "$API_URL/score" \
  -H 'Content-Type: application/json' -d "$PAYLOAD"
echo; echo

echo "== 5. POST /score con version inexistente (se espera HTTP 404) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/score?version=77" \
  -H 'Content-Type: application/json' -d "$PAYLOAD")
echo "HTTP $code"
[ "$code" = "404" ] || { echo "FALLO: se esperaba 404"; exit 1; }
echo

echo "== 6. POST /score con datos invalidos (se espera HTTP 422) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/score" \
  -H 'Content-Type: application/json' \
  -d '{"age":64,"sex":9,"cp":3,"trestbps":120,"chol":267,"fbs":0,"restecg":0,"thalach":99,"exang":1,"oldpeak":1.8,"slope":1,"ca":2,"thal":2}')
echo "HTTP $code"
[ "$code" = "422" ] || { echo "FALLO: se esperaba 422"; exit 1; }
echo
echo "Todas las comprobaciones pasaron."
