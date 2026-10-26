FROM python:3.12-slim
WORKDIR /app
COPY ./requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade -r ./requirements.txt
COPY ./app.py .
COPY ./model ./model
EXPOSE 80
# Render (y otros PaaS) inyectan el puerto en $PORT; en local se usa 80.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-80}"]
