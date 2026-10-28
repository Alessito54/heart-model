#!/usr/bin/env bash
# Demostracion del ciclo de reentrenamiento, de principio a fin.
#
# Muestra, en orden:
#   1. que modelo esta sirviendo la API ahora mismo
#   2. las tres versiones entrenadas y sus metricas
#   3. una prediccion con cada version
#   4. el reentrenamiento: dispara el workflow y espera a que publique la imagen
#   5. la etiqueta de la imagen nueva
#
# Uso:
#   API_URL=https://<tu-api>.onrender.com RETRAIN_TOKEN=<token> ./scripts/demo_retrain.sh
#   ./scripts/demo_retrain.sh https://<tu-api>.onrender.com <token>
#
# Sin RETRAIN_TOKEN hace solo los pasos 1-3 (la parte de solo lectura).
set -uo pipefail

API_URL="${1:-${API_URL:-http://localhost:8000}}"
API_URL="${API_URL%/}"
TOKEN="${2:-${RETRAIN_TOKEN:-}}"

titulo() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
pausa()  { [ -t 0 ] && { printf '\n\033[2m(Enter para continuar)\033[0m'; read -r _; } || true; }

PAYLOAD='{"anio":2025,"mes":6,"clave_ent":9,"bien_juridico_afectado":"El patrimonio","tipo_delito":"Robo","subtipo_delito":"Robo de vehículo automotor","modalidad":"Robo de coche de 4 ruedas Con violencia"}'

titulo "1. Que modelo esta sirviendo la API"
echo "API: $API_URL"
curl -fsS "$API_URL/health" | python3 -m json.tool
pausa

titulo "2. Las tres versiones entrenadas"
curl -fsS "$API_URL/models" | python3 -c '
import json, sys
cab = ("version", "registros", "MAE", "RMSE", "R2")
print("%8s %10s %8s %8s %8s  mejora sobre la media" % cab)
for m in json.load(sys.stdin):
    base = m.get("baseline_mae") or 0
    mejora = (1 - m["mae"] / base) * 100 if base else 0
    print("%7s%% %10s %8.2f %8.2f %8.4f  %10.0f %%" % (
        m["version"], format(m["n_rows"], ","),
        m["mae"], m["rmse"], m["r2"], mejora))
'
pausa

titulo "3. Misma consulta, las tres versiones"
echo "Consulta: CDMX, junio 2025, robo de coche de 4 ruedas con violencia"
echo
for v in 25 50 100; do
  curl -fsS -X POST "$API_URL/predict?version=$v" \
    -H 'Content-Type: application/json' -d "$PAYLOAD" |
    python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'  {d[\"version\"]+\" %\":>7}  ->  {d[\"prediccion_redondeada\"]:>5} carpetas  ({d[\"prediccion\"]:.4f})')
"
done
echo
echo "Las tres difieren solo por el volumen de datos con el que se entrenaron."
pausa

if [ -z "$TOKEN" ]; then
  titulo "4. Reentrenamiento"
  echo "No se indico RETRAIN_TOKEN, asi que la demo termina aqui."
  echo "Para lanzarlo:  RETRAIN_TOKEN=<token> $0 $API_URL"
  exit 0
fi

titulo "4. Lanzar el reentrenamiento"
echo "Esto NO entrena dentro del contenedor: dispara el workflow de GitHub"
echo "Actions, que entrena las tres versiones, corre las pruebas y publica una"
echo "IMAGEN DE DOCKER NUEVA con su propia etiqueta."
pausa

RESP=$(curl -sS -X POST "$API_URL/retrain" \
  -H "X-Retrain-Token: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"nota":"demostracion en clase"}')

echo "$RESP" | python3 -m json.tool 2>/dev/null || { echo "$RESP"; exit 1; }

TAG=$(echo "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tag",""))' 2>/dev/null)
if [ -z "$TAG" ]; then
  echo
  echo "No se pudo lanzar el reentrenamiento (ver el mensaje de arriba)."
  exit 1
fi

titulo "5. Esperando a que el workflow publique la imagen"
echo "Etiqueta de la imagen nueva: $TAG"
echo
for i in $(seq 1 40); do
  ESTADO=$(curl -sS "$API_URL/retrain/status?limit=1" -H "X-Retrain-Token: $TOKEN" |
    python3 -c '
import json, sys
try:
    r = json.load(sys.stdin)["runs"][0]
    print("%s|%s|%s" % (r["status"], r.get("conclusion") or "", r["url"]))
except Exception:
    print("desconocido||")
' 2>/dev/null)
  ST="${ESTADO%%|*}"; RESTO="${ESTADO#*|}"; CONC="${RESTO%%|*}"; URL="${RESTO#*|}"
  printf '\r  [%02d] estado: %-12s %s' "$i" "$ST" "$CONC"
  if [ "$ST" = "completed" ]; then
    echo; echo
    if [ "$CONC" = "success" ]; then
      echo "Listo. Imagen publicada con la etiqueta: $TAG (y 'latest')"
      echo "Corrida: $URL"
      echo
      echo "Siguiente paso: en Render, Manual Deploy -> Deploy latest reference,"
      echo "para que el servicio empiece a servir la imagen nueva."
    else
      echo "El workflow termino con: $CONC"
      echo "Corrida: $URL"
    fi
    exit 0
  fi
  sleep 15
done
echo; echo "Se agoto la espera. Revisa la corrida en GitHub Actions."
