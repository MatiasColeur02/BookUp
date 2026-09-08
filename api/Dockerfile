FROM python:3.12-slim

WORKDIR /app

# Imagen de desarrollo local: `requirements-dev.txt` incluye a `requirements.txt`
# vía `-r`, y suma pytest/httpx para poder correr `docker compose exec api pytest`
# sin instalar nada a mano dentro del contenedor.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
