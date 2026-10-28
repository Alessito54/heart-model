FROM python:3.12-slim
WORKDIR /app
COPY ./requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade -r ./requirements.txt
COPY ./app.py .
# El paquete model/ aporta tres cosas que la API necesita al arrancar:
#   - schema.py      el orden de las columnas, compartido con el entrenamiento
#   - catalog.json   los valores validos de cada campo
#   - incidencia-*.joblib + metrics-*.json   las tres versiones del modelo
COPY ./model ./model
EXPOSE 80
# Render (y otros PaaS) inyectan el puerto en $PORT; en local se usa 80.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-80}"]
