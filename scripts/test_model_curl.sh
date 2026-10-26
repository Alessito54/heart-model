#!/usr/bin/env bash
# Prueba el modelo con cURL usando SIEMPRE el mismo payload.
# Permite comparar la salida del modelo entre despliegues entrenados
# con los datasets al 25 %, 50 % y 100 % (rubrica de la practica).
#
# Uso:
#   ./scripts/test_model_curl.sh                      # http://localhost:8000
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

echo "== 2. POST /score (payload de referencia) =="
echo "payload: $PAYLOAD"
curl -fsS -X POST "$API_URL/score" \
  -H 'Content-Type: application/json' \
  -d "$PAYLOAD"
echo; echo

echo "== 3. POST /score (segundo paciente) =="
curl -fsS -X POST "$API_URL/score" \
  -H 'Content-Type: application/json' \
  -d '{"age":29,"sex":0,"cp":0,"trestbps":110,"chol":180,"fbs":0,"restecg":0,"thalach":190,"exang":0,"oldpeak":0.0,"slope":2,"ca":0,"thal":1}'
echo; echo

echo "== 4. POST /score con datos invalidos (se espera HTTP 422) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/score" \
  -H 'Content-Type: application/json' \
  -d '{"age":64,"sex":9,"cp":3,"trestbps":120,"chol":267,"fbs":0,"restecg":0,"thalach":99,"exang":1,"oldpeak":1.8,"slope":1,"ca":2,"thal":2}')
echo "HTTP $code"
[ "$code" = "422" ] || { echo "FALLO: se esperaba 422"; exit 1; }
echo
echo "Todas las comprobaciones pasaron."
